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
- Checksum: CRC-8/MAXIM (poly 0x31/0x8C, per-type init values)

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
| Battery | 10,000mAh (fuel gauge reports 2946mAh, discrepancy under investigation) |

## Physical Controls

Mode 2 layout (left stick = throttle/yaw, right stick = pitch/roll).

| Control | Type | Position | Notes |
|---------|------|----------|-------|
| Left Gimbal | X5 Hall-Effect, 2 axes | Left of screen | Throttle (Y, non-centering) + Yaw (X) |
| Right Gimbal | X5 Hall-Effect, 2 axes | Right of screen | Pitch (Y) + Roll (X), self-centering |
| SA | 2-pos latching | Top-left shoulder | On/off toggle |
| SB | 3-pos toggle | Top-left shoulder (next to SA) | Up/mid/down |
| SC | 3-pos toggle | Top-right shoulder (next to SD) | Up/mid/down |
| SD | 2-pos latching | Top-right shoulder | On/off toggle |
| SE | 3-pos toggle | Back-left (flanking module bay) | Up/mid/down |
| SF | 3-pos toggle | Back-right (flanking module bay) | Up/mid/down |
| S1 | Potentiometer (smooth) | Left shoulder | Large center detent |
| S2 | Potentiometer (notched) | Right shoulder | No center detent, notches on rotation |
| T1-T4 | Trim buttons | Front face, around gimbals | Physical buttons confirmed |
| 6-pos switch | Rotary selector | Front face, center | Single control, 6 discrete positions |

Sticks are removable and stow in compartments on the back. Upgradeable to AG01 Nano CNC aluminum gimbals. Low-tension spring set included.

### Confirmed UMBUS Mapping

Determined via live calibration tool (`tools/calibrator.py`):

**Gimbal axes** (bytes 6-13 of 0x57 frame, signed 16-bit LE):

| Index | Axis | Stick | UMBUS byte offset |
|-------|------|-------|-------------------|
| G0 | Yaw / Rudder | Left X | 6-7 |
| G1 | Pitch / Elevator | Right Y | 8-9 |
| G2 | Throttle | Left Y (non-centering) | 10-11 |
| G3 | Roll / Aileron | Right X | 12-13 |

**Switch/channel mapping** (bytes 18+ of 0x57 frame, unsigned 16-bit LE):

| Control | Channel | Idle Value | Notes |
|---------|---------|------------|-------|
| S1 (scroll wheel) | CH06 | ~500 | Full range 20-65526 |
| S2 (scroll wheel) | CH07 | ~65036 | Full range 112-65472 |
| SA (2-pos latch) | CH14 | 65036 | Toggles to 500 |
| SB (3-pos) | CH15 | 65036 | 3 positions |
| SC (3-pos) | CH16 | 65036 | 3 positions |
| SD (2-pos latch) | CH17 | 65036 | Toggles to 500 |
| SF (3-pos) | CH19 | 500 | 3 positions |
| 6-pos selector | CH29 | varies | All 6 "front buttons" are one rotary control |
| SE (3-pos) | CH30 | 65024 | Master switch — triggers changes across 23 channels |
| T1 (trim) | CH31 | 766 | Increments by 512 per press (physical button confirmed) |
| T2 (trim) | CH30 | shared with SE | Needs further investigation |

## Onboard Sensors

The MT8788 SoC includes sensor interfaces originally designed for a phone/tablet platform. RadioMaster retained several:

| Sensor | Chip | I2C Address | Bus | Status | Potential Use |
|--------|------|-------------|-----|--------|---------------|
| IMU (6-axis) | ICM-42607 | 0x68/0x69 | i2c@11011000 | Present | Head tracking, tilt control, crash detection |
| Magnetometer | Unknown | 0x0c | i2c@11011000 | Present | Compass heading for GCS |
| GPS | MT6631 combo | N/A | Internal | Hardware present, not exposed to apps | MadsTech reports no GPS detection in Android GPS apps; hardware exists in device tree but may lack driver/permissions |
| ALS/Proximity | Unknown | 0x1e | i2c@1100f000 | Present | Auto-brightness |
| NFC | Unknown | 0x08 | i2c@1100f000 | Present | Model/bind pairing? |
| Camera (main) | Unknown | Various | i2c@11009000 | Wired, not populated | No camera module installed |
| Camera (sub) | Unknown | Various | i2c@11009000 | Wired, not populated | No camera module installed |

The IMU and GPS are particularly interesting for GCS applications — the radio knows its own position and orientation. The NFC chip could enable tap-to-bind or tap-to-load-model workflows.

## Connectivity

| Port | Location | Purpose |
|------|----------|---------|
| Mini HDMI In | Top edge | FPV video feed (DJI/Walksnail/HDZero/OpenIPC) |
| Mini HDMI Out | Top edge | Mirror display to external monitor |
| USB-C (data) | Top edge | Trainer port, ADB, data transfer |
| USB-C (charge) | Bottom edge | USB PD charging |
| 3.5mm audio | Bottom edge | Headphone jack |
| Nano module bay | Top edge | External RF module (ELRS, etc.) |

## HDMI Input Latency

Per MadsTech testing with HDZero as a fixed-latency baseline:
- HDZero VRX → HDZero goggles (HDMI): 6.4ms first pixel, 21.2ms full frame
- HDZero VRX → AX12 (HDMI in): 144.2ms first pixel, 167.6ms full frame
- Added latency from AX12 HDMI input: **~140ms**

The display uses a smartphone-style panel that reads out in portrait orientation (right-to-left in landscape), adding to the perceived latency. Suitable for fixed-wing, long-range, and ground vehicles. Not suitable for proximity freestyle or racing.

The AX12 supports MAVLink pass-through over ELRS, allowing QGroundControl telemetry directly on the touchscreen without separate telemetry radios.

## Power

- Dual 21700 cells, 10,000 mAh total capacity
- USB-C PD charging port (bottom edge)
- Battery fuel gauge reports 2946mAh (discrepancy under investigation)
- RT9465 charger IC on I2C

## Detailed References

- [Device Tree Analysis](device-tree.md) — Full SoC peripheral map
- [System Audit](system-audit.md) — /dev, /sys, partitions, modules
- [UMBUS Protocol](umbus-protocol.md) — Complete protocol specification
- [Native Library Analysis](native-lib-analysis.md) — Class hierarchy, APIs, constants
- [Root & Setup Guide](root-guide.md) — How to set up a dev environment
