from fastapi import APIRouter, Query, Body
from typing import Optional
from backend.services.simulator_service import simulator

router = APIRouter(prefix="/api/simulator", tags=["Testing Simulator"])

@router.get("/status")
def get_simulator_status():
    """Get status of the software testing telemetry simulator."""
    return {
        "is_active": simulator.is_active,
        "device_id": simulator.device_id,
        "simulated_soil_moisture": simulator.soil_moisture,
        "simulated_temperature": simulator.temperature,
        "simulated_humidity": simulator.humidity,
        "simulated_rain_detected": simulator.rain_detected,
        "simulated_pump_state": simulator.pump_state,
        "simulated_mode": simulator.operating_mode,
        "note": "Simulator is explicitly labeled for QA/testing when physical ESP32 is offline."
    }

@router.post("/toggle")
def toggle_simulator(active: bool = Query(...)):
    """Toggle the software test simulator active state."""
    simulator.set_active(active)
    # If activating, run an initial step right away
    if active:
        simulator.step()
    return {
        "status": "success",
        "is_active": simulator.is_active,
        "message": "Software Test Simulator activated" if active else "Simulator deactivated"
    }

@router.post("/step")
def step_simulator(
    force_rain: Optional[bool] = Query(default=None),
    force_dry: Optional[bool] = Query(default=None)
):
    """
    Advance the simulator by one evaluation cycle.
    Useful for test suites or manually simulating environmental triggers like rain or drought.
    """
    result = simulator.step(force_rain=force_rain, force_dry=force_dry)
    return {
        "status": "success",
        "step_result": result
    }
