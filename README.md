# AquaSense — Smart Irrigation System

**Smart Irrigation. Smarter Growing.**

AquaSense is an IoT-based precision agriculture and smart irrigation monitoring platform powered by an **ESP32 WROOM** microcontroller, responsive **FastAPI** backend, persistent **SQLite** database, and a professional web dashboard.

---

## 1. System Features

- **Autonomous Local Irrigation Control**:
  - Automatically activates pump when calibrated soil moisture drops below **15.0%**.
  - Automatically stops pump when soil moisture reaches **25.0%** (hysteresis prevents rapid relay chatter).
  - Rain detection lockout halts watering immediately and inhibits new cycles.
  - Hard local watchdog timer stops physical pump after **20 seconds** continuous run-time on-chip.
  - Enforces a **60-second cooldown** between watering cycles.
  - Safe boot: relay defaults to **OFF** immediately upon startup.
- **Precision Sensor Telemetry**:
  - FC-28 Soil Moisture sensor with configurable two-point ADC calibration.
  - DHT11 ambient temperature & relative humidity sensor.
  - LDR photoresistor light level sensor.
  - Rain detection module.
  - 16×2 LCD display with PCF8574 I²C adapter.
- **Hardware-Enforced Safety**:
  - Independent pump run-time watchdog executed on ESP32 firmware without relying on browser or Wi-Fi.
  - Safe relay boot state (OFF).
  - Explicit documentation on 18650 Li-ion battery protection and inductive motor spike suppression.
- **Real-Time Responsive Web Dashboard**:
  - 9 Dedicated navigation views: *Overview*, *Live Monitoring*, *Irrigation Control*, *Sensor Analytics*, *Irrigation History*, *Alerts & Notifications*, *Device Health*, *Settings*, and *About AquaSense*.
  - Forest Green & Aqua Teal professional color palette.
  - Light mode & Dark Forest Green mode (saved in `localStorage`).
  - Strict honest offline mode: never fabricates live telemetry or shows green online pills without recent valid data.
  - Interactive Chart.js charts for soil moisture, environmental metrics, light, and pump timeline.
  - Searchable and filterable irrigation event audit log with CSV export.
  - Confirmation dialog modal for manual pump activation.
  - Explicitly labeled software testing simulator for end-to-end evaluation without physical hardware.
- **Firebase Cloud Realtime Database & Analytics**:
  - Direct bi-directional synchronization with **Firebase Realtime Database** (`asia-southeast1`).
  - Real-time live telemetry stream updates gauges instantly via WebSocket / Realtime event listener without polling delay.
  - **Google Firebase Analytics** tracking for irrigation commands, mode changes, and dashboard interactions.
  - Dedicated cloud sync panel in Settings view with one-click snapshot sync and console launcher.

---

## 2. Hardware Wiring & Pinout Mapping

| Peripheral | ESP32 GPIO | Operating Voltage | Connection Type |
| :--- | :--- | :--- | :--- |
| **FC-28 Soil Moisture Probe** | GPIO 34 (ADC1_CH6) | 3.3V | Analog Input (ADC1) |
| **DHT11 Temp/Humidity** | GPIO 4 | 3.3V | Digital I/O (4.7kΩ pullup) |
| **LDR Light Sensor** | GPIO 35 (ADC1_CH7) | 3.3V | Analog Input (ADC1) |
| **Rain Detection Plate** | GPIO 32 (ADC1_CH4) | 3.3V | Analog Input (ADC1) |
| **5V Relay Module (Pump)** | GPIO 26 | 3.3V Logic / 5V Coil | Digital Output (Defaults OFF) |
| **LCD1602 SDA** | GPIO 21 | 3.3V Logic / 5V VCC | I²C Data (Level shifted) |
| **LCD1602 SCL** | GPIO 22 | 3.3V Logic / 5V VCC | I²C Clock (Level shifted) |

*Detailed wiring and power diagrams are available in [docs/ELECTRICAL_AND_SAFETY.md](file:///d:/OneDrive/Desktop/IoT_Project/docs/ELECTRICAL_AND_SAFETY.md).*

---

## 3. Quick Start Guide for Windows

### Prerequisites
- Python 3.10+ installed and added to `PATH`.
- Arduino IDE (optional, for flashing ESP32).

### Step 1: Install Dependencies
Open PowerShell or Command Prompt in the project folder and run:
```powershell
pip install -r requirements.txt
```

### Step 2: Run Automated Tests
Verify all API endpoints, threshold logic, rain lockout, and safety limits:
```powershell
python tests/run_tests.py
```
*(Or double-click `run_tests.bat`)*

### Step 3: Launch AquaSense Server
Launch the FastAPI server and web dashboard:
```powershell
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```
*(Or double-click `run_server.bat`)*

### Step 4: Open Web Dashboard
Open your browser and navigate to:
**http://localhost:8000**

Interactive API Swagger documentation is available at:
**http://localhost:8000/docs**

---

## 4. Testing Without Physical Hardware

If your ESP32 is not yet flashed or connected, the dashboard honestly displays:
`ESP32 Offline` and `--` for live sensor readings.

To test the entire application software stack without hardware:
1. Navigate to **About AquaSense** or open the **Settings** view.
2. Click **"Software Test Simulator: Activate"**.
3. A clear banner will appear: `TEST SIMULATION ACTIVE — SIMULATED TELEMETRY`.
4. Click **"Simulate Drought (<15%)"** to watch the automated irrigation engine trigger a watering cycle.
5. Click **"Simulate Rain Event"** to observe rain lockout stopping the pump and preventing new watering.

---

## 5. ESP32 Firmware Setup

1. Open `firmware/aquasense_esp32.ino` in the Arduino IDE.
2. Install the required libraries via Arduino Library Manager:
   - `DHT sensor library` by Adafruit
   - `LiquidCrystal_I2C` by Frank de Brabander
   - `ArduinoJson` (v6 or v7) by Benoit Blanchon
3. Update your Wi-Fi credentials in lines 57-58:
   ```cpp
   const char* WIFI_SSID     = "YOUR_WIFI_NAME";
   const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
   ```
4. Set the `BACKEND_BASE_URL` to your computer's local IP address:
   ```cpp
   const char* BACKEND_BASE_URL = "http://192.168.1.100:8000";
   ```
5. Select Board: **ESP32 Dev Module** and upload.

---

## 6. Electrical Safety & Battery Cautions

1. **18650 Battery (3.7V, 1200mAh)**:
   - Must use an external protection module (**TP4056 with DW01A/FS8205A**).
   - Never discharge below 2.8V or charge above 4.2V.
2. **Pump Power Isolation**:
   - The mini pump draws 0.8A to 1.5A stall/startup surge. **Do not power the pump directly from the ESP32 pins.**
   - Solder a **1N4007 flyback diode** across the pump terminals to quench inductive back-EMF spikes.
   - Use decoupling capacitors (100µF electrolytic + 100nF ceramic) on the 5V power bus.
3. **Relay Boot State**:
   - Firmware initializes GPIO 26 to `OUTPUT` and `HIGH` (Relay OFF for active-low boards) before peripheral init.

---

## 7. Project Structure

```
IoT_Project/
├── app.py                      # FastAPI server & lifespan runner
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration defaults template
├── run_server.bat              # 1-click Windows launch script
├── run_tests.bat               # 1-click test runner script
├── README.md                   # Documentation & setup guide
├── backend/
│   ├── config.py               # Settings & environment variables
│   ├── database/
│   │   └── db.py               # SQLite schema & connection pooling
│   ├── models/
│   │   └── schemas.py          # Pydantic schemas & validators
│   ├── routes/
│   │   ├── readings.py         # Telemetry ingestion & history
│   │   ├── status.py           # Connectivity & system status
│   │   ├── settings.py         # Thresholds & calibration endpoints
│   │   ├── commands.py         # Hardware command queue & ACK
│   │   ├── events.py           # Audit log endpoints
│   │   ├── alerts.py           # Real-time alert evaluator
│   │   ├── export.py           # CSV data export
│   │   └── simulator.py        # Software test telemetry simulator
│   └── services/
│       ├── irrigation_service.py # Hysteresis, calibration & decision rules
│       ├── command_service.py    # Queue manager & safety verifier
│       ├── alert_service.py      # Threshold alert monitoring
│       └── simulator_service.py  # Explicitly-labeled test generator
├── static/
│   ├── index.html              # Responsive single-page application
│   ├── css/
│   │   └── styles.css          # Design system & tokens (Forest & Teal)
│   └── js/
│       ├── api.js              # Fetch client wrapper
│       ├── charts.js           # Chart.js visualizations
│       └── app.js              # State manager & view router
├── firmware/
│   └── aquasense_esp32.ino     # Complete C++ Arduino firmware
├── docs/
│   ├── ELECTRICAL_AND_SAFETY.md # Detailed battery & power safety analysis
│   └── CALIBRATION_GUIDE.md    # Step-by-step FC-28 calibration procedure
└── tests/
    ├── test_api.py             # 12 Automated unit & integration tests
    └── run_tests.py            # Test suite runner
```
