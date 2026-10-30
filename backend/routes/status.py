from fastapi import APIRouter
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from backend.database.db import get_db_connection
from backend.models.schemas import SystemStatus
from backend.services.irrigation_service import get_current_settings, evaluate_irrigation_decision

router = APIRouter(prefix="/api/status", tags=["System Status"])

@router.get("", response_model=SystemStatus)
def get_system_status():
    """
    Get holistic system health, ESP32 connectivity state, and irrigation recommendation.
    Enforces the rule: Never show online unless recent valid telemetry has arrived.
    """
    conn = get_db_connection()
    settings = get_current_settings()
    now = datetime.now(timezone.utc)

    # 1. Device health record
    health = conn.execute("""
    SELECT * FROM device_health ORDER BY last_heartbeat DESC LIMIT 1;
    """).fetchone()

    # 2. Latest reading
    latest = conn.execute("""
    SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1;
    """).fetchone()

    # 3. Active unacknowledged alerts
    alert_count_row = conn.execute("""
    SELECT COUNT(*) as cnt FROM alerts WHERE is_acknowledged = 0;
    """).fetchone()
    active_alerts_count = alert_count_row["cnt"] if alert_count_row else 0

    conn.close()

    # Calculate online status strictly
    is_online = False
    seconds_since_last_seen: Optional[float] = None
    device_id: Optional[str] = None
    firmware_version: Optional[str] = None
    wifi_rssi: Optional[int] = None
    is_simulated = False
    hardware_attached = False

    if health:
        device_id = health["device_id"]
        firmware_version = health["firmware_version"]
        wifi_rssi = health["wifi_rssi"]
        is_simulated = bool(health["is_simulated"])
        hardware_attached = not is_simulated

        if health["last_heartbeat"]:
            try:
                hb_dt = datetime.fromisoformat(health["last_heartbeat"])
                seconds_since_last_seen = round((now - hb_dt).total_seconds(), 1)
                if seconds_since_last_seen <= settings.device_timeout_sec:
                    is_online = True
            except Exception:
                pass

    current_pump_state = "OFF"
    current_mode = "AUTO"
    rain_lockout_active = False
    recommendation = "System initialized. Waiting for sensor telemetry."

    if latest:
        current_pump_state = latest["pump_state"]
        current_mode = latest["operating_mode"]
        rain_lockout_active = bool(latest["rain_detected"]) and settings.rain_lockout_enabled

        # Formulate actionable recommendation
        if not is_online:
            recommendation = "ESP32 is offline. Check hardware power, Wi-Fi link, or start testing simulator."
        elif rain_lockout_active:
            recommendation = "Rain detected. Natural moisture active; automatic irrigation is locked out."
        elif latest["soil_moisture"] < settings.dry_threshold:
            recommendation = f"Soil is dry ({latest['soil_moisture']}% < {settings.dry_threshold}%). Automatic watering active or ready."
        elif latest["soil_moisture"] >= settings.wet_threshold:
            recommendation = f"Root zone moist ({latest['soil_moisture']}%). Soil moisture is adequate; pump is safely idle."
        else:
            recommendation = f"Soil moisture optimal ({latest['soil_moisture']}%). Balanced agronomic moisture range."

    return SystemStatus(
        online=is_online,
        device_id=device_id,
        last_heartbeat=health["last_heartbeat"] if health else None,
        seconds_since_last_seen=seconds_since_last_seen,
        current_pump_state=current_pump_state,
        current_mode=current_mode,
        active_alerts_count=active_alerts_count,
        rain_lockout_active=rain_lockout_active,
        recommendation=recommendation,
        firmware_version=firmware_version,
        wifi_rssi=wifi_rssi,
        is_simulated=is_simulated,
        hardware_attached=hardware_attached
    )
