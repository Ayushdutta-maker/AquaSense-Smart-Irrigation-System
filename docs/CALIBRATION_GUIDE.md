# AquaSense — Sensor Calibration Guide

## 1. FC-28 Soil Moisture Sensor Calibration

The FC-28 probe is a resistive dual-prong sensor. Because probe geometry, soil mineral salinity, and ADC characteristics vary, raw ADC values (0–4095 on ESP32 12-bit ADC) must be calibrated to represent meaningful soil moisture percentages.

### 1.1 The Inverted Resistance Principle
- **Dry Air / Bone-Dry Soil**: The resistance between the two prongs is near infinite. The sensor voltage output is pulled close to `VCC` (3.3V), yielding a high ADC reading: typically **3300 to 3800 counts**.
- **Saturated Soil / Water Immersion**: The resistance drops significantly. The output voltage drops, yielding a low ADC reading: typically **1200 to 1600 counts**.

### 1.2 Two-Point Calibration Procedure
1. **Dry Calibration (`soil_dry_raw`)**:
   - Clean the FC-28 prongs thoroughly with a dry cloth.
   - Hold the prongs in free air (0% moisture).
   - Observe the raw ADC reading in the AquaSense **Live Monitoring** page or serial monitor.
   - Average 10 readings (default recommendation: **3500**).
   - Enter this value into the **Settings -> Sensor Calibration -> Soil Dry Raw ADC** field.
2. **Wet Calibration (`soil_wet_raw`)**:
   - Submerge the prongs in a glass of tap water up to the maximum insertion line (do not submerge the electronic amplifier PCB).
   - Observe the stabilized raw ADC reading.
   - Average 10 readings (default recommendation: **1400**).
   - Enter this value into the **Settings -> Sensor Calibration -> Soil Wet Raw ADC** field.

### 1.3 Mapping Formula
$$\text{Moisture (\%)} = \left(\frac{\text{Dry Raw} - \text{Current Raw}}{\text{Dry Raw} - \text{Wet Raw}}\right) \times 100\%$$
- If $\text{Current Raw} \ge \text{Dry Raw}$, moisture is clamped to $0.0\%$.
- If $\text{Current Raw} \le \text{Wet Raw}$, moisture is clamped to $100.0\%$.

---

## 2. Rain Detection Module Calibration

The rain module consists of a rain track plate and an LM393 comparator board with an adjustable onboard potentiometer:
- **Analog Output (A0 to GPIO 32)**:
  - Dry plate: ADC ~3200–3800.
  - Water droplet bridge: ADC drops below 2500.
  - Heavy rain: ADC drops below 1200.
- **Sensitivity Trimming**:
  - Place two droplets of water across the trace grid.
  - Turn the onboard potentiometer until the onboard LED lights up.
  - Wipe clean and confirm the LED turns off.

---

## 3. DHT11 Sensor Placement & Limitations
- **Temperature Range**: 0°C to 50°C (±2°C accuracy).
- **Humidity Range**: 20% to 90% RH (±5% accuracy).
- **Placement**: Mount in a shaded, ventilated Stevenson-screen-style housing above the canopy, shielded from direct sunlight and pump water splash.
