from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from backend.models.schemas import IrrigationSettings
from backend.database.db import get_db_connection
from backend.services.irrigation_service import get_current_settings, log_event
from backend.services.command_service import create_command
from backend.models.schemas import CommandCreate

router = APIRouter(prefix="/api/settings", tags=["Settings"])

@router.get("", response_model=IrrigationSettings)
def get_settings():
    """Retrieve current irrigation thresholds, safety timeouts, and sensor calibration."""
    return get_current_settings()

@router.put("", response_model=IrrigationSettings)
def update_settings(new_settings: IrrigationSettings):
    """
    Update irrigation thresholds and calibration settings.
    Persists configuration to SQLite and queues an update command for the ESP32.
    """
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()

    conn.execute("""
    UPDATE settings SET
        dry_threshold = ?,
        wet_threshold = ?,
        max_pump_runtime_sec = ?,
        cooldown_duration_sec = ?,
        rain_lockout_enabled = ?,
        default_mode = ?,
        soil_dry_raw = ?,
        soil_wet_raw = ?,
        device_timeout_sec = ?,
        updated_at = ?
    WHERE id = 1;
    """, (
        new_settings.dry_threshold,
        new_settings.wet_threshold,
        new_settings.max_pump_runtime_sec,
        new_settings.cooldown_duration_sec,
        1 if new_settings.rain_lockout_enabled else 0,
        new_settings.default_mode,
        new_settings.soil_dry_raw,
        new_settings.soil_wet_raw,
        new_settings.device_timeout_sec,
        now_iso
    ))
    conn.commit()
    conn.close()

    # Log audit event
    log_event(
        event_type="SETTINGS_UPDATE",
        pump_state="UNCHANGED",
        operating_mode=new_settings.default_mode,
        reason=(
            f"Updated settings: Dry={new_settings.dry_threshold}%, Wet={new_settings.wet_threshold}%, "
            f"MaxRun={new_settings.max_pump_runtime_sec}s, Cooldown={new_settings.cooldown_duration_sec}s, "
            f"RainLockout={new_settings.rain_lockout_enabled}, Calib=[{new_settings.soil_dry_raw}, {new_settings.soil_wet_raw}]"
        ),
        source="DASHBOARD_SETTINGS"
    )

    # Sync updated settings to Firebase Realtime Database
    try:
        from backend.services.firebase_service import schedule_sync_task, sync_settings_to_firebase
        from backend.config import settings
        if settings.FIREBASE_ENABLED:
            schedule_sync_task(sync_settings_to_firebase(new_settings.model_dump()))
    except Exception:
        pass

    return new_settings
