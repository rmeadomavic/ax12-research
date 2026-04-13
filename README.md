# RadioMaster AX12 — Reverse Engineering Reference

Community-built technical reference for the RadioMaster AX12, an Android-based RC transmitter. Everything here was reverse-engineered from a stock device — no manufacturer documentation exists for these internals.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.13](https://img.shields.io/badge/python-3.13-yellow.svg)
![Platform: Android 9](https://img.shields.io/badge/platform-Android%209-green.svg)

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

### Hardware

- **[Hardware Map](docs/hardware/hardware-map.md)** — Architecture, physical controls, sensors, peripherals, channel mapping
- **[Device Tree Analysis](docs/hardware/device-tree.md)** — SoC peripherals: UARTs, SPI, I2C, GPIO, sensors
- **[System Audit](docs/hardware/system-audit.md)** — Partitions, kernel modules, device nodes, sysfs

### Software

- **[Native Library Analysis](docs/software/native-lib-analysis.md)** — 25MB .so reverse engineering: 250+ classes, UMBUS engine, CRSF engine
- **[Lua API Reference](docs/software/lua-api.md)** — Embedded Lua 5.3 VM with LVGL bindings and EdgeTX-compatible API

### Guides

- **[Root & Setup Guide](docs/guides/root-guide.md)** — Install Termux, Tailscale, Claude Code, get root access
- **[Capture Session Guide](docs/guides/capture-session-guide.md)** — Record structured strace sessions for protocol analysis

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

All tools are Python 3.13, stdlib only — no external dependencies.

| Tool | Description |
|------|-------------|
| [`umbus.py`](tools/umbus.py) | UMBUS protocol library — parse, encode, validate, and analyze frames |
| [`monitor.py`](tools/monitor.py) | Live channel visualization with color-coded delta tracking |
| [`strace-parser.py`](tools/strace-parser.py) | Extract and decode UMBUS frames from strace output |
| [`calibrator.py`](tools/calibrator.py) | 3-phase control surface calibration and axis mapping |
| [`capture-session.py`](tools/capture-session.py) | Structured control input recording with operator guidance |
| [`live-mapper.py`](tools/live-mapper.py) | Interactive real-time control-to-channel mapping |
| [`fm_radio.py`](tools/fm_radio.py) | FM radio controller via MT6631 ioctl interface |
| [`umbus_server.py`](tools/umbus_server.py) | SSE broadcast server for UMBUS frames |
| [`build-dashboard.py`](tools/build-dashboard.py) | Generate self-contained HTML protocol dashboard |

## Key Findings

**UMBUS Protocol Decoded.** Eight frame types identified, timed, and field-mapped. The MCU sends channel data at 25 Hz, heartbeats at 4 Hz, ELRS telemetry at 5 Hz, and extended status at ~3 Hz. The app responds with polling, heartbeat acks, and config at 0.5-2 Hz. Total bandwidth: ~2.4 KB/s on a 921.6 kbps link (~2% utilization). Full spec: [UMBUS Protocol](docs/protocol/umbus-protocol.md).

**Per-Type CRC Init Values.** The checksum is CRC-8/MAXIM (poly 0x31), but different frame types use different init values — 0x00 for most, 0x7F for type 0x10, 0x32 for type 0x15. This was the key to achieving 100% checksum validation across all captures. Details: [Checksum Investigation](docs/protocol/checksum-investigation.md).

**33 Output Channels.** The system supports 33 channels (CH00-CH32) with per-channel reverse, slow motion, min/max limits, curves, dual rates, and multi-source mixing. Every gimbal axis, switch, pot, and the 6-position selector have been mapped to their UMBUS byte offsets.

**Model Configuration Format.** Model configs are stored as flat binary `.rcm` files with Unix timestamp filenames. The native library exposes `loadModelCfgFile()`, `QML_Pack_RcModelData`, and `QML_Pack_RcModelCfgData` for serialization. Details: [Hardware Map](docs/hardware/hardware-map.md).

**Lua VM with LVGL.** The AX12 embeds Lua 5.3 with a NodeMCU-lineage ROM table patch and three custom C modules: `bitmap` (LCD rendering), `etxdir` (filesystem), and `lvgl` (full LVGL UI framework). Scripts follow EdgeTX conventions. The serial bridge `luaSetGetSerialByte()` exists but is a dead stub on AX12. Reference: [Lua API](docs/software/lua-api.md).

**FM Radio.** The MT6631 combo chip includes a fully functional FM radio tuner (87.5-108 MHz) accessible via `/dev/fm` ioctls. Uses the headphone cable as antenna. Tool: [`fm_radio.py`](tools/fm_radio.py).

**Factory Root.** The AX12 ships with a SUID root binary at `/system/xbin/su` — no exploit required. The build is `userdebug` with `test-keys` and SELinux in permissive mode. Setup: [Root Guide](docs/guides/root-guide.md).

## Device Specifications

| Component | Detail |
|-----------|--------|
| SoC | MediaTek MT8788 (4x Cortex-A53 + 4x Cortex-A73) |
| MCU | AT32 (Artery Tek) — handles gimbals, switches, RF module |
| Kernel | Linux 4.4.146, Android 9 (Pie), userdebug build |
| RAM | 4 GB (1 GB ZRAM swap) |
| Storage | 64 GB eMMC, 38 partitions |
| Display | 5.5" 1280x720 MIPI DSI touchscreen |
| Battery | 10,000 mAh |
| RF | ELRS internal (Semtech LR1121) + external module bay |
| Gimbals | X5 Hall-Effect, 4 axes, removable, upgradeable to AG01 |
| Sensors | ICM-42607 6-axis IMU, magnetometer, GPS (no antenna populated) |
| Connectivity | WiFi, Bluetooth, FM radio, HDMI out (IT66121 bridge) |
| Video In | Richnano RN6752M analog decoder (HDMI-to-MIPI CSI-2) |

## Project Status

The idle protocol is fully decoded — all 8 frame types, timing, checksums, and channel mappings are documented. Major remaining work: non-idle captures (binding, flying, trainer mode), App-to-MCU command protocol, and ELRS telemetry field identification. See [ROADMAP.md](ROADMAP.md) for the full list.

## Methodology

Protocol data was captured via `strace` on the running Flyshark app — observing the app's own serial I/O without interfering with it. Frame structures, timing, and constants were derived from these passive captures. Native library analysis used `strings` and `readelf` on the extracted `.so` — symbol names and printable strings only, no decompilation.

All tools run on the device itself using Python 3.13 and the standard library only.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on submitting captures, reporting protocol findings, and code style.

## License

[MIT](LICENSE) -- Kyle Adomavicius
