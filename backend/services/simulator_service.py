import math
import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from backend.database.db import get_db_connection
from backend.services.irrigation_service import (
    get_current_settings, calculate_soil_moisture, evaluate_irrigation_decision, log_event
)

class DeviceSimulator:
    """
    Clearly labeled software test simulator for end-to-end dashboard and API testing
    when physical ESP32 hardware is not yet connected.
    All data produced by this service is explicitly stamped with `is_simulated = 1`.
    """
    def __init__(self):
        self.is_active: bool = False
        self.device_id: str = "esp32-aquasense-sim"
        self.soil_moisture: float = 22.0  # initial moderate moisture
        self.temperature: float = 26.5
        self.humidity: float = 58.0
        self.light_raw: int = 2100
        self.rain_detected: bool = False
        self.pump_state: str = "OFF"
        self.operating_mode: str = "AUTO"
        self.pump_active_seconds: int = 0
        self.uptime: int = 120
        self.battery_voltage: Optional[float] = 3.92 # nominal 18650 test voltage

    def set_active(self, active: bool):
        self.is_active = active

    def step(self, force_rain: Optional[bool] = None, force_dry: Optional[bool] = None) -> Dict[str, Any]:
        """Advance simulation by one test tick (simulating ~3-5 seconds of real-world environment)."""
        settings = get_current_settings()
        self.uptime += 5

        # Handle forced test parameters
        if force_rain is not None:
            self.rain_detected = force_rain
        if force_dry is not None and force_dry:
            self.soil_moisture = 13.5 # directly below 15% threshold

        # Physical simulation logic:
        if self.pump_state == "ON":
            self.pump_active_seconds += 5
            # Pump irrigates: soil moisture rises
            self.soil_moisture = min(100.0, self.soil_moisture + random.uniform(2.5, 4.0))
            # Temperature drops slightly due to evaporative cooling
            self.temperature = max(18.0, self.temperature - 0.1)
            self.humidity = min(95.0, self.humidity + 0.5)
        else:
            self.pump_active_seconds = 0
            if self.rain_detected:
                # Rain increases moisture slowly
                self.soil_moisture = min(100.0, self.soil_moisture + 0.8)
            else:
                # Natural soil drying evaporation
                self.soil_moisture = max(8.0, self.soil_moisture - random.uniform(0.3, 0.7))

        self.soil_moisture = round(self.soil_moisture, 1)

        # Micro-fluctuations in environmental readings
        self.temperature = round(self.temperature + random.uniform(-0.2, 0.2), 1)
        self.humidity = round(max(20.0, min(95.0, self.humidity + random.uniform(-0.5, 0.5))), 1)
        self.light_raw = max(200, min(3900, int(self.light_raw + random.randint(-40, 40))))

        # Calculate inverse ADC raw for FC-28:
        # formula: moisture = ((dry_raw - raw_adc)/(dry_raw - wet_raw)) * 100
        # raw_adc = dry_raw - (moisture/100)*(dry_raw - wet_raw)
        raw_adc = int(settings.soil_dry_raw - (self.soil_moisture / 100.0) * (settings.soil_dry_raw - settings.soil_wet_raw))
        raw_adc = max(100, min(4000, raw_adc))

        # Check pending commands from backend queue
        conn = get_db_connection()
        pending = conn.execute("""
        SELECT * FROM commands WHERE device_id = ? AND status = 'PENDING' ORDER BY created_at ASC LIMIT 1;
        """, (self.device_id,)).fetchone()
        
        if pending:
            cmd_type = pending["command_type"]
            cmd_id = pending["id"]
            now_iso = datetime.now(timezone.utc).isoformat()
            
            if cmd_type == "PUMP_START":
                self.pump_state = "ON"
                self.pump_active_seconds = 0
                log_event("PUMP_START", "ON", self.operating_mode, "Simulated device started pump per backend command", self.soil_moisture, source="SIMULATOR")
            elif cmd_type == "PUMP_STOP":
                self.pump_state = "OFF"
                log_event("PUMP_STOP", "OFF", self.operating_mode, "Simulated device stopped pump per backend command", self.soil_moisture, source="SIMULATOR")
            elif cmd_type == "SET_MODE":
                import json
                try:
                    payload = json.loads(pending["payload"])
                    self.operating_mode = payload.get("mode", self.operating_mode)
                except Exception:
                    pass

            conn.execute("UPDATE commands SET status = 'ACKNOWLEDGED', acknowledged_at = ? WHERE id = ?;", (now_iso, cmd_id))
            conn.commit()

        # If in AUTO mode, local ESP32 simulation logic runs:
        if self.operating_mode == "AUTO":
            decision = evaluate_irrigation_decision(
                soil_moisture=self.soil_moisture,
                rain_detected=self.rain_detected,
                current_pump_state=self.pump_state,
                operating_mode=self.operating_mode,
                current_run_duration_sec=self.pump_active_seconds
            )
            
            if decision["action"] == "START" and self.pump_state == "OFF":
                self.pump_state = "ON"
                self.pump_active_seconds = 0
                log_event("PUMP_START", "ON", "AUTO", decision["reason"], self.soil_moisture, source="SIMULATOR_LOCAL_AUTO")
            elif decision["action"] == "STOP" and self.pump_state == "ON":
                self.pump_state = "OFF"
                log_event("PUMP_STOP", "OFF", "AUTO", decision["reason"], self.soil_moisture, duration_sec=self.pump_active_seconds, source="SIMULATOR_LOCAL_AUTO")
                self.pump_active_seconds = 0

        # Save simulated reading to database
        now_iso = datetime.now(timezone.utc).isoformat()
        light_state = "BRIGHT" if self.light_raw < 1500 else ("MODERATE" if self.light_raw < 2800 else "DARK")

        conn.execute("""
        INSERT INTO readings (
            timestamp, device_id, soil_moisture, soil_raw_adc,
            temperature, humidity, light_raw, light_state,
            rain_detected, rain_raw_adc, pump_state, operating_mode,
            wifi_rssi, battery_voltage, is_simulated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
        """, (
            now_iso, self.device_id, self.soil_moisture, raw_adc,
            self.temperature, self.humidity, self.light_raw, light_state,
            1 if self.rain_detected else 0, 800 if self.rain_detected else 3400,
            self.pump_state, self.operating_mode, -62, self.battery_voltage
        ))

        # Update simulated device health
        conn.execute("""
        INSERT INTO device_health (
            device_id, last_heartbeat, firmware_version, wifi_rssi,
            free_heap, uptime_seconds, sensor_status, battery_voltage, is_simulated
        ) VALUES (?, ?, 'v1.0.0-esp32-sim', -62, 185420, ?, '{"soil":"OK","dht11":"OK","ldr":"OK","rain":"OK","relay":"OK"}', ?, 1)
        ON CONFLICT(device_id) DO UPDATE SET
            last_heartbeat = excluded.last_heartbeat,
            wifi_rssi = excluded.wifi_rssi,
            uptime_seconds = excluded.uptime_seconds,
            sensor_status = excluded.sensor_status,
            is_simulated = 1;
        """, (self.device_id, now_iso, self.uptime, self.battery_voltage))

        conn.commit()
        conn.close()

        result_dict = {
            "timestamp": now_iso,
            "device_id": self.device_id,
            "soil_moisture": self.soil_moisture,
            "soil_raw_adc": raw_adc,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "light_raw": self.light_raw,
            "light_state": light_state,
            "rain_detected": self.rain_detected,
            "pump_state": self.pump_state,
            "operating_mode": self.operating_mode,
            "wifi_rssi": -62,
            "battery_voltage": self.battery_voltage,
            "is_simulated": True
        }

        try:
            from backend.services.firebase_service import schedule_sync_task, sync_reading_to_firebase, sync_status_to_firebase
            from backend.config import settings
            if settings.FIREBASE_ENABLED:
                schedule_sync_task(sync_reading_to_firebase(result_dict))
                schedule_sync_task(sync_status_to_firebase({
                    "online": True,
                    "device_id": self.device_id,
                    "current_pump_state": self.pump_state,
                    "current_mode": self.operating_mode,
                    "is_simulated": True,
                    "wifi_rssi": -62,
                    "firmware_version": "v1.0.0-esp32-sim"
                }))
        except Exception:
            pass

        return result_dict

simulator = DeviceSimulator()
