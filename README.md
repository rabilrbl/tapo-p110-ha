# Tapo P110 HA Integration

Custom Home Assistant integration for TP-Link Tapo P110 smart plug using the **TPAP protocol** (TP-Link Adaptive Protocol).

## Why?

Firmware 1.4.0+ replaced the KLAP protocol with TPAP (SPAKE2+ P-256 key exchange + AES-128-CCM encrypted data channel). Existing integrations (official `tplink` via python-kasa, HACS `tapo` via plugp100) do not support TPAP yet.

## Features

- **Local polling** — no cloud dependency after setup
- **TPAP protocol** — SPAKE2+ handshake with cloud credentials
- 24 entities per device across 6 platforms:

### Switches
- Plug Power (outlet on/off)
- Auto-Off Timer (config)
- Auto Firmware Update (config)

### Select
- LED Mode (Always / Auto / Off)

### Sensors
- Power (W), Today/Month/Total Energy (kWh)
- Today/Month Runtime (Xh Ym format), On Time
- Voltage (V), Current (A)
- WiFi Signal (dBm), WiFi Signal Level, WiFi SSID
- On Since (timestamp), Device ID

### Binary Sensors
- Overheat, Power Overload, Overcurrent, Charging Protection

### Button
- Reboot

### Number
- Auto-Off Delay (slider, 1-120 min)

### Diagnostics
- Full raw device state dump with redacted sensitive fields

## Setup

1. Copy `tapo_p110/` to your `custom_components/` directory
2. Restart Home Assistant
3. Add integration → search "Tapo P110"
4. Enter device IP, TP-Link account email and password

## Requirements

- Home Assistant 2026.7+
- `ecdsa` and `cryptography` packages (included in HA)

## Credits

- TPAP protocol reverse-engineered from Tapo P110 fw 1.4.3
- SPAKE2+ implementation based on [python-kasa PR #1592](https://github.com/python-kasa/python-kasa/pull/1592)
- Tapo brand icon from [home-assistant/brands](https://github.com/home-assistant/brands)