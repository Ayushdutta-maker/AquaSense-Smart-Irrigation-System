import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database.db import init_db
from backend.routes import (
    readings, status, settings as settings_route,
    commands, events, alerts, export, simulator, firebase_sync
)
from backend.services.simulator_service import simulator as dev_simulator

import os

# Background simulation runner
sim_task: asyncio.Task = None

async def simulator_background_loop():
    """Background task that runs simulation steps if enabled."""
    try:
        while True:
            if dev_simulator.is_active:
                try:
                    dev_simulator.step()
                except Exception as e:
                    print(f"[Simulator Error] {e}")
            await asyncio.sleep(3.0)
    except asyncio.CancelledError:
        pass

async def device_watchdog_loop():
    """
    Active watchdog task that harmonizes local SQLite and Firebase cloud state.
    Checks whether the physical ESP32 has reported telemetry (either locally or via Firebase Cloud).
    Prevents status flapping by establishing a single synchronized online/offline truth.
    """
    from backend.database.db import get_db_connection
    from backend.services.irrigation_service import get_current_settings
    from backend.services.firebase_service import sync_status_to_firebase
    from datetime import datetime, timezone
    import httpx

    last_synced_state = None

    try:
        while True:
            await asyncio.sleep(3.0)
            try:
                cur_settings = get_current_settings()
                now = datetime.now(timezone.utc)
                conn = get_db_connection()

                # 1. Check local SQLite health
                health = conn.execute(
                    "SELECT * FROM device_health ORDER BY last_heartbeat DESC LIMIT 1;"
                ).fetchone()
                latest = conn.execute(
                    "SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1;"
                ).fetchone()

                local_online = False
                local_elapsed = 9999.0
                if health and health["last_heartbeat"]:
                    try:
                        hb_dt = datetime.fromisoformat(health["last_heartbeat"])
                        local_elapsed = (now - hb_dt).total_seconds()
                        local_online = (local_elapsed <= cur_settings.device_timeout_sec)
                    except Exception:
                        pass

                # 2. Check Firebase Cloud telemetry if enabled
                cloud_online = False
                cloud_data = None
                if settings.FIREBASE_ENABLED and settings.FIREBASE_DATABASE_URL:
                    try:
                        url = f"{settings.FIREBASE_DATABASE_URL.rstrip('/')}/aquasense/telemetry/latest.json"
                        async with httpx.AsyncClient(timeout=2.0) as client:
                            resp = await client.get(url)
                            if resp.is_success and resp.text != "null":
                                cloud_data = resp.json()
                                ts = cloud_data.get("timestamp")
                                if ts:
                                    cloud_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                    cloud_age = (now - cloud_dt).total_seconds()
                                    if cloud_age <= cur_settings.device_timeout_sec:
                                        cloud_online = True
                                        # Update SQLite with real cloud heartbeat so local endpoints agree!
                                        conn.execute("""
                                        INSERT INTO device_health (
                                            device_id, last_heartbeat, firmware_version, wifi_rssi,
                                            uptime_seconds, sensor_status, battery_voltage, is_simulated
                                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                        ON CONFLICT(device_id) DO UPDATE SET
                                            last_heartbeat = excluded.last_heartbeat,
                                            firmware_version = COALESCE(excluded.firmware_version, device_health.firmware_version),
                                            wifi_rssi = excluded.wifi_rssi,
                                            is_simulated = excluded.is_simulated;
                                        """, (
                                            cloud_data.get("device_id", "esp32-aquasense-01"),
                                            now.isoformat(),
                                            cloud_data.get("firmware_version", "v1.0.0-esp32"),
                                            cloud_data.get("wifi_rssi", -60),
                                            cloud_data.get("uptime_seconds", 0),
                                            '{"soil":"OK","dht11":"OK","rain":"OK"}',
                                            cloud_data.get("battery_voltage"),
                                            0
                                        ))
                                        conn.commit()
                    except Exception as e:
                        pass

                conn.close()

                # Device is online if either local HTTP or Firebase Cloud received telemetry
                effective_online = (local_online or cloud_online)

                # Only update Firebase when a genuine state change occurs
                if effective_online != last_synced_state:
                    last_synced_state = effective_online
                    dev_id = (cloud_data.get("device_id") if cloud_data else None) or (health["device_id"] if health else "esp32-aquasense-01")
                    payload = {
                        "online": effective_online,
                        "device_id": dev_id,
                        "seconds_since_last_seen": 0.0 if effective_online else round(local_elapsed, 1),
                        "current_pump_state": latest["pump_state"] if latest else "OFF",
                        "current_mode": latest["operating_mode"] if latest else "AUTO",
                        "is_simulated": False if cloud_online else bool(health["is_simulated"] if health else False),
                        "firmware_version": "v1.0.0-esp32",
                        "wifi_rssi": cloud_data.get("wifi_rssi") if cloud_data else (health["wifi_rssi"] if health else None),
                        "recommendation": (
                            "ESP32 is online and transmitting telemetry."
                            if effective_online
                            else "ESP32 is offline. Check hardware power and Wi-Fi."
                        )
                    }
                    await sync_status_to_firebase(payload)
            except Exception as e:
                print(f"[Watchdog Error] {e}")
    except asyncio.CancelledError:
        pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure SQLite database schema is initialized
    init_db()
    sim_task = None
    watchdog_task = None
    if os.getenv("TESTING") != "1":
        sim_task = asyncio.create_task(simulator_background_loop())
        watchdog_task = asyncio.create_task(device_watchdog_loop())
    try:
        yield
    finally:
        for t in (sim_task, watchdog_task):
            if t:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AquaSense Smart Irrigation System IoT Backend and Dashboard API",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(readings.router)
app.include_router(status.router)
app.include_router(settings_route.router)
app.include_router(commands.router)
app.include_router(events.router)
app.include_router(alerts.router)
app.include_router(export.router)
app.include_router(simulator.router)
app.include_router(firebase_sync.router)

# Mount static frontend directory
STATIC_DIR = Path(__file__).resolve().parent / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
