# RadioMaster AX12 — Hardware Research & Developer Guide

Community-first reference for the RadioMaster AX12 Android RC radio. Everything here was reverse-engineered from the stock device — no manufacturer documentation exists for these internals.

## What is the AX12?

The RadioMaster AX12 is an Android 9-based RC transmitter built on a MediaTek MT8788 SoC. Unlike traditional RC radios with dedicated firmware, the AX12 runs a full Android OS with a Qt6/QML app ("Flyshark") that communicates with an AT32 microcontroller over a proprietary serial protocol called **UMBUS**.

The AT32 MCU handles all physical inputs (gimbals, switches, pots) and controls the ELRS RF module. The Android app handles the UI, mixer, telemetry display, maps, and configuration — then sends mixed channel data back to the MCU for transmission.

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

| Document | Description |
|----------|-------------|
| **[Root & Setup Guide](docs/root-guide.md)** | Install Termux, Tailscale, Claude Code CLI, get root access |
| **[Hardware Map](docs/hardware-map.md)** | Architecture overview, key classes, system specs |
| **[UMBUS Protocol](docs/umbus-protocol.md)** | Complete serial protocol specification with frame formats |
| **[Device Tree Analysis](docs/device-tree.md)** | SoC peripherals: UARTs, SPI, I2C, GPIO, sensors |
| **[System Audit](docs/system-audit.md)** | Partitions, kernel modules, device nodes, sysfs |
| **[Native Library Analysis](docs/native-lib-analysis.md)** | 25MB .so reverse engineering: classes, methods, constants |

## Tools

| Tool | Description |
|------|-------------|
| `tools/umbus.py` | UMBUS protocol library — parse, encode, and analyze frames |
| `tools/monitor.py` | Live channel visualization with color-coded delta tracking |
| `tools/strace-parser.py` | Extract and decode UMBUS frames from strace output |

### Quick Start

```bash
# Parse strace output
python tools/strace-parser.py captures/idle-strace.txt

# Live monitor (requires root + exclusive ttyS0 access)
su 0 /path/to/python3 tools/monitor.py
```

## Key Findings

### Root Access
The AX12 ships with a factory root binary at `/system/xbin/su`. No exploit needed — just run `su 0 <command>` from Termux. See [Root Guide](docs/root-guide.md) for full setup instructions.

### UMBUS Protocol
The MCU sends 4 frame types at different rates: channel data (25Hz), heartbeat (4Hz), ELRS telemetry (5Hz), and extended status (~3Hz). The app responds with polling requests, heartbeat acks, and config at 0.5-2Hz. Total bandwidth is ~2.4 KB/s on a 921.6 kbps link, using only ~2% of capacity. See [UMBUS Protocol](docs/umbus-protocol.md).

### Software Stack
The Flyshark app is a Qt6/QML application with embedded Lua 5.3 scripting (EdgeTX-compatible). It includes a full ground control station with 30+ map providers, terrain elevation, mission planning, AHRS display, and RTSP video streaming. The native library exposes 250+ classes. See [Native Library Analysis](docs/native-lib-analysis.md).

### 32 Channels
The system supports 32 output channels with per-channel reverse, slow motion, min/max limits, curves, dual rates, and multi-source mixing.

### Lua Scripting
Custom Lua scripts can be placed at `/storage/emulated/0/AX12LUA/` for widgets, mixes, and tools. A serial bridge (`luaSetGetSerialByte`) enables custom serial protocols from Lua.

## Device Specs

| Component | Detail |
|-----------|--------|
| SoC | MediaTek MT8788 (4x A53 + 4x A73) |
| RAM | 4GB |
| Storage | 64GB eMMC |
| Display | 5.5" 1280x720 touchscreen |
| Battery | 10,000mAh |
| OS | Android 9 (userdebug build) |
| RF | ELRS (LR1121), internal + external module support |
| Sensors | ICM-42607 6-axis IMU, magnetometer, ALS |
| Connectivity | WiFi, Bluetooth, GPS, NFC, HDMI out |

## Work in Progress

- [ ] Gimbal axis-to-stick mapping (needs per-axis physical testing)
- [ ] Switch and pot data path mapping
- [ ] ELRS telemetry field identification (RSSI, LQ, SNR bytes)
- [ ] Magisk persistent root (dm-verity blocks patched boot images)
- [ ] DSC port USB loopback trick (gamepad mode for gimbal access)
- [ ] Custom control app development

## Methodology

Protocol data was captured via `strace` on the running Flyshark app — observing the app's own serial I/O without interfering with it. Frame structures, timing, and constants were derived from these passive captures. Native library analysis used `strings` and `readelf` on the extracted `.so` (symbol names and printable strings only — no decompilation).

Gimbal axis mapping and some interactive captures are still TBD. Early hands-on testing sessions were noisy (wrong USB cables, stick movement timing issues, port confusion) — the protocol spec intentionally relies only on clean automated captures, not those manual sessions.

## Contributing

This is an ongoing reverse engineering effort. If you have an AX12 and want to help:

1. Run the tools and share captures from different states (flying, binding, different models)
2. Test the DSC port loopback trick documented in the Bardwell video
3. Help identify unknown fields in the UMBUS protocol
4. Try unlocking the bootloader (`fastboot flashing unlock`) — we haven't risked it yet

## License

This research is provided for educational and development purposes. The AX12 hardware and Flyshark software are products of RadioMaster. This project documents publicly observable behavior of a device we own.
