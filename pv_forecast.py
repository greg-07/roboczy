import os
from datetime import datetime, timedelta, timezone, time as dtime
import requests
import json
from datetime import datetime, timedelta, timezone
import time
import schedule
import logging
from daily_windows import calculate_daily_windows  # Import z tego samego katalogu

# Konfiguracja logowania
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Ścieżki plików
CONFIG_FILE = "/home/greg/sze_system/config/system_config.json"
JSON_FILE = "/home/greg/sze_system/calc_working_data1.json"

# Współczynniki korekcyjne dla miesięcy (ze względu na zacienienie)
MONTH_FACTORS = {
    1: 0.5,
    2: 0.6,
    3: 0.7,
    4: 0.8,
    5: 1.0,
    6: 1.0,
    7: 1.0,
    8: 1.0,
    9: 0.9,
    10: 0.8,
    11: 0.6,
    12: 0.5
}

# Ładowanie konfiguracji z system_config.json
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        pv_config = config.get("pv_installation", {})
        lat_str, lon_str = pv_config.get("coordinates", "51.290050, 22.818633").split(",")
        LAT = float(lat_str.strip())
        LON = float(lon_str.strip())
        KWP = pv_config.get("installed_power_wp", 2430) / 1000.0  # Przelicz na kWp
        DEC = pv_config.get("tilt_degrees", 45)
        AZ = pv_config.get("azimuth_degrees", 180)
        return LAT, LON, KWP, DEC, AZ
    except Exception as e:
        logger.error(f"Błąd ładowania konfiguracji: {e}")
        # Domyślne wartości
        return 51.2900, 22.8186, 2.43, 45, 180

LAT, LON, KWP, DEC, AZ = load_config()
API_URL = f"https://api.forecast.solar/estimate/watts/{LAT}/{LON}/{DEC}/{AZ}/{KWP}"
TIMEZONE = timezone(timedelta(hours=1))  # UTC+1 dla Polski (zimą; latem +2, ale astral w daily_windows obsłuży)

# Funkcja do pobierania i przetwarzania danych z API
def fetch_forecast():
    try:
        response = requests.get(API_URL)
        if response.status_code == 200:
            data = response.json()['result']  # {"result": {"YYYY-MM-DD HH:MM": power_w, ...}}
            headers = response.headers
            remaining = int(headers.get('X-Ratelimit-Remaining', 12))
            if remaining < 1:
                reset_time = int(headers.get('X-Ratelimit-Reset', 0))  # Unix timestamp
                wait_seconds = max(0, reset_time - time.time()) + 60  # +1 min jitter
                logger.info(f"Limit przekroczony, czekam {wait_seconds/60:.0f} min...")
                time.sleep(wait_seconds)
                return fetch_forecast()  # Retry
            return data
        else:
            logger.error(f"Błąd API: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Wyjątek podczas pobierania: {e}")
        return None

# Funkcja do obliczenia energii w oknie (suma Wh / 1000 = kWh), z korekcją miesięczną
def calculate_energy(forecast_data, start, end, from_time=None):
    total_wh = 0
    now = datetime.now(TIMEZONE)
    month = now.month
    factor = MONTH_FACTORS.get(month, 1.0)  # Domyślnie 1.0 jeśli błąd
    logger.info(f"Używam współczynnika korekcyjnego dla miesiąca {month}: {factor}")
    
    for dt_str, power_w in forecast_data.items():
        # Parsuj datetime (format: "YYYY-MM-DD HH:MM:SS" lub "YYYY-MM-DD HH:MM")
        try:
            dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc).astimezone(TIMEZONE)
        except ValueError:
            # Jeśli brak sekund, dodaj :00
            dt_str += ":00"
            dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc).astimezone(TIMEZONE)
        
        if from_time and dt < from_time:
            continue  # Pomijaj przed from_time
        if start <= dt < end:
            total_wh += power_w  # Zakładamy 1h na wpis
    
    energia_kwh = (total_wh / 1000) * factor  # Korekcja
    return energia_kwh

# Główna funkcja prognozy
def make_forecast(is_midnight=True):
    now = datetime.now(TIMEZONE)
    date = now.date()
    
    # Pobierz okna z daily_windows.py
    windows = calculate_daily_windows()
    
    # Parsuj stringi HH:MM na datetime.today() + time
    def parse_window_time(time_str):
        h, m = map(int, time_str.split(':'))
        return datetime.combine(date, dtime(h, m)).replace(tzinfo=TIMEZONE)
    
    start = parse_window_time(windows['poczatek_okna_ladowania'])
    end = parse_window_time(windows['koniec_okna_ladowania'])
    
    forecast_data = fetch_forecast()
    if not forecast_data:
        logger.error("Nie udało się pobrać danych prognozy")
        return
    
    if is_midnight:
        # Prognoza o 00:00: całe okno ładowania
        energia_kwh = calculate_energy(forecast_data, start, end)
        typ = "calodzienna"
        from_time_str = windows['poczatek_okna_ladowania']
    else:
        # Prognoza o 12:00: od 12:00 do końca okna
        from_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
        energia_kwh = calculate_energy(forecast_data, start, end, from_time)
        typ = "popoludniowa"
        from_time_str = "12:00"
    
    prognoza = {
        "data": date.isoformat(),
        "start": from_time_str,
        "end": windows['koniec_okna_ladowania'],
        "energia_kwh": round(energia_kwh, 2),
        "typ": typ
    }
    
            # Zapisz do JSON (append do listy lub utwórz nową)
    try:
        # Próba wczytania istniejącego pliku
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                logger.warning(f"Plik {JSON_FILE} nie jest listą – tworzę nową")
                data = []
        except FileNotFoundError:
            logger.info(f"Plik {JSON_FILE} nie istnieje – tworzę nowy")
            data = []
        except json.JSONDecodeError as e:
            logger.warning(f"Uszkodzony JSON w {JSON_FILE}: {e} – tworzę nowy")
            data = []

        # Dodaj nową prognozę
        data.append(prognoza)

        # Zapisz z powrotem
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        logger.info(f"Prognoza zapisana do {JSON_FILE}: {prognoza}")

    except Exception as e:
        logger.error(f"Błąd zapisu do {JSON_FILE}: {e}")

# Scheduler
def run_scheduler():
    schedule.every().day.at("00:00").do(make_forecast, is_midnight=True)
    schedule.every().day.at("12:00").do(make_forecast, is_midnight=False)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Czekaj 1 min

if __name__ == "__main__":
    # Utwórz plik JSON jeśli nie istnieje (pusta lista)
    if not os.path.exists(JSON_FILE):
        with open(JSON_FILE, 'w') as f:
            json.dump([], f)
    
    run_scheduler()
