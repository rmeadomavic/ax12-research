# AX12 Hardware Map

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  RadioMaster AX12                                                   │
│                                                                     │
│  ┌──────────────┐  UMBUS/UART (ttyS0, 921600)   ┌───────────────┐  │
│  │  MT8788 SoC  │◄──────────────────────────────►│   AT32 MCU    │  │
│  │  ARM64 8-core│  Bidirectional:                │               │  │
│  │  Android 9   │  MCU→App (25Hz):               │ Reads:        │  │
│  │  4GB RAM     │   Channel data, heartbeat,     │  - 4 gimbal   │  │
│  │  64GB eMMC   │   ELRS telemetry, ext status   │    axes (ADC) │  │
│  │              │  App→MCU (2Hz):                │  - Switches   │  │
│  │  App:        │   Poll, heartbeat ack,         │  - Pots/sliders│  │
│  │  Flyshark    │   config, keep-alive           │  - Scroll wheel│  │
│  │  Qt6/QML     │                                │               │  │
│  │  Lua 5.3     │  SPI1 (mt8788_spi1_plat_drv)   │ Controls:     │  │
│  │              │◄──────────────────────────────►│  - ELRS TX    │  │
│  │  GCS/Maps    │  Secondary bus (RF/data?)       │    (LR1121)   │  │
│  └──────────────┘                                └───────────────┘  │
│                                                                     │
│  Serial ports:                                                      │
│  - ttyS0 @ 921600: UMBUS protocol to MCU (primary link)             │
│  - ttyS1 @ 9600:   Unused (no data observed)                        │
│  - ttyS2:          Root-only permissions                             │
│                                                                     │
│  SPI buses:                                                         │
│  - spi@1100a000: DM9051 Ethernet (disabled), fingerprint (disabled) │
│  - spi@11010000: mt8788_spi1_plat_drv — RC-specific, likely MCU/RF  │
│  - spi@11012000-11019000: unused (4 buses)                          │
│                                                                     │
│  I2C buses (12 total):                                              │
│  - i2c@11005000: RT9465 charger, speaker amp @34                    │
│  - i2c@11007000: cap_touch @40                                      │
│  - i2c@11008000: camera (main2)                                     │
│  - i2c@11009000: camera (main, sub)                                 │
│  - i2c@1100f000: ALS/proximity @1e, NFC @08                         │
│  - i2c@11011000: ICM-42607 IMU @68/@69, msensor @0c, nm_i2c1 @01   │
│  - i2c@11017000: MT6370 sub-PMIC @34, USB-C @4e                     │
│                                                                     │
│  Other:                                                             │
│  - ITE IT66121 HDMI bridge (video out capable)                      │
│  - Mali Bifrost GPU                                                 │
│  - WiFi/BT/GPS/FM via MT6631 combo chip                             │
│  - 5.5" 1280x720 MIPI DSI touchscreen                              │
│  - 24 thermal zones                                                 │
│  - 8 LEDs (RGB + backlight + MT6370 channels)                       │
│  - ZRAM swap (1GB)                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## UMBUS Protocol Summary

RadioMaster's internal bus protocol. Full spec: [umbus-protocol.md](umbus-protocol.md)

| Type | Size | Direction | Rate | Purpose |
|------|------|-----------|------|---------|
| 0x57 | 87B | MCU→App | 25 Hz | Channel/gimbal data |
| 0x08 | 7B | MCU→App | 4 Hz | Heartbeat |
| 0x15 | 21B | MCU→App | 5 Hz | ELRS RF telemetry |
| 0x10 | 18B | MCU→App | ~3 Hz | Extended telemetry |
| 0x0E | 14B | App→MCU | 2 Hz | Poll/status request |
| 0x08 | 8B | App→MCU | 1 Hz | Heartbeat response |
| 0x0C | 12B | App→MCU | 1 Hz | Config/state |
| 0x07 | 7B | App→MCU | 0.5 Hz | Keep-alive ping |

### Gimbal Data (in 0x57 frames)

Bytes 6-13: 4 signed 16-bit LE gimbal values (~-500 to +500 at center)  
Bytes 18+: unsigned 16-bit LE channel outputs (center = 0x8000)

### Key Constants

- Sync: `0xA6`
- Channel center: `0x8000` (32768)
- Switch high: `0xFE0C` (65036)
- Checksum: last byte, algorithm unknown

## Software Architecture

Full analysis: [native-lib-analysis.md](native-lib-analysis.md)

```
QML UI ─── QML Singletons ─── Communication ─── UMBUS Engine ─── CRSF Engine
                                    │
                              QCommUsart (UART)
                              QCommTcp (TCP)
                              USB-HID
```

### Key Classes

| Class | Role |
|-------|------|
| AppComHub | Central UMBUS message router (singleton) |
| QCommUsart | UART driver for ttyS0 |
| AppRadioControl | RC control: sources, mixer, channels, models, telemetry |
| QGimbalControl | Camera gimbal control (external, not stick gimbals) |
| QSharkRFModule | ELRS RF module interface |
| QElrsModule | ELRS settings and telemetry decoder |
| CrsfSerial | CRSF protocol encode/decode |
| QSensorControl | IMU/oscilloscope data |
| QSharkFwControl | Firmware updates (MCU + ELRS backpack) |
| HardwareModule | Hardware detection singleton |
| AppFcTaskCtr | Flight controller task management |
| QFcStateViewControl | FC status display |
| QMapControl | GCS map engine (30+ providers, offline cache) |

### Lua Scripting

Embedded Lua 5.3.6 (EdgeTX-compatible):
- Scripts at `/storage/emulated/0/AX12LUA/`
- Types: tools, mixes, widgets
- Serial bridge: `luaSetGetSerialByte()` for custom serial protocols

### Channel System

- **32 output channels** (CH01-CH32)
- Per-channel: reverse, slow motion, min/max, midpoint offset, curves, D/R
- Mixer: multi-source mixing per channel
- Sources: sticks, switches, pots, sliders, trims, logical switches

## System Info

| Property | Value |
|----------|-------|
| SoC | MediaTek MT8788 (device tree: mt6771, Helio P60 family) |
| CPU | 4x Cortex-A53 + 4x Cortex-A73 |
| GPU | Mali Bifrost |
| Kernel | Linux 4.4.146 |
| Android | 9 (Pie), build: userdebug, test-keys |
| Build date | 2026-01-07 |
| SELinux | Permissive |
| Security Patch | 2019-12-05 |
| Boot state | Green (verified boot, dm-verity enforcing) |
| Root | Factory su at `/system/xbin/su` (SUID) |
| Display | 5.5" 1280x720 MIPI DSI, cap touch |
| Storage | 64GB eMMC, 38 partitions |
| RAM | 4GB (3.7GB usable), 1GB ZRAM swap |
| Battery | Li-ion, 2946mAh per cell |

## Detailed References

- [Device Tree Analysis](device-tree.md) — Full SoC peripheral map
- [System Audit](system-audit.md) — /dev, /sys, partitions, modules
- [UMBUS Protocol](umbus-protocol.md) — Complete protocol specification
- [Native Library Analysis](native-lib-analysis.md) — Class hierarchy, APIs, constants
- [Root & Setup Guide](root-guide.md) — How to set up a dev environment
