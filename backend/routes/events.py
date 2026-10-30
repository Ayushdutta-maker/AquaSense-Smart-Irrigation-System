from fastapi import APIRouter, Query
from typing import List, Optional
from backend.models.schemas import EventResponse
from backend.database.db import get_db_connection

router = APIRouter(prefix="/api/events", tags=["Irrigation History & Events"])

@router.get("", response_model=List[EventResponse])
def get_irrigation_events(
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    operating_mode: Optional[str] = Query(default=None, description="Filter by operating mode (AUTO/MANUAL)"),
    source: Optional[str] = Query(default=None, description="Filter by source"),
    from_date: Optional[str] = Query(default=None, description="ISO format starting timestamp"),
    to_date: Optional[str] = Query(default=None, description="ISO format ending timestamp"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Retrieve filterable audit log of pump activations, threshold triggers, rain lockouts, and safety stops.
    """
    conn = get_db_connection()
    conditions = []
    params = []

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if operating_mode:
        conditions.append("operating_mode = ?")
        params.append(operating_mode)
    if source:
        conditions.append("source = ?")
        params.append(source)
    if from_date:
        conditions.append("timestamp >= ?")
        params.append(from_date)
    if to_date:
        conditions.append("timestamp <= ?")
        params.append(to_date)

    where_str = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
    SELECT * FROM events
    {where_str}
    ORDER BY timestamp DESC
    LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [
        EventResponse(
            id=r["id"],
            timestamp=r["timestamp"],
            event_type=r["event_type"],
            soil_moisture=r["soil_moisture"],
            pump_state=r["pump_state"],
            operating_mode=r["operating_mode"],
            reason=r["reason"],
            duration_sec=r["duration_sec"] or 0.0,
            source=r["source"]
        )
        for r in rows
    ]
