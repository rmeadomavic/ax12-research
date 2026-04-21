# Flyshark App Analysis

**Package:** `com.Flyshark.RadioMasterAX`
**Type:** Qt6/QML Android application with native C++ backend
**Purpose:** RC transmitter control, ELRS configuration, ground control station

## Architecture

Single-Activity app (`AndroidStart`) with no Services, ContentProviders, or user-facing BroadcastReceivers. A `BootBroadcastReceiver` listens for `BOOT_COMPLETED` to auto-start the app on power-on.

```
QML UI (RCAX12V2_*.qml, QControl_*.qml, LVGL widgets)
  ↓
QML Singletons (AppRadioControl, AppComHub, QElrsModule, QGimbalControl)
  ↓
Communication (QCommUsart → ttyS0, QCommTcp, USB-HID)
  ↓
UMBUS Protocol Engine → CRSF Protocol Engine (CrsfSerial)
  ↓
RC Control Engine (EdgeTX-derived) + Lua 5.3 VM
```

**Native library:** `libRadioMasterAX_arm64-v8a.so` (25.2 MB, 13,023 dynamic symbols). All protocol handling, mixer logic, and hardware control lives here. QML is presentation only.

## Serial Port Usage

The app exclusively owns `/dev/ttyS0` (921600 baud, 8N1) via `QSerialPort`, with a UUCP lock file at `LCK..ttyS0`. This is the only UMBUS transport in normal operation.

- **QCommUsart** — UART driver: `openComByName()`, timer-driven `onTimeToRead()`, `writePack()` for framed output, `umbusRxPackCallBack()` for receive-complete dispatch.
- **AppComHub** — Central UMBUS message router (singleton). Dispatches decoded frames to 12+ type-specific handlers. Also routes CRSF frames on channel 0xC3.
- **CrsfSerial** — CRSF frame parser/encoder for ELRS telemetry. Handles CRC-8/DVB-S2 validation, channel packing, and link statistics.

All external access to ttyS0 while the app is running must use strace — direct reads steal bytes and corrupt app state.

## UMBUS Message Handlers

The app processes 8 frame types over a 2-second repeating cycle:

| Type | Size | Dir | Rate | Purpose |
|------|------|-----|------|---------|
| 0x57 | 87B | MCU→App | 25 Hz | Channel/gimbal data (33 channels + 4 axes) |
| 0x08 | 7/8B | Both | 4/1 Hz | Heartbeat (MCU 7B, App 8B) |
| 0x15 | 21B | MCU→App | 5 Hz | ELRS telemetry (wraps CRSF 0x3A HANDSET) |
| 0x10 | 18B | MCU→App | ~3 Hz | Extended telemetry (3 sub-indices, CRC init 0x7F) |
| 0x0E | 14B | App→MCU | 2 Hz | Poll/status request |
| 0x0C | 12B | App→MCU | 1 Hz | Config/state |
| 0x07 | 7B | App→MCU | 0.5 Hz | Keep-alive ping |

Traffic is asymmetric: MCU→App is 97.9% of volume (~2.4 KB/s total, ~2% link utilization).

## Lua Scripting VM

Embedded **Lua 5.3.6** with NodeMCU-lineage ROM table support and EdgeTX-compatible API.

- **Script storage:** `/sdcard/AX12LUA/SCRIPTS/TOOLS/`
- **Entry point:** `return { init=init, run=run }` — `run(event, touchState)` returns 0 (continue) or 2 (exit)
- **Shipped scripts:** `elrsV3.lua` (ELRS configurator), `Game-simulator.lua` (FPV sim)

**Three custom C modules:**
1. `bitmap` — LCD drawing/bitmap rendering
2. `etxdir` — Directory listing/file access
3. `lvgl` — Full LVGL v8 widget bindings (Arc, Dialog, FilePicker, Slider, etc.)

**API surface:** `lcd.*` drawing, `model.*` mixer/output/timer, `getValue()`/`getFieldInfo()` for sources, `crossfireTelemetryPop()`/`Push()` for CRSF, `playSound()`. Serial bridge stubs (`luaSetGetSerialByte`) exist but are dead/non-functional on AX12.

## Model Storage

**Format:** Flat binary `.rcm` files at `/data/data/com.Flyshark.RadioMasterAX/files/rcModel/`
**Size:** 1813–1877 bytes (variable, depends on endpoint section)

| Offset | Size | Field |
|--------|------|-------|
| 0x000 | 4B | Magic: `0x12345678` |
| 0x004 | 4B | Creation timestamp (equals filename for user models) |
| 0x008 | 200B | Model name (null-padded) |
| 0x0D0 | 252B | Icon path (`qrc:/image/...`) |
| 0x1CC | 4B | Last-modified timestamp (0 for templates) |
| 0x200 | 4B | Config version (`0x02EC`) |
| 0x204 | 1B | Model type magic (`0xA3`) |
| 0x205 | 1B | Model type: 0=FixedWing, 1=DeltaWing, 2=Heli, 3=Drone |
| 0x208 | 24B | Model-specific params (heli swash config, else zeros) |
| 0x23D | 1B | Trims flag (always 1) |
| 0x23E | 36B | Trim values (center = `0x7F`) |
| 0x262 | 612B | Rate/expo curves (34B records: type, points, expo) |
| 0x4C6 | 36B | Rate values (default `0x64` = 100%) |
| 0x4EC | 276B | Uninitialized memory (leaked heap, not config data) |
| 0x600 | 8B | Endpoint section header (data size × 2, u32le) |
| 0x608 | var | Endpoint records: header + channel mixer/endpoint defs + defaults |

C++ types: `QML_Pack_RcModelCfgData`, `QML_Pack_RcCurveCfgData`, `QML_Pack_RcChOutCfg`,
`QML_Pack_RcMixCfgData`, `QML_Pack_RcChCfgDr`. Full spec in [hardware-map.md](../hardware/hardware-map.md).

Active model tracked in `RcCfgFile.rcCfg` (magic `0x4F61BC00`). Built-in templates: FPVDrone, FixedWing, Helicopter, DeltaWing.

## Settings & Configuration

Qt INI files at `/data/data/com.Flyshark.RadioMasterAX/files/settings/`. No useful config in `shared_prefs`. AES encryption (`QAESEncryption`) protects some config data. Calibration data synced to MCU via `syncRcCfgDataToDev()`.

## HDMI Video Input

FPV video enters via mini-HDMI, decoded by **Richnano RN6752M** (AHD/TVI/CVI/CVBS → MIPI CSI-2, 4-lane, up to 1080p). The app accesses it through Android's Camera2 API, where the RN6752M registers as `camera_main` (sensor ID 0x501). Adds ~140ms latency through the multi-stage conversion pipeline.

## Permissions

`CAMERA` (HDMI input), `BLUETOOTH`, `INTERNET` (firmware updates, map tiles), `ACCESS_FINE_LOCATION` (GCS), `READ/WRITE_EXTERNAL_STORAGE` (Lua scripts, models), `RECORD_AUDIO`, `RECEIVE_BOOT_COMPLETED`.

## IPC Surface

**None.** No exported Activities, no bound Services, no ContentProviders, no useful BroadcastReceivers beyond boot. The app cannot be controlled programmatically. The only integration points are:

1. **Serial port** (ttyS0) — but the app holds exclusive lock
2. **Simulated UI events** — `input tap`/`input keyevent` via ADB
3. **Lua scripts** — user-loaded scripts run inside the app's VM

## GCS Capabilities

Beyond RC control, the app is a full ground control station:
- `QGCMapEngine` — Offline tile caching (30+ map providers)
- `TerrainTileCopernicus` — Copernicus DEM terrain data
- `AppFcTaskCtr` / `AppSharkFcCtr` — Flight controller integration
- `QRTSPVideo` — RTSP video streaming
- `QSharkFwControl` — MCU + ELRS firmware updates (OTA via UMBUS block transfer)
- `QGimbalControl` — External camera gimbal pitch/roll/yaw

## Key Observations

1. **EdgeTX heritage** — Mixer, sources, curves, Lua API, and model format are direct ports from EdgeTX/OpenTX.
2. **UMBUS wraps CRSF** — ELRS telemetry travels as CRSF frames encapsulated in UMBUS 0x15 messages.
3. **33 output channels** — Not the standard 16; full 33-channel system with per-channel reverse, slow motion, min/max, curves, and dual rates.
4. **Three transports** — UART (primary), TCP (simulator/debug), USB-HID (PC); all speak UMBUS.
5. **Dual UI** — Qt Quick/QML for main UI, LVGL for Lua script widgets.
6. **Sole ttyS0 consumer** — All protocol research must go through strace while the app is running.


## SpaceMouse 6DOF Input Modes

The native library defines 6 SpaceMouse variants:
- SpaceMouse A
- SpaceMouse B
- SpaceMouse C
- SpaceMouse D
- SpaceMouse E
- SpaceMouse F

Each likely maps the 6DOF axes (X/Y/Z translation + pitch/roll/yaw rotation) to different channel combinations. The SpaceMouse is a 3Dconnexion device that outputs USB HID events, which aligns with the AppComHub.usbhidPackReceived handler found in the native lib.

## App Version Info

| Field | Value |
|-------|-------|
| Package | com.Flyshark.RadioMasterAX |
| Version | 1.0 (versionCode=1) |
| Min SDK | 28 (Android 9) |
| Target SDK | 35 (Android 15) |
| First install | 2026-03-24 |
| Qt framework | Qt 6.x |
| Build date | Available via QSysApp.getBuildDate() |

## AUX Serial Modes (complete list)

| Mode | Description |
|------|-------------|
| None | Serial port inactive |
| Telemetry In | Receive telemetry from external sensor |
| SBUS Trainer | SBUS trainer input/output |
| Debug | Debug output |
| Lua | Lua script serial access (STUB - not functional) |
| GPS sensor | External GPS receiver input |
| SpaceMouse A-F | 6DOF SpaceMouse input (6 axis mapping variants) |

## Firmware Update

The app checks for updates at:
- fly-shark.com/FileDownload/FirmwareFile/RadioMasterAX.apk
- Update UI: RcSetFirmware settings page
- MCU firmware: via QSharkFwControl (UMBUS firmware update protocol)
- ELRS firmware: via ELRS backpack WiFi or top USB port


## QML UI Architecture

Main entry: qrc:/Qml/RCAX12V2/Ax12Main.qml (version 'V2')

### Settings Pages (20)

| Page | Purpose |
|------|---------|
| RcSetApp | Application settings |
| RcSetBarModel | Model selection bar |
| RcSetChLock | Channel lock configuration |
| RcSetChMixes | Channel mixer editor |
| RcSetChOut | Channel output/endpoint editor |
| RcSetCurvePick | Rate/expo curve picker |
| RcSetElrsV3 | ELRS v3 module settings |
| RcSetFailsafe | Failsafe behavior configuration |
| RcSetFirmware | MCU/ELRS firmware update |
| RcSetFirmwareApp | Android app firmware update |
| RcSetJSModePick | Joystick mode picker (Mode 1/2/3/4) |
| RcSetModelList | Model list and selector |
| RcSetPreCheck | Pre-flight safety checks |
| RcSetSrcList | Source/input list |
| RcSetSystem | System-level settings |
| RcSetTelNotify | Telemetry alert/notification config |
| RcSetTemplate | Model template management |
| RcSetTimer | Timer configuration |
| AppSharkFcSetting | Flight controller settings |

### Camera/Video QML

The HDMI video input uses Qt6 Multimedia:
- Camera object with start()/stop() control
- VideoOutput with PreserveAspectFit fill mode
- 500ms active-check timer (checkCameraActiveTimer)
- cameraUI.cameraIsActive flag for state tracking
