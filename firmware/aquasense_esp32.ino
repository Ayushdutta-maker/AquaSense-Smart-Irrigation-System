/*
 * ==============================================================================
 * AQUASENSE SMART IRRIGATION SYSTEM — ESP32 FIRMWARE (PRO DUAL-SYNC v2.1)
 * Compatible with AquaSense Web Dashboard & Firebase Realtime Database
 * ==============================================================================
 * 
 * HARDWARE PIN MAPPING:
 * 1. FC-28 Soil Moisture Sensor AO -> GPIO 34 (Analog Input)
 * 2. Rain Detection Sensor AO      -> GPIO 35 (Analog Input)
 * 3. DHT11 Temp/Humidity Data      -> GPIO 4  (Digital I/O)
 * 4. 5V Relay Module (Water Pump)  -> GPIO 27 (Digital Output, Active-LOW)
 * 
 * RELAY SPECIFICATIONS:
 * - Active-LOW Relay: LOW = Pump ON, HIGH = Pump OFF
 * 
 * LIBRARIES REQUIRED IN ARDUINO IDE:
 * - "DHT sensor library" by Adafruit
 * (WiFi, HTTPClient, WiFiClientSecure are built-in with ESP32 board package)
 * ==============================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <time.h>
#include "DHT.h"

// ==============================================================================
// 1. PIN DEFINITIONS & RELAY SETTINGS
// ==============================================================================
#define SOIL_PIN        34       // Soil sensor AO pin
#define RAIN_PIN        35       // Rain sensor AO pin
#define DHTPIN          4        // DHT11 DATA pin
#define MOTOR_PIN       27       // Relay IN pin (GPIO 27)

#define DHTTYPE         DHT11

// --- Active-LOW Relay Settings ---
const int MOTOR_ON  = LOW;       // LOW dene par relay ON hota hai
const int MOTOR_OFF = HIGH;      // HIGH dene par relay OFF hota hai

// --- Threshold Values ---
int SOIL_DRY_THRESHOLD = 2800;   // 2800 se zyada value matlab mitti sookhi hai
int RAIN_THRESHOLD     = 2500;   // 2500 se kam value matlab baarish ho rahi hai

// Calibration points for Soil Moisture % (0 - 100%)
const int SOIL_DRY_RAW = 3500;   // Air ADC
const int SOIL_WET_RAW = 1400;   // Water ADC

DHT dht(DHTPIN, DHTTYPE);

// ==============================================================================
// 2. WI-FI & BACKEND CONFIGURATION
// ==============================================================================
// Apna Wi-Fi ka naam aur password yahan dalein:
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Local Laptop IP Address (Port 8000)
// Apke laptop ka IP 192.168.1.5 hai:
const char* BACKEND_BASE_URL = "http://192.168.1.5:8000";
const char* API_KEY          = "aquasense_secret_key_2026";

// Firebase Realtime Database Configuration:
const char* FIREBASE_HOST    = "https://aquasense-62dda-default-rtdb.asia-southeast1.firebasedatabase.app";
const char* DEVICE_ID        = "esp32-aquasense-01";

// Intervals
const unsigned long TELEMETRY_INTERVAL_MS = 3000;  // 3 second update
const unsigned long DHT_INTERVAL_MS       = 2000;  // DHT11 read interval
const unsigned long CLOUD_POLL_INTERVAL_MS= 4000;  // Firebase command poll interval

unsigned long lastTelemetryMillis = 0;
unsigned long lastDhtMillis       = 0;
unsigned long lastCloudPollMillis = 0;

// Current States
float currentTemp       = 25.0;
float currentHumidity   = 60.0;
int   currentSoilRaw    = 0;
float currentMoisture   = 0.0;
int   currentRainRaw    = 0;
bool  currentRainState  = false;
bool  isPumpRunning     = false;
String operatingMode    = "AUTO"; // "AUTO" or "MANUAL"

// Manual Command Control Variables
unsigned long manualPumpEndTime   = 0;
String lastExecutedCommandId      = "";

// ==============================================================================
// 3. HELPER FUNCTIONS: CALIBRATION & NTP
// ==============================================================================
float calculateMoisturePercentage(int rawVal) {
    if (rawVal >= SOIL_DRY_RAW) return 0.0;
    if (rawVal <= SOIL_WET_RAW) return 100.0;
    float pct = ((float)(SOIL_DRY_RAW - rawVal) / (float)(SOIL_DRY_RAW - SOIL_WET_RAW)) * 100.0;
    if (pct < 0.0) pct = 0.0;
    if (pct > 100.0) pct = 100.0;
    return round(pct * 10.0) / 10.0;
}

String getIsoTimestamp() {
    time_t now;
    time(&now);
    struct tm timeinfo;
    if (gmtime_r(&now, &timeinfo) && now > 100000) {
        char buf[30];
        strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
        return String(buf);
    }
    return String("2026-10-29T23:00:00Z");
}

// Lightweight JSON helper to avoid heavy libraries
String extractJsonString(const String& json, const String& key) {
    String searchKey = "\"" + key + "\":\"";
    int start = json.indexOf(searchKey);
    if (start == -1) {
        // Try without quotes around value
        searchKey = "\"" + key + "\":";
        start = json.indexOf(searchKey);
        if (start == -1) return "";
        start += searchKey.length();
        while (start < json.length() && (json[start] == ' ' || json[start] == '\"')) start++;
        int end = start;
        while (end < json.length() && json[end] != '\"' && json[end] != ',' && json[end] != '}' && json[end] != ']') end++;
        return json.substring(start, end);
    }
    start += searchKey.length();
    int end = json.indexOf("\"", start);
    if (end == -1) return "";
    return json.substring(start, end);
}

int extractJsonInt(const String& json, const String& key, int defaultVal = 0) {
    String val = extractJsonString(json, key);
    if (val.length() == 0) return defaultVal;
    return val.toInt();
}

// ==============================================================================
// 4. COMMAND DISPATCH ENGINE
// ==============================================================================
void executeCommand(String cmdId, String cmdType, String targetState, int durationSec, String mode) {
    if (cmdId.length() > 0 && cmdId == lastExecutedCommandId) {
        return; // Already executed this command
    }
    if (cmdId.length() > 0) {
        lastExecutedCommandId = cmdId;
    }

    Serial.println("\n------------------------------------------");
    Serial.printf("[COMMAND RECEIVED] Type: %s | State: %s | Duration: %ds | Mode: %s\n",
                  cmdType.c_str(), targetState.c_str(), durationSec, mode.c_str());

    if (cmdType == "PUMP_START") {
        operatingMode = "MANUAL";
        digitalWrite(MOTOR_PIN, MOTOR_ON);
        isPumpRunning = true;
        if (durationSec <= 0) durationSec = 15; // Default safety 15 seconds
        manualPumpEndTime = millis() + (durationSec * 1000UL);
        Serial.printf("[RELAY ACTION] -> MOTOR ON for %d seconds (MANUAL OVERRIDE)\n", durationSec);
    } 
    else if (cmdType == "PUMP_STOP") {
        digitalWrite(MOTOR_PIN, MOTOR_OFF);
        isPumpRunning = false;
        manualPumpEndTime = 0;
        Serial.println("[RELAY ACTION] -> MOTOR OFF immediately (STOP EXECUTED)");
    } 
    else if (cmdType == "SET_MODE") {
        if (mode == "AUTO" || mode == "MANUAL") {
            operatingMode = mode;
            Serial.printf("[MODE SWITCH] -> Mode is now: %s\n", operatingMode.c_str());
            if (operatingMode == "AUTO") {
                manualPumpEndTime = 0; // Clear any manual override timer
            }
        }
    }
    Serial.println("------------------------------------------\n");
}

// ==============================================================================
// 5. LOCAL BACKEND SYNC (FastAPI - Port 8000)
// ==============================================================================
void syncToLocalBackend(float soilPct, int soilRaw, float temp, float hum, int rainRaw, bool isRaining, bool pumpOn) {
    if (WiFi.status() != WL_CONNECTED || String(BACKEND_BASE_URL).length() == 0) return;

    HTTPClient http;
    http.setTimeout(1500); // 1.5s max
    String url = String(BACKEND_BASE_URL) + "/api/readings";

    if (http.begin(url)) {
        http.addHeader("Content-Type", "application/json");
        http.addHeader("X-API-Key", API_KEY);

        String payload = "{";
        payload += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
        payload += "\"soil_raw_adc\":" + String(soilRaw) + ",";
        payload += "\"soil_moisture\":" + String(soilPct, 1) + ",";
        payload += "\"temperature\":" + String(temp, 1) + ",";
        payload += "\"humidity\":" + String(hum, 1) + ",";
        payload += "\"light_raw\":1800,";
        payload += "\"rain_detected\":" + String(isRaining ? "true" : "false") + ",";
        payload += "\"rain_raw_adc\":" + String(rainRaw) + ",";
        payload += "\"pump_state\":\"" + String(pumpOn ? "ON" : "OFF") + "\",";
        payload += "\"operating_mode\":\"" + operatingMode + "\",";
        payload += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
        payload += "\"firmware_version\":\"v2.1.0-esp32\",";
        payload += "\"uptime_seconds\":" + String(millis() / 1000) + ",";
        payload += "\"is_simulated\":false";
        payload += "}";

        int httpCode = http.POST(payload);
        if (httpCode > 0) {
            String response = http.getString();
            Serial.printf("[Local Backend] Telemetry sent! HTTP %d\n", httpCode);

            // Check if response contains pending commands
            if (response.indexOf("\"commands\":[") != -1 && response.indexOf("\"command_type\"") != -1) {
                String cmdType = extractJsonString(response, "command_type");
                String cmdId   = extractJsonString(response, "id");
                String state   = extractJsonString(response, "target_state");
                int duration   = extractJsonInt(response, "duration_sec", 15);
                String mode    = extractJsonString(response, "mode");
                if (cmdType.length() > 0) {
                    executeCommand(cmdId, cmdType, state, duration, mode);
                }
            }
        } else {
            Serial.printf("[Local Backend] Connection error: %s\n", http.errorToString(httpCode).c_str());
        }
        http.end();
    }
}

// ==============================================================================
// 6. FIREBASE REALTIME DATABASE SYNC (asia-southeast1)
// ==============================================================================
void syncToFirebase(float soilPct, int soilRaw, float temp, float hum, int rainRaw, bool isRaining, bool pumpOn) {
    if (WiFi.status() != WL_CONNECTED) return;

    WiFiClientSecure client;
    client.setInsecure(); // SSL verification bypass
    client.setTimeout(3);

    HTTPClient https;
    https.setTimeout(3000);
    String timestamp = getIsoTimestamp();

    // Atomic PATCH updates both telemetry/latest and status simultaneously
    String syncUrl = String(FIREBASE_HOST) + "/aquasense.json";
    if (https.begin(client, syncUrl)) {
        https.addHeader("Content-Type", "application/json");

        String patchJson = "{\"telemetry/latest\":{";
        patchJson += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
        patchJson += "\"soil_moisture\":" + String(soilPct, 1) + ",";
        patchJson += "\"soil_raw_adc\":" + String(soilRaw) + ",";
        patchJson += "\"temperature\":" + String(temp, 1) + ",";
        patchJson += "\"humidity\":" + String(hum, 1) + ",";
        patchJson += "\"light_raw\":1800,";
        patchJson += "\"light_state\":\"MODERATE\",";
        patchJson += "\"rain_detected\":" + String(isRaining ? "true" : "false") + ",";
        patchJson += "\"rain_raw_adc\":" + String(rainRaw) + ",";
        patchJson += "\"pump_state\":\"" + String(pumpOn ? "ON" : "OFF") + "\",";
        patchJson += "\"operating_mode\":\"" + operatingMode + "\",";
        patchJson += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
        patchJson += "\"battery_voltage\":3.95,";
        patchJson += "\"is_simulated\":false,";
        patchJson += "\"timestamp\":\"" + timestamp + "\"";
        patchJson += "},\"status\":{";
        patchJson += "\"online\":true,";
        patchJson += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
        patchJson += "\"current_pump_state\":\"" + String(pumpOn ? "ON" : "OFF") + "\",";
        patchJson += "\"current_mode\":\"" + operatingMode + "\",";
        patchJson += "\"rain_lockout_active\":" + String(isRaining ? "true" : "false") + ",";
        patchJson += "\"recommendation\":\"ESP32 is online and transmitting live telemetry.\",";
        patchJson += "\"firmware_version\":\"v2.1.0-esp32\",";
        patchJson += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
        patchJson += "\"is_simulated\":false,";
        patchJson += "\"hardware_attached\":true,";
        patchJson += "\"last_updated\":\"" + timestamp + "\"";
        patchJson += "}}";

        int code = https.sendRequest("PATCH", patchJson);
        if (code > 0) {
            Serial.printf("[Firebase RTDB] Telemetry & Online Status synced! (HTTP %d)\n", code);
        } else {
            Serial.printf("[Firebase Error] %s\n", https.errorToString(code).c_str());
        }
        https.end();
    }
    client.stop(); // CRITICAL: Free SSL buffers to prevent memory leaks!
}

// ==============================================================================
// 7. FIREBASE COMMAND POLLER
// ==============================================================================
void pollFirebaseCommands() {
    if (WiFi.status() != WL_CONNECTED) return;

    WiFiClientSecure client;
    client.setInsecure();
    client.setTimeout(2);

    HTTPClient https;
    https.setTimeout(2500);
    String url = String(FIREBASE_HOST) + "/aquasense/commands/latest.json";

    if (https.begin(client, url)) {
        int code = https.GET();
        if (code == 200) {
            String payload = https.getString();
            if (payload != "null" && payload.length() > 10) {
                String status = extractJsonString(payload, "status");
                if (status == "PENDING") {
                    String cmdId   = extractJsonString(payload, "id");
                    String cmdType = extractJsonString(payload, "command_type");
                    String state   = extractJsonString(payload, "target_state");
                    int duration   = extractJsonInt(payload, "duration_sec", 15);
                    String mode    = extractJsonString(payload, "mode");

                    if (cmdId != lastExecutedCommandId) {
                        executeCommand(cmdId, cmdType, state, duration, mode);

                        // Mark as ACKNOWLEDGED in Firebase
                        HTTPClient ackHttp;
                        String ackUrl = String(FIREBASE_HOST) + "/aquasense/commands/latest/status.json";
                        if (ackHttp.begin(client, ackUrl)) {
                            ackHttp.PUT("\"ACKNOWLEDGED\"");
                            ackHttp.end();
                        }
                    }
                }
            }
        }
        https.end();
    }
    client.stop(); // Free SSL heap
}

// ==============================================================================
// 8. SETUP
// ==============================================================================
void setup() {
    Serial.begin(115200);
    delay(500);

    dht.begin();

    pinMode(SOIL_PIN, INPUT);
    pinMode(RAIN_PIN, INPUT);
    pinMode(MOTOR_PIN, OUTPUT);

    // Boot Safety: Motor initially OFF
    digitalWrite(MOTOR_PIN, MOTOR_OFF);
    isPumpRunning = false;

    Serial.println("\n==================================================");
    Serial.println("  AquaSense Smart Irrigation System (v2.1.0)     ");
    Serial.println("  ESP32 -> Local PC & Firebase Cloud Dual-Sync   ");
    Serial.println("==================================================");

    // Connect to Wi-Fi
    Serial.print("Connecting to Wi-Fi: ");
    Serial.println(WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 25) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[Wi-Fi CONNECTED]");
        Serial.print("ESP32 IP: ");
        Serial.println(WiFi.localIP());
        Serial.print("Signal (RSSI): ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
        Serial.print("Target Laptop Server: ");
        Serial.println(BACKEND_BASE_URL);

        configTime(0, 0, "pool.ntp.org", "time.nist.gov");
        Serial.println("[NTP] Time synchronization configured.");
    } else {
        Serial.println("\n[Wi-Fi WARNING] Could not connect. Operating in Autonomous Offline Mode.");
    }
}

// ==============================================================================
// 9. MAIN LOOP
// ==============================================================================
void loop() {
    unsigned long currentMillis = millis();

    // 1. Read DHT11 Sensor (every 2 seconds)
    if (currentMillis - lastDhtMillis >= DHT_INTERVAL_MS) {
        lastDhtMillis = currentMillis;

        float t = dht.readTemperature();
        float h = dht.readHumidity();

        if (!isnan(t) && !isnan(h)) {
            currentTemp = t;
            currentHumidity = h;
        } else {
            Serial.println("[DHT11] Reading error! Checking sensor connection...");
        }
    }

    // 2. Read Soil & Rain Sensors
    currentSoilRaw = analogRead(SOIL_PIN);
    currentRainRaw = analogRead(RAIN_PIN);
    currentMoisture = calculateMoisturePercentage(currentSoilRaw);

    bool isSoilDry   = (currentSoilRaw > SOIL_DRY_THRESHOLD);
    currentRainState = (currentRainRaw < RAIN_THRESHOLD);

    // 3. Actuator Control Logic (AUTO vs MANUAL)
    if (operatingMode == "MANUAL") {
        // In MANUAL mode, check if timed duration has expired
        if (isPumpRunning && manualPumpEndTime > 0 && currentMillis >= manualPumpEndTime) {
            digitalWrite(MOTOR_PIN, MOTOR_OFF);
            isPumpRunning = false;
            manualPumpEndTime = 0;
            Serial.println("[MANUAL TIMER] Timed duration reached. Motor turned OFF.");
        }
    } else {
        // In AUTO mode, decisions are dictated by Sensor Thresholds
        if (isSoilDry && !currentRainState) {
            digitalWrite(MOTOR_PIN, MOTOR_ON);
            isPumpRunning = true;
        } else {
            digitalWrite(MOTOR_PIN, MOTOR_OFF);
            isPumpRunning = false;
        }
    }

    // Print summary to Serial Monitor every second
    Serial.printf("[Sensors] Soil ADC: %4d (%.1f%%) | Rain: %4d (%s) | Temp: %.1fC | Pump: %s | Mode: %s\n",
                  currentSoilRaw, currentMoisture, currentRainRaw,
                  currentRainState ? "RAIN" : "CLEAR",
                  currentTemp,
                  isPumpRunning ? "ON " : "OFF",
                  operatingMode.c_str());

    // 4. Send Real-Time Telemetry (every 3 seconds)
    if (currentMillis - lastTelemetryMillis >= TELEMETRY_INTERVAL_MS) {
        lastTelemetryMillis = currentMillis;

        if (WiFi.status() == WL_CONNECTED) {
            // A. Sync to Local FastAPI Backend on your laptop (192.168.1.5:8000)
            syncToLocalBackend(currentMoisture, currentSoilRaw, currentTemp, currentHumidity,
                               currentRainRaw, currentRainState, isPumpRunning);

            // B. Sync to Firebase Realtime Database
            syncToFirebase(currentMoisture, currentSoilRaw, currentTemp, currentHumidity,
                           currentRainRaw, currentRainState, isPumpRunning);
        } else {
            Serial.println("[Wi-Fi] Disconnected. Reconnecting...");
            WiFi.reconnect();
        }
    }

    // 5. Poll Firebase Commands (every 4 seconds)
    if (currentMillis - lastCloudPollMillis >= CLOUD_POLL_INTERVAL_MS) {
        lastCloudPollMillis = currentMillis;
        pollFirebaseCommands();
    }

    delay(1000); // 1-second cadence
}
