from fastapi import APIRouter, HTTPException, Query, Header, Depends
from typing import List, Optional
from datetime import datetime, timezone
from backend.models.schemas import SensorReadingCreate, ReadingResponse
from backend.database.db import get_db_connection
from backend.services.irrigation_service import (
    calculate_soil_moisture, classify_soil_status, get_current_settings, log_event
)
from backend.services.alert_service import evaluate_system_alerts
from backend.services.firebase_service import (
    schedule_sync_task, sync_reading_to_firebase, sync_status_to_firebase
)
from backend.services.command_service import get_pending_commands_for_device
from backend.config import settings

router = APIRouter(prefix="/api/readings", tags=["Readings"])

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Validate API key header if configured in production."""
    if settings.API_KEY and settings.API_KEY != "aquasense_secret_key_2026":
        if x_api_key != settings.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")
    return True

@router.post("", response_model=dict)
def submit_reading(reading: SensorReadingCreate, authenticated: bool = Depends(verify_api_key)):
    """
    Endpoint for ESP32 firmware to post telemetry.
    Saves reading to SQLite, computes calibrated moisture, and records device heartbeat.
    """
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    current_settings = get_current_settings()

    # Calculate calibrated moisture if not explicitly supplied or as verification
    if reading.soil_moisture is None:
        calibrated_moisture = calculate_soil_moisture(
            reading.soil_raw_adc,
            current_settings.soil_dry_raw,
            current_settings.soil_wet_raw
        )
    else:
        calibrated_moisture = round(reading.soil_moisture, 1)

    # Classify light state
    light_state = "BRIGHT" if reading.light_raw < 1500 else ("MODERATE" if reading.light_raw < 2800 else "DARK")

    # Insert into readings
    cursor = conn.execute("""
    INSERT INTO readings (
        timestamp, device_id, soil_moisture, soil_raw_adc,
        temperature, humidity, light_raw, light_state,
        rain_detected, rain_raw_adc, pump_state, operating_mode,
        wifi_rssi, battery_voltage, is_simulated
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        now_iso, reading.device_id, calibrated_moisture, reading.soil_raw_adc,
        reading.temperature, reading.humidity, reading.light_raw, light_state,
        1 if reading.rain_detected else 0, reading.rain_raw_adc or 0,
        reading.pump_state, reading.operating_mode, reading.wifi_rssi,
        reading.battery_voltage, 1 if reading.is_simulated else 0
    ))
    reading_id = cursor.lastrowid

    # Update or insert device health heartbeat
    sensor_map = {
        "soil": "OK" if 100 <= reading.soil_raw_adc <= 4000 else "FAULT",
        "dht11": "OK" if 0.0 <= reading.humidity <= 100.0 else "FAULT",
        "ldr": "OK",
        "rain": "OK",
        "relay": "OK"
    }
    import json
    sensor_json = json.dumps(sensor_map)

    conn.execute("""
    INSERT INTO device_health (
        device_id, last_heartbeat, firmware_version, wifi_rssi,
        uptime_seconds, sensor_status, battery_voltage, is_simulated
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(device_id) DO UPDATE SET
        last_heartbeat = excluded.last_heartbeat,
        firmware_version = COALESCE(excluded.firmware_version, device_health.firmware_version),
        wifi_rssi = excluded.wifi_rssi,
        uptime_seconds = excluded.uptime_seconds,
        sensor_status = excluded.sensor_status,
        battery_voltage = excluded.battery_voltage,
        is_simulated = excluded.is_simulated;
    """, (
        reading.device_id, now_iso, reading.firmware_version,
        reading.wifi_rssi, reading.uptime_seconds or 0,
        sensor_json, reading.battery_voltage, 1 if reading.is_simulated else 0
    ))

    conn.commit()
    conn.close()

    # Trigger alert evaluation in background
    evaluate_system_alerts()

    # Synchronize telemetry to Firebase Realtime Database
    if settings.FIREBASE_ENABLED:
        reading_dict = {
            "device_id": reading.device_id,
            "soil_moisture": calibrated_moisture,
            "soil_raw_adc": reading.soil_raw_adc,
            "temperature": reading.temperature,
            "humidity": reading.humidity,
            "light_raw": reading.light_raw,
            "light_state": light_state,
            "rain_detected": reading.rain_detected,
            "rain_raw_adc": reading.rain_raw_adc,
            "pump_state": reading.pump_state,
            "operating_mode": reading.operating_mode,
            "wifi_rssi": reading.wifi_rssi,
            "battery_voltage": reading.battery_voltage,
            "is_simulated": reading.is_simulated,
            "timestamp": now_iso
        }
        schedule_sync_task(sync_reading_to_firebase(reading_dict))
        schedule_sync_task(sync_status_to_firebase({
            "online": True,
            "device_id": reading.device_id,
            "seconds_since_last_seen": 0.0,
            "current_pump_state": reading.pump_state,
            "current_mode": reading.operating_mode,
            "is_simulated": reading.is_simulated,
            "firmware_version": reading.firmware_version,
            "wifi_rssi": reading.wifi_rssi,
            "recommendation": "ESP32 is online and transmitting."
        }))

    # Fetch any pending commands for this device so it can execute them immediately
    pending_commands = get_pending_commands_for_device(reading.device_id)

    return {
        "status": "success",
        "reading_id": reading_id,
        "calibrated_moisture": calibrated_moisture,
        "recorded_at": now_iso,
        "commands": pending_commands
    }

@router.get("/latest", response_model=Optional[ReadingResponse])
def get_latest_reading():
    """
    Retrieve the most recent telemetry entry.
    Returns None / null if no readings have been recorded yet.
    Includes reading freshness in seconds.
    """
    conn = get_db_connection()
    row = conn.execute("""
    SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1;
    """).fetchone()
    conn.close()

    if not row:
        return None

    now = datetime.now(timezone.utc)
    freshness = None
    try:
        read_dt = datetime.fromisoformat(row["timestamp"])
        freshness = round((now - read_dt).total_seconds(), 1)
    except Exception:
        pass

    return ReadingResponse(
        id=row["id"],
        timestamp=row["timestamp"],
        device_id=row["device_id"],
        soil_moisture=row["soil_moisture"],
        soil_raw_adc=row["soil_raw_adc"],
        temperature=row["temperature"],
        humidity=row["humidity"],
        light_raw=row["light_raw"],
        light_state=row["light_state"],
        rain_detected=bool(row["rain_detected"]),
        rain_raw_adc=row["rain_raw_adc"],
        pump_state=row["pump_state"],
        operating_mode=row["operating_mode"],
        wifi_rssi=row["wifi_rssi"],
        battery_voltage=row["battery_voltage"],
        is_simulated=bool(row["is_simulated"]),
        freshness_seconds=freshness
    )

@router.get("/history", response_model=List[ReadingResponse])
def get_reading_history(
    limit: int = Query(default=60, ge=1, le=1000),
    timeframe: str = Query(default="24h", pattern="^(1h|24h|7d|30d|all)$")
):
    """
    Retrieve chronological telemetry history for Chart.js analytics.
    Timeframe filtering: 1h, 24h, 7d, 30d, all.
    """
    conn = get_db_connection()
    
    where_clause = ""
    params = []
    
    now = datetime.now(timezone.utc)
    if timeframe == "1h":
        cutoff = (now - datetime.timedelta(hours=1)).isoformat() if hasattr(datetime, "timedelta") else None
    
    # Use SQLite datetime functions
    if timeframe == "1h":
        where_clause = "WHERE timestamp >= datetime('now', '-1 hour')"
    elif timeframe == "24h":
        where_clause = "WHERE timestamp >= datetime('now', '-1 day')"
    elif timeframe == "7d":
        where_clause = "WHERE timestamp >= datetime('now', '-7 days')"
    elif timeframe == "30d":
        where_clause = "WHERE timestamp >= datetime('now', '-30 days')"

    query = f"""
    SELECT * FROM readings
    {where_clause}
    ORDER BY timestamp ASC
    LIMIT ?;
    """
    
    rows = conn.execute(query, (limit,)).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append(ReadingResponse(
            id=r["id"],
            timestamp=r["timestamp"],
            device_id=r["device_id"],
            soil_moisture=r["soil_moisture"],
            soil_raw_adc=r["soil_raw_adc"],
            temperature=r["temperature"],
            humidity=r["humidity"],
            light_raw=r["light_raw"],
            light_state=r["light_state"],
            rain_detected=bool(r["rain_detected"]),
            rain_raw_adc=r["rain_raw_adc"],
            pump_state=r["pump_state"],
            operating_mode=r["operating_mode"],
            wifi_rssi=r["wifi_rssi"],
            battery_voltage=r["battery_voltage"],
            is_simulated=bool(r["is_simulated"])
        ))
    return result
