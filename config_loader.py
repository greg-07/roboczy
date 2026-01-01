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

# Ścieżka do folderu z konfiguracją (względem lokalizacji tego pliku)
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
