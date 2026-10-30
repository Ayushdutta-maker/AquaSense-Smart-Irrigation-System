from fastapi import APIRouter, HTTPException, Path
from typing import List
from backend.models.schemas import AlertResponse
from backend.services.alert_service import evaluate_system_alerts, acknowledge_alert

router = APIRouter(prefix="/api/alerts", tags=["Alerts & Notifications"])

@router.get("", response_model=List[AlertResponse])
def get_alerts():
    """
    Retrieve active and recent alerts evaluated against real-time sensor limits and connection heartbeats.
    """
    alerts = evaluate_system_alerts()
    return alerts

@router.post("/{alert_id}/ack", response_model=dict)
def ack_alert(alert_id: int = Path(..., ge=1)):
    """Acknowledge and mark an alert as reviewed."""
    success = acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert ID {alert_id} not found.")
    return {"status": "success", "message": f"Alert {alert_id} acknowledged."}
