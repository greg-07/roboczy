"""
FastAPI serwer dla Systemu Zarządzania Energią
"""
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
from datetime import datetime
import json
import os

# ZMIANA: zamiast config importujemy config_loader
from core.config_loader import reload_all_configs, get_system_config, get_energy_profiles, get_cwu_schedule, get_user_corrections
from core.sze_core import system_manager

# Konfiguracja logowania NAJPIERW
# ZMIANA: log_file bierzemy z JSON przez config_loader
reload_all_configs()  # Ładujemy konfigurację
system_config = get_system_config() or {}
log_file = system_config.get("system_settings", {}).get("log_file", "sze_system.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Import MQTT i uruchomienie
try:
    from mqtt_sa import mqtt_client, start_mqtt_in_background
    MQTT_AVAILABLE = True
    # Uruchom MQTT w tle
    mqtt_started = start_mqtt_in_background()
    if mqtt_started:
        logger.info("MQTT uruchomiony pomyślnie")
    else:
        logger.warning("MQTT nie mógł się uruchomić")
except ImportError as e:
    MQTT_AVAILABLE = False
    mqtt_client = None
    logger.warning(f"Moduł MQTT nie jest dostępny: {e}")

# Inicjalizacja FastAPI
app = FastAPI(
    title="System Zarządzania Energią (SZE)",
    description="System do zarządzania energią z PV, magazynem i siecią",
    version="2.0.0"
)

# Szablony HTML
templates = Jinja2Templates(directory="templates")

# Logowanie startu systemu - ZMIANA: własna funkcja
def log_system_startup():
    """Logowanie informacji o starcie systemu"""
    logger.info("=" * 60)
    logger.info("URUCHAMIANIE SYSTEMU ZARZĄDZANIA ENERGIĄ (SZE)")
    logger.info("=" * 60)
    
    # Pobierz konfigurację
    config = get_system_config() or {}
    mqtt_conf = config.get("mqtt_solar_assistant", {})
    
    logger.info(f"MQTT Broker: {mqtt_conf.get('broker', 'Brak')}:{mqtt_conf.get('port', 'Brak')}")
    logger.info(f"Prefiks MQTT: {mqtt_conf.get('topic_prefix', 'Brak')}")
    logger.info(f"Plik logów: {log_file}")

log_system_startup()

# Funkcja do ładowania danych JSON - ZMIANA: użyj config_loader
def load_json_data():
    """Ładuje dane z plików JSON przez config_loader"""
    try:
        # Przeładuj wszystkie konfiguracje
        reload_all_configs()
        
        # Pobierz wszystkie dane
        return {
            "energy_profiles": get_energy_profiles(),
            "cwu_schedule": get_cwu_schedule(),
            "system_config": get_system_config(),
            "user_corrections": get_user_corrections()
        }
        
    except Exception as e:
        logger.error(f"Błąd ładowania danych JSON: {e}")
        return {}

# Funkcja do pobierania danych MQTT
def get_mqtt_data():
    """Pobiera dane z MQTT"""
    if MQTT_AVAILABLE and mqtt_client:
        try:
            data = mqtt_client.get_current_data()  # To jest metoda!
            return {
                "mqtt_connected": data.get('connected', False),
                "last_update": data.get('last_update', 'Brak danych'),
                "data": {
                    "battery_soc": data.get('battery', {}).get('soc_percent', 0),
                    "grid_power": data.get('grid', {}).get('power_w', 0),
                    "pv_power": data.get('pv', {}).get('power_w', 0),
                    "load_power": data.get('load', {}).get('power_w', 0),
                    "output_source": data.get('inverter', {}).get('output_source', ''),
                    "charger_source": data.get('inverter', {}).get('charger_source', '')
                }
            }
        except Exception as e:
            logger.error(f"Błąd pobierania danych MQTT: {e}")
            return {"mqtt_connected": False, "error": str(e), "data": {}}
    else:
        return {
            "mqtt_connected": False,
            "last_update": "Moduł MQTT niedostępny",
            "data": {}
        }

# Ścieżki API
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Główny dashboard systemu"""
    try:
        system_manager.refresh_data()
        json_data = load_json_data()
        mqtt_info = get_mqtt_data()
        
        # Pobierz informacje o systemie
        system_info = {}
        if hasattr(system_manager, 'get_system_info'):
            system_info = system_manager.get_system_info()
        elif hasattr(system_manager, 'get_status'):
            system_info = system_manager.get_status()
        else:
            system_info = {
                "status": "active",
                "timestamp": datetime.now().isoformat(),
                "profiles": ["dzien_roboczy", "sobota", "niedziela_swieto"]
            }
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "system": system_info,
                "json_data": json_data,
                "mqtt_data": mqtt_info,
                "config": json_data.get("system_config", {})  # ZMIANA: config z JSON
            }
        )
    except Exception as e:
        logger.error(f"Błąd w dashboard: {e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": str(e)
            },
            status_code=500
        )

@app.get("/api/status")
async def get_status():
    """API statusu systemu"""
    try:
        system_manager.refresh_data()
        
        if hasattr(system_manager, 'get_system_info'):
            return system_manager.get_system_info()
        elif hasattr(system_manager, 'get_status'):
            return system_manager.get_status()
        else:
            return {
                "status": "active",
                "timestamp": datetime.now().isoformat(),
                "profiles": ["dzien_roboczy", "sobota", "niedziela_swieto"]
            }
    except Exception as e:
        logger.error(f"Błąd w get_status: {e}")
        return {"error": str(e), "status": "error"}

@app.get("/api/json-data")
async def get_json_data():
    """API danych z plików JSON"""
    return load_json_data()

@app.get("/api/mqtt-data")
async def get_mqtt_data_api():
    """API danych z MQTT"""
    return get_mqtt_data()

@app.get("/api/mqtt/status")
async def get_mqtt_status():
    """API statusu MQTT"""
    config = get_system_config() or {}
    mqtt_conf = config.get("mqtt_solar_assistant", {})
    
    return {
        "available": MQTT_AVAILABLE,
        "connected": getattr(mqtt_client, 'connected', False) if MQTT_AVAILABLE and mqtt_client else False,
        "broker": f"{mqtt_conf.get('broker', '192.168.8.143')}:{mqtt_conf.get('port', 1883)}",
        "prefix": mqtt_conf.get('topic_prefix', 'SZE')
    }

@app.get("/api/calculate-balance/{window_type}")
async def calculate_balance(window_type: str):
    """API obliczania bilansu"""
    try:
        if hasattr(system_manager, 'calculate_balance'):
            result = system_manager.calculate_balance(window_type)
            return result
        else:
            return {
                "error": "Metoda calculate_balance nie dostępna",
                "window_type": window_type
            }
    except Exception as e:
        logger.error(f"Błąd w calculate_balance: {e}")
        return {"error": str(e)}

@app.post("/api/toggle-cwu-boiler")
async def toggle_cwu_boiler(enabled: bool = Form(...)):
    """API przełączania CWU z kotła"""
    try:
        if hasattr(system_manager, 'toggle_cwu_boiler'):
            result = system_manager.toggle_cwu_boiler(enabled)
            return result
        else:
            return {"success": False, "message": "Metoda nie dostępna"}
    except Exception as e:
        logger.error(f"Błąd w toggle_cwu_boiler: {e}")
        return {"success": False, "error": str(e)}

@app.get("/logs")
async def view_logs(request: Request, lines: int = 100):
    """Przegląd logów systemu"""
    try:
        with open(log_file, 'r') as f:
            log_lines = f.readlines()[-lines:]
        
        return templates.TemplateResponse(
            "logs.html",
            {
                "request": request,
                "logs": log_lines,
                "log_file": log_file,
                "lines": lines
            }
        )
    except FileNotFoundError:
        return HTMLResponse("<h2>Plik logów nie istnieje</h2>")

@app.get("/api/logs")
async def get_logs_api(lines: int = 50):
    """API logów systemu"""
    try:
        with open(log_file, 'r') as f:
            log_lines = f.readlines()[-lines:]
        return {"logs": log_lines}
    except FileNotFoundError:
        return {"error": "Plik logów nie istnieje"}

# Endpoint do testowania
@app.get("/api/test")
async def test_endpoint():
    """Testowy endpoint"""
    config = get_system_config() or {}
    return {
        "status": "ok",
        "message": "System SZE działa poprawnie",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "data_source": "JSON files",
        "mqtt_available": MQTT_AVAILABLE,
        "mqtt_connected": mqtt_client.get_current_data().get('connected', False) if MQTT_AVAILABLE and mqtt_client else False,
        "config_files_loaded": len([v for v in [get_energy_profiles(), get_cwu_schedule(), get_system_config(), get_user_corrections()] if v is not None])
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "system": "SZE",
        "data_format": "JSON",
        "mqtt": "available" if MQTT_AVAILABLE else "unavailable",
        "config_loaded": get_system_config() is not None
    }

# Uruchomienie serwera (dla bezpośredniego uruchomienia api.py)
if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("SYSTEM ZARZĄDZANIA ENERGIĄ (SZE)")
    print("=" * 60)
    print("Dashboard: http://localhost:8000")
    print("API Status: http://localhost:8000/api/status")
    print("JSON Data: http://localhost:8000/api/json-data")
    print("MQTT Data: http://localhost:8000/api/mqtt-data")
    print("Logi: http://localhost:8000/logs")
    print("Health: http://localhost:8000/health")
    print("\nNaciśnij Ctrl+C aby zatrzymać")
    print("=" * 60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
