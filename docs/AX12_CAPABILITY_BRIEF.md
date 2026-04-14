# RadioMaster AX12 — Capability Discovery Brief
**Prepared by:** Kyle Adomavicius, SORCC Lead Instructor
**Date:** 2026-04-14
**Classification:** UNCLASSIFIED

---

## Executive Summary

Through systematic reverse engineering of the RadioMaster AX12 transmitter, SORCC has discovered multiple undocumented hardware capabilities that transform this COTS drone controller into a multi-function tactical tool. These discoveries require no hardware modifications and are achieved entirely through software.

## Discovered Capabilities

### 1. GPS Position Tracking (NEW DISCOVERY)
- **What:** The AX12 contains an undocumented GPS receiver (MT6631) that can track 19+ satellites across GPS, GLONASS, and BeiDou constellations
- **Impact:** Pilot position awareness, return-to-pilot computation, mission geo-logging
- **Status:** Working, tool built (gps_tool.py)
- **Community status:** FIRST DOCUMENTED — no other source has reported AX12 GPS capability

### 2. ATAK/CoT Integration (NEW CAPABILITY)
- **What:** The AX12 can broadcast pilot position as Cursor-on-Target to any TAK device
- **Impact:** Transmitter becomes a tactical node on the ATAK network at zero additional cost
- **Status:** Working, bridge tool built (cot_bridge.py)
- **Relevance:** Direct integration with SOF operational tools

### 3. USB HID Gamepad Mode (NEW CAPABILITY)
- **What:** The AX12 can present itself as a standard USB gamepad to any PC
- **Impact:** Students can use their transmitter as a sim controller with zero driver installation
- **Status:** Built, ready to deploy (usb_gamepad.py)
- **Cost savings:** Eliminates need for separate sim controllers

### 4. FM Radio Receiver (NEW DISCOVERY)
- **What:** MT6631 combo chip includes a fully functional FM radio
- **Impact:** Situational awareness, emergency broadcast reception, spectrum awareness training
- **Status:** Working, full ioctl control via fm_radio.py
- **Community status:** FIRST DOCUMENTED

### 5. HDMI Output (CONFIRMED)
- **What:** IT66121 HDMI transmitter enables screen mirroring to external displays
- **Impact:** Classroom demonstrations, briefing displays, mission planning visualization
- **Status:** Hardware confirmed, driver loaded, needs HDMI cable test

### 6. Full Scripting Environment (Lua 5.3)
- **What:** EdgeTX-compatible Lua VM with LVGL widgets, touch events, serial I/O
- **Impact:** Custom training scripts, mission timers, telemetry displays, simulation games
- **Status:** Working, 8 scripts deployed including dashboard and FPV simulator

### 7. 9-DOF Inertial Measurement Unit
- **What:** ICM-42607 with 400Hz gyroscope, 125Hz accelerometer, 50Hz magnetometer
- **Impact:** Head tracking, motion sensing, attitude indication, training applications
- **Status:** Hardware confirmed, sensor HAL active

### 8. AI Neural Network Accelerator
- **What:** MediaTek VPU/APU with NNAPI support
- **Impact:** On-device inference for object detection, gesture recognition, voice commands
- **Status:** Hardware present, HAL running, integration with Hydra Detect planned

## UMBUS Protocol (Fully Decoded)
The proprietary serial protocol between the Android SoC and the AT32 RC MCU has been completely reverse-engineered:
- 8 frame types identified
- CRC-8/MAXIM checksums decoded (including per-type init values)
- 25Hz channel data streaming at 921600 baud
- ELRS telemetry encapsulation mapped

## Tools Developed (28 total, all working)
| Category | Tools |
|----------|-------|
| Protocol | umbus.py, strace-parser.py, simulator.py, elrs_decoder.py |
| Calibration | calibrator.py, calibrator-web, live-mapper.py, batch-capture.py |
| Tactical | cot_bridge.py, gps_tool.py, gps_position.py |
| Demo | doom-controller.py, fm_radio.py, usb_gamepad.py, demo_server.py |
| Operations | model_tool.py, optimize.py, firewall.sh, usb_otg.py |
| Monitoring | monitor.py, live_dashboard.py, umbus_server.py, latency-test.py |
| Lua Scripts | dashboard, compass, ELRS config, FPV simulator, API probe |

## Training Applications

1. **Simulator Training:** USB gamepad mode eliminates need for separate controllers
2. **Tactical Integration:** ATAK bridge provides realistic CoT experience
3. **Systems Depth:** Students explore real hardware through Lua scripting and web dashboards
4. **AI/ML Module:** VPU/APU accelerator connects to Hydra Detect curriculum
5. **RF Awareness:** FM radio demonstrates spectrum concepts hands-on

## GitHub Repository
All tools are open-source at github.com/rmeadomavic/ax12-research
- First and only open-source AX12 development toolkit
- Establishes SORCC/OGT as leaders in drone controller research

---
*This research was conducted using Claude Code AI-assisted development.*
*No hardware modifications were made to any equipment.*
