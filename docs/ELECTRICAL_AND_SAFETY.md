# AquaSense — Electrical Architecture & Power Safety Report

## 1. Executive Summary & Hardware Context

The AquaSense Smart Irrigation System integrates sensitive 3.3V CMOS microelectronics (ESP32 WROOM), analog and digital sensors (FC-28, DHT11, LDR, Rain Plate), an I²C LCD display, a 5V electromechanical relay, and an inductive DC water pump powered by an 18650 lithium-ion cell.

Operating inductive loads alongside Wi-Fi microcontrollers introduces brownout risks, inductive voltage transients (back-EMF), and fire/degradation risks if lithium chemistry is mishandled. This document specifies the engineering safeguards and wiring topology required for reliable operation.

---

## 2. 18650 Lithium-Ion Battery Safety (3.7V, 1200mAh, 4.44Wh)

### 2.1 Cell Characteristics & Unknown Protection
The available cell is labelled:
- Chemistry: Lithium-ion cylindrical cell (18650 format)
- Nominal Voltage: 3.7 V
- Rated Capacity: 1200 mAh (4.44 Wh)
- Protection Status: **Unprotected cell (assumed raw bare cell)**

> [!CAUTION]
> Bare 18650 lithium-ion cells lack internal cutoff circuits. If discharged below 2.5V, copper dendrites form, leading to internal short circuits and thermal runaway upon recharging. If charged above 4.25V, electrolyte breakdown can cause outgassing and combustion.

### 2.2 Mandatory Battery Management Requirements
1. **Protection Circuit Module (PCM/BMS)**:
   - A dedicated battery protection board (such as the standard TP4056 module featuring **DW01A battery protection IC** and **FS8205A dual N-channel MOSFET**) must be wired directly to the 18650 cell terminals.
   - **Overcharge Cutoff**: 4.25 V ± 0.05 V
   - **Overdischarge Cutoff**: 2.80 V ± 0.08 V
   - **Overcurrent Cutoff**: 3.0 A (latched trip)
2. **Charging Protocol**:
   - CC/CV (Constant Current / Constant Voltage) profile strictly.
   - Charging current must not exceed 0.5C to 1C (600 mA to 1000 mA maximum for a 1200 mAh cell). The TP4056 programming resistor (`R_prog`) should be set to 1.2 kΩ (1000 mA) or 2 kΩ (580 mA recommended for longevity).

---

## 3. Power Rail Segregation & Voltage Regulation

The system requires two distinct voltage rails:
1. **3.3V Logic Rail** for ESP32 CPU and 3.3V sensors.
2. **5V Power Rail** for the Relay Coil, LCD1602 Backlight, and 3-6V Mini Submersible Pump.

### 3.1 Why Pump and ESP32 Cannot Share an Unbuffered Power Rail
- **Stall & Startup Inrush Current**: A 3-6V DC mini submersible pump has a nominal running current of 150–250 mA, but an inrush/stall surge current of **800 mA to 1.5 A**.
- **Brownout Reset**: The ESP32's internal Brownout Detector triggers a system reset if `VDD33` dips below 2.8V for even a few microseconds (such as during Wi-Fi transmission bursts of 350-500 mA concurrent with pump motor startup).
- **Back-EMF Spikes**: When the relay disconnects the pump motor, the collapsing magnetic field in the motor windings generates high-voltage reverse inductive transients (spikes exceeding -40V to -100V) capable of puncturing semiconductor junctions.

### 3.2 Recommended Power Delivery Circuit
```
 [ 18650 Li-Ion Cell ] (3.0V - 4.2V)
          │
          ▼
   [ TP4056 Charger + Protection Board ]
     (B+ / B- to cell; OUT+ / OUT- to load)
          │
          ▼
  [ Boost Converter: MT3608 or XL6009 ] ───► Stepped up to stable 5.0V Rail
          │                                        │
          ├────────────────────────────────────────┤
          │                                        │
          ▼                                        ▼
   [ ESP32 DevKit ]                         [ Relay Coil & Pump Subsystem ]
   (Vin 5V pin with onboard                 (Opto-isolated 5V rail with
    AMS1117-3.3V LDO regulator)              flyback diode & decoupling)
```

---

## 4. Inductive Load Suppression & Noise Decoupling

To prevent electromagnetic interference (EMI) and voltage spikes:
1. **Flyback (Freewheeling) Diode**:
   - Solder a fast-recovery or Schottky diode (e.g., **1N4007** or **1N5819**) in reverse polarity directly across the positive and negative terminals of the mini submersible pump.
   - Cathode (striped end) to Pump (+)
   - Anode to Pump (-)
2. **Decoupling Capacitors**:
   - Place a **100 µF to 220 µF electrolytic capacitor** in parallel with a **100 nF ceramic capacitor** across the 5V power bus close to the pump power connection to absorb inductive transients.
3. **Snubber / Isolation**:
   - Keep motor wiring physically separated and twisted away from the analog FC-28 and DHT11 signal lines.

---

## 5. Relay Module & Logic Compatibility

- **Relay Coil**: Rated for 5V DC. Power the coil from the regulated 5V boost rail, never from the ESP32 3.3V pin.
- **Relay Logic Compatibility**: The single-channel module includes an onboard NPN or PNP transistor driver and optical isolator (EL817). Ensure the module triggers cleanly with 3.3V CMOS high/low output from ESP32 GPIO 26.
- **Boot State**: ESP32 GPIO 26 initializes as a high-impedance input during strapping. The firmware explicitly sets `pinMode(PIN_RELAY, OUTPUT)` and writes the relay to OFF before any peripheral initialization.

---

## 6. LCD1602 I²C Bus 5V vs 3.3V Compatibility

- The PCF8574T I²C adapter board is commonly powered by 5V to illuminate the 1602 LCD backlight.
- **Risk**: Standard PCF8574T breakout boards have onboard 4.7 kΩ pull-up resistors tied to their `VCC` (5V). When connected directly to ESP32 GPIO 21 (SDA) and GPIO 22 (SCL), this continuously injects 5V into the ESP32 pins. While ESP32 pins are somewhat resilient, exceeding `VDD + 0.3V` violates the Espressif datasheet and degrades the silicon.
- **Remedy**:
  - *Option A (Recommended)*: Use a bi-directional 2-channel logic level shifter (such as BSS138-based converter) between ESP32 3.3V and PCF8574 5V.
  - *Option B*: Desolder/cut the onboard pull-up resistors on the PCF8574 adapter and rely on the ESP32's internal 3.3V pull-ups (`pinMode(21, INPUT_PULLUP)`).
  - *Option C*: Power the PCF8574T module from 3.3V (some PCF8574T variants function at 3.3V, although display contrast may require adjustment).

---

## 7. Complete Hardware Pinout Mapping

| Component | ESP32 GPIO | Pin Mode | Operating Voltage | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **FC-28 Soil Moisture** | GPIO 34 (ADC1_CH6) | Analog Input | 3.3V | ADC1 channel; safe alongside Wi-Fi |
| **DHT11 Temp/Humidity** | GPIO 4 | Digital I/O | 3.3V | Needs 4.7kΩ pull-up to 3.3V |
| **LDR Light Sensor** | GPIO 35 (ADC1_CH7) | Analog Input | 3.3V | ADC1 channel |
| **Rain Detection Module** | GPIO 32 (ADC1_CH4) | Analog Input | 3.3V | Wet plate drops ADC voltage |
| **Relay Signal Input** | GPIO 26 | Digital Output | 3.3V Logic | Defaults OFF at boot |
| **LCD1602 SDA** | GPIO 21 | I²C Data | 3.3V Logic | Level-shifted to PCF8574 |
| **LCD1602 SCL** | GPIO 22 | I²C Clock | 3.3V Logic | Level-shifted to PCF8574 |
| **Relay Coil VCC** | External 5V Rail | Power | 5.0V | High current coil rail |
| **Water Pump (+)** | Switched Relay NO | Switched DC | 3.0V – 6.0V | Protected by 1N4007 flyback |
