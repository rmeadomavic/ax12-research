# Native Library Analysis: libRadioMasterAX_arm64-v8a.so

**File:** `lib/arm64-v8a/libRadioMasterAX_arm64-v8a.so`  
**Size:** 25,233,176 bytes (~25MB)  
**Type:** ELF 64-bit LSB shared object, ARM aarch64  
**Strings:** 266,670 total  
**Dynamic symbols:** 13,023  

## Architecture Overview

The Flyshark app (`com.Flyshark.RadioMasterAX`) is a Qt6/QML application with a large native C++ backend. The native library handles all hardware communication, protocol parsing, radio control logic, and exposes QML-accessible singletons for the UI layer.

```
┌─────────────────────────────────────────────────────────────┐
│                      QML UI Layer                           │
│  (RCAX12V2_*.qml, QControl_*.qml, LVGL widgets)            │
├─────────────────────────────────────────────────────────────┤
│                   QML Singletons                            │
│  AppRadioControl  AppComHub  QElrsModule  QGimbalControl    │
│  QSharkFwControl  QSensorControl  QSysApp  AppThemes        │
├─────────────────────────────────────────────────────────────┤
│                  Communication Layer                        │
│  QCommUsart (UART/ttyS0)  QCommTcp  USB-HID                │
├─────────────────────────────────────────────────────────────┤
│              UMBUS Protocol Engine                          │
│  UMBUS_Init  UMBUS_Decode  UMBUS_Fill  UMBUS_GetPack       │
│  UMBUS_StartPack  UMBUS_EndPack  UMBUS_Msg_Pack            │
│  UMBUS_Reset                                                │
├─────────────────────────────────────────────────────────────┤
│              CRSF Protocol Engine                           │
│  CrsfSerial  (encode/decode ELRS CRSF frames)              │
├─────────────────────────────────────────────────────────────┤
│           RC Control Engine (EdgeTX-derived)                │
│  RcMixed*  RcSrc*  rcCurve*  rcJoystickMap                 │
│  Lua 5.3 scripting engine                                   │
├─────────────────────────────────────────────────────────────┤
│              Map / Terrain / GCS Engine                     │
│  QGCMapEngine  TerrainQuery  QGeoTiled*                     │
│  Multiple map providers (Google, Bing, Esri, OSM, etc.)     │
└─────────────────────────────────────────────────────────────┘
```

## UMBUS Protocol

### C API Functions

| Function | Purpose |
|----------|---------|
| `UMBUS_Init` | Initialize UMBUS state machine |
| `UMBUS_Decode` | Parse incoming byte stream into messages |
| `UMBUS_Fill` | Add data to an outgoing UMBUS frame |
| `UMBUS_GetPack` | Retrieve a complete parsed packet |
| `UMBUS_StartPack` | Begin constructing a new outgoing frame |
| `UMBUS_EndPack` | Finalize outgoing frame (add checksum) |
| `UMBUS_Msg_Pack` | Packed message struct passed to handlers |
| `UMBUS_Reset` | Reset protocol state |

### Addresses

| Constant | Purpose |
|----------|---------|
| `COM_UMBUS_ADD_RC` | Radio controller (the AT32 MCU) |
| `COM_UMBUS_ADD_FC` | Flight controller (external, via serial/telemetry) |
| `COM_UMBUS_ADD_GIMBAL` | Camera gimbal (external) |

### Error Strings

- `UMBUS-ERROR %d:%s` — General UMBUS error with code and description
- `UMBUS-RX CHECKSUM ERROR %x : %x` — Received frame checksum mismatch (expected vs actual)
- `UMBUS-RX LENGTH ERROR` — Frame length field doesn't match actual data
- `UMBUS-RX TIMEOUT..` — No complete frame received within timeout period

### Message Routing

AppComHub receives raw bytes from three transports and routes parsed UMBUS messages:

```
QCommUsart (UART/ttyS0) ──→ umbusRxPackCallBack() ──→ uartPackReceived()
QCommTcp   (TCP)         ──→ umbusRxPackCallBack() ──→ tcpPackReceived()
USB-HID                  ──→                        ──→ usbhidPackReceived()
                                                          │
                                                          ▼
                                                   umbusDataPackRxed()
                                                          │
                                                          ▼
                                                   umbusPackRxed()
                                                          │
                    ┌─────────────┬──────────────┬────────┴────────┐
                    ▼             ▼              ▼                 ▼
           AppRadioControl  QGimbalControl  QSharkRFModule  QSensorControl
           AppFcTaskCtr     QMapControl     QComPackControl QFcStateViewControl
           AppSharkFcCtr    QSharkFwControl QSysApp         AppSharkFcSetting
```

All 12 handler classes implement `umbusPackReceived(UMBUS_Msg_Pack)`.

### Transport: QCommUsart

The UART driver class:

| Method | Purpose |
|--------|---------|
| `openComByName(QString)` | Open serial port by device path |
| `closeCom()` | Close serial port |
| `IsConnect()` | Check connection state |
| `getSerialPortList()` | Enumerate available serial ports |
| `onTimeToRead()` | Timer-driven read callback |
| `usartReceived()` | Data received signal |
| `writePack(int, unsigned char*, int, int, int)` | Write a packet (addr, data, len, type, subtype?) |
| `umbusFillToTxBuff(unsigned char*, int)` | Fill TX buffer with UMBUS frame bytes |
| `umbusRxPackCallBack(_UMBUS*, _UMBUS_MSG*)` | RX complete callback |

Underlying serial port abstraction uses `QSerialPortLinux` (openPort, closePort, readAll, writeBytes) wrapping standard POSIX termios.

## CRSF Protocol (ELRS)

The app includes a full CRSF (Crossfire Serial) implementation for ELRS communication:

### CrsfSerial Class

| Method | Purpose |
|--------|---------|
| `serialDataIn(const unsigned char*, int)` | Feed raw bytes into CRSF parser |
| `processPacketIn(unsigned char)` | Process one byte through state machine |
| `shiftRxBuffer(unsigned char)` | Shift RX buffer for byte alignment |
| `packetChannelsPacked(const crsf_header_s*)` | Decode packed RC channel data |
| `makePacket(unsigned char, unsigned char, const void*, unsigned char, unsigned char*)` | Construct a CRSF packet |
| `writePacket(unsigned char, unsigned char, const void*, unsigned char)` | Write packet to output |
| `calCrc(unsigned char*, unsigned char)` | Calculate CRC8 |
| `initCrc(unsigned char)` | Initialize CRC lookup table |

### ELRS Module (QElrsModule)

| Method | Purpose |
|--------|---------|
| `packRxed(crsf_header_s*, unsigned char*)` | Handle received CRSF packet |
| `packetLinkStatistics(const crsf_header_s*)` | Parse link stats (RSSI, LQ, SNR) |
| `packetGps(const crsf_header_s*)` | Parse GPS telemetry |
| `packetAttitude(const crsf_header_s*)` | Parse attitude (pitch/roll/yaw) |
| `packBattery(const crsf_header_s*)` | Parse battery telemetry |
| `packDeviceInf(const crsf_header_s*)` | Parse device info response |
| `decodeElrsParameterStruct(crsf_header_s*)` | Decode ELRS Lua parameter |
| `parseElrsInfoMessage(const crsf_header_s*)` | Parse ELRS info message |
| `reqElrsParameterTask()` | Request ELRS parameters |
| `startReqParameter()` | Start parameter request sequence |
| `sendMenuCmd(int, int)` | Send menu command to ELRS module |
| `getElrsSetItemList()` | Get ELRS settings as QML list |

### Crossfire Telemetry Functions

```
getCrossfireSensor(unsigned char, unsigned char)
getCrossfireTelemetryValue<4>(unsigned char, int&, unsigned char*)
processCrossfireTelemetryFrame(unsigned char*)
processCrossfireTelemetryValue(unsigned char, int, unsigned char*)
pushCrossfireDataToQueues(unsigned char*, int)
clearCrossfireDataQueues()
crossfireSetDefault(int, unsigned char, unsigned char)
crsfTelemetryPackEnd(CrossfireSensor&)
```

### HardwareModule

| Method | Purpose |
|--------|---------|
| `instance()` | Singleton access |
| `isCrossfireConnect()` | Check if CRSF/ELRS module is connected |
| `setCrossfireModePtr(unsigned char*)` | Set CRSF mode pointer |

## Radio Control Engine

### Source/Input System

Sources (`_SRC_IDX_DEF`) represent all physical inputs. Key functions:

| Function | Purpose |
|----------|---------|
| `RcSrcInit(signed char*)` | Initialize source system |
| `RcSrcEnable(_SRC_IDX_DEF, int)` | Enable/disable a source |
| `RcSrcGetRaw(int)` | Get raw value for source index |
| `RcSrcSetRaw(int, int)` | Set raw value (for testing/override) |
| `RcSrcGetType(int)` | Get source type (stick, switch, pot, etc.) |
| `RcSrcUpdate(int)` | Update source value |
| `RcSrcGetTramList()` | Get trim list |
| `RcSrcEventCallback(int, int)` | Source change event callback |
| `RcSwEnableCheck(int, int)` | Check if switch is enabled |

Source types observed in QML: `srcType === 4` (switches), `srcType !== 0x00` (enabled sources).

### Input Labels

| Function | Purpose |
|----------|---------|
| `getSwitchName(char*, unsigned char, bool)` | Get switch label (SA, SB, SC...) |
| `getSwitchIndex(const char*, bool)` | Get switch index from name |
| `getSwitchPositionName(char*, int, bool)` | Get position label (up/mid/down) |
| `getSwitchPositionSymbol(unsigned char)` | Get position icon |
| `getSwitchWarnSymbol(unsigned char)` | Get warning indicator |
| `getPotLabel(unsigned char, bool)` | Get pot/slider label |
| `getTrimLabel(unsigned char, bool)` | Get trim label |
| `getTrimSourceLabel(unsigned short, signed char)` | Get trim source label |
| `getTrimEvent()` | Get current trim event |

Stick names: `STR_STICK_NAMES0` through `STR_STICK_NAMES3` (4 gimbal axes).

### Mixer System

| Function | Purpose |
|----------|---------|
| `RcMixedInit()` | Initialize mixer |
| `RcMixedAdd(int, _CH_MIXED_CFG*)` | Add mix to channel |
| `RcMixedGetCfgData(int, int)` | Get mix config for channel+index |
| `RcMixedGetChCfg(int)` | Get all mixes for a channel |
| `RcMixedDelCfg(int, int)` | Delete a mix |
| `RcMixedClear()` | Clear all mixes |
| `RcMixUpdateOut(int)` | Update mixer output |
| `RcMixLoadBytes(unsigned char*, int)` | Load mixer config from bytes |
| `RcMixSaveBytes(unsigned char*, int)` | Save mixer config to bytes |
| `RcMixCfgFileSize()` | Get mixer config file size |
| `creatMixChannel(_SRC_IDX_DEF, _CH_MIXED_CFG*)` | Create mix from source |
| `getMixedCfg(int, int)` | Get mixed config |

### Curve System

| Function | Purpose |
|----------|---------|
| `rcCurveInit(_RC_CURVE*)` | Initialize curve |
| `rcCurveSet(_RC_CURVE*)` | Set curve data |
| `rcCurveGet(int)` | Get curve by index |
| `rcCurveApply(int, float)` | Apply curve to value |
| `rcCureExpo(float, float)` | Apply expo curve |

### Channel Output

- **32 channels** total (monitors: 1-8, 9-16, 17-24, 25-32)
- `MAX_OUTPUT_CHANNELS` constant defined
- `CH01` through `CH16` primary, `CH17-CH32` extended
- Channel range: expandable to **125%**
- Per-channel: reverse, slow motion (0.1-5.0s), min/max limits, midpoint offset, curves, D/R

### Joystick Mapping

`rcJoystickMap(int*, int*, int)` — maps between physical stick axes and logical channels.

## AppRadioControl (Main RC Controller)

QML singleton — the central radio control class:

### Model Management
- `getRcModelList()` — list all models
- `loadRcCfgFile()` / `loadModelCfgFile(QString)` — load model config
- `saveCurrentModelToFile(QML_Pack_RcModelData)` — save model
- `deleteModel(QString)` — delete model
- `makeNewRcModelStruct()` — create new model
- `importModelCfg(QString, QString)` / `exportModelCfg(QString, QString)` — import/export
- `modelToTemplate(QString, QString)` / `getTemplateList()` — template support

### Source/Input
- `getSrcCfgList()` — get all source configurations (sticks, switches, pots)
- `updateSource(int, int)` — update source value
- `sourceUpdated(int)` — signal: source changed
- `srcInputChannged(int, int, QString)` — signal: input changed

### Mixer/Channels
- `getChOutList()` — get channel output list
- `addMixCfgData(int, int)` / `delMixCfgData(int, int)` / `setMixCfgData(QML_Pack_RcMixCfgData)` — mixer config
- `getCurveList(int)` — get curves
- `getDrData(int, int)` / `setDrData(QML_Pack_RcChCfgDr)` — dual rates
- `setChOutCfgData(QML_Pack_RcChOutCfg)` — channel output config

### Calibration
- `setAdcCalibration(int)` — ADC calibration mode
- `adcSetStateChanged()` — calibration state signal

### Telemetry
- `updateTelemetrySensor(int, _RcTelemetryData&)` — update sensor
- `telemetrySensorUpdated(int)` — signal
- `setTelemetryPosation(double, double)` — GPS position
- `TelemetryNotifyCallback(int, _TelemetryNotify)` — notification callback
- `getBlackBoxTelemetrySampleRecords()` — black box data

### Device Sync
- `syncRcCfgDataFromDev()` / `syncRcCfgDataToDev()` — sync config with MCU
- `taskSyncDataAndDev()` — sync task
- `syncCfgFromeDeviceEnd()` / `syncCfgToDeviceEnd()` — sync complete signals

### RF Control
- `rebootRFModule()` — reboot ELRS module
- `setUsbToVcp(unsigned char)` — switch USB to virtual COM port mode

### Attitude/IMU
- `setAttitude(double, double, double)` — set attitude (pitch, roll, yaw)
- `attitudeChanged(double, double, double)` — attitude signal

## QGimbalControl (Camera Gimbal)

Controls an external camera gimbal via UMBUS:

| Method | Purpose |
|--------|---------|
| `setGimbalAngle(double, double, double)` | Set gimbal angles (pitch, roll, yaw) |
| `saveSetting()` | Save gimbal settings |
| `loadSetFromFile(QString)` / `saveToFile(QString)` | File I/O |
| `qml_Get_GimbalCfg()` | Get config for QML |
| `qml_UpdateSetting(const QML_Pack_GimbalCfg&)` | Update from QML |
| `motoDisableChanged()` | Motor disable signal |

**Note:** This controls an external camera gimbal connected via UMBUS, NOT the radio's control sticks (which are called "gimbals" in RC terminology but are read by the AT32 MCU as analog inputs).

## QSensorControl (IMU/Oscilloscope)

| Method | Purpose |
|--------|---------|
| `reqOscData()` | Request oscilloscope data |
| `oscDataRxEnd(QList<int>)` | Oscilloscope data received |
| `fillLogToWaveView()` | Fill waveform display |
| `setLineGroup(int)` | Set waveform display group |

## QSharkFwControl (Firmware Updates)

Handles firmware updates for both MCU and ELRS backpack:

| Method | Purpose |
|--------|---------|
| `checkFirmwareInfoWeb(const QString&, const QString&)` | Check for updates online |
| `downloadFirmwareFile(const QString&)` | Download firmware file |
| `loadFwFromFile(QString)` / `loadFwFile()` | Load local firmware file |
| `decodeFwFile(const QByteArray&)` | Decode firmware binary |
| `convertBin2Array(QString)` | Convert binary to array |
| `updateFw()` / `updateApp(QString)` | Flash firmware |
| `threadUpdateFw()` / `threadGetLog()` | Background threads |
| `sendBlock(unsigned char*, int)` | Send firmware block |
| `SendEndPack(unsigned char*)` | Send end-of-update packet |
| `reqDevInf(int)` | Request device info |
| `requestLogInf()` / `requestLogPage()` | Request MCU logs |
| `saveLogToFile(QString)` | Save logs |
| `umbusRXED_FwUpdate(const UMBUS_Msg_Pack&)` | Handle FW update UMBUS response |

## Lua Scripting Engine

The app embeds **Lua 5.3.6** with EdgeTX-compatible scripting:

- Scripts stored at `/storage/emulated/0/AX12LUA/`
- Packaged scripts at `://luaScript/AX12LUA.tar.gz` (in APK assets)
- Script types: tools (`SCRIPTS/TOOLS/`), mixes (`Lua mix output %d`)
- Entry point: `main.lua`
- Classes: `LuaScriptManager`, `LuaEventHandler`, `LuaWidget`, `LuaWidgetFactory`, `QLuaWidget`, `StandaloneLuaWindow`
- Lua ↔ serial bridge: `luaSetGetSerialByte(void*, callback)` — allows Lua scripts to send/receive serial data

## Map / GCS Engine

Full ground control station capability with:

### Map Providers (30+)
Google (street, satellite, hybrid, terrain, labels), Bing (road, satellite, hybrid), Esri (street, satellite, terrain), OpenStreetMap, Mapbox (8 variants), MapQuest, VWorld, Japan GSI (5 variants), CyberJapan, Eniro, Statkart (3 variants), LINZ, Copernicus elevation, custom URL.

### Tile Cache System
`QGCMapEngine` with offline tile caching:
- `QGCCachedTileSet` — tile set management
- `QGCFetchTileTask` / `QGCSaveTileTask` — download and save
- `QGCExportTileTask` / `QGCImportTileTask` — export/import
- `QGCPruneCacheTask` — cache maintenance
- `QGeoFileTileCacheQGC` — file-based cache

### Terrain
- `TerrainTileCopernicus` — Copernicus DEM
- `TerrainAirMapQuery` / `TerrainOfflineAirMapQuery` — AirMap integration
- `TerrainPathQuery` / `TerrainPolyPathQuery` — path elevation profiles

### Flight Controller Integration
- `AppFcTaskCtr` / `AppSharkFcCtr` — FC task control
- `AppSharkFcSetting` — FC settings with motor mix table
- `QFcStateViewControl` — FC state display
- `QML_Pack_FcSet` / `QML_Pack_FcFwInf` — FC config/firmware info
- `QML_Pack_AhrsReport` — AHRS attitude data
- `QML_Pack_NavReport` — Navigation data
- `QML_Pack_FlyReport` — Flight report
- `QML_Pack_MissionData` — Mission waypoints

## QML Data Models

These structs are exposed to the QML layer:

| Type | Purpose |
|------|---------|
| `QML_Pack_RcSrcCfg` | Source/input configuration (name, type, index, enable) |
| `QML_Pack_RcSrcRaw` | Raw source values |
| `QML_Pack_RcChOutCfg` | Channel output configuration |
| `QML_Pack_RcMixCfgData` | Mixer configuration |
| `QML_Pack_RcCurveCfgData` | Curve configuration |
| `QML_Pack_RcChCfgDr` | Dual rates configuration |
| `QML_Pack_RcModelData` | Model data (name, config) |
| `QML_Pack_RcModelCfgData` | Full model configuration |
| `QML_Pack_RcTimeCfgData` | Timer configuration |
| `QML_Pack_GimbalCfg` | Camera gimbal configuration |
| `QML_Pack_ElrsSetItem` | ELRS settings item |
| `QML_Pack_FHSS_CFG_DATA` | Frequency hopping configuration |
| `QML_Pack_MissionData` | Mission waypoint data |
| `QML_Pack_FcSet` | Flight controller settings |
| `QML_Pack_FcFwInf` | FC firmware info |
| `QML_Pack_AhrsReport` | AHRS attitude report |
| `QML_Pack_NavReport` | Navigation report |
| `QML_Pack_FlyReport` | Flight report data |
| `QML_Pack_BlackBoxTelemetrySample` | Black box telemetry sample |
| `QmlPack_TelemetryItem` | Telemetry sensor item |

## UI Framework

Dual UI system:
1. **QML/Qt Quick** — primary UI (RCAX12V2_*.qml files)
2. **LVGL** — secondary UI for certain screens (EdgeTX-derived widgets)

LVGL widgets include: Arc, Box, Circle, Choice, ColorPicker, Dialog, FilePicker, FontPicker, Image, Label, Line, Menu, NumberEdit, Picker, QRCode, Rectangle, Setting, Slider, SourcePicker, SwitchPicker, TextButton, TextEdit, TimerPicker, ToggleSwitch, Triangle.

Custom Qt components: `QAttitudeDashboardA`, `QJoystickDashboardA`, `QWaveView`, `QWaveView2`, `QCMarkQml` (Markdown renderer), `QRTSPVideo` (RTSP video stream), `QRCode`.

## Other Notable Features

### Audio
- `AudioThread` — audio playback
- Text-to-speech via Android TTS
- MP3 playback for custom voice alerts
- `AppRadioControl::playAudioFile(QString)` — play audio

### Camera
- `AppCameraControl` — camera control
- `QRTSPVideo` / `RtspWorkerThread` — RTSP video streaming
- Camera I2C at `i2c@11008000` (main2) and `i2c@11009000` (main, sub)

### Encryption
- `QAESEncryption` — AES encryption (for config protection?)

### Logging
- `AppSharkLog` — application logging
- `spdlog` library for structured logging
- `Logger` class

### USB
- `setUsbToVcp(unsigned char)` — switch USB mode to Virtual COM Port
- `UsbSDConnected` — USB/SD card detection

### RTSP Video
- Full RTSP client for FPV video streaming

## String Constants (STR_* labels)

The library contains 200+ `STR_*` constants for UI localization. Key RC-specific ones:

- `STR_STICK_NAMES0` through `STR_STICK_NAMES3` — gimbal axis names
- `STR_BAUDRATE` / `STR_MAXBAUDRATE` — baud rate settings
- `STR_CRSF_ARMING_MODE` / `STR_CRSF_ARMING_MODES` — CRSF arm modes
- `STR_FLASH_EXTERNAL_ELRS` — external ELRS flash
- `STR_16CH_WITH_TELEMETRY` / `STR_16CH_WITHOUT_TELEMETRY` / `STR_8CH_WITH_TELEMETRY` — channel modes
- `STR_PWM_STICKS_POTS_SLIDERS` — PWM output for sticks/pots
- `STR_AUX_SERIAL_MODE` / `STR_AUX2_SERIAL_MODE` — auxiliary serial modes
- `STR_ADCFILTERVALUES` — ADC filter settings
- `STR_MODULE_NO_SERIAL_MODE` — module serial mode
- `STR_SERIAL_BUS` / `STR_USB_SERIAL` — serial bus config

## Key Observations

1. **EdgeTX Heritage**: The mixer, source, curve, and Lua systems are clearly derived from EdgeTX/OpenTX. Function names like `RcMixed*`, `RcSrc*`, `rcCurve*`, and the LVGL widget layer are direct ports.

2. **UMBUS Wraps CRSF**: The app speaks UMBUS to the MCU over UART. For ELRS communication, CRSF frames are encapsulated within UMBUS messages. The MCU then relays CRSF to the actual ELRS RF module.

3. **Three Communication Transports**: UART (primary, to MCU), TCP (network, for simulators?), USB-HID (for direct PC connection). All use the same UMBUS protocol.

4. **Full GCS Capability**: The app is far more than a radio controller — it includes a full ground control station with maps, terrain, mission planning, FC settings, telemetry, and video streaming.

5. **32 Channels**: The system supports 32 output channels, not just the 16 visible in basic ELRS mode.

6. **Camera Gimbal Control**: Separate from stick gimbals — controls an external camera gimbal via UMBUS (pitch/roll/yaw angles).

7. **Lua Scripting**: Full Lua 5.3 support for custom widgets, mixes, and tools, stored at `/storage/emulated/0/AX12LUA/`.

8. **Firmware Update Over UMBUS**: The app can flash both MCU firmware and ELRS backpack firmware via the UMBUS protocol, using block-transfer commands.

9. **ADC Calibration**: `setAdcCalibration(int)` suggests the MCU's ADC values are calibrated through the app, with calibration data synced between app and MCU via `syncRcCfgDataToDev()`.

10. **Oscilloscope Feature**: `QSensorControl` has oscilloscope/waveform display capability — likely for viewing raw sensor data (IMU, ADC) in real-time.


## UMBUS Symbol Map (from libRadioMasterAX_arm64-v8a.so, 24MB, 266,670 strings)

### Core UMBUS Engine Functions
| Symbol | Purpose |
|--------|---------|
| UMBUS_Init | Initialize the UMBUS engine |
| UMBUS_Decode | Decode incoming UMBUS frames |
| UMBUS_Fill | Fill a frame buffer with data |
| UMBUS_StartPack | Begin multi-frame config transfer |
| UMBUS_EndPack | End multi-frame config transfer |
| UMBUS_GetPack | Retrieve packed data from transfer |
| UMBUS_Msg_Pack | Message packing struct/type |
| UMBUS_Reset | Reset the engine state |

### UMBUS Address Constants
| Constant | Target |
|----------|--------|
| COM_UMBUS_ADD_RC | Radio controller (AT32 MCU) |
| COM_UMBUS_ADD_FC | Flight controller (external) |
| COM_UMBUS_ADD_GIMBAL | Camera gimbal (external) |

### Error Messages (from UMBUS_Decode)
- UMBUS-ERROR %d:%s (generic error with code)
- UMBUS-RX CHECKSUM ERROR %x : %x (expected vs received CRC)
- UMBUS-RX LENGTH ERROR (frame size validation failed)
- UMBUS-RX TIMEOUT.. (no data within timeout window)

### Communication Hub Architecture

AppComHub is the central message dispatcher:

| Method | Source |
|--------|--------|
| uartPackReceived | Physical serial port (ttyS0) |
| tcpPackReceived | Network TCP connection |
| usbhidPackReceived | USB HID device |
| umbusPackRxed | General UMBUS pack handler |
| umbusDataPackRxed | Data-specific pack handler |

Discovery: UMBUS protocol has THREE transport layers - UART, TCP, and USB HID.

### UMBUS Pack Receivers (per controller)
| Class | Responsibility |
|-------|----------------|
| AppRadioControl | Main radio/channel control |
| QSharkRFModule | ELRS RF module (telemetry, link) |
| QSensorControl | Sensor data (IMU, temperature) |
| QGimbalControl | External gimbal control |
| AppFcTaskCtr | Flight controller task management |
| AppSharkFcCtr | Shark FC control interface |
| AppSharkFcSetting | FC settings/configuration |
| QFcStateViewControl | FC state display |
| QMapControl | Map/navigation |
| QComPackControl | Communication pack control |
| QSharkFwControl | Firmware updates |
| QSysApp | System application |

### Firmware Update Protocol
QSharkFwControl has:
- umbusPackReceived - general packet handler
- umbusRXED_FwUpdate - firmware update data receiver
- umbusPackLog - packet logging for firmware updates

### Transport Classes
| Class | Function |
|-------|----------|
| QCommUsart | UART serial (ttyS0), primary transport |
| QCommTcp | TCP/IP transport (UMBUS over network!) |
| QSerialPortLinux | Linux serial port abstraction |
| QSerialPortExt | Extended serial port features |

Both QCommUsart and QCommTcp implement:
- umbusFillToTxBuff(uint8_t* data, int len) - write to TX buffer
- umbusRxPackCallBack(_UMBUS*, _UMBUS_MSG*) - receive callback

### Implications

1. UMBUS over TCP means remote control is architecturally supported - a laptop app could send UMBUS commands over WiFi/Tailscale
2. USB HID input handler means external HID devices (SpaceMouse, gamepads) are wired into the control path
3. The UMBUS_StartPack/EndPack/GetPack API confirms multi-frame config transfers exist (model sync protocol)
4. Three-address scheme (RC/FC/GIMBAL) shows UMBUS was designed as a multi-device bus, not just SoC-to-MCU


## Application Class Architecture (488 classes, 141 key)

### QGroundControl Heritage
The Flyshark app is built on a QGroundControl fork with RadioMaster-specific extensions:
- QGCMapEngine, QGCMapEngineManager, QGeoTiledMapQGC — QGC map tile engine
- 30+ map providers (Google, Mapbox, Bing, Esri, OSM, LINZ, Statkart, etc.)
- QMapWaypointData — mission/waypoint management
- TerrainAirMapQuery, TerrainOfflineAirMapQuery — terrain elevation queries
- TelemetryBlackBox — flight data recording

### Flight Controller Integration
| Class | Purpose |
|-------|---------|
| QML_Pack_AhrsReport | AHRS (attitude/heading reference) from FC |
| QML_Pack_NavReport | Navigation/position data from FC |
| QML_Pack_FlyReport | In-flight telemetry report |
| QML_Pack_MissionData | Waypoint/mission data |
| QML_Pack_FcFwInf | Flight controller firmware info |
| QML_Pack_FcSet | FC settings configuration |
| QML_Pack_GimbalCfg | Camera gimbal configuration |
| QML_Pack_BlackBoxTelemetrySample | Blackbox telemetry record |
| QML_Pack_FHSS_CFG_DATA | Frequency hopping spread spectrum config |
| AppFcTaskCtr, AppSharkFcCtr, AppSharkFcSetting | FC task/control/settings |
| QFcStateViewControl | FC status display |

### Radio Model Configuration (matches .rcm binary format)
| Class | Maps to .rcm section |
|-------|---------------------|
| QML_Pack_RcModelCfgData | Model config header |
| QML_Pack_RcModelData | Full model data |
| QML_Pack_RcChOutCfg | Channel output endpoints |
| QML_Pack_RcChCfgDr | Channel dual-rate settings |
| QML_Pack_RcCurveCfgData | Rate/expo curve data |
| QML_Pack_RcMixCfgData | Mixer configuration |
| QML_Pack_RcSrcCfg | Source (input) configuration |
| QML_Pack_RcSrcRaw | Raw source input data |
| QML_Pack_RcTimeCfgData | Timer configuration |

### Lua Engine
| Class | Purpose |
|-------|---------|
| LuaScriptManager | Script lifecycle management |
| LuaEventData / LuaEventHandler | Event dispatch system |
| LuaWidget / LuaWidgetFactory | Widget creation and rendering |
| StandaloneLuaWindow | Full-screen Lua app display |
| QLuaWidget | QML-embedded Lua widget |
| LvglWidgetSwitchPicker | LVGL switch picker control |
| LvglWidgetToggleSwitch | LVGL toggle switch control |

### Communication Layer
| Class | Transport |
|-------|-----------|
| QCommUsart | UART serial (ttyS0, primary) |
| QCommTcp | TCP/IP (network UMBUS) |
| QSerialPortLinux | Linux serial port driver |
| CrsfSerial | CRSF protocol handler |

### ELRS Module
| Class | Purpose |
|-------|---------|
| QSharkRFModule | ELRS radio module control |
| QElrsModule | ELRS configuration |
| QML_Pack_ElrsSetItem | ELRS settings items |

### Other Notable Classes
| Class | Purpose |
|-------|---------|
| UsbSDConnected | USB storage detection |
| ModelConfigData | Model config data management |
| SwitchChoice | Switch input configuration |
| ChannelBar / OutputChannelBar / MixerChannelBar | Channel display widgets |
| LogicalSwitchesViewPage | Logical switch editor |
| RadioTelemetry | Radio telemetry processing |
| SimuDirHandle | Simulator directory handling |
| LcdUpdateThread | Display update thread |


## UMBUS Function Sizes (from ELF symbol table)

### Core Engine
| Function | Size | Purpose |
|----------|------|---------|
| UMBUS_Init | 52B | Initialize engine state |
| UMBUS_Decode | 1332B | Main frame decoder (significant logic) |
| UMBUS_Fill | 108B | Fill frame buffer with data |
| UMBUS_StartPack | 424B | Begin multi-frame config transfer |
| UMBUS_EndPack | 160B | End multi-frame transfer |
| UMBUS_GetPack | 272B | Retrieve packed data |
| UMBUS_Reset | 88B | Reset engine state |

### Pack Receivers (sorted by complexity)
| Class | Size | Handles |
|-------|------|---------|
| AppSharkFcCtr | 3008B | FC commands, AHRS, navigation, missions |
| AppRadioControl | 2780B | Channel data (0x57), radio config |
| QSharkFwControl | 1996B | Firmware update protocol |
| QSharkRFModule | 1660B | ELRS RF module telemetry + config |
| QSharkFwControl (log) | 1532B | FW update logging |
| QGimbalControl | 1316B | External gimbal commands |
| QComPackControl | 1292B | Communication pack control |
| QSharkFwControl (FW RX) | 976B | Firmware data receiver |
| AppSharkFcSetting | 920B | FC settings push/pull |
| AppFcTaskCtr | 704B | FC task management |
| QSensorControl | 516B | Sensor data (IMU, temp) |
| QFcStateViewControl | 304B | FC state display |
| AppComHub (dispatcher) | 88B | Route to handlers |
| QSysApp | 4B | Stub (no-op) |
| QMapControl | 4B | Stub (no-op) |

UMBUS_Decode at 1332 bytes is the most complex single function in the engine,
containing the full frame parsing, CRC validation, and type dispatch logic.
