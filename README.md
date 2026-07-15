# Tapo P110 HA Integration

Custom Home Assistant integration for TP-Link Tapo P110 smart plug using the **TPAP protocol** (TP-Link Adaptive Protocol).

## Why?

Firmware 1.4.0+ replaced the KLAP protocol with TPAP (SPAKE2+ P-256 key exchange + AES-128-CCM encrypted data channel). Existing integrations (official `tplink` via python-kasa, HACS `tapo` via plugp100) do not support TPAP yet.

I was frustrated after I bought a new Tapo P110 (IN/1.20) and couldn't get any existing integration to work, so I built my own dedicated to the Tapo P110.

## Features

- **Local polling** — no cloud dependency after setup
- **TPAP protocol** — SPAKE2+ handshake with cloud credentials
- 27 entities per device across 6 platforms:

### Switches
- Plug Power (outlet on/off)
- Auto-Off Timer
- Auto Firmware Update (config)
- Power Protection

### Select
- LED Mode (Always On / Auto / Off)
- Default State (Last 'On' State / On / Off)

### Sensors
- Power (W), Today/Month/Total Energy (kWh)
- Today/Month Runtime (Xh Ym format), On Time
- Voltage (V), Current (A)
- WiFi Signal (dBm), WiFi Signal Level, WiFi SSID
- On Since (timestamp), Device ID

### Binary Sensors
- Overheat, Power Overload, Overcurrent, Charging Protection

### Button
- Reboot (config)

### Number
- Auto-Off After (box input, 0–1439 min)
- Power Protection Threshold (box input, 1–3580W)

### Diagnostics
- Full raw device state dump with redacted sensitive fields

## Installation

### Via HACS (recommended)

1. Ensure [HACS](https://hacs.xyz) is installed in your Home Assistant
2. Go to **HACS → Custom Repositories**
3. Add this repository URL: `https://github.com/rabilrbl/tapo-p110-ha`
4. Select category: **Integration**
5. Search for "Tapo P110" in HACS and click **Install**
6. Restart Home Assistant

### Manual

1. Copy the `custom_components/tapo_p110/` directory to your HA `custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"Tapo P110"**
3. Enter:
   - **IP Address or Hostname** — your Tapo P110's local address (e.g. `192.168.1.100`)
   - **TP-Link Account Email** — your TP-Link cloud account email
   - **TP-Link Account Password** — your TP-Link cloud account password
4. Click **Submit** — the integration will perform the TPAP handshake and set up all entities

> **Note:** Cloud credentials are required for the SPAKE2+ key exchange. After setup, all communication is local — no cloud dependency for polling.

## Requirements

- Home Assistant 2026.7+
- `ecdsa` and `cryptography` packages (included in HA by default)

## Supported Devices

| Model | Firmware | Protocol |
|-------|----------|----------|
| Tapo P110 (IN) | 1.4.3 | TPAP |
| Tapo P110 (EU/UK/AU) | ≥1.4.0 | TPAP |

## Credits

- TPAP protocol reverse-engineered from Tapo P110 fw 1.4.3
- SPAKE2+ implementation based on [python-kasa PR #1592](https://github.com/python-kasa/python-kasa/pull/1592)
- Tapo brand icon from [home-assistant/brands](https://github.com/home-assistant/brands)
