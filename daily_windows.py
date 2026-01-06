"""
Obliczanie okien dobowych względem wschodu/zachodu słońca
"""
from datetime import datetime, time, timedelta
from astral import LocationInfo
from astral.sun import sun
import logging

logger = logging.getLogger(__name__)

def calculate_daily_windows():
    """
    Oblicza okna dobowe na podstawie wschodu/zachodu słońca
    
    Zwraca:
    {
        'wschod_slonca': '07:33',
        'zachod_slonca': '15:32',
        'poczatek_okna_ladowania': '09:03',      # wschód + 1h30
        'koniec_okna_ladowania': '14:02',        # zachód - 1h29 (59 min)
        'poczatek_okna_wieczornego': '14:02',    # zachód - 1h30
        'koniec_okna_wieczornego': '23:59',      # 1 min przed północą
        'poczatek_okna_nocnego': '00:00',        # północ
        'koniec_okna_nocnego': '09:02'           # wschód + 1h29 (59 min)
    }
    """
    try:
        # Współrzędne z system_config.json
        from core.config_loader import get_system_config
        config = get_system_config()
        pv_config = config.get("pv_installation", {})
        
        # Parsuj współrzędne
        coords_str = pv_config.get("coordinates", "51.290050, 22.818633")
        lat_str, lon_str = coords_str.split(",")
        latitude = float(lat_str.strip())
        longitude = float(lon_str.strip())
        
        # Utwórz lokację
        city = LocationInfo(
            name="PV Installation",
            region="Poland",
            timezone="Europe/Warsaw",
            latitude=latitude,
            longitude=longitude
        )
        
        # Oblicz wschód/zachód
        today = datetime.now().date()
        s = sun(city.observer, date=today, tzinfo=city.timezone)
        
        sunrise = s["sunrise"]
        sunset = s["sunset"]
        
        # Formatuj jako string HH:MM
        wschod_str = sunrise.strftime("%H:%M")
        zachod_str = sunset.strftime("%H:%M")
        
        # Oblicz godziny jako float
        sunrise_hour = sunrise.hour + sunrise.minute/60
        sunset_hour = sunset.hour + sunset.minute/60
        
        # Oblicz okna zgodnie z specyfikacją
        ladowania_start = sunrise_hour + 1.5          # wschód + 1h30
        ladowania_end = sunset_hour - 1.5 + (1/60)    # zachód - 1h29 (59 min)
        wieczorne_start = sunset_hour - 1.5           # zachód - 1h30
        nocne_end = sunrise_hour + 1.5 - (1/60)       # wschód + 1h29 (59 min)
        
        # Formatuj okna jako string
        def hour_to_str(hour_float):
            hour = int(hour_float)
            minute = int((hour_float - hour) * 60)
            return f"{hour:02d}:{minute:02d}"
        
        windows = {
            'wschod_slonca': wschod_str,
            'zachod_slonca': zachod_str,
            'poczatek_okna_ladowania': hour_to_str(ladowania_start),
            'koniec_okna_ladowania': hour_to_str(ladowania_end),
            'poczatek_okna_wieczornego': hour_to_str(wieczorne_start),
            'koniec_okna_wieczornego': '23:59',
            'poczatek_okna_nocnego': '00:00',
            'koniec_okna_nocnego': hour_to_str(nocne_end)
        }
        
        logger.info(f"Okna: wschód {wschod_str}, zachód {zachod_str}")
        logger.info(f"Ładowanie: {windows['poczatek_okna_ladowania']} - {windows['koniec_okna_ladowania']}")
        logger.info(f"Wieczorne: {windows['poczatek_okna_wieczornego']} - {windows['koniec_okna_wieczornego']}")
        logger.info(f"Nocne: {windows['poczatek_okna_nocnego']} - {windows['koniec_okna_nocnego']}")
        
        return windows
        
    except Exception as e:
        logger.error(f"Błąd obliczania okien: {e}")
        # Wartości domyślne
        return {
            'wschod_slonca': '07:33',
            'zachod_slonca': '15:32',
            'poczatek_okna_ladowania': '09:03',
            'koniec_okna_ladowania': '14:02',
            'poczatek_okna_wieczornego': '14:02',
            'koniec_okna_wieczornego': '23:59',
            'poczatek_okna_nocnego': '00:00',
            'koniec_okna_nocnego': '09:02'
        }
#=========================================
def get_current_window_simple(current_time=None):
    """
    Określa do którego okna należy aktualna godzina
    
    Zwraca: 'loading_window', 'evening_window', 'night_window', lub None
    """
    if current_time is None:
        current_time = datetime.now()
    
    current_hour = current_time.hour + current_time.minute/60
    
    windows = calculate_daily_windows()
    
    # Parsuj stringi czasu na float
    def parse_time(time_str):
        if time_str == '23:59':
            return 23 + 59/60
        elif time_str == '00:00':
            return 0.0
        else:
            try:
                h, m = map(int, time_str.split(':'))
                return h + m/60
            except:
                return 0.0
    
    # Sprawdź okna
    loading_start = parse_time(windows['poczatek_okna_ladowania'])
    loading_end = parse_time(windows['koniec_okna_ladowania'])
    evening_start = parse_time(windows['poczatek_okna_wieczornego'])
    evening_end = parse_time(windows['koniec_okna_wieczornego'])
    night_start = parse_time(windows['poczatek_okna_nocnego'])
    night_end = parse_time(windows['koniec_okna_nocnego'])
    
    # Logika określania okna (uwzględnia przejście przez północ)
    if evening_start <= current_hour < evening_end:
        return 'evening_window'
    elif night_start <= current_hour < night_end or (night_end < night_start and (current_hour >= night_start or current_hour < night_end)):
        return 'night_window'
    elif loading_start <= current_hour < loading_end:
        return 'loading_window'
    else:
        return None
#========================================
def get_current_window(latitude=None, longitude=None, current_time=None):
    """
    Kompatybilność z sze_core.py - zachowuje stary interfejs
    """
    # Ignorujemy latitude/longitude - calculate_daily_windows() bierze z konfiguracji
    return get_current_window_simple(current_time)
#druga zzmiana==============================
if __name__ == "__main__":
    # Test
    windows = calculate_daily_windows()
    print("=== POPRAWIONE OKNA DOBOWE ===")
    for key, value in windows.items():
        print(f"{key}: {value}")
