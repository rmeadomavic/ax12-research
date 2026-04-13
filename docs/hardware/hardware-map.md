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
│  Serial ports (all ST16650V2 UARTs, 8N1, clocal, no flow control):   │
│  - ttyS0 @ 921600: UMBUS to MCU (MMIO 0x11002000) ✓ verified stty   │
│  - ttyS1 @ 9600:   Silent, RTS/DTR asserted (MMIO 0x11003000) ✓     │
│  - ttyS2 @ 9600:   Root-only (MMIO 0x11004000) — untested           │
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
│  - i2c@1100f000: ALS/prox @1e (NOT POPULATED), NFC @08 (NOT POP.)   │
│  - i2c@11011000: ICM-42607 IMU @68/@69, msensor @0c, nm_i2c1 @01   │
│  - i2c@11017000: MT6370 sub-PMIC @34, USB-C @4e                     │
│                                                                     │
│  Other:                                                             │
│  - ITE IT66121 HDMI bridge (video out)                              │
│  - Richnano RN6752M analog video decoder (HDMI in → MIPI CSI-2)    │
│  - Mali Bifrost GPU                                                 │
│  - WiFi/BT/GPS/FM via MT6631 combo chip                             │
│  - 5.5" 1280x720 MIPI DSI touchscreen                              │
│  - 24 thermal zones                                                 │
│  - 8 LEDs (RGB + backlight + MT6370 channels)                       │
│  - ZRAM swap (1GB)                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## UMBUS Protocol Summary

RadioMaster's internal bus protocol. Full spec: [umbus-protocol.md](../protocol/umbus-protocol.md)

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

Full analysis: [native-lib-analysis.md](../software/native-lib-analysis.md)

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

Embedded Lua 5.3 VM with ROM table support (NodeMCU lineage patch). Full details: [lua-api.md](../software/lua-api.md)
- Scripts at `/sdcard/AX12LUA/SCRIPTS/TOOLS/`
- Types: tools, mixes, widgets (follows OpenTX/EdgeTX `return {init=..., run=...}` convention)
- Custom modules: `luaopen_bitmap` (LCD), `luaopen_etxdir` (dirs), `luaopen_lvgl` (UI framework)
- Standard EdgeTX API: `crossfireTelemetryPush/Pop`, LCD drawing, input reading
- Serial bridge: `luaSetGetSerialByte()` exists but serial functions are **dead stubs** on AX12 (see [Lua API](../software/lua-api.md#9-serial-port-access--dead-stubs))

### Channel System

- **33 output channels** (CH00-CH32)
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
| IMU (6-axis) | ICM-42607 | 0x68/0x69 | i2c@11011000 | Active — drivers loaded, SensorService delivering data | Accel 125Hz, gyro 10-400Hz, FIFO 4500 events. 9-axis fusion available. Data path: SCP→HAL→SensorService (no direct I2C — no i2c-dev module). Not used by Flyshark for head-tracking |
| Magnetometer | Unknown | 0x0c | i2c@11011000 | Present | Compass heading for GCS |
| GPS | MT6631 combo | /dev/stpgps (char 191,0) | Internal (STP transport) | Software functional, **NO ANTENNA POPULATED** | GNSS mode 1 (GPS+GLONASS), scans BeiDou. Daemons: mnld, mtk_agpsd, gnss@1.1-service, lbs_hidl_service. AGC: L1 ~2800-3100, L5 ~6300-6400 (thermal noise floor only — no antenna). Zero satellites acquired across hours of testing including window-mounted. GNSS RTC stuck at 2000-01-01 (never obtained a time fix). RadioMaster did not populate the ceramic patch antenna or RF trace on the PCB. **Unusable without external antenna hardware modification.** Not used by Flyshark. Test: `su 0 am start -n com.mediatek.ygps/.YgpsActivity` |
| ALS/Proximity | Unknown | 0x1e | i2c@1100f000 | **NOT POPULATED** | Device tree entry inherited from MT8788 reference design. Full I2C bus scan with custom kernel module confirmed zero devices respond at this address. No physical sensor on PCB. |
| NFC | Unknown | 0x08 | i2c@1100f000 | **NOT POPULATED** | Device tree entry inherited from MT8788 reference design. Full I2C bus scan with custom kernel module confirmed zero devices respond at this address. No physical chip on PCB. Kernel also compiled with CONFIG_NFC=n. |
| Camera (main) | Unknown | Various | i2c@11009000 | Wired, **not populated** (confirmed) | Camera ISP framework present, 3 AF motor drivers and 3 EEPROM slots wired in DT, but no image sensor physically soldered. Camera thermal sensors read -127°C (powered off). |
| Camera (sub) | Unknown | Various | i2c@11009000 | Wired, **not populated** (confirmed) | Same as main — ISP bus wired but no sensor on PCB. |

The IMU is confirmed functional for GCS applications — the radio knows its own orientation. GPS software stack is fully operational but **the GNSS antenna was never populated on the PCB** — the RF frontend samples thermal noise only, acquiring zero satellites. GPS would require an external antenna hardware mod to be usable. NFC and ALS/proximity sensor entries in the device tree are inherited from the MT8788 reference design — **neither chip is physically populated on the AX12 PCB**. Full I2C bus 3 scan with a custom kernel module confirmed zero devices respond at either address.

## Onboard Peripherals

Peripherals confirmed via /sys, /dev, and device-tree probing (2026-04-13):

| Peripheral | Interface | Path | Notes |
|------------|-----------|------|-------|
| RGB LED | sysfs | `/sys/class/leds/{red,green,blue}/brightness` | 0-255 range. Supports `timer`, `breath_mode`, `pwm_mode` triggers. Green was on at boot. |
| Vibration motor | timed_output | `/sys/class/timed_output/vibrator/enable` | Write duration in ms to activate. |
| Speaker | I2C (RT5509 Class-D amp) | Bus 6, addr 0x34 | Full Android audio stack, 33 PCM devices. |
| Headphone jack | ACCDET | `/dev/accdet` (input event0) | Plug/unplug detection via MediaTek ACCDET driver. |
| LCD backlight | sysfs | `/sys/class/leds/lcd-backlight/brightness` | 0-255 range. |
| MT6370 PMU LEDs | sysfs | `/sys/class/leds/led{1-4}/brightness` | 4 ISINK channels. led1-led3 max brightness 6, led4 max brightness 3. |
| NFC chip | I2C | Bus 3, addr 0x08 | **NOT POPULATED.** DT entry inherited from MT8788 reference design. Bus scan confirmed no device responds. Kernel also has CONFIG_NFC=n. |
| FM Radio | char device | `/dev/fm` (char 213:0) | **Fully functional.** MT6631 combo chip, firmware mt6631_fm_v1_patch.bin loaded. Tunes 87.5-108.0 MHz. RSSI reads -114 dBm without antenna (needs headphone cable as antenna via 3.5mm jack). Pre-installed app: com.android.fmradio. Ioctl map: POWERUP=0xC008F500, TUNE=0xC008F502, GETRSSI=0xC008F507. |
| Flash LEDs | MT6370 driver | — | Driver loaded but LEDs not physically populated (intended for camera connector). |
| ALS/Proximity | I2C | Bus 3, addr 0x1E | **NOT POPULATED.** DT entry inherited from MT8788 reference design. Bus scan confirmed no device responds. |
| Touchscreen | I2C | Bus 0, addr 0x40 | GSL680 (SiliconWorks), driver gslX680. |
| Bluetooth | char device | `/dev/stpbt` | MT6631 combo chip, Android BT stack. |
| Thermal sensors | sysfs | 24 zones | CPU ~41°C, Battery 25°C, PMIC 40°C, WiFi 48°C (typical idle). |

## Connectivity

| Port | Location | Purpose |
|------|----------|---------|
| Mini HDMI In | Top edge | FPV video feed (DJI/Walksnail/HDZero/OpenIPC). Internally: HDMI→analog→RN6752M→MIPI CSI-2 |
| Mini HDMI Out | Top edge | Mirror display to external monitor |
| USB-C (data) | Top edge | Trainer port, ADB, data transfer. **Gadget mode only** (ADB/MTP/RNDIS). USB OTG host mode disabled — CONFIG_USB_MTK_OTG, CONFIG_SSUSB_DRV, CONFIG_SSUSB_MTK_XHCI all unset. XHCI host controller silicon present but glue driver not compiled. Custom kernel required for host mode. |
| USB-C (charge) | Bottom edge | USB PD charging |
| 3.5mm audio | Bottom edge | Headphone jack |
| Nano module bay | Top edge | External RF module (ELRS, etc.) |

## Video Input Pipeline

The HDMI input does **not** use a Loitium HDMI-to-MIPI bridge as previously documented. The active video decoder is a **Richnano RN6752M** — an analog video decoder (AHD/TVI/CVI/CVBS to MIPI CSI-2).

| Property | Value |
|----------|-------|
| Chip | Richnano RN6752M |
| Sensor ID | 0x501 |
| I2C | Bus 2, addr 0x36 |
| MIPI | 4-lane CSI-2 |
| Resolution | Up to 1080p |
| MCLK | 26 MHz |
| Input formats | AHD, TVI, CVI, CVBS |

The HDMI input signal is converted to analog (likely by an upstream converter before the RN6752M), then decoded to MIPI CSI-2 for the MT8788 ISP. The previous "Loitium" reference may refer to an upstream chip in the signal chain or may have been incorrect.

### HDMI Input Latency

Per MadsTech testing with HDZero as a fixed-latency baseline:
- HDZero VRX → HDZero goggles (HDMI): 6.4ms first pixel, 21.2ms full frame
- HDZero VRX → AX12 (HDMI in): 144.2ms first pixel, 167.6ms full frame
- Added latency from AX12 HDMI input: **~140ms**

The ~140ms latency is consistent with a multi-stage conversion pipeline (HDMI → analog → MIPI CSI-2). The display also uses a smartphone-style panel that reads out in portrait orientation (right-to-left in landscape), adding to the perceived latency. Suitable for fixed-wing, long-range, and ground vehicles. Not suitable for proximity freestyle or racing.

The AX12 supports MAVLink pass-through over ELRS, allowing QGroundControl telemetry directly on the touchscreen without separate telemetry radios.

## Power

- Dual 21700 cells, 10,000 mAh total capacity
- USB-C PD charging port (bottom edge)
- Battery fuel gauge reports 2946mAh (discrepancy under investigation)
- RT9465 charger IC on I2C

## Serial Port Details

All three serial ports use ST16650V2 UARTs with 8N1 framing and clocal (ignore modem control) mode.

| Port | Baud | MMIO Base | Status | Notes |
|------|------|-----------|--------|-------|
| ttyS0 | 921600 | 0x11002000 | Active — owned by app_process64 (Flyshark) | UMBUS protocol link to AT32 MCU. `LCK..ttyS0` lockfile present. No flow control. |
| ttyS1 | 9600 | 0x11003000 | Silent — no process has it open | RTS/DTR modem control lines asserted (something configured them). Probed with 7 command types (newline, AT, `?`, version, help, 0x00, 0xA6 sync) at 9600 baud — zero bytes received. May be boot-only debug output, TX-only wiring, or require a different baud rate. |
| ttyS2 | 9600 | 0x11004000 | Root-only, untested | Permissions restrict access. No traffic testing performed. |

Baud rates verified 2026-04-13 via `su 0 stty -a -F /dev/ttyS<n>`.

## Model Configuration Storage

Model configs are stored as flat binary structs in the Flyshark app's private directory.

**Location:** `/data/data/com.Flyshark.RadioMasterAX/files/`  
**Format:** Fixed-size binary structs (NOT SQLite or other database)

### .rcm Files (~1877 bytes each)

| Offset | Size | Type | Description |
|--------|------|------|-------------|
| 0 | 4 | u32le | Magic: `0x12345678` |
| 4 | 200 | char[] | Model name (null-padded) |
| 204 | 256 | char[] | Icon path (null-padded) |
| 460 | 4 | u32le | Timestamp (Unix epoch) |
| 464 | 2 | u16le | Version |
| 466 | 2 | u16le | Flags |
| 468 | 32 | u8[32] | Trim values (center = 0x7F) |
| 500 | 32 | u8[32] | Rate values (100% = 0x64) |
| 532+ | var | — | Mixer configuration |
| tail | 14×N | — | Channel endpoint records (14 bytes each) |

### Active Model Pointer

**File:** `RcCfgFile.rcCfg`  
**Magic:** `0x4F61BC00` (little-endian)  
**Purpose:** Points to the path of the currently active .rcm model file.

### Templates (read-only)

Four built-in model templates ship with the app:
- FPVDrone
- FixedWing
- Helicopter
- DeltaWing

### Naming Convention

User-created model files use Unix timestamps as filenames (e.g., `1681234567.rcm`).

## Detailed References

- [Device Tree Analysis](device-tree.md) — Full SoC peripheral map
- [System Audit](system-audit.md) — /dev, /sys, partitions, modules
- [UMBUS Protocol](../protocol/umbus-protocol.md) — Complete protocol specification
- [Native Library Analysis](../software/native-lib-analysis.md) — Class hierarchy, APIs, constants
- [Root & Setup Guide](../guides/root-guide.md) — How to set up a dev environment
- [ELRS Telemetry Analysis](../protocol/elrs-telemetry-analysis.md) — RF link telemetry decoding
- [Lua API](../software/lua-api.md) — Lua VM details, installed scripts, API reference
