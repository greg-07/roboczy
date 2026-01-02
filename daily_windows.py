"""
Obliczanie okien dobowych względem wschodu/zachodu słońca
"""
import math
from datetime import datetime, date, timedelta
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

def calculate_sun_times(latitude: float, longitude: float, 
                       target_date: date = None) -> Tuple[datetime, datetime]:
    """
    Oblicza wschód i zachód słońca dla danej daty i współrzędnych.
    Algorytm przybliżony - dokładność ±10 minut.
    
    Args:
        latitude: Szerokość geograficzna (stopnie)
        longitude: Długość geograficzna (stopnie)
        target_date: Data (domyślnie dzisiaj)
    
    Returns:
        Tuple (wschód_słońca, zachód_słońca) jako datetime
    """
    if target_date is None:
        target_date = date.today()
    
    # Konwersja na radiany
    lat_rad = math.radians(latitude)
    
    # Dzień roku (1-365)
    day_of_year = target_date.timetuple().tm_yday
    
    # Deklinacja słońca (przybliżona)
    declination = 23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365))
    declination_rad = math.radians(declination)
    
    # Czas równania czasu (przybliżony w minutach)
    B = math.radians(360 * (day_of_year - 81) / 364)
    eq_time = 9.87 * math.sin(2*B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
    
    # Godzina wschodu/zachodu (kąt godzinowy)
    hour_angle = math.degrees(math.acos(
        -math.tan(lat_rad) * math.tan(declination_rad)
    ))
    
    # Przeliczenie na godziny
    sunrise_hour = 12 - hour_angle/15 - (longitude/15) + eq_time/60
    sunset_hour = 12 + hour_angle/15 - (longitude/15) + eq_time/60
    
    # Tworzenie datetime
    sunrise = datetime.combine(target_date, datetime.min.time()) + \
              timedelta(hours=sunrise_hour)
    sunset = datetime.combine(target_date, datetime.min.time()) + \
             timedelta(hours=sunset_hour)
    
    logger.debug(f"Obliczono wschód: {sunrise.strftime('%H:%M')}, "
                 f"zachód: {sunset.strftime('%H:%M')} dla {target_date}")
    
    return sunrise, sunset

def calculate_daily_windows(latitude: float = 51.29, longitude: float = 22.82,
                           target_date: date = None) -> Dict[str, str]:
    """
    Oblicza okna dobowe na podstawie wschodu/zachodu słońca.
    
    Okna:
    - wieczorne: 1.5h przed zachodem do 24:00
    - nocne: 00:00 do 1.5h po wschodzie
    - ładowania: 1.5h po wschodzie do 1.5h przed zachodem
    
    Returns:
        Słownik z godzinami w formacie HH:MM
    """
    try:
        sunrise, sunset = calculate_sun_times(latitude, longitude, target_date)
        
        # Oblicz granice okien
        evening_start = sunset - timedelta(hours=1.5)
        night_end = sunrise + timedelta(hours=1.5)
        
        windows = {
            'wschod_slonca': sunrise.strftime('%H:%M'),
            'zachod_slonca': sunset.strftime('%H:%M'),
            'poczatek_okna_wieczornego': evening_start.strftime('%H:%M'),
            'koniec_okna_ladowania': evening_start.strftime('%H:%M'),  # to samo
            'koniec_okna_nocnego': night_end.strftime('%H:%M'),
        }
        
        logger.info(f"Okna dobowe: wieczorne od {windows['poczatek_okna_wieczornego']}, "
                   f"nocne do {windows['koniec_okna_nocnego']}")
        return windows
        
    except Exception as e:
        logger.error(f"Błąd obliczania okien: {e}")
        # Fallback na sztywne godziny
        return {
            'wschod_slonca': '06:30',
            'zachod_slonca': '17:45',
            'poczatek_okna_wieczornego': '16:15',
            'koniec_okna_ladowania': '16:15',
            'koniec_okna_nocnego': '08:00',
        }

def get_current_window(latitude: float = 51.29, longitude: float = 22.82,
                      current_time: datetime = None) -> str:
    """
    Określa aktualne okno dobowe.
    
    Returns:
        'wieczorne', 'nocne', lub 'ładowania'
    """
    if current_time is None:
        current_time = datetime.now()
    
    windows = calculate_daily_windows(latitude, longitude, current_time.date())
    current_hour_min = current_time.strftime('%H:%M')
    
    # Konwertuj stringi na datetime dla porównania
    try:
        eve_start = datetime.strptime(windows['poczatek_okna_wieczornego'], '%H:%M').time()
        night_end = datetime.strptime(windows['koniec_okna_nocnego'], '%H:%M').time()
        current_t = current_time.time()
        
        # Okno wieczorne (od początku do północy)
        if current_t >= eve_start or current_hour_min >= '22:00':
            return 'wieczorne'
        # Okno nocne (od północy do końca okna nocnego)
        elif current_t < datetime.strptime('06:00', '%H:%M').time() or current_t < night_end:
            return 'nocne'
        else:
            return 'ładowania'
            
    except Exception as e:
        logger.error(f"Błąd określania okna: {e}")
        # Fallback
        hour = current_time.hour
        if 16 <= hour < 24:
            return 'wieczorne'
        elif 0 <= hour < 8:
            return 'nocne'
        else:
            return 'ładowania'
