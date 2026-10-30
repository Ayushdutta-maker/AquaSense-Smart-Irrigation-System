from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from datetime import datetime, timezone

from backend.config import settings
from backend.services.firebase_service import (
    test_firebase_connection, get_firebase_stats,
    sync_reading_to_firebase, sync_status_to_firebase,
    sync_settings_to_firebase, sync_alerts_to_firebase
)
from backend.database.db import get_db_connection
from backend.services.irrigation_service import get_current_settings
from backend.services.alert_service import evaluate_system_alerts

router = APIRouter(prefix="/api/firebase", tags=["Firebase Cloud Sync"])


@router.get("/config", response_model=Dict[str, Any])
def get_firebase_frontend_config():
    """
    Returns public Firebase client configuration for web dashboard initialization.
    Includes Realtime Database URL, project ID, and API keys.
    """
    return {
        "enabled": settings.FIREBASE_ENABLED,
        "apiKey": settings.FIREBASE_API_KEY,
        "authDomain": settings.FIREBASE_AUTH_DOMAIN,
        "databaseURL": settings.FIREBASE_DATABASE_URL,
        "projectId": settings.FIREBASE_PROJECT_ID,
        "storageBucket": settings.FIREBASE_STORAGE_BUCKET,
        "messagingSenderId": settings.FIREBASE_MESSAGING_SENDER_ID,
        "appId": settings.FIREBASE_APP_ID,
        "measurementId": settings.FIREBASE_MEASUREMENT_ID,
        "consoleUrl": f"https://console.firebase.google.com/u/0/project/{settings.FIREBASE_PROJECT_ID}/database/{settings.FIREBASE_PROJECT_ID}-default-rtdb/data/~2F"
    }


@router.get("/status", response_model=Dict[str, Any])
async def get_firebase_status():
    """
    Live ping test to Firebase Realtime Database with measured latency in milliseconds.
    """
    conn_info = await test_firebase_connection()
    return conn_info


@router.post("/sync", response_model=Dict[str, Any])
async def force_full_sync():
    """
    Force a full snapshot sync of latest telemetry, system status, active alerts,
    and agronomic settings to Firebase Realtime Database.
    """
    conn = get_db_connection()
    latest_row = conn.execute("SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1;").fetchone()
    health_row = conn.execute("SELECT * FROM device_health ORDER BY last_heartbeat DESC LIMIT 1;").fetchone()
    conn.close()

    results = {}

    # 1. Sync Settings
    try:
        current_settings = get_current_settings()
        await sync_settings_to_firebase(current_settings.model_dump())
        results["settings"] = "synced"
    except Exception as e:
        results["settings"] = f"error: {str(e)}"

    # 2. Sync Latest Reading
    if latest_row:
        try:
            reading_dict = dict(latest_row)
            await sync_reading_to_firebase(reading_dict)
            results["reading"] = "synced"
        except Exception as e:
            results["reading"] = f"error: {str(e)}"
    else:
        results["reading"] = "no_data"

    # 3. Sync Status
    try:
        status_payload = {
            "online": bool(health_row is not None),
            "device_id": health_row["device_id"] if health_row else "esp32-aquasense-01",
            "current_pump_state": latest_row["pump_state"] if latest_row else "OFF",
            "current_mode": latest_row["operating_mode"] if latest_row else "AUTO",
            "firmware_version": health_row["firmware_version"] if health_row else "v1.0.0",
            "wifi_rssi": health_row["wifi_rssi"] if health_row else None,
            "is_simulated": bool(latest_row["is_simulated"]) if latest_row else False
        }
        await sync_status_to_firebase(status_payload)
        results["status"] = "synced"
    except Exception as e:
        results["status"] = f"error: {str(e)}"

    # 4. Sync Alerts
    try:
        active_alerts = evaluate_system_alerts()
        await sync_alerts_to_firebase(active_alerts)
        results["alerts"] = "synced"
    except Exception as e:
        results["alerts"] = f"error: {str(e)}"

    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database_url": settings.FIREBASE_DATABASE_URL,
        "sync_results": results
    }
