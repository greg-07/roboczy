"""
Prognoza produkcji z PV na podstawie API forecast.solar
"""
import requests
import json
import os
import logging
from datetime import datetime, timedelta
import time

from .daily_windows import calculate_daily_windows  # Zaimportuj z daily_windows

logger = logging.getLogger(__name__)

# Relative path do config (zamiast hardcoded absolute) - zakłada, że pv_forecast.py jest w core/, config/ obok
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Idzie do sze_system/
CONFIG_FILE = os.path.join(BASE_DIR, 'config', 'system_config.json')

# Czynniki korekcyjne zacienienia miesięczne (zależne od miesiąca)
MONTH_FACTORS = {
    1: 0.7,   # Styczeń
    2: 0.85,  # Luty
    3: 1.0,   # Marzec
    4: 1.1,   # Kwiecień
    5: 1.15,  # Maj
    6: 1.1,   # Czerwiec
    7: 1.05,  # Lipiec
    8: 1.0,   # Sierpień
    9: 0.95,  # Wrzesień
    10: 0.85, # Październik
    11: 0.75, # Listopad
    12: 0.7   # Grudzień
}

def load_pv_config():
    """Ładuje konfigurację PV z pliku JSON."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        return config.get('pv_installation', {})
    except Exception as e:
        logger.error(f"Błąd ładowania konfiguracji PV: {e}")
        return {}

def build_api_url(pv_config):
    """Buduje URL do API forecast.solar."""
    lat, lon = pv_config.get('coordinates', '51.290050,22.818633').split(',')
    lat = lat.strip()
    lon = lon.strip()
    dec = pv_config.get('tilt_degrees', 45)
    az = pv_config.get('azimuth_degrees', 180)
    kwp = pv_config.get('installed_power_wp', 2430) / 1000  # Przelicz na kWp
    
    return f"https://api.forecast.solar/estimate/{lat}/{lon}/{dec}/{az}/{kwp}"

def fetch_forecast(api_url, max_retries=3, retry_delay=60):
    """Pobiera prognozę z API z obsługą retry."""
    for attempt in range(max_retries):
        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:  # Rate limit
                logger.warning(f"Rate limit osiągnięty. Czekam {retry_delay} sekund...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Błąd API: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Błąd pobierania prognozy: {e}")
    return None

def parse_forecast(forecast_data):
    """Parsuje dane z API na słownik z datami i watami."""
    if 'result' not in forecast_data or 'watts' not in forecast_data['result']:
        logger.error("Nieprawidłowa struktura danych prognozy")
        return {}
    
    watts = forecast_data['result']['watts']
    parsed = {}
    for timestamp_str, power in watts.items():
        try:
            dt = datetime.fromisoformat(timestamp_str)
            parsed[dt] = power
        except ValueError:
            logger.warning(f"Nieprawidłowy format daty: {timestamp_str}")
    return parsed

def correct_forecast(forecast, month):
    """Koryguje prognozę czynnikiem miesięcznym."""
    factor = MONTH_FACTORS.get(month, 1.0)
    return {dt: power * factor for dt, power in forecast.items()}

def calculate_energy(forecast, start_time, end_time):
    """Oblicza energię (kWh) w podanym oknie czasowym."""
    energy_wh = 0.0
    prev_dt = None
    prev_power = None
    
    for dt in sorted(forecast.keys()):
        if dt < start_time or dt > end_time:
            continue
        
        if prev_dt is not None:
            time_diff_hours = (dt - prev_dt).total_seconds() / 3600.0
            avg_power = (prev_power + forecast[dt]) / 2.0
            energy_wh += avg_power * time_diff_hours
        
        prev_dt = dt
        prev_power = forecast[dt]
    
    return energy_wh / 1000.0  # Przelicz na kWh

def save_forecast_to_json(forecast_data, filename='calc_working_data1.json'):
    """Zapisuje prognozę do JSON (append do listy)."""
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
        else:
            data = []
        
        data.append(forecast_data)
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        logger.info(f"Prognoza zapisana do {filename}")
    except Exception as e:
        logger.error(f"Błąd zapisu prognozy: {e}")

def get_forecast_for_window(forecast_time_str, window_type='afternoon'):
    """
    Pobiera prognozę dla okna (całodzienna lub popołudniowa).
    window_type: 'full_day' lub 'afternoon'
    """
    pv_config = load_pv_config()
    api_url = build_api_url(pv_config)
    raw_data = fetch_forecast(api_url)
    
    if not raw_data:
        return None
    
    forecast = parse_forecast(raw_data)
    month = datetime.now().month
    corrected_forecast = correct_forecast(forecast, month)
    
    windows = calculate_daily_windows()
    
    today = datetime.now().date()
    forecast_time = datetime.strptime(forecast_time_str, "%H:%M").time()
    forecast_datetime = datetime.combine(today, forecast_time)
    
    if window_type == 'full_day':
        # Okno całodzienne: od 00:00 do 23:59
        start = datetime.combine(today, time(0, 0))
        end = datetime.combine(today, time(23, 59))
    elif window_type == 'afternoon':
        # Okno popołudniowe: od forecast_time do zachodu
        sunset_str = windows['zachod_slonca']
        sunset_time = datetime.strptime(sunset_str, "%H:%M").time()
        start = forecast_datetime
        end = datetime.combine(today, sunset_time)
    else:
        return None
    
    energy_kwh = calculate_energy(corrected_forecast, start, end)
    
    result = {
        'prognoza_kwh': energy_kwh,
        'okno': f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}",
        'typ': window_type,
        'data': today.strftime('%Y-%m-%d'),
        'godzina_prognozy': forecast_time_str
    }
    
    save_forecast_to_json(result)
    return result

# Scheduler (pozostaje bez zmian)
def run_forecast_scheduler():
    while True:
        now = datetime.now()
        if now.hour == 0 and now.minute == 0:
            get_forecast_for_window('00:00', 'full_day')
        elif now.hour == 12 and now.minute == 0:
            get_forecast_for_window('12:00', 'afternoon')
        
        time.sleep(60)  # Sprawdź co minutę

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forecast_scheduler()
