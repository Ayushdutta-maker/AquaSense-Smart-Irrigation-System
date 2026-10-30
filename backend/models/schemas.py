from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator
from datetime import datetime

class SensorReadingCreate(BaseModel):
    device_id: str = Field(default="esp32-aquasense-01", description="Unique identifier for the ESP32 node")
    soil_raw_adc: int = Field(ge=0, le=4095, description="Raw 12-bit ADC reading from FC-28 probe (0-4095)")
    soil_moisture: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="Calibrated moisture percentage")
    temperature: float = Field(ge=-20.0, le=70.0, description="Ambient temperature in degrees Celsius from DHT11")
    humidity: float = Field(ge=0.0, le=100.0, description="Relative humidity percentage from DHT11")
    light_raw: int = Field(ge=0, le=4095, description="Raw ADC or light level from LDR sensor")
    rain_detected: bool = Field(description="True if moisture/rain is detected on the rain sensor plate")
    rain_raw_adc: Optional[int] = Field(default=0, ge=0, le=4095, description="Analog rain sensor level")
    pump_state: str = Field(default="OFF", pattern="^(ON|OFF)$", description="Physical relay/pump status")
    operating_mode: str = Field(default="AUTO", pattern="^(AUTO|MANUAL)$", description="Current operating mode")
    wifi_rssi: Optional[int] = Field(default=None, ge=-110, le=0, description="Wi-Fi signal strength in dBm")
    battery_voltage: Optional[float] = Field(default=None, ge=0.0, le=15.0, description="Measured battery voltage in Volts")
    firmware_version: Optional[str] = Field(default="v1.0.0-esp32", description="Firmware build string")
    uptime_seconds: Optional[int] = Field(default=0, ge=0, description="Node uptime in seconds")
    is_simulated: Optional[bool] = Field(default=False, description="Flag indicating simulated telemetry")

class ReadingResponse(BaseModel):
    id: int
    timestamp: str
    device_id: str
    soil_moisture: float
    soil_raw_adc: int
    temperature: float
    humidity: float
    light_raw: int
    light_state: str
    rain_detected: bool
    rain_raw_adc: int
    pump_state: str
    operating_mode: str
    wifi_rssi: Optional[int] = None
    battery_voltage: Optional[float] = None
    is_simulated: bool
    freshness_seconds: Optional[float] = None

class IrrigationSettings(BaseModel):
    dry_threshold: float = Field(
        default=15.0, ge=5.0, le=45.0,
        description="Soil moisture percentage below which automatic watering is triggered"
    )
    wet_threshold: float = Field(
        default=25.0, ge=15.0, le=80.0,
        description="Soil moisture percentage at or above which automatic watering stops (hysteresis)"
    )
    max_pump_runtime_sec: int = Field(
        default=20, ge=5, le=120,
        description="Hard cutoff time in seconds for continuous pump operation"
    )
    cooldown_duration_sec: int = Field(
        default=60, ge=10, le=1800,
        description="Enforced rest duration in seconds between watering cycles"
    )
    rain_lockout_enabled: bool = Field(
        default=True,
        description="Whether rain detection immediately inhibits watering"
    )
    default_mode: str = Field(
        default="AUTO", pattern="^(AUTO|MANUAL)$",
        description="Default operating mode on startup"
    )
    soil_dry_raw: int = Field(
        default=3500, ge=1500, le=4095,
        description="FC-28 ADC reading measured in dry air for calibration"
    )
    soil_wet_raw: int = Field(
        default=1400, ge=500, le=3000,
        description="FC-28 ADC reading measured in water for calibration"
    )
    device_timeout_sec: int = Field(
        default=45, ge=10, le=300,
        description="Inactivity window before marking ESP32 device offline"
    )

    @model_validator(mode="after")
    def validate_thresholds_and_calibration(self) -> "IrrigationSettings":
        if self.wet_threshold <= self.dry_threshold + 2.0:
            raise ValueError(
                f"Wet threshold ({self.wet_threshold}%) must be at least 2.0% higher than dry threshold ({self.dry_threshold}%) to ensure safe hysteresis and prevent relay chatter."
            )
        if self.soil_dry_raw <= self.soil_wet_raw + 200:
            raise ValueError(
                f"Soil dry calibration ADC ({self.soil_dry_raw}) must be greater than wet ADC ({self.soil_wet_raw}) by at least 200 counts."
            )
        return self

class CommandCreate(BaseModel):
    command_type: str = Field(
        pattern="^(PUMP_START|PUMP_STOP|SET_MODE|SET_SETTINGS)$",
        description="Type of command to dispatch"
    )
    target_state: Optional[str] = Field(default=None, pattern="^(ON|OFF)$")
    duration_sec: Optional[int] = Field(default=None, ge=1, le=120)
    mode: Optional[str] = Field(default=None, pattern="^(AUTO|MANUAL)$")
    source: str = Field(default="MANUAL_DASHBOARD")
    reason: Optional[str] = Field(default="User initiated action from dashboard")

class CommandResponse(BaseModel):
    id: str
    device_id: str
    command_type: str
    payload: Optional[str]
    status: str
    source: str
    created_at: str
    acknowledged_at: Optional[str] = None
    error_message: Optional[str] = None

class CommandAck(BaseModel):
    command_id: str
    status: str = Field(pattern="^(ACKNOWLEDGED|FAILED)$")
    error_message: Optional[str] = None
    pump_state: Optional[str] = Field(default=None, pattern="^(ON|OFF)$")
    operating_mode: Optional[str] = Field(default=None, pattern="^(AUTO|MANUAL)$")

class EventResponse(BaseModel):
    id: int
    timestamp: str
    event_type: str
    soil_moisture: Optional[float]
    pump_state: str
    operating_mode: str
    reason: str
    duration_sec: float
    source: str

class AlertResponse(BaseModel):
    id: int
    timestamp: str
    alert_key: str
    severity: str
    title: str
    explanation: str
    recommended_action: str
    is_acknowledged: bool
    resolved_at: Optional[str] = None

class SystemStatus(BaseModel):
    online: bool
    device_id: Optional[str] = None
    last_heartbeat: Optional[str] = None
    seconds_since_last_seen: Optional[float] = None
    current_pump_state: str = "OFF"
    current_mode: str = "AUTO"
    active_alerts_count: int = 0
    rain_lockout_active: bool = False
    recommendation: str = "System healthy."
    firmware_version: Optional[str] = None
    wifi_rssi: Optional[int] = None
    is_simulated: bool = False
    hardware_attached: bool = False
