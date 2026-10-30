from fastapi import APIRouter, HTTPException, Query, Header, Depends
from typing import List, Optional
from backend.models.schemas import CommandCreate, CommandResponse, CommandAck
from backend.services.command_service import (
    create_command, get_pending_commands_for_device, acknowledge_command
)
from backend.routes.readings import verify_api_key

router = APIRouter(prefix="/api/commands", tags=["Hardware Commands"])

@router.post("", response_model=dict)
def send_command(cmd: CommandCreate, device_id: str = Query(default="esp32-aquasense-01")):
    """
    Dispatch a hardware or mode command from the dashboard.
    Verifies device online status and safety rules before queueing.
    """
    try:
        created = create_command(cmd, device_id=device_id)

        # Sync command to Firebase RTDB
        try:
            from backend.services.firebase_service import schedule_sync_task, sync_command_to_firebase
            from backend.config import settings
            if settings.FIREBASE_ENABLED:
                schedule_sync_task(sync_command_to_firebase(created))
        except Exception:
            pass

        return {
            "status": "success",
            "message": f"Command {cmd.command_type} queued for delivery to {device_id}.",
            "command": created
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue command: {str(e)}")

@router.get("/pending", response_model=List[dict])
def poll_pending_commands(
    device_id: str = Query(default="esp32-aquasense-01"),
    authenticated: bool = Depends(verify_api_key)
):
    """
    ESP32 polling endpoint: retrieves pending commands and marks them as SENT.
    """
    return get_pending_commands_for_device(device_id)

@router.post("/ack", response_model=dict)
def acknowledge_device_command(ack: CommandAck, authenticated: bool = Depends(verify_api_key)):
    """
    ESP32 confirmation endpoint: confirms hardware relay action or reports fault.
    """
    success = acknowledge_command(
        command_id=ack.command_id,
        status=ack.status,
        error_message=ack.error_message,
        pump_state=ack.pump_state,
        operating_mode=ack.operating_mode
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Command ID {ack.command_id} not found.")
    return {"status": "success", "message": f"Command {ack.command_id} acknowledged."}
