# RadioMaster AX12 — Reverse Engineering Reference

Independent hardware research on the RadioMaster AX12 RC transmitter. No manufacturer documentation exists for these internals. Everything here came from a stock device — passive `strace` captures on the running app, symbol-level binary analysis, and on-device probing. No firmware was modified.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.13](https://img.shields.io/badge/python-3.13-yellow.svg)
![Platform: Android 9](https://img.shields.io/badge/platform-Android%209-green.svg)

## Architecture

The AX12 pairs a MediaTek MT8788 SoC running Android 9 with an AT32F435 coprocessor that owns all physical I/O. The two communicate over UMBUS — a proprietary serial protocol at 921600 baud.

```
┌──────────────┐  UART @ 921600   ┌───────────┐  CRSF  ┌──────────┐
│  MT8788 SoC  │◄───── UMBUS ────►│  AT32 MCU │◄──────►│ ELRS TX  │
│  Android 9   │                  │  AT32F435 │        │ (LR1121) │
│  Flyshark    │                  │           │        └──────────┘
│  Qt6 + Lua   │                  │ Gimbals   │
└──────────────┘                  │ Switches  │
                                  │ Pots/Trims│
                                  └───────────┘
```

The Android side runs Flyshark, a Qt6/QML application with an embedded Lua 5.3 VM. The MCU handles hall-effect gimbals, switches, pots, trims, and drives the ELRS LR1121 RF module over CRSF.

## Key Findings

**UMBUS protocol fully decoded.** Eight frame types, field-mapped and timed. MCU sends channel data at 25 Hz, heartbeats at 4 Hz, ELRS telemetry at 5 Hz. The checksum is CRC-8/MAXIM with per-type init values — the insight that got us to 100% validation. [Protocol spec →](docs/protocol/umbus-protocol.md)

**33 output channels** with per-channel reverse, curves, dual rates, and mixing. Every physical control mapped to its UMBUS byte offset. [Hardware map →](docs/hardware/hardware-map.md)

**MCU operates autonomously.** The AT32 broadcasts all frame types at documented rates with or without the app running. No handshake required.

**Factory root.** Ships with SUID `su`, `userdebug` build, SELinux permissive. No exploit needed. [Root guide →](docs/guides/root-guide.md)

**Undocumented hardware.** FM tuner (MT6631, functional), HDMI video input via RN6752M, IMU (ICM-42607, driver broken in current firmware), USB OTG support in sysfs, dormant LTE baseband with no SIM slot. The MT6631 also carries a GNSS core and the GPS software stack runs — but **no antenna is populated**, so it acquires zero satellites and is unusable without a hardware mod (see hardware map). None of it is exposed by the stock UI. [Hardware map →](docs/hardware/hardware-map.md)

**25MB native library analyzed.** 13,000+ dynamic symbols. Three communication transports (UART, TCP, USB-HID), Lua 5.3 VM with LVGL bindings, ground control station with offline maps. Analysis via strings/readelf — no decompilation. [Analysis →](docs/software/native-lib-analysis.md)

## Quick Start

```bash
# Parse UMBUS frames from a strace capture
python3 tools/strace-parser.py captures/idle-strace.txt

# Validate CRC checksums
python3 tools/umbus.py captures/idle-frames.bin

# Generate synthetic traffic for offline testing
python3 tools/simulator.py generate --seconds 5
```

On a rooted AX12, see the [Capture Session Guide](docs/guides/capture-session-guide.md) to record your own data.

## Documentation

### Protocol
- [UMBUS Protocol](docs/protocol/umbus-protocol.md) — Frame format, timing, field maps
- [Checksum Investigation](docs/protocol/checksum-investigation.md) — CRC-8/MAXIM, per-type init values
- [ELRS Telemetry](docs/protocol/elrs-telemetry-analysis.md) — RF link quality over UMBUS
- [CRSF Reference](docs/protocol/crsf-reference.md) — Crossfire serial protocol

### Hardware
- [Hardware Map](docs/hardware/hardware-map.md) — Architecture, controls, sensors, peripherals
- [AT32F435 MCU](docs/hardware/at32-mcu.md) — Coprocessor role, firmware, SWD access
- [Device Tree](docs/hardware/device-tree.md) — SoC peripherals from decompiled DTS
- [System Audit](docs/hardware/system-audit.md) — Partitions, kernel modules, device nodes
- [ELRS Backpack](docs/hardware/elrs-backpack.md) — ESP backpack, WiFi MAVLink, OTA
- [MT8788 Research](docs/hardware/mt8788-research.md) — Platform internals
- [Peripheral Exploration](docs/peripheral-exploration.md) — IMU, SPI1, Bluetooth, LEDs, modem, and 12 other subsystems

### Software
- [Native Library](docs/software/native-lib-analysis.md) — 25MB `.so` reverse engineering
- [Lua API](docs/software/lua-api.md) — Lua 5.3 VM, LVGL, EdgeTX API
- [Flyshark App](docs/software/flyshark-app.md) — Qt6/QML architecture, model format

### Guides
- [Getting Started](docs/guides/getting-started.md) — Setup and first capture
- [Developer Quick Start](docs/DEVELOPER_QUICKSTART.md) — SSH, tools, Lua development
- [Root Guide](docs/guides/root-guide.md) — Termux, Tailscale, root access
- [Capture Sessions](docs/guides/capture-session-guide.md) — Recording strace data
- [Tool Reference](docs/guides/tool-usage.md) — All tools with usage examples

## Tools

40+ Python tools, stdlib only. No external dependencies.

| Tool | Purpose |
|------|---------|
| `umbus.py` | Protocol library — parse, encode, validate |
| `strace-parser.py` | Extract UMBUS frames from strace output |
| `monitor.py` | Live TUI channel viewer |
| `calibrator.py` | Control surface calibration |
| `live_dashboard.py` | Web-based real-time dashboard |
| `simulator.py` | Synthetic traffic generator |
| `system_test.py` | Automated diagnostic suite |
| `fm_radio.py` | FM radio control |
| `gps_tool.py` | Location reader (Android network/fused position — GNSS unusable, no antenna populated) |

Full list: [`tools/README.md`](tools/README.md)

### Tactical Tools

Operational tools (ATAK/CoT bridges, MAVLink integration, airspace awareness, Lua tactical widgets) are in a separate repo: [`ax12-tac-tools`](https://github.com/rmeadomavic/ax12-tac-tools)

## Specifications

| | |
|---|---|
| **SoC** | MediaTek MT8788 — 4×A73 + 4×A53 @ 2.0 GHz, 12nm |
| **MCU** | AT32F435 — Cortex-M4F @ 288 MHz |
| **RF** | ELRS (LR1121), 250 mW, 2.4 GHz / sub-GHz |
| **Display** | 5.5" 1280×720 IPS, 1000 nits |
| **Battery** | Dual 21700, 10 Ah, USB PD 20W |
| **Gimbals** | Hall-effect, 4-axis, removable |
| **Video In** | Mini HDMI → RN6752M → CSI-2, up to 1080p60 |
| **Kernel** | Linux 4.4.146, Android 9 |
| **Storage** | 64 GB eMMC |
| **Weight** | 649 g |

## Status

The idle-state protocol is solid — fully decoded, CRC-validated, and tooled. Hardware is enumerated. The native library is mapped at the symbol level.

Open targets: non-idle captures (binding, flying, trainer), app-to-MCU command semantics, ELRS telemetry field mapping, USB OTG physical testing. See [ROADMAP.md](ROADMAP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Highest-value contributions right now: captures from non-idle states, ELRS telemetry field identification, and physical USB OTG testing.

## License

[MIT](LICENSE) — Kyle Adomavicius
