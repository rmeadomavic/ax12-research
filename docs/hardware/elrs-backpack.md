# ELRS Backpack on AX12

## Overview

The AX12 includes a dedicated ELRS backpack chip, separate from the main
ESP32+LR1121 radio module. The backpack provides WiFi-based auxiliary
functions: VTX sync, OTA updates, MAVLink forwarding, and wireless input
expansion.

**Source:** `github.com/ExpressLRS/targets` — `TX/Radiomaster AX12.json`

## Hardware

| Property        | Value                                      |
|-----------------|--------------------------------------------|
| Chip            | ESP8285 or ESP32-C3 (WiFi only, no BLE)    |
| UART to main TX | 460800 baud (matches ttyS1 configuration)  |
| GPIO — RX       | GPIO18                                     |
| GPIO — TX       | GPIO5                                      |
| GPIO — EN       | GPIO19 (enable)                            |
| GPIO — BOOT     | GPIO23 (flash mode)                        |
| `use_backpack`  | `true` in target definition                |

The backpack communicates with the main ESP32 via UART at 460800 baud
using **MSP protocol** (MultiWii Serial Protocol), not CRSF. The main
ESP32 bridges between CRSF (from MCU) and MSP (to backpack).

## Capabilities

### VTX Channel Sync

Backpack sends the configured VTX channel to goggles via ESP-NOW.
Changing VTX channel on the TX automatically updates the goggle receiver.
Supported: HDZero, Rapidfire, SteadyView, generic ESP-NOW receivers.

### WiFi OTA Updates

Backpack enters AP mode (SSID: `ExpressLRS TX Backpack`, IP `10.0.0.1`).
Firmware upload via web UI at `http://10.0.0.1`. Updates both backpack
and (via passthrough) the main ELRS TX firmware.

### MAVLink Telemetry over WiFi (v1.5.0+)

The backpack creates a WiFi AP and forwards MAVLink telemetry via UDP on
port 14550. Any WiFi client (QGroundControl, ATAK, Mission Planner) can
connect and receive live telemetry without serial port access.

**This is the key capability for AX12-as-GCS.** The Android apps on the
AX12 can connect to the backpack's WiFi AP and receive vehicle telemetry
over a standard MAVLink UDP stream — no root, no serial hacks, no cables.

### CRSF Telemetry Relay

Forwards CRSF telemetry frames via ESP-NOW to compatible receivers
(e.g., goggle OSD modules). Enables telemetry display in goggles without
a dedicated telemetry radio link.

### DVR Recording Control

Sends start/stop DVR commands to HDZero goggles via ESP-NOW, triggered
by a TX switch assignment.

### Wireless Switch Expansion (v1.5.2+)

An external ESP32 module with physical switches can send channel data to
the backpack via ESP-NOW, using the Head Tracking input pathway. The
backpack injects this as additional channel data into ELRS.

Use case: foot pedals, external switch panels, wheelchair-mounted
controls. Proven by ExpressLRS wireless pedal PR #201 in the Backpack
repo.

### Antenna Tracker Integration

Backpack can forward GPS coordinates via ESP-NOW to an antenna tracker
module, enabling automatic directional tracking.

## What Runs Where

| Function          | Chip            | Notes                           |
|-------------------|-----------------|---------------------------------|
| ELRS radio link   | Main ESP32      | LR1121 sub-GHz RF               |
| Backpack features | ESP8285/C3      | WiFi + ESP-NOW, no BLE          |
| BLE Joystick      | Main ESP32      | Uses BLE on main, NOT backpack  |

**BLE Joystick is mutually exclusive with the radio link** — it runs on
the main ESP32 and disables ELRS while active. It does not involve the
backpack at all.

## Communication Path

```
Vehicle ─── RF ──► Main ESP32 (LR1121) ─── CRSF ──► AT32 MCU
                        │                              │
                        │ MSP (UART 460800)            │ UMBUS (ttyS0 921600)
                        ▼                              ▼
                   Backpack ESP                    MT8788 SoC
                   (WiFi/ESP-NOW)                  (Android/Flyshark)
                        │
                        ├── ESP-NOW ──► Goggles (VTX sync, DVR, telemetry OSD)
                        ├── WiFi AP ──► QGC/ATAK (MAVLink UDP :14550)
                        └── ESP-NOW ◄── External switches (wireless input)
```

## References

- Target definition: `github.com/ExpressLRS/targets` — `TX/Radiomaster AX12.json`
- Backpack firmware: `github.com/ExpressLRS/Backpack` — `src/Tx_main.cpp`
- MAVLink forwarding: Backpack v1.5.0 release notes
- Wireless switch input: Backpack PR #201, v1.5.2+
