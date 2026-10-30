from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from backend.database.db import get_db_connection
from backend.services.irrigation_service import get_current_settings

def create_alert_if_not_active(
    alert_key: str,
    severity: str,
    title: str,
    explanation: str,
    recommended_action: str
) -> Optional[int]:
    """
    Create an alert entry if an unacknowledged/unresolved alert of the same key does not already exist.
    Prevents alert flooding and duplicate spam.
    """
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Check if existing unacknowledged alert with this key was created within the last 15 minutes
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    existing = conn.execute("""
    SELECT id FROM alerts 
    WHERE alert_key = ? AND is_acknowledged = 0 AND timestamp > ?;
    """, (alert_key, cutoff)).fetchone()
    
    if existing:
        conn.close()
        return None
        
    cursor = conn.execute("""
    INSERT INTO alerts (
        timestamp, alert_key, severity, title, explanation,
        recommended_action, is_acknowledged
    ) VALUES (?, ?, ?, ?, ?, ?, 0);
    """, (now_iso, alert_key, severity, title, explanation, recommended_action))
    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return alert_id

def evaluate_system_alerts() -> List[Dict[str, Any]]:
    """
    Evaluate system health conditions, sensor thresholds, and connection freshness.
    Emits alerts when anomalies or threshold events occur.
    """
    conn = get_db_connection()
    settings = get_current_settings()
    now = datetime.now(timezone.utc)
    
    # 1. Check ESP32 connectivity
    health = conn.execute("SELECT * FROM device_health ORDER BY last_heartbeat DESC LIMIT 1;").fetchone()
    if health and health["last_heartbeat"]:
        try:
            last_hb = datetime.fromisoformat(health["last_heartbeat"])
            elapsed = (now - last_hb).total_seconds()
            if elapsed > settings.device_timeout_sec:
                create_alert_if_not_active(
                    alert_key="DEVICE_OFFLINE",
                    severity="CRITICAL",
                    title="ESP32 Device Offline",
                    explanation=f"No telemetry received from node '{health['device_id']}' for {int(elapsed)} seconds (threshold: {settings.device_timeout_sec}s).",
                    recommended_action="Check ESP32 power, Wi-Fi router connectivity, and firmware status. Manual irrigation commands disabled until device reconnects."
                )
        except Exception:
            pass
    elif not health:
        # No device has ever connected
        pass

    # 2. Check latest reading
    latest = conn.execute("SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1;").fetchone()
    if latest:
        try:
            read_time = datetime.fromisoformat(latest["timestamp"])
            freshness = (now - read_time).total_seconds()
            
            # Check stale data
            if freshness > settings.device_timeout_sec:
                create_alert_if_not_active(
                    alert_key="SENSOR_DATA_STALE",
                    severity="WARNING",
                    title="Sensor Data Stale",
                    explanation=f"Latest sensor telemetry is {int(freshness)}s old. Stale readings are ignored for automated watering decisions.",
                    recommended_action="Verify physical sensor connections and ESP32 HTTP upload loop."
                )

            # Check low soil moisture
            if latest["soil_moisture"] < settings.dry_threshold and not latest["rain_detected"]:
                create_alert_if_not_active(
                    alert_key="LOW_SOIL_MOISTURE",
                    severity="WARNING",
                    title="Low Soil Moisture Detected",
                    explanation=f"Soil moisture is at {latest['soil_moisture']}%, below the dry threshold of {settings.dry_threshold}%.",
                    recommended_action="If in AUTO mode, the system will trigger irrigation shortly. If in MANUAL mode, review soil and consider manual irrigation."
                )

            # Check rain detection lockout
            if latest["rain_detected"] == 1:
                create_alert_if_not_active(
                    alert_key="RAIN_DETECTED",
                    severity="INFO",
                    title="Rain Detected — Watering Lockout Active",
                    explanation="Precipitation sensed on rain module. Automated irrigation is inhibited to conserve water and prevent soil oversaturation.",
                    recommended_action="No action required. Automatic watering will resume once the rain sensor plate dries."
                )

            # Check sensor sanity (FC-28 disconnected or DHT11 read failure)
            if latest["soil_raw_adc"] < 50 or latest["soil_raw_adc"] > 4090:
                create_alert_if_not_active(
                    alert_key="SENSOR_READING_INVALID",
                    severity="CRITICAL",
                    title="Soil Moisture Sensor Fault",
                    explanation=f"FC-28 raw ADC reading ({latest['soil_raw_adc']}) indicates an open circuit, disconnected probe, or short circuit.",
                    recommended_action="Inspect FC-28 wiring to GPIO 34, ensure probe is firmly inserted into soil, and clean probe corrosion."
                )

            # Check battery voltage if measured
            if latest["battery_voltage"] is not None and latest["battery_voltage"] > 0.0:
                if latest["battery_voltage"] < 3.3:
                    create_alert_if_not_active(
                        alert_key="LOW_BATTERY",
                        severity="CRITICAL",
                        title="Critical Low Battery Voltage",
                        explanation=f"18650 battery voltage dropped to {latest['battery_voltage']:.2f}V. Operating below 3.0V risks permanent cell damage.",
                        recommended_action="Disconnect cell immediately and charge using a TP4056 lithium charger with integrated protection."
                    )
        except Exception:
            pass

    # 3. Retrieve all unacknowledged alerts
    alerts_cursor = conn.execute("""
    SELECT id, timestamp, alert_key, severity, title, explanation, recommended_action, is_acknowledged
    FROM alerts
    ORDER BY is_acknowledged ASC, timestamp DESC
    LIMIT 30;
    """)
    alerts = [dict(row) for row in alerts_cursor.fetchall()]
    conn.close()
    return alerts

def acknowledge_alert(alert_id: int) -> bool:
    """Acknowledge an alert."""
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute("""
    UPDATE alerts SET is_acknowledged = 1, resolved_at = ?
    WHERE id = ?;
    """, (now_iso, alert_id))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success
