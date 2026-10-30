import json
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
from backend.database.db import get_db_connection
from backend.models.schemas import IrrigationSettings

def get_current_settings() -> IrrigationSettings:
    """Retrieve the current persistent settings from SQLite."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM settings WHERE id = 1;").fetchone()
    conn.close()
    if not row:
        return IrrigationSettings()
    return IrrigationSettings(
        dry_threshold=row["dry_threshold"],
        wet_threshold=row["wet_threshold"],
        max_pump_runtime_sec=row["max_pump_runtime_sec"],
        cooldown_duration_sec=row["cooldown_duration_sec"],
        rain_lockout_enabled=bool(row["rain_lockout_enabled"]),
        default_mode=row["default_mode"],
        soil_dry_raw=row["soil_dry_raw"],
        soil_wet_raw=row["soil_wet_raw"],
        device_timeout_sec=row["device_timeout_sec"],
    )

def calculate_soil_moisture(raw_adc: int, dry_raw: int, wet_raw: int) -> float:
    """
    Map raw 12-bit ADC reading (0-4095) to calibrated moisture percentage.
    FC-28 characteristic:
      - Dry air = high resistance -> higher ADC reading (~3500)
      - Pure water = low resistance -> lower ADC reading (~1400)
    Formula: ((dry_raw - raw_adc) / (dry_raw - wet_raw)) * 100.0
    """
    if dry_raw <= wet_raw:
        return 0.0
    
    # Clamp raw_adc within calibration envelope for percentage mapping
    val = (float(dry_raw) - float(raw_adc)) / float(dry_raw - wet_raw) * 100.0
    val = max(0.0, min(100.0, val))
    return round(val, 1)

def classify_soil_status(moisture: float, dry_threshold: float, wet_threshold: float) -> str:
    """Classify soil condition into clear, human-readable agronomic categories."""
    if moisture < dry_threshold:
        return "Dry (Irrigation Required)"
    elif moisture < wet_threshold:
        return "Moderate (Optimal Root Zone)"
    else:
        return "Sufficiently Moist (Watering Inactive)"

def log_event(event_type: str, pump_state: str, operating_mode: str, reason: str,
              soil_moisture: Optional[float] = None, duration_sec: float = 0.0,
              source: str = "AUTO", conn = None):
    """Record an irrigation or safety event to the audit log."""
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute("""
    INSERT INTO events (
        timestamp, event_type, soil_moisture, pump_state,
        operating_mode, reason, duration_sec, source
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (now_iso, event_type, soil_moisture, pump_state, operating_mode, reason, duration_sec, source))

    if should_close:
        conn.commit()
        conn.close()

def evaluate_irrigation_decision(
    soil_moisture: float,
    rain_detected: bool,
    current_pump_state: str,
    operating_mode: str,
    last_stop_time: Optional[datetime] = None,
    current_run_duration_sec: float = 0.0
) -> Dict[str, Any]:
    """
    Evaluate the local/cloud irrigation decision rulebook with hysteresis:
      - Start watering if moisture < dry_threshold (15%) AND no rain AND not cooling down
      - Stop watering if moisture >= wet_threshold (25%)
      - Stop watering immediately if rain detected (lockout)
      - Stop watering if max run-time exceeded
    """
    settings = get_current_settings()
    now = datetime.now(timezone.utc)
    
    # 1. Rain lockout rule
    if rain_detected and settings.rain_lockout_enabled:
        return {
            "action": "STOP" if current_pump_state == "ON" else "HOLD",
            "reason": "Rain detected: Natural precipitation active. Rain lockout enforces pump shutdown to conserve water.",
            "lockout_active": True,
            "target_pump_state": "OFF"
        }

    # 2. Maximum run-time rule
    if current_pump_state == "ON" and current_run_duration_sec >= settings.max_pump_runtime_sec:
        return {
            "action": "STOP",
            "reason": f"Maximum continuous pump run-time ({settings.max_pump_runtime_sec}s) reached. Watchdog triggered cutoff.",
            "lockout_active": False,
            "target_pump_state": "OFF"
        }

    # 3. Manual mode bypasses automatic start logic (ESP32 honors manual state unless safety triggers)
    if operating_mode == "MANUAL":
        return {
            "action": "MANUAL_HOLD",
            "reason": "Manual control mode active. Automatic trigger suspended.",
            "lockout_active": False,
            "target_pump_state": current_pump_state
        }

    # 4. Hysteresis rule: If Pump is ON, check if we reached wet_threshold (25%)
    if current_pump_state == "ON":
        if soil_moisture >= settings.wet_threshold:
            return {
                "action": "STOP",
                "reason": f"Soil moisture reached wet hysteresis cutoff ({soil_moisture}% >= {settings.wet_threshold}%). Irrigation completed.",
                "lockout_active": False,
                "target_pump_state": "OFF"
            }
        else:
            return {
                "action": "CONTINUE",
                "reason": f"Watering in progress. Current moisture: {soil_moisture}% (Target: {settings.wet_threshold}%).",
                "lockout_active": False,
                "target_pump_state": "ON"
            }

    # 5. Cooldown check before initiating new cycle
    if last_stop_time:
        elapsed_since_stop = (now - last_stop_time).total_seconds()
        if elapsed_since_stop < settings.cooldown_duration_sec:
            remaining = int(settings.cooldown_duration_sec - elapsed_since_stop)
            return {
                "action": "HOLD",
                "reason": f"System in cooldown rest period ({remaining}s remaining of {settings.cooldown_duration_sec}s). Preventing rapid cycling.",
                "lockout_active": False,
                "target_pump_state": "OFF"
            }

    # 6. Automatic Trigger: Moisture below dry_threshold (15%)
    if soil_moisture < settings.dry_threshold:
        return {
            "action": "START",
            "reason": f"Soil moisture ({soil_moisture}%) dropped below threshold ({settings.dry_threshold}%). Automatic irrigation initiated.",
            "lockout_active": False,
            "target_pump_state": "ON"
        }

    return {
        "action": "HOLD",
        "reason": f"Soil moisture adequate ({soil_moisture}% between {settings.dry_threshold}% and {settings.wet_threshold}%). Monitoring.",
        "lockout_active": False,
        "target_pump_state": "OFF"
    }
