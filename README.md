# RadioMaster AX12 — Reverse Engineering Reference

Community-built technical reference for the RadioMaster AX12, an Android-based RC transmitter. Everything here was reverse-engineered from a stock device — no manufacturer documentation exists for these internals.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.13](https://img.shields.io/badge/python-3.13-yellow.svg)
![Platform: Android 9](https://img.shields.io/badge/platform-Android%209-green.svg)

## What You Didn't Know Your AX12 Could Do

RadioMaster put a phone-grade SoC into a transmitter and barely scratched the surface. Here is what is hiding inside.

**Your transmitter has GPS.** The MT6631 combo chip includes a multi-constellation GNSS receiver (GPS + GLONASS + BeiDou, 19 satellites observed). No review has ever mentioned this. Your drone controller knows where you are.

**It can be a USB gamepad.** The kernel has USB HID compiled in. Plug the AX12 into any PC and it shows up as a native gamepad -- 4 axes, 12 buttons, zero drivers. Use your actual gimbals in Velocidrone, Liftoff, or DRL Sim.

**It runs DOOM.** Chocolate Doom on the touchscreen, controlled by your gimbals. Right stick moves, left stick strafes, SA fires.

**It has an FM radio.** The MT6631 includes an FM receiver (87.5-108 MHz). Tune stations, scan the band, check signal strength -- all from Python.

**It streams to ATAK.** The CoT bridge reads GPS position and sends Cursor-on-Target XML over UDP. Your transmitter becomes a node on the TAK map.

**It has a 9-axis IMU.** ICM-42607 with 400Hz gyro, 125Hz accel, 50Hz magnetometer. Head tracking, motion sensing, attitude reference.

**It has an AI accelerator.** MediaTek VPU/APU with NNAPI. On-device neural network inference.

**It has HDMI output.** ITE IT66121 transmitter mirrors the screen to any display.

**It runs Meshtastic.** Install the app, pair a node, join the mesh network. Combined with CoT, pilot position goes over LoRa to the whole team.

**14 Lua scripts ready to run.** CCIP targeting reticle, TAK-style HUD, compass, race timer, mission timer, MGRS converter, pre-flight checklist, VTx channel manager, FPV simulator, and more.

**Full UMBUS protocol decoded.** 8 frame types, CRC-8/MAXIM checksums with per-type init values, 33 channels mapped. This is the foundation everything builds on.

All tools are Python stdlib only. All Lua scripts follow EdgeTX conventions. Everything runs on-device.

## New Discoveries

Hardware capabilities found through reverse engineering that are not documented by RadioMaster or mentioned in any review.

| Discovery | Status | Details |
|-----------|--------|---------|
| **GPS Receiver** | Confirmed working | MT6631 GNSS: GPS + GLONASS + BeiDou, 19 satellites, 13m accuracy. Hidden behind Android location services -- no UI exposes it. |
| **FM Radio** | Chip responds, antenna TBD | MT6631 FM tuner (87.5-108 MHz). Full ioctl control working. Headphone antenna path may not be wired on AX12 PCB -- needs hardware investigation. |
| **USB HID Gamepad** | Ready to deploy | Kernel has CONFIG_USB_F_HID=y. ConfigFS hid.gs0 function pre-created at boot. Init RC has property trigger. |
| **AI Accelerator** | Hardware confirmed | MediaTek VPU/APU with NNAPI HAL service running and 33MB ION memory allocated. |
| **9-DOF IMU** | Hardware confirmed | ICM-42607: 400Hz gyro, 125Hz accel, 50Hz magnetometer. Accessible via Android SensorManager. |
| **HDMI Output** | Hardware confirmed | ITE IT66121 HDMI 1.4 transmitter on I2C. Driver loaded, currently disabled in software. |
| **Miracast** | Works | WiFi Display enabled, P2P discovery functional. Successfully found LG TV on network. |
| **Analog Video Decoder** | Registered as camera | RN6752M decodes CVBS/AHD to 1080p MIPI CSI-2. HDMI input may route through inline converter -- needs physical test. |
| **LTE Modem** | Silicon present | MT8788 baseband active, 21 ccmni interfaces, MOLY firmware running. No SIM slot or antenna populated. |
| **NFC** | Not present | Software stack exists but chip not populated on PCB. Hardware modification required. |
| **Lua 5.3 VM** | Fully functional | EdgeTX-derived with LVGL widgets, touch events, serial I/O, shared memory IPC. Custom AX12 extensions (getShmVar/setShmVar). |
| **Factory Root** | Confirmed | Ships with SUID su binary, userdebug build, SELinux permissive. No exploit needed. |

These findings apply to firmware K908-V2.0-XY8788WA. Other firmware versions may differ.



## New Discoveries

Hardware capabilities found through reverse engineering that are not documented by RadioMaster or mentioned in any review.

| Discovery | Status | Details |
|-----------|--------|---------|
| **GPS Receiver** | Confirmed working | MT6631 GNSS: GPS + GLONASS + BeiDou, 19 satellites, 13m accuracy. Hidden behind Android location services -- no UI exposes it. |
| **FM Radio** | Chip responds, antenna TBD | MT6631 FM tuner (87.5-108 MHz). Full ioctl control working. Headphone antenna path may not be wired on AX12 PCB -- needs hardware investigation. |
| **USB HID Gamepad** | Ready to deploy | Kernel has CONFIG_USB_F_HID=y. ConfigFS hid.gs0 function pre-created at boot. Init RC has property trigger. |
| **AI Accelerator** | Hardware confirmed | MediaTek VPU/APU with NNAPI HAL service running and 33MB ION memory allocated. |
| **9-DOF IMU** | Hardware confirmed | ICM-42607: 400Hz gyro, 125Hz accel, 50Hz magnetometer. Accessible via Android SensorManager. |
| **HDMI Output** | Hardware confirmed | ITE IT66121 HDMI 1.4 transmitter on I2C. Driver loaded, currently disabled in software. |
| **Miracast** | Works | WiFi Display enabled, P2P discovery functional. Successfully found LG TV on network. |
| **Analog Video Decoder** | Registered as camera | RN6752M decodes CVBS/AHD to 1080p MIPI CSI-2. HDMI input may route through inline converter -- needs physical test. |
| **LTE Modem** | Silicon present | MT8788 baseband active, 21 ccmni interfaces, MOLY firmware running. No SIM slot or antenna populated. |
| **NFC** | Not present | Software stack exists but chip not populated on PCB. Hardware modification required. |
| **Lua 5.3 VM** | Fully functional | EdgeTX-derived with LVGL widgets, touch events, serial I/O, shared memory IPC. Custom AX12 extensions (getShmVar/setShmVar). |
| **Factory Root** | Confirmed | Ships with SUID su binary, userdebug build, SELinux permissive. No exploit needed. |

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

| Tool | Description |
|------|-------------|
| [`umbus.py`](tools/umbus.py) | UMBUS protocol library — parse, encode, validate, and analyze frames |
| [`monitor.py`](tools/monitor.py) | Live channel visualization with color-coded delta tracking |
| [`strace-parser.py`](tools/strace-parser.py) | Extract and decode UMBUS frames from strace output |
| [`calibrator.py`](tools/calibrator.py) | 3-phase control surface calibration and axis mapping |
| [`capture-session.py`](tools/capture-session.py) | Structured control input recording with operator guidance |
| [`batch-capture.py`](tools/batch-capture.py) | Non-interactive batch capture — timed prompts, no keyboard input |
| [`live-mapper.py`](tools/live-mapper.py) | Interactive real-time control-to-channel mapping |
| [`live_dashboard.py`](tools/live_dashboard.py) | Web-based real-time UMBUS dashboard via SSE |
| [`simulator.py`](tools/simulator.py) | Synthetic UMBUS traffic generator for offline testing |
| [`umbus_server.py`](tools/umbus_server.py) | SSE broadcast server for UMBUS frames |
| [`build-dashboard.py`](tools/build-dashboard.py) | Generate self-contained HTML protocol dashboard |
| [`cot_bridge.py`](tools/cot_bridge.py) | MAVLink-to-CoT bridge for ATAK integration |
| [`test_cot.py`](tools/test_cot.py) | CoT test sender — verify ATAK connectivity |
| [`fm_radio.py`](tools/fm_radio.py) | FM radio controller via MT6631 ioctl interface |
| [`usb_otg.py`](tools/usb_otg.py) | USB OTG host/device mode switcher via sysfs |
| [`optimize.py`](tools/optimize.py) | Safe performance optimizer — bloatware, governor, camera tuning |
| [`latency-test.py`](tools/latency-test.py) | HDMI pipeline latency measurement via frame timestamp comparison |
| [`firewall.sh`](tools/firewall.sh) | iptables firewall rules — block telemetry, restrict inbound |

## Key Findings

**UMBUS Protocol Decoded.** Eight frame types identified, timed, and field-mapped. The MCU sends channel data at 25 Hz, heartbeats at 4 Hz, ELRS telemetry at 5 Hz, and extended status at ~3 Hz. The app responds with polling, heartbeat acks, and config at 0.5-2 Hz. Total bandwidth: ~2.4 KB/s on a 921.6 kbps link (~2% utilization). Full spec: [UMBUS Protocol](docs/protocol/umbus-protocol.md).

**Per-Type CRC Init Values.** The checksum is CRC-8/MAXIM (poly 0x31), but different frame types use different init values — 0x00 for most, 0x7F for type 0x10, 0x32 for type 0x15. This was the key to achieving 100% checksum validation across all captures. Details: [Checksum Investigation](docs/protocol/checksum-investigation.md).

**33 Output Channels.** The system supports 33 channels (CH00-CH32) with per-channel reverse, slow motion, min/max limits, curves, dual rates, and multi-source mixing. Every gimbal axis, switch, pot, and the 6-position selector have been mapped to their UMBUS byte offsets.

**Model Configuration Format.** Model configs are stored as flat binary `.rcm` files with Unix timestamp filenames. The native library exposes `loadModelCfgFile()`, `QML_Pack_RcModelData`, and `QML_Pack_RcModelCfgData` for serialization. Details: [Hardware Map](docs/hardware/hardware-map.md).

**Lua VM with LVGL.** The AX12 embeds Lua 5.3 with a NodeMCU-lineage ROM table patch and three custom C modules: `bitmap` (LCD rendering), `etxdir` (filesystem), and `lvgl` (full LVGL UI framework). Scripts follow EdgeTX conventions. The serial bridge `luaSetGetSerialByte()` exists but is a dead stub on AX12. Reference: [Lua API](docs/software/lua-api.md).

**FM Radio.** The MT6631 combo chip includes a fully functional FM radio tuner (87.5-108 MHz) accessible via `/dev/fm` ioctls. Uses the headphone cable as antenna. Tool: [`fm_radio.py`](tools/fm_radio.py).

**AT32F435 MCU Identified.** The RC microcontroller is an Artery AT32F435 (Cortex-M4F, 288 MHz) — pin-compatible with the STM32F405 but different silicon. It owns all physical inputs, ADC sampling, GPIO debounce, and SPI/UART to the ELRS LR1121 RF module. The Android SoC never touches hardware directly; everything is mediated through UMBUS. Details: [AT32F435 MCU](docs/hardware/at32-mcu.md).

**USB OTG Host Mode via Sysfs.** The top USB-C port supports OTG host mode, toggled by writing to three MT8788 sysfs controls: host GPIO (VBUS power), MUSB cmode, and dual_role mode. This enables keyboards, GPS receivers, and flash drives without hardware modification. Tool: [`usb_otg.py`](tools/usb_otg.py), guide: [USB OTG Testing](docs/guides/usb-otg-testing.md).

**ELRS Backpack WiFi MAVLink.** The AX12 includes a dedicated ELRS backpack chip (ESP8285/ESP32-C3) that can create a WiFi AP and forward MAVLink telemetry via UDP on port 14550 (v1.5.0+). Any WiFi client — QGroundControl, ATAK, Mission Planner — can receive live vehicle telemetry without serial port access or root. This is the cleanest path to AX12-as-GCS. Details: [ELRS Backpack](docs/hardware/elrs-backpack.md).

**Flyshark Three-Transport Architecture.** The native library supports three communication transports — UART (primary, to MCU), TCP (network, for simulators), and USB-HID (direct PC connection) — all using UMBUS protocol. AUX and AUX2 serial modes are configurable, and the app includes a full ground control station with offline maps, terrain data, mission planning, RTSP video, and gimbal control. Analysis: [Flyshark App](docs/software/flyshark-app.md).

**Factory Root.** The AX12 ships with a SUID root binary at `/system/xbin/su` — no exploit required. The build is `userdebug` with `test-keys` and SELinux in permissive mode. Setup: [Root Guide](docs/guides/root-guide.md).


**HDMI Latency Root Cause.** The RN6752M video decoder is registered as a camera sensor (imgsensor) in MediaTek's HAL, routing all HDMI input through the full ISP pipeline — 22+ tuning libraries for HDR, noise reduction, 3A, and face detection. Camera FPS is capped at 30fps on a 56.4Hz display. The display dynamically switches between DIRECT_LINK (low latency) and DECOUPLE (high latency, triple-buffered) modes based on layer count. Five CAMSV DMA engines (0x1a050000-0x1a055000) are available for ISP bypass via kernel module. Details: [Latency Optimization](docs/guides/latency-optimization.md).

**MCU Operates Autonomously.** The AT32 MCU broadcasts all four frame types (channel data, heartbeat, ELRS telemetry, extended telemetry) at their documented rates even when the Flyshark app is not running. The MCU does not require an app handshake to start operating.

**Complete I2C Device Map.** 28 devices across 7 I2C buses fully enumerated: IT66121 HDMI 1.4 transmitter (output), RT5509 Class-D speaker amp, RT9465 charger, MT6370 sub-PMIC with USB-C TCPC, ICM-42607 IMU, and 14 phantom entries from the MT8788 reference design. Details: [Hardware Map](docs/hardware/hardware-map.md).

**Cellular Modem Present.** The MT8788 baseband processor runs MOLY firmware (MOLY.LR12A.R2.MP.V109.4) and is configured for LTE. 21 cellular network interfaces exist but are inactive — no SIM slot or antenna is populated on the AX12 PCB.

**OpenIPC FPV Compatibility.** The PixelPilot Android app (minSdk 26) can turn the AX12 into an OpenIPC FPV ground station via USB OTG + RTL8812AU WiFi dongle (~0). A known MediaTek libusb bug (issue #6) has a fix merged in PR #97. Details: [OpenIPC FPV](docs/hardware/openipc-fpv.md).

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

The idle protocol is fully decoded — all 8 frame types, timing, checksums, and channel mappings are documented. Major remaining work: non-idle captures (binding, flying, trainer mode), App-to-MCU command protocol, and ELRS telemetry field identification. See [ROADMAP.md](ROADMAP.md) for the full list.

## Methodology

Protocol data was captured via `strace` on the running Flyshark app — observing the app's own serial I/O without interfering with it. Frame structures, timing, and constants were derived from these passive captures. Native library analysis used `strings` and `readelf` on the extracted `.so` — symbol names and printable strings only, no decompilation.

All tools run on the device itself using Python 3.13 and the standard library only.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on submitting captures, reporting protocol findings, and code style.

## License

[MIT](LICENSE) -- Kyle Adomavicius
