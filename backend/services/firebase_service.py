"""
AquaSense Firebase Realtime Database & Cloud Service
Synchronizes telemetry, system status, hardware commands, alerts, and settings
to Firebase Realtime Database in real time.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import httpx

from backend.config import settings

logger = logging.getLogger("aquasense.firebase")

# Track sync statistics & health
_firebase_stats = {
    "status": "initialized",
    "last_sync_timestamp": None,
    "total_syncs": 0,
    "last_error": None,
    "latency_ms": None,
    "database_url": settings.FIREBASE_DATABASE_URL
}


def _get_base_url() -> str:
    url = settings.FIREBASE_DATABASE_URL.rstrip('/')
    return url


async def _put_json(path: str, data: Any, timeout: float = 4.0) -> bool:
    """Helper to PUT JSON data to Firebase Realtime Database path."""
    if not settings.FIREBASE_ENABLED or not settings.FIREBASE_DATABASE_URL:
        return False

    url = f"{_get_base_url()}/{path.lstrip('/')}.json"
    start_time = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.put(url, json=data)
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0

            if resp.is_success:
                _firebase_stats["status"] = "connected"
                _firebase_stats["last_sync_timestamp"] = datetime.now(timezone.utc).isoformat()
                _firebase_stats["total_syncs"] += 1
                _firebase_stats["latency_ms"] = round(elapsed, 1)
                _firebase_stats["last_error"] = None
                return True
            else:
                _firebase_stats["status"] = "error"
                _firebase_stats["last_error"] = f"HTTP {resp.status_code}: {resp.text[:120]}"
                logger.warning(f"[Firebase RTDB Error] {url} -> {resp.status_code}: {resp.text[:100]}")
                return False
    except Exception as e:
        _firebase_stats["status"] = "error"
        _firebase_stats["last_error"] = str(e)
        logger.warning(f"[Firebase Sync Failed] {url} -> {e}")
        return False


async def sync_reading_to_firebase(reading: Dict[str, Any]) -> bool:
    """Sync latest sensor reading to Firebase RTDB."""
    clean_reading = {
        "device_id": reading.get("device_id"),
        "soil_moisture": reading.get("soil_moisture"),
        "soil_raw_adc": reading.get("soil_raw_adc"),
        "temperature": reading.get("temperature"),
        "humidity": reading.get("humidity"),
        "light_raw": reading.get("light_raw"),
        "light_state": reading.get("light_state", "MODERATE"),
        "rain_detected": bool(reading.get("rain_detected")),
        "rain_raw_adc": reading.get("rain_raw_adc", 0),
        "pump_state": reading.get("pump_state", "OFF"),
        "operating_mode": reading.get("operating_mode", "AUTO"),
        "wifi_rssi": reading.get("wifi_rssi"),
        "battery_voltage": reading.get("battery_voltage"),
        "is_simulated": bool(reading.get("is_simulated")),
        "timestamp": reading.get("timestamp") or datetime.now(timezone.utc).isoformat()
    }
    # Update latest telemetry node
    success = await _put_json("aquasense/telemetry/latest", clean_reading)
    return success


async def sync_status_to_firebase(status_data: Dict[str, Any]) -> bool:
    """Sync system and device status to Firebase RTDB."""
    payload = {
        "online": bool(status_data.get("online")),
        "device_id": status_data.get("device_id", "esp32-aquasense-01"),
        "current_pump_state": status_data.get("current_pump_state", "OFF"),
        "current_mode": status_data.get("current_mode", "AUTO"),
        "active_alerts_count": status_data.get("active_alerts_count", 0),
        "rain_lockout_active": bool(status_data.get("rain_lockout_active")),
        "recommendation": status_data.get("recommendation", ""),
        "firmware_version": status_data.get("firmware_version", "v1.0.0"),
        "wifi_rssi": status_data.get("wifi_rssi"),
        "is_simulated": bool(status_data.get("is_simulated")),
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    return await _put_json("aquasense/status", payload)


async def sync_settings_to_firebase(settings_data: Dict[str, Any]) -> bool:
    """Sync agronomic thresholds and settings to Firebase RTDB."""
    payload = {
        "dry_threshold": float(settings_data.get("dry_threshold", 15.0)),
        "wet_threshold": float(settings_data.get("wet_threshold", 25.0)),
        "max_pump_runtime_sec": int(settings_data.get("max_pump_runtime_sec", 20)),
        "cooldown_duration_sec": int(settings_data.get("cooldown_duration_sec", 60)),
        "rain_lockout_enabled": bool(settings_data.get("rain_lockout_enabled", True)),
        "operating_mode": settings_data.get("operating_mode", "AUTO"),
        "soil_dry_raw": int(settings_data.get("soil_dry_raw", 3500)),
        "soil_wet_raw": int(settings_data.get("soil_wet_raw", 1400)),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    return await _put_json("aquasense/settings", payload)


async def sync_command_to_firebase(command_data: Dict[str, Any]) -> bool:
    """Sync dispatched hardware command to Firebase RTDB."""
    payload = {
        "id": command_data.get("id"),
        "command_type": command_data.get("command_type"),
        "target_state": command_data.get("target_state"),
        "duration_sec": command_data.get("duration_sec"),
        "mode": command_data.get("mode"),
        "status": command_data.get("status", "PENDING"),
        "created_at": command_data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "device_id": command_data.get("device_id", "esp32-aquasense-01")
    }
    # Update latest command pointer
    await _put_json("aquasense/commands/latest", payload)
    if command_data.get("id"):
        await _put_json(f"aquasense/commands/history/{command_data['id']}", payload)
    return True


async def sync_alerts_to_firebase(alerts_list: List[Dict[str, Any]]) -> bool:
    """Sync list of active system alerts to Firebase RTDB."""
    payload = {
        "alerts": alerts_list,
        "count": len(alerts_list),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    return await _put_json("aquasense/alerts", payload)


async def test_firebase_connection() -> Dict[str, Any]:
    """Test connection to Firebase Realtime Database and measure latency."""
    if not settings.FIREBASE_ENABLED:
        return {
            "enabled": False,
            "status": "disabled",
            "message": "Firebase is disabled in configuration."
        }

    url = f"{_get_base_url()}/aquasense/cloud_meta.json"
    start = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000.0
            is_ok = resp.is_success
            _firebase_stats["status"] = "connected" if is_ok else "error"
            _firebase_stats["latency_ms"] = round(latency, 1)
            return {
                "enabled": True,
                "status": "connected" if is_ok else "error",
                "http_status": resp.status_code,
                "database_url": settings.FIREBASE_DATABASE_URL,
                "project_id": settings.FIREBASE_PROJECT_ID,
                "latency_ms": round(latency, 1),
                "last_sync": _firebase_stats["last_sync_timestamp"],
                "total_syncs": _firebase_stats["total_syncs"],
                "last_error": _firebase_stats["last_error"]
            }
    except Exception as e:
        _firebase_stats["status"] = "unreachable"
        _firebase_stats["last_error"] = str(e)
        return {
            "enabled": True,
            "status": "unreachable",
            "database_url": settings.FIREBASE_DATABASE_URL,
            "project_id": settings.FIREBASE_PROJECT_ID,
            "error": str(e)
        }


def get_firebase_stats() -> Dict[str, Any]:
    """Return local sync health stats."""
    return {
        "enabled": settings.FIREBASE_ENABLED,
        "database_url": settings.FIREBASE_DATABASE_URL,
        "project_id": settings.FIREBASE_PROJECT_ID,
        **_firebase_stats
    }


def schedule_sync_task(coro):
    """Safely spawn a fire-and-forget task without crashing if loop is busy."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # Fallback if outside active event loop
        asyncio.run(coro)
