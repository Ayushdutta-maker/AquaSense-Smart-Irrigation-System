import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from backend.config import settings

def get_db_connection():
    """Create a connection with row factory enabled."""
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    """Initialize database tables and default configuration."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Readings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        device_id TEXT NOT NULL,
        soil_moisture REAL NOT NULL,
        soil_raw_adc INTEGER NOT NULL,
        temperature REAL NOT NULL,
        humidity REAL NOT NULL,
        light_raw INTEGER NOT NULL,
        light_state TEXT NOT NULL,
        rain_detected INTEGER NOT NULL,
        rain_raw_adc INTEGER NOT NULL,
        pump_state TEXT NOT NULL,
        operating_mode TEXT NOT NULL,
        wifi_rssi INTEGER DEFAULT NULL,
        battery_voltage REAL DEFAULT NULL,
        is_simulated INTEGER DEFAULT 0
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_readings_device ON readings(device_id);")

    # 2. Irrigation Settings Table (single-row persistent config)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        dry_threshold REAL NOT NULL,
        wet_threshold REAL NOT NULL,
        max_pump_runtime_sec INTEGER NOT NULL,
        cooldown_duration_sec INTEGER NOT NULL,
        rain_lockout_enabled INTEGER NOT NULL,
        default_mode TEXT NOT NULL,
        soil_dry_raw INTEGER NOT NULL,
        soil_wet_raw INTEGER NOT NULL,
        device_timeout_sec INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 3. Commands Queue Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS commands (
        id TEXT PRIMARY KEY,
        device_id TEXT NOT NULL,
        command_type TEXT NOT NULL,
        payload TEXT,
        status TEXT NOT NULL,
        source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        sent_at TEXT,
        acknowledged_at TEXT,
        error_message TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);")

    # 4. Irrigation and Safety Events Audit Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        soil_moisture REAL,
        pump_state TEXT NOT NULL,
        operating_mode TEXT NOT NULL,
        reason TEXT NOT NULL,
        duration_sec REAL DEFAULT 0.0,
        source TEXT NOT NULL
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);")

    # 5. Alerts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        alert_key TEXT NOT NULL,
        severity TEXT NOT NULL,
        title TEXT NOT NULL,
        explanation TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        is_acknowledged INTEGER DEFAULT 0,
        resolved_at TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ack ON alerts(is_acknowledged, timestamp DESC);")

    # 6. Device Health Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS device_health (
        device_id TEXT PRIMARY KEY,
        last_heartbeat TEXT NOT NULL,
        firmware_version TEXT,
        wifi_rssi INTEGER,
        free_heap INTEGER,
        uptime_seconds INTEGER,
        sensor_status TEXT,
        last_command_ack_id TEXT,
        battery_voltage REAL,
        is_simulated INTEGER DEFAULT 0
    );
    """)

    # Seed initial default settings if empty
    cursor.execute("SELECT COUNT(*) FROM settings WHERE id = 1;")
    if cursor.fetchone()[0] == 0:
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
        INSERT INTO settings (
            id, dry_threshold, wet_threshold, max_pump_runtime_sec,
            cooldown_duration_sec, rain_lockout_enabled, default_mode,
            soil_dry_raw, soil_wet_raw, device_timeout_sec, updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            settings.DEFAULT_DRY_THRESHOLD,
            settings.DEFAULT_WET_THRESHOLD,
            settings.DEFAULT_MAX_RUNTIME_SEC,
            settings.DEFAULT_COOLDOWN_SEC,
            1, # Rain lockout enabled by default
            'AUTO',
            settings.DEFAULT_SOIL_DRY_RAW,
            settings.DEFAULT_SOIL_WET_RAW,
            settings.DEVICE_TIMEOUT_SECONDS,
            now_iso
        ))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("AquaSense database initialized successfully.")
