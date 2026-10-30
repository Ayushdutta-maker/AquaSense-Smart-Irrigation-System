import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from backend.database.db import get_db_connection
from backend.models.schemas import CommandCreate, CommandResponse
from backend.services.irrigation_service import log_event, get_current_settings

def create_command(cmd: CommandCreate, device_id: str = "esp32-aquasense-01") -> Dict[str, Any]:
    """Create and queue a control command for the ESP32."""
    conn = get_db_connection()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Check device online status
    health = conn.execute("SELECT * FROM device_health WHERE device_id = ?;", (device_id,)).fetchone()
    settings = get_current_settings()
    
    is_online = False
    if health and health["last_heartbeat"]:
        try:
            last_dt = datetime.fromisoformat(health["last_heartbeat"])
            if (now - last_dt).total_seconds() <= settings.device_timeout_sec:
                is_online = True
        except Exception:
            is_online = False

    # Check rain lockout if PUMP_START requested
    if cmd.command_type == "PUMP_START" and settings.rain_lockout_enabled:
        latest = conn.execute("SELECT rain_detected FROM readings WHERE device_id = ? ORDER BY id DESC LIMIT 1;", (device_id,)).fetchone()
        if latest and latest["rain_detected"] == 1:
            conn.close()
            raise ValueError(
                "Cannot start pump: Rain is currently detected and Rain Lockout is enabled. "
                "Disable rain lockout in Settings if you must override natural rainfall."
            )

    command_id = str(uuid.uuid4())
    payload_dict = {
        "command_type": cmd.command_type,
        "target_state": cmd.target_state,
        "duration_sec": cmd.duration_sec,
        "mode": cmd.mode,
        "reason": cmd.reason,
        "device_was_online": is_online
    }
    payload_json = json.dumps(payload_dict)

    # If any previous pending command of same type exists, cancel it (deduplication)
    conn.execute("""
    UPDATE commands SET status = 'SUPERSEDED', error_message = 'Superseded by newer command'
    WHERE device_id = ? AND status = 'PENDING' AND command_type = ?;
    """, (device_id, cmd.command_type))

    # If STOP command, supersede any pending PUMP_START
    if cmd.command_type == "PUMP_STOP":
        conn.execute("""
        UPDATE commands SET status = 'SUPERSEDED', error_message = 'Cancelled by emergency PUMP_STOP'
        WHERE device_id = ? AND status = 'PENDING' AND command_type = 'PUMP_START';
        """, (device_id,))

    conn.execute("""
    INSERT INTO commands (
        id, device_id, command_type, payload, status, source, created_at
    ) VALUES (?, ?, ?, ?, 'PENDING', ?, ?);
    """, (command_id, device_id, cmd.command_type, payload_json, cmd.source, now_iso))

    # Log action to audit events using same connection transaction
    log_event(
        event_type=cmd.command_type,
        pump_state=cmd.target_state or "UNCHANGED",
        operating_mode=cmd.mode or "CURRENT",
        reason=f"Queued {cmd.command_type}: {cmd.reason or 'User action'}",
        source=cmd.source,
        conn=conn
    )

    conn.commit()
    conn.close()

    return {
        "id": command_id,
        "device_id": device_id,
        "command_type": cmd.command_type,
        "payload": payload_json,
        "status": "PENDING",
        "source": cmd.source,
        "created_at": now_iso
    }

def get_pending_commands_for_device(device_id: str) -> List[Dict[str, Any]]:
    """Called by the ESP32 node when polling for authorized commands."""
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Mark old pending commands as EXPIRED if older than 90 seconds
    expire_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    conn.execute("""
    UPDATE commands SET status = 'EXPIRED', error_message = 'Delivery timeout: ESP32 did not pick up command within 90s'
    WHERE status = 'PENDING' AND created_at < ?;
    """, (expire_cutoff,))

    cursor = conn.execute("""
    SELECT * FROM commands
    WHERE device_id = ? AND status = 'PENDING'
    ORDER BY created_at ASC;
    """, (device_id,))
    rows = cursor.fetchall()
    
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "command_type": r["command_type"],
            "payload": json.loads(r["payload"]) if r["payload"] else {},
            "created_at": r["created_at"]
        })
        # Mark as SENT
        conn.execute("UPDATE commands SET status = 'SENT', sent_at = ? WHERE id = ?;", (now_iso, r["id"]))
        
    conn.commit()
    conn.close()
    return result

def acknowledge_command(command_id: str, status: str, error_message: Optional[str] = None,
                        pump_state: Optional[str] = None, operating_mode: Optional[str] = None) -> bool:
    """Record receipt and hardware execution confirmation from the ESP32."""
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    cmd = conn.execute("SELECT * FROM commands WHERE id = ?;", (command_id,)).fetchone()
    if not cmd:
        conn.close()
        return False
        
    conn.execute("""
    UPDATE commands 
    SET status = ?, acknowledged_at = ?, error_message = ?
    WHERE id = ?;
    """, (status, now_iso, error_message, command_id))
    
    # Update device_health last_command_ack_id
    conn.execute("""
    UPDATE device_health
    SET last_command_ack_id = ?
    WHERE device_id = ?;
    """, (command_id, cmd["device_id"]))
    
    # Log acknowledgment
    log_event(
        event_type="COMMAND_ACK",
        pump_state=pump_state or "UNKNOWN",
        operating_mode=operating_mode or "UNKNOWN",
        reason=f"ESP32 acknowledged {cmd['command_type']} as {status}. {error_message or ''}",
        source="ESP32_FIRMWARE",
        conn=conn
    )
    
    conn.commit()
    conn.close()
    return True
