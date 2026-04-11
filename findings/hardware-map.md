# AX12 Hardware Map

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  RadioMaster AX12                                           │
│                                                             │
│  ┌──────────┐  UMBUS/UART (ttyS0, 921600)   ┌───────────┐  │
│  │ MT8788   │◄─────────────────────────────►│ AT32 MCU  │  │
│  │ SoC      │  Bidirectional:                │           │  │
│  │ Android 9│  MCU→App: gimbal ADC, switch   │ Reads:    │  │
│  │          │           states, MCU status    │ - Gimbals │  │
│  │ App:     │  App→MCU: mixed channel data,  │ - Switches│  │
│  │ Flyshark │           commands, config      │ - Pots    │  │
│  │ Qt6/QML  │                                │ - Scroll  │  │
│  └──────────┘                                │           │  │
│                                              │ Controls: │  │
│                                              │ - ELRS TX │  │
│                                              └───────────┘  │
│                                                             │
│  Serial ports:                                              │
│  - ttyS0 @ 921600: UMBUS protocol to MCU (primary link)     │
│  - ttyS1 @ 9600:   Unknown (no data observed)               │
│  - ttyS2:          Unknown (no data observed)                │
│                                                             │
│  SPI buses (in device tree, NOT used by app):               │
│  - spi@1100a000: ethernet_dm9051, fingerprint               │
│  - spi@11010000: spi1_plat_drv (mt8788 custom)              │
│  - spi@11012000-11019000: unused                            │
│                                                             │
│  I2C buses:                                                 │
│  - i2c@11005000: rt9465 charger, speaker amp @34            │
│  - i2c@11007000: cap_touch @40                              │
│  - i2c@11008000: camera (main2)                             │
│  - i2c@11009000: camera (main, sub)                         │
│  - i2c@1100f000: ALS/proximity @1e, NFC @08                 │
│  - i2c@11011000: gsensor @68, gyro @69, icm42607,           │
│                   msensor @0c, nm_i2c1 @01                  │
│  - i2c@11017000: subpmic @34, usb_type_c @4e               │
└─────────────────────────────────────────────────────────────┘
```

## UMBUS Protocol

RadioMaster's internal bus protocol for MCU ↔ Android communication.

### Frame format
- Sync: 0xA6
- Length: next byte (e.g., 0x57 = 87-byte frame when app active, 0x77 = variable when idle)
- Header: 10 02 04 01 (for channel/status frames)
- Payload: varies by frame type
- Checksum: last byte

### Frame types observed
- `A6 57` (87 bytes): Channel data frame — gimbal values + output channels + switch states
- `A6 08` (8 bytes): Short status/heartbeat
- `A6 10` (16 bytes): Extended status (type 06 subcommand)
- `A6 07`, `A6 0E`, `A6 0C`: App→MCU command packets

### Gimbal data location (in A6 57 frames)
Bytes 6-13 contain 4 signed 16-bit LE gimbal values:
- G0 (bytes 6-7): Gimbal axis — range approx -500 to +500
- G1 (bytes 8-9): Gimbal axis
- G2 (bytes 10-11): Gimbal axis
- G3 (bytes 12-13): Gimbal axis — confirmed moving with stick input

Axis-to-stick mapping: TBD (needs controlled per-axis test)

### Output channels
Bytes 18+ contain 16-bit unsigned values:
- Center: 0x8000 (32768)
- Switch high: 0xFE0C (65036)
- Switch alt: 0xFF9C (65436)

### UMBUS addresses
- COM_UMBUS_ADD_RC: Radio controller (MCU)
- COM_UMBUS_ADD_FC: Flight controller
- COM_UMBUS_ADD_GIMBAL: Camera gimbal

## Key Classes (from native lib)

| Class | Role |
|-------|------|
| AppComHub | Central UMBUS message router (UART, TCP, USB-HID) |
| QSerialPortLinux | Serial port I/O (openPort, closePort, readAll, writeBytes) |
| QSerialPortExt | Extended serial port wrapper |
| AppRadioControl | Radio/mixer control, getSrcCfgList() |
| QGimbalControl | Camera gimbal control, setGimbalAngle, saveSettings |
| QSharkRFModule | ELRS RF module interface |
| QSensorControl | Sensor data (IMU at i2c@11011000?) |
| AppFcTaskCtr / AppSharkFcCtr | Flight controller task management |
| QComPackControl | ELRS backpack control |
| QSharkFwControl | Firmware update (MCU + backpack) |
| LvglWidgetSwitchPicker | Switch UI widget (LVGL-based) |
| QFcStateViewControl | FC status display |
| QMapControl | Map display |

## Helper Functions
- `getSwitchName(char*, bool)` — get switch label
- `getSwitchIndex(const char*, bool)` — get switch index by name
- `getSwitchValue` — get current switch state
- `getSwitchPositionName` — get position label (up/mid/down)
- `getSwitchPositionSymbol` — get position icon
- `getSwitchWarnSymbol` — get warning indicator
- `getPotLabel(unsigned char, bool)` — get pot/slider label
- `setSerialBaudrate` — configure UART speed

## System Info
- SoC: MediaTek MT8788 (device tree: mediatek,mt6771)
- Kernel: 4.4.146
- Android: 9 (Pie), RadioMasterOS
- Root: su 0 <cmd> (factory-installed /system/xbin/su)
- SELinux: permissive
- Boot: verified boot (dm-verity enforcing, green state)
- eMMC: write-protected boot/lk partitions
