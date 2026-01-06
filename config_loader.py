"""
Centralny ładowacz konfiguracji dla systemu SZE.
Ładuje wszystkie pliki JSON z folderu config/ i udostępnia je reszcie systemu.
"""
import json
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Ścieżka do folderu z konfiguracją (względem lokalizacji tego pliku) - już relative, ujednolicone
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')

# Globalny cache z załadowanymi konfiguracjami
_config_cache = {
    'energy_profiles': None,
    'cwu_schedule': None,
    'system_config': None,
    'user_corrections': None,
    'last_load_time': None
}

def _load_json_file(filename: str) -> Optional[Dict[str, Any]]:
    """Ładuje pojedynczy plik JSON i zwraca jako słownik."""
    filepath = os.path.join(CONFIG_DIR, filename)
    
    if not os.path.exists(filepath):
        logger.error(f"Plik konfiguracyjny nie istnieje: {filepath}")
        return None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Załadowano konfigurację z: {filename}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Błąd parsowania JSON w pliku {filename}: {e}")
        return None
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd przy ładowaniu {filename}: {e}")
        return None

def _validate_energy_profiles(data: Dict[str, Any]) -> Dict[str, Any]:
    """Waliduje energy_profiles.json i ustawia defaults jeśli brak kluczy."""
    required_keys = ['energy_profiles']
    for key in required_keys:
        if key not in data:
            logger.warning(f"Brak klucza '{key}' w energy_profiles.json - ustawiam default: pusty dict")
            data[key] = {}
    
    # Sprawdź podklucze w 'energy_profiles'
    if 'energy_profiles' in data:
        sub_keys = ['dzien_roboczy', 'sobota', 'niedziela_swieto']
        for sub_key in sub_keys:
            if sub_key not in data['energy_profiles']:
                logger.warning(f"Brak podklucza '{sub_key}' w energy_profiles - ustawiam default: pusta lista")
                data['energy_profiles'][sub_key] = []
    
    return data

def _validate_cwu_schedule(data: Dict[str, Any]) -> Dict[str, Any]:
    """Waliduje cwu_schedule.json i ustawia defaults jeśli brak kluczy."""
    required_keys = ['temperatury', 'harmonogram_poranny', 'harmonogram_wieczorny', 'harmonogram_dowolny']
    for key in required_keys:
        if key not in data:
            logger.warning(f"Brak klucza '{key}' w cwu_schedule.json - ustawiam default: pusty dict")
            data[key] = {}
    
    # Dodatkowe sprawdzenia dla podkluczy
    if 'temperatury' in data:
        sub_keys = ['temp_ranek_celsius', 'temp_wieczor_celsius', 'temp_dowolny_celsius']
        for sub_key in sub_keys:
            if sub_key not in data['temperatury']:
                default_value = 40 if 'ranek' in sub_key else 50
                logger.warning(f"Brak '{sub_key}' w temperaturach - ustawiam default: {default_value}")
                data['temperatury'][sub_key] = default_value
    
    if 'harmonogram_poranny' in data:
        sub_keys = ['dzien_roboczy_godzina', 'sobota_godzina', 'niedziela_swieto_godzina']
        for sub_key in sub_keys:
            if sub_key not in data['harmonogram_poranny']:
                default_value = "04:30" if 'roboczy' in sub_key else "07:00" if 'sobota' in sub_key else "08:00"
                logger.warning(f"Brak '{sub_key}' w harmonogram_poranny - ustawiam default: {default_value}")
                data['harmonogram_poranny'][sub_key] = default_value
    
    if 'harmonogram_wieczorny' in data:
        sub_keys = ['dzien_roboczy_godzina', 'sobota_godzina', 'niedziela_swieto_godzina']
        for sub_key in sub_keys:
            if sub_key not in data['harmonogram_wieczorny']:
                default_value = "19:30" if 'roboczy' in sub_key else "19:00"
                logger.warning(f"Brak '{sub_key}' w harmonogram_wieczorny - ustawiam default: {default_value}")
                data['harmonogram_wieczorny'][sub_key] = default_value
    
    if 'harmonogram_dowolny' in data:
        sub_keys = ['wlaczony', 'godzina_dowolna']
        for sub_key in sub_keys:
            if sub_key not in data['harmonogram_dowolny']:
                default_value = False if 'wlaczony' in sub_key else None
                logger.warning(f"Brak '{sub_key}' w harmonogram_dowolny - ustawiam default: {default_value}")
                data['harmonogram_dowolny'][sub_key] = default_value
    
    return data

def _validate_system_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """Waliduje system_config.json i ustawia defaults jeśli brak kluczy."""
    required_keys = [
        'supla_hardware', 'api_keys', 'pv_installation', 'boiler', 
        'mqtt_solar_assistant', 'calendar', 'tariff_g12w', 'system_settings',
        'switches', 'battery'
    ]
    for key in required_keys:
        if key not in data:
            logger.warning(f"Brak klucza '{key}' w system_config.json - ustawiam default: pusty dict")
            data[key] = {}
    
    # Dodatkowe sprawdzenia dla krytycznych podkluczy (np. switches)
    if 'switches' in data:
        sub_keys = ['urlop', 'wyjazd', 'tryb_reczny']
        for sub_key in sub_keys:
            if sub_key not in data['switches']:
                if sub_key == 'tryb_reczny':
                    default = False
                    logger.warning(f"Brak '{sub_key}' w switches - ustawiam default: {default}")
                    data['switches'][sub_key] = default
                else:
                    default = {"enabled": False, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
                    logger.warning(f"Brak '{sub_key}' w switches - ustawiam default: {default}")
                    data['switches'][sub_key] = default
    
    if 'battery' in data:
        if 'capacity_kwh' not in data['battery']:
            default = 16.0
            logger.warning(f"Brak 'capacity_kwh' w battery - ustawiam default: {default}")
            data['battery']['capacity_kwh'] = default
    
    # Dla innych sekcji, podobne, ale dla uproszczenia zakładamy pusty dict jako default
    return data

def _validate_user_corrections(data: Dict[str, Any]) -> Dict[str, Any]:
    """Waliduje user_corrections.json i ustawia defaults jeśli brak kluczy."""
    required_keys = ['balance_increase_wh', 'system_losses_percent']
    for key in required_keys:
        if key not in data:
            logger.warning(f"Brak klucza '{key}' w user_corrections.json - ustawiam default: pusty dict")
            data[key] = {}
    
    # Sprawdź podklucze w 'balance_increase_wh'
    if 'balance_increase_wh' in data:
        sub_keys = ['window_evening', 'window_night', 'window_loading']
        for sub_key in sub_keys:
            if sub_key not in data['balance_increase_wh']:
                logger.warning(f"Brak '{sub_key}' w balance_increase_wh - ustawiam default: 0")
                data['balance_increase_wh'][sub_key] = 0
    
    # Sprawdź podklucze w 'system_losses_percent'
    if 'system_losses_percent' in data:
        sub_keys = ['conversion_dc_ac', 'charging_ac_dc']
        for sub_key in sub_keys:
            if sub_key not in data['system_losses_percent']:
                default_value = 5.0 if 'dc_ac' in sub_key else 7.0
                logger.warning(f"Brak '{sub_key}' w system_losses_percent - ustawiam default: {default_value}")
                data['system_losses_percent'][sub_key] = default_value
    
    return data

def reload_all_configs() -> bool:
    """
    Przeładowuje wszystkie pliki konfiguracyjne z dysku.
    Zwraca True jeśli wszystkie pliki załadowano poprawnie.
    """
    logger.info("Przeładowywanie wszystkich konfiguracji...")
    
    global _config_cache
    
    # Próbuj załadować każdy plik
    energy_data = _load_json_file('energy_profiles.json')
    cwu_data = _load_json_file('cwu_schedule.json')
    system_data = _load_json_file('system_config.json')
    corrections_data = _load_json_file('user_corrections.json')
    
    # Waliduj dane jeśli załadowane
    if energy_data:
        energy_data = _validate_energy_profiles(energy_data)
    
    if cwu_data:
        cwu_data = _validate_cwu_schedule(cwu_data)
    
    if system_data:
        system_data = _validate_system_config(system_data)
    
    if corrections_data:
        corrections_data = _validate_user_corrections(corrections_data)
    
    # Sprawdź, które pliki załadowały się poprawnie
    success = True
    loaded_files = []
    
    if energy_data:
        _config_cache['energy_profiles'] = energy_data
        loaded_files.append('energy_profiles.json')
    else:
        success = False
        logger.warning("Nie udało się załadować energy_profiles.json")
    
    if cwu_data:
        _config_cache['cwu_schedule'] = cwu_data
        loaded_files.append('cwu_schedule.json')
    else:
        success = False
        logger.warning("Nie udało się załadować cwu_schedule.json")
    
    if system_data:
        _config_cache['system_config'] = system_data
        loaded_files.append('system_config.json')
    else:
        success = False
        logger.warning("Nie udało się załadować system_config.json")
    
    if corrections_data:
        _config_cache['user_corrections'] = corrections_data
        loaded_files.append('user_corrections.json')
    else:
        success = False
        logger.warning("Nie udało się załadować user_corrections.json")
    
    if loaded_files:
        _config_cache['last_load_time'] = datetime.now().isoformat()
        logger.info(f"Pomyślnie załadowano pliki: {', '.join(loaded_files)}")
    
    return success

def get_energy_profiles(day_type: str = None) -> Optional[Dict[str, Any]]:
    """
    Zwraca profile energetyczne.
    Jeśli podano day_type ('dzien_roboczy', 'sobota', 'niedziela_swieto'),
    zwraca tylko profil dla tego dnia.
    """
    if not _config_cache['energy_profiles']:
        reload_all_configs()
    
    data = _config_cache['energy_profiles']
    if not data:
        return None
    
    if day_type and day_type in data:
        return {day_type: data[day_type]}
    
    return data

def get_cwu_schedule() -> Optional[Dict[str, Any]]:
    """Zwraca harmonogram CWU."""
    if not _config_cache['cwu_schedule']:
        reload_all_configs()
    
    return _config_cache['cwu_schedule']

def get_system_config() -> Optional[Dict[str, Any]]:
    """Zwraca konfigurację systemu."""
    if not _config_cache['system_config']:
        reload_all_configs()
    
    return _config_cache['system_config']

def get_user_corrections() -> Optional[Dict[str, Any]]:
    """Zwraca korekty użytkownika."""
    if not _config_cache['user_corrections']:
        reload_all_configs()
    
    return _config_cache['user_corrections']

def get_config_status() -> Dict[str, Any]:
    """Zwraca status wszystkich konfiguracji."""
    return {
        'energy_profiles_loaded': _config_cache['energy_profiles'] is not None,
        'cwu_schedule_loaded': _config_cache['cwu_schedule'] is not None,
        'system_config_loaded': _config_cache['system_config'] is not None,
        'user_corrections_loaded': _config_cache['user_corrections'] is not None,
        'last_load_time': _config_cache['last_load_time']
    }

def get_energy_profiles_with_variables(day_type: str = None) -> Dict[str, Any]:
    """
    Zwraca profile energetyczne z podstawionymi zmiennymi czasowymi.
    
    Zmienne do podstawienia w polach 'od'/'do':
    - poczatek_okna_wieczornego
    - koniec_okna_ladowania
    - wschod_slonca
    - zachod_slonca
    - koniec_okna_nocnego
    """
    profiles = get_energy_profiles(day_type)
    if not profiles:
        return {}
    
    # Oblicz aktualne okna - import tutaj aby uniknąć cyklicznych importów
    try:
        from .daily_windows import calculate_daily_windows
    except ImportError:
        logger.error("Nie można zaimportować daily_windows")
        return profiles
    
    system_config = get_system_config() or {}
    pv_config = system_config.get('pv_installation', {})
    
    try:
        coords = pv_config.get('coordinates', '51.290050, 22.818633')
        lat_str, lon_str = coords.split(',')
        lat = float(lat_str.strip())
        lon = float(lon_str.strip())
    except:
        lat, lon = 51.29, 22.82
    
    windows = calculate_daily_windows(latitude=lat, longitude=lon)
    logger.debug(f"Podstawiam zmienne okien: {windows}")
    
    # Funkcja do zamiany zmiennych w stringu
    def replace_variables(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        for var_name, var_value in windows.items():
            if var_name in text:
                text = text.replace(var_name, var_value)
        return text
    
    # Głęboka kopia i zamiana
    import copy
    profiles_copy = copy.deepcopy(profiles)
    
    # Przejdź przez wszystkie profile
    for day_key, day_data in profiles_copy.items():
        if day_type and day_key != day_type:
            continue
            
        if 'profile' in day_data and isinstance(day_data['profile'], list):
            for profile in day_data['profile']:
                if 'od' in profile:
                    profile['od'] = replace_variables(profile['od'])
                if 'do' in profile:
                    profile['do'] = replace_variables(profile['do'])
                # Obsługa 'od_wybierz_pozniejsza' jeśli istnieje
                if 'od_wybierz_pozniejsza' in profile and isinstance(profile['od_wybierz_pozniejsza'], list):
                    profile['od_wybierz_pozniejsza'] = [
                        replace_variables(item) for item in profile['od_wybierz_pozniejsza']
                    ]
    
    return profiles_copy
#zmiana ścieżek hardcoded paths na relative; walidacja na kluczach w dict.
