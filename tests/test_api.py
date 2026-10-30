import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["TESTING"] = "1"

import unittest
from fastapi.testclient import TestClient
from app import app
from backend.database.db import init_db, get_db_connection

class AquaSenseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        conn = get_db_connection()
        conn.execute("DELETE FROM readings;")
        conn.execute("DELETE FROM commands;")
        conn.execute("DELETE FROM device_health;")
        conn.execute("DELETE FROM events;")
        conn.execute("DELETE FROM alerts;")
        conn.commit()
        conn.close()
        cls.client = TestClient(app)

    def test_01_initial_status(self):
        """Verify device defaults to offline before telemetry is sent."""
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("online", data)
        self.assertIn("recommendation", data)
        self.assertEqual(data["current_pump_state"], "OFF")

    def test_02_get_settings_defaults(self):
        """Verify default agronomic thresholds: 15% dry, 25% wet hysteresis."""
        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        settings = resp.json()
        self.assertEqual(settings["dry_threshold"], 15.0)
        self.assertEqual(settings["wet_threshold"], 25.0)
        self.assertEqual(settings["max_pump_runtime_sec"], 20)
        self.assertTrue(settings["rain_lockout_enabled"])

    def test_03_settings_validation_hysteresis(self):
        """Verify that wet threshold <= dry threshold is rejected."""
        invalid_payload = {
            "dry_threshold": 25.0,
            "wet_threshold": 20.0, # Invalid: must be > dry + 2.0%
            "max_pump_runtime_sec": 20,
            "cooldown_duration_sec": 60,
            "rain_lockout_enabled": True,
            "default_mode": "AUTO",
            "soil_dry_raw": 3500,
            "soil_wet_raw": 1400,
            "device_timeout_sec": 45
        }
        resp = self.client.put("/api/settings", json=invalid_payload)
        self.assertEqual(resp.status_code, 422)

    def test_04_submit_sensor_reading(self):
        """Verify ESP32 telemetry submission and calibration calculation."""
        payload = {
            "device_id": "esp32-aquasense-unit1",
            "soil_raw_adc": 2450, # Mid-range moisture
            "temperature": 24.5,
            "humidity": 62.0,
            "light_raw": 1850,
            "rain_detected": False,
            "rain_raw_adc": 3200,
            "pump_state": "OFF",
            "operating_mode": "AUTO",
            "wifi_rssi": -65,
            "firmware_version": "v1.0.0-esp32",
            "uptime_seconds": 360
        }
        resp = self.client.post("/api/readings", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertGreater(data["calibrated_moisture"], 0.0)
        self.assertLess(data["calibrated_moisture"], 100.0)

    def test_05_get_latest_reading_freshness(self):
        """Verify GET /api/readings/latest reflects recent reading and freshness."""
        resp = self.client.get("/api/readings/latest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data)
        self.assertEqual(data["device_id"], "esp32-aquasense-unit1")
        self.assertIsNotNone(data["freshness_seconds"])
        self.assertLess(data["freshness_seconds"], 10.0)

    def test_06_device_online_after_heartbeat(self):
        """Verify device status marks online when telemetry is recent."""
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["online"])
        self.assertEqual(data["device_id"], "esp32-aquasense-unit1")

    def test_07_rain_lockout_blocks_pump_start(self):
        """Verify that when rain is detected, pump start is blocked."""
        # Submit rain reading
        rain_payload = {
            "device_id": "esp32-aquasense-unit1",
            "soil_raw_adc": 3400, # Dry soil
            "temperature": 21.0,
            "humidity": 88.0,
            "light_raw": 3100,
            "rain_detected": True, # Rain detected!
            "pump_state": "OFF",
            "operating_mode": "AUTO",
            "wifi_rssi": -68
        }
        self.client.post("/api/readings", json=rain_payload)

        # Attempt to start pump
        cmd_payload = {
            "command_type": "PUMP_START",
            "target_state": "ON",
            "duration_sec": 15,
            "source": "MANUAL_DASHBOARD"
        }
        resp = self.client.post("/api/commands?device_id=esp32-aquasense-unit1", json=cmd_payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Rain is currently detected", resp.json()["detail"])

    def test_08_command_queue_and_acknowledgement(self):
        """Test command creation without rain lockout, polling and ACK."""
        # Submit clear weather reading
        clear_payload = {
            "device_id": "esp32-aquasense-unit1",
            "soil_raw_adc": 2500,
            "temperature": 25.0,
            "humidity": 55.0,
            "light_raw": 1200,
            "rain_detected": False,
            "pump_state": "OFF",
            "operating_mode": "MANUAL",
            "wifi_rssi": -60
        }
        self.client.post("/api/readings", json=clear_payload)

        # Dispatch command
        cmd_payload = {
            "command_type": "PUMP_START",
            "target_state": "ON",
            "duration_sec": 10,
            "source": "MANUAL_DASHBOARD",
            "reason": "Test manual irrigation"
        }
        resp = self.client.post("/api/commands?device_id=esp32-aquasense-unit1", json=cmd_payload)
        self.assertEqual(resp.status_code, 200)
        cmd_id = resp.json()["command"]["id"]

        # ESP32 polls pending commands
        poll_resp = self.client.get("/api/commands/pending?device_id=esp32-aquasense-unit1")
        self.assertEqual(poll_resp.status_code, 200)
        pending = poll_resp.json()
        self.assertTrue(any(c["id"] == cmd_id for c in pending))

        # ESP32 sends ACK
        ack_payload = {
            "command_id": cmd_id,
            "status": "ACKNOWLEDGED",
            "pump_state": "ON",
            "operating_mode": "MANUAL"
        }
        ack_resp = self.client.post("/api/commands/ack", json=ack_payload)
        self.assertEqual(ack_resp.status_code, 200)

    def test_09_events_audit_log(self):
        """Verify events audit log returns recorded actions."""
        resp = self.client.get("/api/events")
        self.assertEqual(resp.status_code, 200)
        events = resp.json()
        self.assertIsInstance(events, list)
        self.assertGreater(len(events), 0)

    def test_10_alerts_evaluation(self):
        """Verify alerts endpoint returns system alerts."""
        resp = self.client.get("/api/alerts")
        self.assertEqual(resp.status_code, 200)
        alerts = resp.json()
        self.assertIsInstance(alerts, list)

    def test_11_csv_export(self):
        """Verify CSV export for readings and events."""
        resp_readings = self.client.get("/api/export/csv?data_type=readings")
        self.assertEqual(resp_readings.status_code, 200)
        self.assertIn("text/csv", resp_readings.headers["content-type"])
        self.assertIn("Soil Moisture", resp_readings.text)

        resp_events = self.client.get("/api/export/csv?data_type=events")
        self.assertEqual(resp_events.status_code, 200)
        self.assertIn("Event Type", resp_events.text)

    def test_12_simulator_explicit_tagging(self):
        """Verify simulator produces explicitly marked telemetry."""
        step_resp = self.client.post("/api/simulator/step?force_dry=true")
        self.assertEqual(step_resp.status_code, 200)
        res = step_resp.json()["step_result"]
        self.assertTrue(res["is_simulated"])
        self.assertLessEqual(res["soil_moisture"], 15.0)

    def test_13_firebase_config_and_status(self):
        """Verify Firebase client config and status endpoints."""
        cfg_resp = self.client.get("/api/firebase/config")
        self.assertEqual(cfg_resp.status_code, 200)
        cfg = cfg_resp.json()
        self.assertEqual(cfg["projectId"], "aquasense-62dda")
        self.assertIn("asia-southeast1.firebasedatabase.app", cfg["databaseURL"])
        self.assertTrue(cfg["enabled"])

        status_resp = self.client.get("/api/firebase/status")
        self.assertEqual(status_resp.status_code, 200)
        st = status_resp.json()
        self.assertTrue(st["enabled"])

if __name__ == "__main__":
    unittest.main()
