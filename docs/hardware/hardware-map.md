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
│  └──────────────┘                                │  + ext PA/FE  │  │
│                                                  └───────────────┘  │
│  Internal architecture: multi-board (compute module + I/O board,     │
│  per teardown videos). WiFi/BT share a single antenna.              │
│                                                                     │
│  Serial ports (all ST16650V2 UARTs, 8N1, clocal, no flow control):   │
│  - ttyS0 @ 921600: UMBUS to MCU (MMIO 0x11002000) ✓ verified stty   │
│  - ttyS1 @ 460800: Silent, RTS/DTR asserted (MMIO 0x11003000) ✓     │
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
│  - Mali-G72 MP3 GPU @ 700 MHz (Bifrost)                              │
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
| SoC | MediaTek MT8788 (device tree: mt6771, Helio P60 family), TSMC 12nm FinFET |
| CPU | 4x Cortex-A73 @ 2.0 GHz (big) + 4x Cortex-A53 @ 2.0 GHz (LITTLE), big.LITTLE DynamIQ |
| GPU | Mali-G72 MP3 (Bifrost architecture), 700 MHz |
| Kernel | Linux 4.4.146 |
| Android | 9 (Pie), build: userdebug, test-keys. **Cannot be updated** (per RadioMaster) |
| Build date | 2026-01-07 |
| SELinux | Permissive |
| Security Patch | 2019-12-05 |
| Boot state | Green (verified boot, dm-verity enforcing) |
| Boot time | ~40 seconds (Android cold boot) |
| Root | Factory su at `/system/xbin/su` (SUID) |
| Display | 5.5" 1280x720 IPS MIPI DSI touchscreen, 1000 nits max brightness |
| Storage | 64GB eMMC, 38 partitions |
| RAM | 4GB (3.7GB usable), 1GB ZRAM swap |
| Battery | Dual 3.7V 21700 Li-ion cells, 10,000mAh total (fuel gauge reports 2946mAh — see [Power](#power)) |
| Weight | 640g (RadioMaster claimed) / 649g (measured by Oscar Liang) |
| Dimensions | 171 × 168 × 73 mm |
| Price | $249.99 USD (MSRP at launch) |
| FCC ID | 2BLHG-AX12 |
| Working current | 1.10 A (at maximum RF output power) |

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

**Note:** Gimbal indices are interleaved across sticks, not contiguous per stick.
Left stick = G0 (X) + G2 (Y). Right stick = G3 (X) + G1 (Y). Verified by physical testing 2026-04-13.

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
| Mini HDMI Out | Top edge | Mirror display to external monitor (includes Android UI overlays — no clean output mode) |
| USB-C (data) | Top edge | Trainer port, ADB, data transfer. Default: gadget mode (ADB/MTP/RNDIS). **USB OTG host mode: hardware supported, software-switchable via sysfs (no custom kernel needed).** See [USB OTG Host Mode](#usb-otg-host-mode) below. |
| USB-C (charge) | Bottom edge | USB PD charging only — **no data lines** (per QSG diagram) |
| 3.5mm audio | Bottom edge | Headphone jack |
| Nano module bay | Top edge | External RF module (ELRS, etc.) |

## USB OTG Host Mode

**Status: Hardware supported, software-switchable via sysfs. NEEDS PHYSICAL TESTING.**

Previous documentation stated USB OTG required a custom kernel (`CONFIG_USB_MTK_OTG`, `CONFIG_SSUSB_DRV`, `CONFIG_SSUSB_MTK_XHCI` unset). This is incorrect — the MT8788 USB stack exposes userspace-accessible sysfs controls that trigger the TCPC (Type-C Port Controller) state machine to switch between device and host roles.

### Key Discovery

The `device_host_gpio_attr` at `/sys/devices/platform/device_host_gpio/` is **world-writable**. Writing `1` triggers a TCPC transition to `AttachWait.SRC` (host/source mode).

### Enable Host Mode

```bash
# Step 1: Toggle the device/host GPIO (triggers TCPC role switch)
echo 1 > /sys/devices/platform/device_host_gpio/device_host_gpio_attr

# Step 2: Set MUSB controller to host mode (cmode: 0=device, 1=host, 2=charge-only)
echo 1 > /sys/devices/platform/11200000.usb3/musb-hdrc/cmode

# Step 3: Set USB-C port role to DFP (downstream-facing port = host)
echo dfp > /sys/class/dual_role_usb/dual-role-type_c_port0/mode
```

### Alternative Method

USB OTG can also be toggled via the **MTK Engineer Mode** app's `UsbOtgSwitch` activity, which writes the same sysfs values.

### Hardware Details

| Component | Details |
|-----------|---------|
| MUSB controller | DesignWare MUSB-HDRC at `11200000.usb3` |
| MUSB cmode values | 0 = device, 1 = host, 2 = charge-only |
| xHCI host controller | `11200000.usb3_xhci` — present in device tree, driver binds only when a device is connected |
| TCPC transition | `AttachWait.SRC` on GPIO assert (host/source role) |
| GPIO control | `/sys/devices/platform/device_host_gpio/device_host_gpio_attr` (world-writable) |

### Loaded USB Class Drivers

All standard USB host class drivers are already loaded in the stock kernel:

- **Hub** — USB hub support
- **HID** — Keyboards, mice, gamepads
- **Mass storage** — USB drives, SD readers
- **Audio** — USB audio devices
- **Ethernet** — r8152 (Realtek), asix, ax88179_178a (USB Ethernet adapters)

### What Remains

**Physical testing required.** The sysfs interfaces respond correctly and the TCPC state machine transitions, but no physical USB-C OTG adapter + device test has been performed to confirm:
- Full device enumeration
- Power delivery to connected device (VBUS sourcing)
- Functional data transfer (HID input, storage mount, etc.)

## Video Input Pipeline

The HDMI input does **not** use a Loitium HDMI-to-MIPI bridge as previously documented. The active video decoder is a **Richnano RN6752M** — an analog video decoder (AHD/TVI/CVI/CVBS to MIPI CSI-2).

| Property | Value |
|----------|-------|
| Chip | Richnano RN6752M |
| Sensor ID | 0x501 |
| I2C | Bus 2, addr 0x36 |
| MIPI | 4-lane CSI-2 |
| Resolution | Up to 1080p, 720p/1080p @ up to 60 Hz |
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

- Dual 3.7V 21700 Li-ion cells, 10,000 mAh total capacity, non-removable (max charging voltage 4.2V per cell)
- USB-C PD charging port (bottom edge, **charge only — no data lines**), up to 20W measured (QSG says max 30W)
- 0% to 80% in ~70 minutes (measured by Oscar Liang)
- Claimed runtime: 8+ hours (RadioMaster), ~6 hours (unmanned.tech)
- **Runtime analysis:** 10,000 mAh × 3.7V = ~37 Wh. At 1.10A working current (max RF), that implies ~9.1 hours. The ~6 hour real-world figure implies ~1.7A average draw (~6.2W), plausible with screen at high brightness + WiFi + HDMI/GPU workloads active.
- Battery fuel gauge reports 2946mAh (discrepancy under investigation — likely per-cell capacity, 2×2946 ≈ 5900mAh, still short of 10,000mAh claim)
- RT9465 secondary charger IC on I2C bus 6
- MT6370 sub-PMIC handles USB-C PD negotiation (TCPC at I2C bus 5, addr 0x4E)

## Serial Port Details

All three serial ports use ST16650V2 UARTs with 8N1 framing and clocal (ignore modem control) mode.

| Port | Baud | MMIO Base | Status | Notes |
|------|------|-----------|--------|-------|
| ttyS0 | 921600 | 0x11002000 | Active — owned by app_process64 (Flyshark) | UMBUS protocol link to AT32 MCU. `LCK..ttyS0` lockfile present. No flow control. |
| ttyS1 | 460800 | 0x11003000 | Silent — no process has it open | RTS/DTR modem control lines asserted (something configured them). Previously probed at 9600 baud (wrong rate) — zero bytes received. Actual baud rate is 460800 (verified via stty). Re-probing at correct baud rate needed. |
| ttyS2 | 9600 | 0x11004000 | Root-only, untested | Permissions restrict access. No traffic testing performed. |

Baud rates verified 2026-04-13 via `su 0 stty -a -F /dev/ttyS<n>`. Note: ttyS1 was previously documented as 9600 baud but is actually configured at 460800.

## Model Configuration Storage

Model configs are stored as flat binary structs in the Flyshark app's private directory.

**Location:** `/data/data/com.Flyshark.RadioMasterAX/files/`  
**Format:** Fixed-size binary structs (NOT SQLite or other database)

### .rcm Files (1813–1877 bytes, variable)

File size varies by model type due to variable-length endpoint section.
Sizes observed: DeltaWing=1813, Helicopter=1853, FPVDrone/FixedWing=1877.

**C++ backing types** (from `libRadioMasterAX_arm64-v8a.so`):
`QML_Pack_RcModelCfgData`, `QML_Pack_RcCurveCfgData`, `QML_Pack_RcChOutCfg`,
`QML_Pack_RcMixCfgData`, `QML_Pack_RcChCfgDr`, `QML_Pack_RcSrcCfg`

#### Header (0x000–0x1FF)

| Offset | Size | Type | Description |
|--------|------|------|-------------|
| 0x000 | 4 | u32le | Magic: `0x12345678` |
| 0x004 | 4 | u32le | Creation timestamp (Unix epoch). Equals the filename for user models |
| 0x008 | 200 | char[200] | Model name (null-terminated, null-padded) |
| 0x0D0 | 252 | char[252] | Icon path (null-terminated, Qt `qrc:/` path) |
| 0x1CC | 4 | u32le | Last-modified timestamp (Unix epoch). 0 for templates |
| 0x1D0 | 48 | — | Reserved (all zeros) |

#### Config Section (0x200–0x261)

| Offset | Size | Type | Description |
|--------|------|------|-------------|
| 0x200 | 4 | u32le | Config version: always `0x000002EC` (748) |
| 0x204 | 1 | u8 | Model type magic: always `0xA3` (163) |
| 0x205 | 1 | u8 | Model type: 0=FixedWing, 1=DeltaWing, 2=Helicopter, 3=FPVDrone |
| 0x206 | 2 | — | Padding (zeros) |
| 0x208 | 24 | u8[24] | Model-specific params (Helicopter: swash config; zeros for others) |
| 0x220 | 13 | — | Reserved (zeros) |
| 0x22D | 16 | u8[16] | Unknown: `0xAA`×16 for DeltaWing/Helicopter, zeros otherwise |
| 0x23D | 1 | u8 | Trims flag: always `0x01` |
| 0x23E | 36 | u8[36] | Trim values per channel (center = `0x7F`/127) |

#### Rate/Expo Curves (0x262–0x4C5, `QML_Pack_RcCurveCfgData`)

612 bytes, structured as 34-byte records (max 18 channels), zero-padded.
Only populated in FPVDrone and Helicopter templates; user models typically zeros.

Each 34-byte record has two sub-arrays:

| Sub | Offset | Size | Description |
|-----|--------|------|-------------|
| A | +0 | 18 | Rate curve: `[type u8] [num_points u8] [points i8[16]]` |
| B | +18 | 16 | Expo curve: `[points i8[16]]` (same point count as rate) |

Curve point values are signed: `0x9C`=−100, `0x00`=0, `0x64`=+100.
Type `0x04` = D/R curve (standard). Type `0x02` = throttle/collective (helicopter).

**Example** — FPVDrone CH0 (Aileron), 5-point:
- Rate: `04 05 9C CE 00 32 64` → type=4, 5pts: [−100, −50, 0, +50, +100] (linear)
- Expo: `9C F6 1E 46 64` → 5pts: [−100, −10, +30, +70, +100] (exponential)

#### Rates & Runtime Data (0x4C6–0x5FF)

| Offset | Size | Type | Description |
|--------|------|------|-------------|
| 0x4C6 | 36 | u8[36] | Rate values per channel (default = `0x64`/100%) |
| 0x4EA | 1 | u8 | Unused (always 0) |
| 0x4EB | 1 | u8 | Unknown flag: `0x24` for FPVDrone/DeltaWing/Helicopter, else 0 |
| 0x4EC | 276 | — | **Uninitialized memory** — leaked runtime pointers/heap, not meaningful |

> **Bug:** The app serializes raw struct memory at 0x4EC–0x5FF without zeroing it,
> leaking ARM64 heap addresses. These differ between saves and carry no config data.

#### Endpoint Section (0x600–EOF, variable length)

| Offset | Size | Type | Description |
|--------|------|------|-------------|
| 0x600 | 4 | u32le | Endpoint data byte count (from 0x608 to EOF) |
| 0x604 | 4 | u32le | Duplicate of above |
| 0x608 | var | — | Endpoint records (see sub-format below) |

Observed sizes: DeltaWing=269, Helicopter=309, FPVDrone/FixedWing/users=333.

**Endpoint record layout:**

```
[Header]     = 0xA4 marker (1B) + endpoint_def (14B) = 15 bytes
[Channel]×N  = channel_id (1B) + mixer_entry (8B)×M + endpoint_def (14B)
[Default]×T  = endpoint_def (14B) — unconfigured channel defaults
[Padding]    = 4 bytes of zeros
```

**Mixer entry** (8 bytes, `QML_Pack_RcMixCfgData`):

| Offset | Size | Type | Description |
|--------|------|------|-------------|
| +0 | 1 | u8 | Source channel number |
| +1 | 1 | i8 | Weight: +100=normal, −100=reversed (`0x9C`) |
| +2 | 1 | i8 | Offset (0 = none) |
| +3 | 2 | u16le | Limit/curve value (`0xFFC0` for simple mix, position for curves) |
| +5 | 1 | u8 | Enabled flag (1=yes, 0=no) |
| +6 | 2 | — | Reserved (zeros) |

**Endpoint definition** (14 bytes, `QML_Pack_RcChOutCfg`):

| Offset | Size | Type | Description |
|--------|------|------|-------------|
| +0 | 1 | u8 | Travel positive (default 100 = `0x64`) |
| +1 | 1 | u8 | Subtrim (default 0) |
| +2 | 1 | i8 | Travel negative (default −100 = `0x9C`) |
| +3 | 1 | u8 | Rate (default 100 = `0x64`) |
| +4 | 1 | u8 | Curve type (`0xFF`=linear, `0x05`=helicopter special) |
| +5 | 1 | u8 | Flags (context-dependent) |
| +6 | 8 | u16le[4] | Limit values (default `0x00C0`=192 each) |

**Model-specific mixer examples:**

- **FPVDrone**: 13 channels, 1 mixer input each (direct stick→channel mapping)
- **DeltaWing**: Elevon records have 2 mixer inputs (aileron+elevator mixed).
  Second elevon uses `weight=−100` for reversed elevator.
- **Helicopter**: Pitch/throttle records have 3 mixer inputs (curve breakpoints).
  Values in the limit field encode curve positions instead of travel limits.

Channel order in endpoint records follows output assignment, not numerical order.
FPVDrone order: CH3(ail), CH1(ele), CH2(thr), CH0(rud), CH20–25(aux), CH4, CH13, CH35.

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

## Complete I2C Device Map

Full enumeration from  (verified 2026-04-13):

| Bus | Addr | Name | Chip | Status |
|-----|------|------|------|--------|
| 0 | 0x40 | cap_touch | GSL680 (SiliconWorks) | Active — touchscreen controller |
| 1 | 0x01 | i2c_demo | Reference stub | Inactive — MT8788 BSP artifact |
| 1 | 0x0C | msensor | Magnetometer | Active — part of 9-axis fusion |
| 1 | 0x10 | gsensor_a | Accelerometer (HAL) | Active — IMU accel for SensorService |
| 1 | 0x11 | gyro_g | Gyroscope (HAL) | Active — IMU gyro for SensorService |
| 1 | 0x4C | it66121 | ITE IT66121 | Active — HDMI 1.4 transmitter (output) |
| 1 | 0x68 | gsensor | ICM-42607 accel | Active — raw accel interface |
| 1 | 0x69 | gyro | ICM-42607 gyro | Active — raw gyro interface |
| 2 | 0x0C | camera_main_af | Camera AF motor | NOT POPULATED — phantom DT entry |
| 2 | 0x10 | camera_sub | Sub camera | NOT POPULATED — phantom DT entry |
| 2 | 0x15 | camera_sub_af | Sub camera AF | NOT POPULATED — phantom DT entry |
| 2 | 0x33 | ccu_sensor_i2c_main | Camera control unit | NOT POPULATED |
| 2 | 0x36 | camera_main | Main camera | NOT POPULATED — phantom DT entry |
| 2 | 0x43 | ccu_sensor_i2c_sub_ | Camera control unit | NOT POPULATED |
| 2 | 0x50 | camera_main_eeprom | Camera cal EEPROM | NOT POPULATED |
| 2 | 0x54 | camera_sub_eeprom | Camera cal EEPROM | NOT POPULATED |
| 3 | 0x08 | nfc | NFC controller | NOT POPULATED — DT stub, CONFIG_NFC=n |
| 3 | 0x1E | alsps | ALS/proximity | NOT POPULATED — DT stub, bus scan empty |
| 4 | 0x0E | camera_main_two_af | Camera 3 AF | NOT POPULATED — phantom DT entry |
| 4 | 0x11 | ccu_sensor_i2c_main | Camera control unit | NOT POPULATED |
| 4 | 0x12 | ccu_sensor_i2c_main | Camera control unit | NOT POPULATED |
| 4 | 0x38 | camera_main_two | Camera 3 sensor | NOT POPULATED — phantom DT entry |
| 4 | 0x52 | camera_main_two_eep | Camera 3 EEPROM | NOT POPULATED |
| 5 | 0x34 | subpmic_pmu | MT6370 sub-PMIC | Active — LED/charger/LDO controller |
| 5 | 0x4E | usb_type_c | MT6370 TCPC | Active — USB-C PD/OTG negotiation |
| 6 | 0x34 | speaker_amp | Richtek RT5509 | Active — Class-D speaker amplifier |
| 6 | 0x4B | rt9465 | Richtek RT9465 | Active — secondary charging IC |

**Summary:** 28 registered I2C devices across 7 buses. 11 active, 14 phantom (MT8788 reference design stubs), 3 camera control units (inactive).

### HDMI Signal Path



The IT66121 is an HDMI 1.4 transmitter by ITE Tech. Its register set is fully I2C-accessible. A mainline Linux DRM bridge driver exists (, merged in kernel 5.15+) but would need backporting for the 4.4 kernel.

The RN6752M is a Richnano analog video decoder (AHD/TVI/CVI/CVBS → MIPI CSI-2). It handles analog-domain input only — HDMI input likely goes through a separate HDMI-to-analog bridge upstream. The RN6752M adds minimal latency (1-3 scan lines, ~30-100µs) as it's primarily a protocol converter, not an ISP.


## Complete I2C Device Map

Full enumeration from sysfs device names (verified 2026-04-13):

| Bus | Addr | Name | Chip | Status |
|-----|------|------|------|--------|
| 0 | 0x40 | cap_touch | GSL680 | Active - touchscreen controller |
| 1 | 0x01 | i2c_demo | Reference stub | Inactive - MT8788 BSP artifact |
| 1 | 0x0C | msensor | Magnetometer | Active - part of 9-axis fusion |
| 1 | 0x10 | gsensor_a | Accelerometer HAL | Active - IMU accel for SensorService |
| 1 | 0x11 | gyro_g | Gyroscope HAL | Active - IMU gyro for SensorService |
| 1 | 0x4C | it66121 | ITE IT66121 | Active - HDMI 1.4 transmitter (output) |
| 1 | 0x68 | gsensor | ICM-42607 accel | Active - raw accel interface |
| 1 | 0x69 | gyro | ICM-42607 gyro | Active - raw gyro interface |
| 2 | 0x0C-0x54 | camera_* | 8 entries | NOT POPULATED - phantom DT entries |
| 3 | 0x08 | nfc | NFC controller | NOT POPULATED - DT stub, CONFIG_NFC=n |
| 3 | 0x1E | alsps | ALS/proximity | NOT POPULATED - DT stub |
| 4 | 0x0E-0x52 | camera_main_two_* | 5 entries | NOT POPULATED - phantom DT entries |
| 5 | 0x34 | subpmic_pmu | MT6370 sub-PMIC | Active - LED/charger/LDO controller |
| 5 | 0x4E | usb_type_c | MT6370 TCPC | Active - USB-C PD/OTG negotiation |
| 6 | 0x34 | speaker_amp | Richtek RT5509 | Active - Class-D speaker amplifier |
| 6 | 0x4B | rt9465 | Richtek RT9465 | Active - secondary charging IC |

Summary: 28 registered I2C devices across 7 buses. 11 active, 14 phantom from MT8788 reference design, 3 camera control stubs.

### HDMI Signal Path

The AX12 has separate input and output HDMI paths using different chips:

- HDMI OUTPUT: MT8788 display pipeline -> IT66121 HDMI 1.4 transmitter (I2C bus 1, addr 0x4C) -> HDMI Out connector
- HDMI INPUT: External HDMI source -> bridge chip (TBD) -> RN6752M analog decoder -> MIPI CSI-2 -> MT8788 ISP -> display

The IT66121 register set is fully I2C-accessible. A mainline Linux DRM bridge driver exists (merged kernel 5.15+) but needs backporting for 4.4.

The RN6752M adds minimal latency (1-3 scan lines, approximately 30-100 microseconds) as it is primarily a protocol converter, not an image signal processor. No public datasheet; register map available only under NDA.


## Cellular Modem (Not Populated, Hardware Present)

The MT8788's cellular modem is active with loaded firmware:

| Property | Value |
|----------|-------|
| Baseband firmware | MOLY.LR12A.R2.MP.V109.4 |
| Default network | LTE (type 9) |
| CCCI devices | /dev/ccci_* present (modem IPC channel) |
| SIM state | Not inserted |
| Network interfaces | ccmni0-20 (21 cellular interfaces, all DOWN) |
| RIL daemon | Not running (no SIM) |

The modem firmware is loaded and initialized by the bootloader even though no SIM slot or cellular antenna is populated on the AX12 PCB. RadioMaster kept the modem active (likely because disabling it requires kernel/bootloader changes).

### Theoretical LTE Capability

With hardware modifications (SIM card adapter, cellular antenna, RF frontend), the AX12 could potentially support native 4G LTE. This would enable:
- Direct cellular backhaul without USB OTG dongle
- TAK Server connectivity over cellular
- Remote operation beyond WiFi range

This is NOT practical without significant PCB modification and is listed for completeness only. USB LTE dongle via OTG is the recommended approach.


## Cross-Referenced Specifications (from reviews)

| Spec | Value | Source |
|------|-------|--------|
| Weight | 640g claimed / 649g measured | Oscar Liang review |
| Weight | ~650g | unmanned.tech review |
| Dimensions | 171 × 168 × 73 mm | Oscar Liang review (matches RadioMaster spec) |
| Screen brightness | 1000 nits (outdoor-readable) | Oscar Liang review, unmanned.tech review |
| Max TX power | 250 mW / 24 dBm (dynamic power). **Note:** some mirrored manuals list 20 dBm; official QSG says 24 dBm. Needs RF bench test to resolve. | QSG specs, Oscar Liang review, unmanned.tech review |
| External PA (inferred) | LR1121 internal 2.4 GHz PA path is only +11.5 dBm (per Semtech datasheet). Achieving 24 dBm at 2.4 GHz **requires an external PA/front-end module** — not yet identified on PCB. Sub-GHz PA path is +22 dBm, closer to the 24 dBm claim. | Semtech LR1121 datasheet vs AX12 QSG claim |
| Antenna gain | 2 dBi | QSG specs |
| RF frequency | 2.400–2.480 GHz (2.4 GHz version) | QSG specs |
| RF bands | 2.4 GHz **or** 868/915 MHz — not simultaneous, **no Dual-band Gemini-X** | Oscar Liang review |
| RF chip | Semtech LR1121 (2.4 GHz or sub-G 900 MHz) | confirmed |
| RF channels | Max 16 (depending on receiver) | QSG specs, RadioMaster product page |
| Working current | 1.10 A (at maximum output power) | RadioMaster product page |
| Nano module bay | Top edge, for external ELRS or other nano RF modules | Oscar Liang review |
| Battery | Dual 3.7V 21700 Li-ion, 10,000 mAh total, non-removable | Oscar Liang review |
| Battery runtime | 8+ hours (RadioMaster claim) | Oscar Liang review |
| Battery runtime | ~6 hours (real-world) | unmanned.tech review |
| Charging | USB PD up to 20W, 0-80% in ~70 min | Oscar Liang review |
| Boot time | ~40 seconds (cold boot) | Oscar Liang review |
| Android | 9.0 — **cannot be updated** (per RadioMaster) | Oscar Liang review |
| Gimbals | Mini Hall X5, removable/storable, stick height not adjustable | Oscar Liang review |
| Gimbal upgrade | AG01 Nano CNC aluminum gimbals | Oscar Liang review, unmanned.tech review |
| Connectivity | WiFi, Bluetooth — **no SIM, no GPS antenna, no camera** | Oscar Liang review |
| IMU / Accelerometer | Oscar Liang states "no accelerometer" — **incorrect**: ICM-42607 6-axis IMU confirmed present and active on I2C bus 1 (see [Onboard Sensors](#onboard-sensors)) | Oscar Liang review vs. device audit |
| HDMI input | Mini HDMI, 720p/1080p up to 60 Hz. Compatible: Walksnail, HDZero, OpenIPC, DJI (with additional hardware). ~140ms added latency. | Oscar Liang review |
| HDMI output | Mini HDMI, mirrors full Android display to external monitor — **includes UI overlays** (status bar, icons). No "clean output" mode reported; community suggests app-based streaming as workaround. | Oscar Liang review, intoFPV forum |
| HDMI jitter | Reported with RunCam OpenIPC sources | unmanned.tech review |
| DJI Fly app | Works via USB-C for DJI Goggles 2/3 video output. Requires USB debugging enabled, USB-A to USB-C cable with adapter (A-end to goggles). USB-C to USB-C OTG cables did not work. | Oscar Liang review |
| SpeedyBee app | Works via Bluetooth (SpeedyBee Adapter 3). USB connection did not work. | Oscar Liang review |
| Betaflight Configurator | Web version loads in Chrome but cannot detect FC via USB-C. FC receives power but is not recognized as USB device. | Oscar Liang review |
| FPV simulators | Run on device with frame drops (GPU ~7 year old phone class). Gimbal-to-Android via Bluetooth has ~1 second latency — nearly unflyable for FPV practice. | Oscar Liang review |
| RadioMasterOS | Android app replacing EdgeTX. Modern UI, model profiles, channel monitor, telemetry, ELRS integration, Lua scripts. First-generation, not as mature as EdgeTX. | Oscar Liang review |
| Price | $249.99 USD | Oscar Liang review |

## External References

### 3D scan

Physical scan of the AX12 transmitter — useful for custom enclosures, mount design, accessory CAD, and dimensional reference.

- [AX12 transmitter scan on Thingiverse](https://www.thingiverse.com/thing:7347916) — scan by LNDSQD
