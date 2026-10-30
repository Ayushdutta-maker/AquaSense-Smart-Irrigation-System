import csv
import io
from fastapi import APIRouter, Query, Response
from backend.database.db import get_db_connection

router = APIRouter(prefix="/api/export", tags=["Export"])

@router.get("/csv")
def export_csv(
    data_type: str = Query(default="readings", pattern="^(readings|events)$"),
    limit: int = Query(default=1000, ge=1, le=5000)
):
    """
    Export telemetry readings or irrigation events to downloadable CSV format.
    """
    conn = get_db_connection()
    output = io.StringIO()
    writer = csv.writer(output)

    if data_type == "readings":
        writer.writerow([
            "ID", "Timestamp (UTC)", "Device ID", "Soil Moisture (%)", "Soil Raw ADC",
            "Temperature (C)", "Humidity (%)", "Light Raw ADC", "Light State",
            "Rain Detected", "Rain Raw ADC", "Pump State", "Operating Mode",
            "WiFi RSSI (dBm)", "Battery Voltage (V)", "Is Simulated"
        ])
        rows = conn.execute("""
        SELECT * FROM readings ORDER BY timestamp DESC LIMIT ?;
        """, (limit,)).fetchall()
        for r in rows:
            writer.writerow([
                r["id"], r["timestamp"], r["device_id"], r["soil_moisture"], r["soil_raw_adc"],
                r["temperature"], r["humidity"], r["light_raw"], r["light_state"],
                bool(r["rain_detected"]), r["rain_raw_adc"], r["pump_state"], r["operating_mode"],
                r["wifi_rssi"], r["battery_voltage"], bool(r["is_simulated"])
            ])
        filename = f"aquasense_readings_{limit}.csv"
    else:
        writer.writerow([
            "ID", "Timestamp (UTC)", "Event Type", "Soil Moisture (%)",
            "Pump State", "Operating Mode", "Reason", "Duration (sec)", "Source"
        ])
        rows = conn.execute("""
        SELECT * FROM events ORDER BY timestamp DESC LIMIT ?;
        """, (limit,)).fetchall()
        for r in rows:
            writer.writerow([
                r["id"], r["timestamp"], r["event_type"], r["soil_moisture"],
                r["pump_state"], r["operating_mode"], r["reason"], r["duration_sec"], r["source"]
            ])
        filename = f"aquasense_events_{limit}.csv"

    conn.close()

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
