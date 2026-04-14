# RadioMaster AX12 — Reverse Engineering Reference

Community-built technical reference for the RadioMaster AX12, an Android-based RC transmitter. Everything here was reverse-engineered from a stock device — no manufacturer documentation exists for these internals.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.13](https://img.shields.io/badge/python-3.13-yellow.svg)
![Platform: Android 9](https://img.shields.io/badge/platform-Android%209-green.svg)

## Hardware Discoveries

Capabilities found through reverse engineering that are not documented by RadioMaster or mentioned in any review.

**Verification key:** Confirmed = tested on device with observed results. Detected = hardware/driver present, not functionally tested. Theoretical = code analysis only, needs physical testing.

| Discovery | Status | Details |
|-----------|--------|---------|
| **Factory Root** | Confirmed | Ships with SUID su binary, userdebug build, SELinux permissive. No exploit needed. |
| **GPS Receiver** | Confirmed | MT6631 GNSS: GPS + GLONASS + BeiDou, 19 satellites observed via Android location services. No UI exposes it. |
| **FM Radio** | Detected | MT6631 FM tuner (87.5-108 MHz). Chip responds to ioctl commands. Headphone antenna path may not be wired on AX12 PCB — needs hardware investigation. |
| **Lua 5.3 VM** | Confirmed | EdgeTX-derived with LVGL widgets, touch events, shared memory IPC. Custom AX12 extensions (getShmVar/setShmVar). Scripts run on device. |
| **Miracast** | Confirmed | WiFi Display P2P discovery functional. Successfully found LG TV on network. |
| **HDMI Output** | Detected | ITE IT66121 HDMI 1.4 transmitter on I2C bus 1. Driver loaded, currently disabled in software. |
| **Analog Video Decoder** | Detected | RN6752M decodes HDMI to MIPI CSI-2, registered as camera sensor. Routed through ISP pipeline (~140ms measured latency). |
| **9-DOF IMU** | Detected, driver broken | ICM-42607 on I2C. Sensor HAL expects device nodes that don't exist in current firmware. Needs fix from RadioMaster. |
| **AI Accelerator** | Detected | MediaTek VPU/APU with NNAPI HAL service running. No inference testing done. |
| **USB HID Gamepad** | Theoretical | Kernel has CONFIG_USB_F_HID=y, ConfigFS function pre-created. Tool written but never tested with a physical USB connection to a PC. |
| **USB OTG Host** | Theoretical | Sysfs controls respond. No physical test with USB-C OTG adapter and connected device. |
| **LTE Modem** | Detected, not usable | MT8788 baseband active, MOLY firmware running, 21 ccmni interfaces. No SIM slot or antenna populated on PCB. |
| **NFC** | Not present | Software stack exists but chip not populated. Hardware modification required. |

These findings apply to firmware K908-V2.0-XY8788WA. Other firmware versions may differ.

## Overview

The RadioMaster AX12 is an RC transmitter built on a MediaTek MT8788 SoC running Android 9. Unlike traditional radios with dedicated firmware, the AX12 runs a full Android OS with a Qt6/QML application ("Flyshark") that communicates with an AT32 microcontroller over a proprietary serial protocol we call **UMBUS**.

The AT32 MCU handles all physical inputs — hall-effect gimbals, six switches, two pots, trim buttons, and a 6-position rotary selector — and controls the ELRS RF module (Semtech LR1121). The Android app handles the UI, mixer logic, telemetry display, ground control station, and Lua scripting, then sends mixed channel data back to the MCU for transmission.

This project documents the UMBUS protocol, maps the hardware, analyzes the native library, and provides Python tools for passive monitoring and protocol analysis. All data was captured non-invasively via `strace` on the running application.

## Architecture

```
┌──────────────┐  UART @ 921600   ┌───────────┐  CRSF  ┌──────────┐
│  MT8788 SoC  │◄───── UMBUS ────►│  AT32 MCU │◄──────►│ ELRS TX  │
│  Android 9   │                  │           │        │ (LR1121) │
│  Flyshark App│                  │ Gimbals   │        └──────────┘
│  Qt6 + Lua   │                  │ Switches  │
└──────────────┘                  │ Pots      │
                                  └───────────┘
```

## Documentation

### Protocol

- **[UMBUS Protocol Specification](docs/protocol/umbus-protocol.md)** — Complete frame format, timing, field maps for all 8 frame types
- **[Checksum Investigation](docs/protocol/checksum-investigation.md)** — CRC-8/MAXIM algorithm with per-type init values
- **[ELRS Telemetry Analysis](docs/protocol/elrs-telemetry-analysis.md)** — RF link quality frames embedded in UMBUS
- **[CRSF Protocol Reference](docs/protocol/crsf-reference.md)** — Crossfire/ELRS serial protocol quick reference

### Hardware

- **[Hardware Map](docs/hardware/hardware-map.md)** — Architecture, physical controls, sensors, peripherals, channel mapping
- **[Device Tree Analysis](docs/hardware/device-tree.md)** — SoC peripherals: UARTs, SPI, I2C, GPIO, sensors
- **[System Audit](docs/hardware/system-audit.md)** — Partitions, kernel modules, device nodes, sysfs
- **[AT32F435 MCU](docs/hardware/at32-mcu.md)** — RC microcontroller: role, specs, firmware, SWD debug access
- **[ELRS Backpack](docs/hardware/elrs-backpack.md)** — ESP backpack chip: WiFi MAVLink, VTX sync, OTA, switch expansion
- **[MT8788 Platform Research](docs/hardware/mt8788-research.md)** — SoC findings: kernel, drivers, optimization targets

### Software

- **[Native Library Analysis](docs/software/native-lib-analysis.md)** — 25MB .so reverse engineering: 250+ classes, UMBUS engine, CRSF engine
- **[Lua API Reference](docs/software/lua-api.md)** — Embedded Lua 5.3 VM with LVGL bindings and EdgeTX-compatible API
- **[Flyshark App Analysis](docs/software/flyshark-app.md)** — Qt6/QML app architecture, serial port usage, model storage format

### Guides

- **[Getting Started](docs/guides/getting-started.md)** — Setup guide for AX12 protocol exploration and tool usage
- **[Root & Setup Guide](docs/guides/root-guide.md)** — Install Termux, Tailscale, Claude Code, get root access
- **[Capture Session Guide](docs/guides/capture-session-guide.md)** — Record structured strace sessions for protocol analysis
- **[MAVLink Telemetry Setup](docs/guides/mavlink-setup.md)** — End-to-end ELRS MAVLink on AX12 with QGC or ATAK
- **[HDMI Latency Optimization](docs/guides/latency-optimization.md)** — Reducing glass-to-glass latency on HDMI input
- **[USB OTG Testing](docs/guides/usb-otg-testing.md)** — Enable USB host mode for peripherals via sysfs
- **[Tool Usage Guide](docs/guides/tool-usage.md)** — Comprehensive reference for every tool in `tools/`
- **[Security Hardening](docs/guides/security-hardening.md)** — Mitigating factory root, open ADB, and known CVEs

## Quick Start

**Read the protocol spec:**
Start with [UMBUS Protocol Specification](docs/protocol/umbus-protocol.md) for the full frame format, then [Hardware Map](docs/hardware/hardware-map.md) for the system architecture.

**Run the tools:**
```bash
# Parse UMBUS frames from a strace capture
python3 tools/strace-parser.py captures/idle-strace.txt

# Validate CRC checksums across a capture
python3 tools/umbus.py captures/idle-frames.bin
```

**Capture your own data:**
Follow the [Capture Session Guide](docs/guides/capture-session-guide.md) to record strace sessions from a rooted AX12, then parse with `strace-parser.py`.

## Tools

All Python tools are Python 3.13, stdlib only — no external dependencies.

### Protocol analysis

| Tool | Description |
|------|-------------|
| [`umbus.py`](tools/umbus.py) | UMBUS protocol library — parse, encode, validate, and analyze frames |
| [`strace-parser.py`](tools/strace-parser.py) | Extract and decode UMBUS frames from strace output |
| [`monitor.py`](tools/monitor.py) | Live channel visualization with color-coded delta tracking |
| [`simulator.py`](tools/simulator.py) | Synthetic UMBUS traffic generator for offline testing |
| [`elrs_decoder.py`](tools/elrs_decoder.py) | ELRS telemetry frame decoder |

### Capture and mapping

| Tool | Description |
|------|-------------|
| [`capture-session.py`](tools/capture-session.py) | Structured control input recording with operator guidance |
| [`batch-capture.py`](tools/batch-capture.py) | Non-interactive batch capture — timed prompts, no keyboard input |
| [`calibrator.py`](tools/calibrator.py) | 3-phase control surface calibration and axis mapping |
| [`live-mapper.py`](tools/live-mapper.py) | Interactive real-time control-to-channel mapping |
| [`model_tool.py`](tools/model_tool.py) | Model file (.rcm) listing, backup, and inspection |
| [`model_diff.py`](tools/model_diff.py) | Model file hex diff and binary analysis |

### Dashboard and visualization

| Tool | Description |
|------|-------------|
| [`live_dashboard.py`](tools/live_dashboard.py) | Web-based real-time UMBUS dashboard via SSE |
| [`umbus_server.py`](tools/umbus_server.py) | SSE broadcast server for UMBUS frames |
| [`build-dashboard.py`](tools/build-dashboard.py) | Generate self-contained HTML protocol dashboard |

### Device and hardware

| Tool | Description |
|------|-------------|
| [`fm_radio.py`](tools/fm_radio.py) | FM radio controller via MT6631 ioctl interface |
| [`gps_tool.py`](tools/gps_tool.py) | GPS position reader via Android location services |
| [`usb_otg.py`](tools/usb_otg.py) | USB OTG host/device mode switcher via sysfs |
| [`optimize.py`](tools/optimize.py) | Safe performance optimizer — bloatware, governor, camera tuning |
| [`latency-test.py`](tools/latency-test.py) | HDMI pipeline latency measurement via frame timestamp comparison |
| [`device_health.py`](tools/device_health.py) | Diagnostic check across device subsystems |
| [`system_test.py`](tools/system_test.py) | Automated pre-demo verification suite |
| [`firewall.sh`](tools/firewall.sh) | iptables firewall rules — block telemetry, restrict inbound |

### Experimental (need physical verification)

| Tool | Description |
|------|-------------|
| [`usb_gamepad.py`](tools/usb_gamepad.py) | USB HID gamepad via ConfigFS — untested with physical USB connection |
| [`cot_bridge.py`](tools/cot_bridge.py) | MAVLink-to-CoT bridge for ATAK — not tested end-to-end |
| [`mavlink_bridge.py`](tools/mavlink_bridge.py) | MAVLink WiFi bridge for QGC/Mission Planner |
| [`imu_tracker.py`](tools/imu_tracker.py) | IMU reader — blocked by broken sensor HAL in current firmware |

## Key Findings

### Protocol (confirmed from strace captures)

**UMBUS Protocol Decoded.** Eight frame types identified, timed, and field-mapped. The MCU sends channel data at 25 Hz, heartbeats at 4 Hz, ELRS telemetry at 5 Hz, and extended status at ~3 Hz. The app responds with polling, heartbeat acks, and config at 0.5-2 Hz. Total bandwidth: ~2.4 KB/s on a 921.6 kbps link (~2% utilization). Full spec: [UMBUS Protocol](docs/protocol/umbus-protocol.md).

**Per-Type CRC Init Values.** The checksum is CRC-8/MAXIM (poly 0x31), but different frame types use different init values — 0x00 for most, 0x7F for type 0x10, 0x32 for type 0x15. This was the key to achieving 100% checksum validation across all captures. Details: [Checksum Investigation](docs/protocol/checksum-investigation.md).

**33 Output Channels.** The system supports 33 channels (CH00-CH32) with per-channel reverse, slow motion, min/max limits, curves, dual rates, and multi-source mixing. Every gimbal axis, switch, pot, and the 6-position selector have been mapped to their UMBUS byte offsets.

**MCU Operates Autonomously.** The AT32 MCU broadcasts all four frame types at their documented rates even when the Flyshark app is not running. No app handshake is required. Confirmed with a standalone capture (captures/umbus-mcu-standalone.bin).

### Hardware (confirmed on device)

**AT32F435 MCU Identified.** The RC microcontroller is an Artery AT32F435 (Cortex-M4F, 288 MHz) — pin-compatible with the STM32F405 but different silicon. It owns all physical inputs, ADC sampling, GPIO debounce, and SPI/UART to the ELRS LR1121 RF module. The Android SoC never touches hardware directly; everything is mediated through UMBUS. Details: [AT32F435 MCU](docs/hardware/at32-mcu.md).

**Complete I2C Device Map.** 28 devices across 7 I2C buses fully enumerated: IT66121 HDMI 1.4 transmitter (output), RT5509 Class-D speaker amp, RT9465 charger, MT6370 sub-PMIC with USB-C TCPC, ICM-42607 IMU, and 14 phantom entries from the MT8788 reference design. Details: [Hardware Map](docs/hardware/hardware-map.md).

**Factory Root.** The AX12 ships with a SUID root binary at `/system/xbin/su` — no exploit required. The build is `userdebug` with `test-keys` and SELinux in permissive mode. Setup: [Root Guide](docs/guides/root-guide.md).

**Model Configuration Format.** Model configs are stored as flat binary `.rcm` files with Unix timestamp filenames. Header (magic, timestamps, name), config section (trims, rates, curves), and variable-length endpoint section (mixer entries, travel limits) substantially decoded. Details: [Hardware Map](docs/hardware/hardware-map.md).

### Software (from code analysis and on-device observation)

**Lua VM with LVGL.** The AX12 embeds Lua 5.3 with a NodeMCU-lineage ROM table patch and three custom C modules: `bitmap` (LCD rendering), `etxdir` (filesystem), and `lvgl` (full LVGL UI framework). Scripts follow EdgeTX conventions. The serial bridge `luaSetGetSerialByte()` exists but is a dead stub on AX12. Reference: [Lua API](docs/software/lua-api.md).

**Flyshark Three-Transport Architecture.** The native library (25MB, 13,000+ symbols) supports three communication transports — UART (primary, to MCU), TCP (network, for simulators), and USB-HID (direct PC connection) — all using UMBUS protocol. The app includes a ground control station with offline maps, terrain data, mission planning, RTSP video, and gimbal control. Analysis based on strings/readelf, no decompilation. Analysis: [Flyshark App](docs/software/flyshark-app.md).

**ELRS Backpack.** The AX12 includes an ELRS backpack chip (ESP8285/ESP32-C3) on ttyS1 at 460800 baud. Per ExpressLRS documentation, firmware v1.5.0+ can create a WiFi AP and forward MAVLink telemetry via UDP on port 14550. Not yet tested end-to-end on AX12. Details: [ELRS Backpack](docs/hardware/elrs-backpack.md).

### HDMI pipeline (partially confirmed)

**HDMI Latency Root Cause.** The RN6752M video decoder is registered as a camera sensor in MediaTek's HAL, routing HDMI input through the full ISP pipeline — 22+ tuning libraries for HDR, noise reduction, 3A, and face detection. Baseline latency measured at ~140ms. Phase 1 optimizations (disable CZ/DRE, VSync phase zeroing) saved 10-15ms. Further optimizations (Direct Link mode, CAMSV DMA bypass) are identified but untested. Details: [Latency Optimization](docs/guides/latency-optimization.md).

### Untested / theoretical

**USB OTG Host Mode.** Sysfs controls for host GPIO, MUSB cmode, and dual_role mode are present and respond to writes. All USB class drivers (hub, HID, mass storage, audio, ethernet) are loaded in the stock kernel. Needs physical testing with a USB-C OTG adapter to confirm device enumeration, VBUS sourcing, and data transfer. Tool: [`usb_otg.py`](tools/usb_otg.py), guide: [USB OTG Testing](docs/guides/usb-otg-testing.md).

**OpenIPC FPV.** The PixelPilot Android app could theoretically turn the AX12 into an OpenIPC ground station via USB OTG + RTL8812AU dongle. Depends on USB OTG host mode working (untested). Details: [OpenIPC FPV](docs/hardware/openipc-fpv.md).

**Cellular Modem.** The MT8788 baseband processor runs MOLY firmware and is configured for LTE. 21 cellular network interfaces exist but are inactive — no SIM slot or antenna is populated on the AX12 PCB. Hardware modification would be required.

## Device Specifications

| Component | Detail |
|-----------|--------|
| SoC | MediaTek MT8788 (4x Cortex-A73 @ 2.0 GHz + 4x Cortex-A53 @ 2.0 GHz), TSMC 12nm |
| GPU | Mali-G72 MP3 (Bifrost), 700 MHz |
| MCU | AT32F435 (Artery Tek) — Cortex-M4F @ 288 MHz, handles gimbals, switches, RF module |
| Kernel | Linux 4.4.146, Android 9 (Pie), userdebug build. **Android cannot be updated.** |
| RAM | 4 GB (1 GB ZRAM swap) |
| Storage | 64 GB eMMC, 38 partitions |
| Display | 5.5" 1280x720 IPS touchscreen, 1000 nits max brightness |
| Battery | Dual 3.7V 21700 Li-ion, 10,000 mAh total, non-removable. USB PD charging up to 20W. |
| RF | ELRS internal (Semtech LR1121), 250 mW / 24 dBm max, 2.4 GHz or 868/915 MHz (not simultaneous, no Gemini-X), 2 dBi antenna |
| Module Bay | Nano module bay (top edge) for external RF modules |
| Gimbals | X5 Hall-Effect, 4 axes, removable/storable, upgradeable to AG01 Nano |
| Sensors | ICM-42607 6-axis IMU, magnetometer, GPS (no antenna populated) |
| Connectivity | WiFi, Bluetooth, FM radio. No SIM slot, no camera. |
| Video In | Mini HDMI input → Richnano RN6752M (HDMI-to-MIPI CSI-2), 720p/1080p up to 60 Hz, ~140ms latency |
| Video Out | Mini HDMI output (IT66121 bridge), mirrors Android display |
| Weight | 640g claimed / 649g measured |
| Dimensions | 171 × 168 × 73 mm |
| Boot time | ~40 seconds |
| Price | $249.99 USD |

## Project Status

**What's solid:** The idle-state UMBUS protocol is fully decoded — all 8 frame types, timing, CRC checksums, and 33 channel mappings are documented and validated from real captures. Hardware has been enumerated via device tree, I2C scans, and sysfs. The native library has been analyzed via strings/readelf (no decompilation). 33 Lua scripts and 40+ Python tools have been written.

**What's next:** Non-idle captures (binding, flying, trainer mode), App-to-MCU command protocol semantics, ELRS telemetry field mapping, and physical testing of USB OTG host mode. See [ROADMAP.md](ROADMAP.md) for the full list.

**What needs verification:** Several tools and integrations have been written but not tested end-to-end on the physical device. These are marked as "Experimental" in the tools table and "Theoretical" in the discoveries table above.

## Methodology

Protocol data was captured via `strace` on the running Flyshark app — observing the app's own serial I/O without interfering with it. Frame structures, timing, and constants were derived from these passive captures. Native library analysis used `strings` and `readelf` on the extracted `.so` — symbol names and printable strings only, no decompilation.

All tools run on the device itself using Python 3.13 and the standard library only.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on submitting captures, reporting protocol findings, and code style.

## License

[MIT](LICENSE) -- Kyle Adomavicius
