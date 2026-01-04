"""
Integracja MQTT z Solar Assistant
"""
import paho.mqtt.client as mqtt
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import threading
import time

logger = logging.getLogger(__name__)

class SolarAssistantMQTT:
    """Komunikacja z Solar Assistant przez MQTT"""
    
    def __init__(self, broker_ip: str = "192.168.8.143", port: int = 1883, prefix: str = "SZE"):
        self.broker_ip = broker_ip
        self.port = port
        self.prefix = prefix
        self.client = None
        
        # Dane z SA
        self.current_data = {
            'timestamp': None,
            'inverter': {},
            'battery': {},
            'grid': {},
            'pv': {},
            'load': {},
            'connected': False,
            'last_update': None
        }
        
        # Cache danych
        self.data_cache = {}
        self.lock = threading.Lock()
        
        logger.info(f"MQTT SA: broker={broker_ip}, prefix={prefix}")
    
    def connect(self) -> bool:
        """Nawiązanie połączenia MQTT"""
        try:
            self.client = mqtt.Client()
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            
            # Ustawienia
            self.client.connect(self.broker_ip, self.port, 60)
            self.client.loop_start()
            
            logger.info(f"Połączono z MQTT brokerem {self.broker_ip}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Błąd połączenia MQTT: {e}")
            return False
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback połączenia"""
        if rc == 0:
            logger.info("MQTT: Połączenie udane")
            
            # Subskrybuj tematy
            topics = [
                f"{self.prefix}/inverter_1/#",
                f"{self.prefix}/total/#",
                f"{self.prefix}/battery_1/#",
                f"{self.prefix}/set/response_message/state"
            ]
            
            for topic in topics:
                client.subscribe(topic)
                logger.debug(f"Subskrybowano: {topic}")
            
            self.current_data['connected'] = True
            self.current_data['last_connect'] = datetime.now().isoformat()
            
        else:
            logger.error(f"MQTT: Błąd połączenia {rc}")
    
    def _on_message(self, client, userdata, msg):
        """Callback wiadomości MQTT"""
        try:
            topic = msg.topic
            payload = msg.payload.decode()
            
            with self.lock:
                # Zaktualizuj cache
                self.data_cache[topic] = {
                    'value': payload,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Parsuj dane wg tematu
                if "inverter_1" in topic:
                    self._parse_inverter_data(topic, payload)
                elif "total" in topic:
                    self._parse_total_data(topic, payload)
                elif "battery_1" in topic:
                    self._parse_battery_data(topic, payload)
                
                self.current_data['timestamp'] = datetime.now().isoformat()
                self.current_data['last_update'] = datetime.now().strftime("%H:%M:%S")
                
                # Loguj tylko ważne zmiany
                if "grid_power" in topic or "battery_state_of_charge" in topic:
                    logger.debug(f"MQTT << {topic}: {payload}")
                    
        except Exception as e:
            logger.error(f"Błąd parsowania MQTT: {e}")
    
    def _parse_inverter_data(self, topic: str, payload: str):
        """Parsuje dane z inwertera"""
        if "grid_power" in topic:
            self.current_data['grid']['power_w'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
        elif "pv_power" in topic:
            self.current_data['pv']['power_w'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
        elif "load_power" in topic:
            self.current_data['load']['power_w'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
        elif "output_source_priority" in topic:
            self.current_data['inverter']['output_source'] = payload
        elif "charger_source_priority" in topic:
            self.current_data['inverter']['charger_source'] = payload
        elif "max_grid_charge_current" in topic:
            self.current_data['inverter']['max_grid_charge_a'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
    
    def _parse_total_data(self, topic: str, payload: str):
        """Parsuje dane zbiorcze"""
        if "battery_state_of_charge" in topic:
            self.current_data['battery']['soc_percent'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
        elif "battery_power" in topic:
            self.current_data['battery']['power_w'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
        elif "grid_power" in topic:
            self.current_data['grid']['power_w'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
    
    def _parse_battery_data(self, topic: str, payload: str):
        """Parsuje dane z baterii"""
        if "state_of_charge" in topic:
            self.current_data['battery']['soc_percent'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
        elif "voltage" in topic:
            self.current_data['battery']['voltage_v'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
        elif "current" in topic:
            self.current_data['battery']['current_a'] = float(payload) if payload.replace('.', '', 1).isdigit() else 0
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback rozłączenia"""
        logger.warning(f"MQTT rozłączony (rc={rc})")
        self.current_data['connected'] = False
        self.current_data['last_disconnect'] = datetime.now().isoformat()
    
    def get_current_data(self) -> Dict[str, Any]:
        """Zwraca aktualne dane"""
        with self.lock:
            return self.current_data.copy()
    
    def publish_command(self, topic_suffix: str, value: str) -> bool:
        """Wysyła polecenie do SA"""
        try:
            topic = f"{self.prefix}/{topic_suffix}"
            self.client.publish(topic, value)
            logger.info(f"MQTT >> {topic}: {value}")
            return True
        except Exception as e:
            logger.error(f"Błąd wysyłania MQTT: {e}")
            return False
    
    def set_output_source_priority(self, priority: str) -> bool:
        """Ustawia output_source_priority"""
        # Możliwe wartości: "Utility first", "Solar first", "Solar/Battery/Utility", "Solar/Utility/Battery"
        return self.publish_command("inverter_1/output_source_priority/set", priority)
    
    def set_max_grid_charge_current(self, amps: int) -> bool:
        """Ustawia max_grid_charge_current (A)"""
        return self.publish_command("inverter_1/max_grid_charge_current/set", str(amps))
    
    def set_charger_source_priority(self, priority: str) -> bool:
        """Ustawia charger_source_priority"""
        # Możliwe: "Utility first", "Solar first", "Solar and utility simultaneously", "Solar only"
        return self.publish_command("inverter_1/charger_source_priority/set", priority)
    
    def disconnect(self):
        """Rozłączenie MQTT"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Rozłączono MQTT")

# Globalna instancja
mqtt_client = SolarAssistantMQTT()

def start_mqtt_in_background():
    """Uruchamia MQTT w tle"""
    success = mqtt_client.connect()
    if success:
        logger.info("MQTT uruchomiony w tle")
    return success
