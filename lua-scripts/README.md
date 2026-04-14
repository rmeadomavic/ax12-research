# AX12 Lua Scripts

Custom Lua scripts for the RadioMaster AX12. Run from: **RadioMaster App > System Menu > Lua Scripts > Tools**

Scripts are installed to `/storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/` on the device.

## Military / Tactical

| Script | Description |
|--------|-------------|
| **tak-osd.lua** | TAK/ATAK-style HUD: GPS coords, MGRS grid, compass, RSSI/LQ, armed status, mission timer |
| **ccip.lua** | CCIP targeting reticle: physics-based impact point, range rings, drift vector, RELEASE cue |
| **mgrs-tool.lua** | MGRS coordinate converter: WGS84 to UTM/MGRS, waypoint save, distance/bearing |
| **preflight.lua** | 12-item pre-flight checklist with auto-check from telemetry, GO/NO-GO status |
| **mission-timer.lua** | 6-phase mission timer: STARTUP/LAUNCH/TRANSIT/ON STATION/RTB/RECOVERY |

## FPV / Racing

| Script | Description |
|--------|-------------|
| **bf-osd.lua** | Betaflight-style OSD: artificial horizon, compass tape, battery, RSSI, altitude, speed, warnings |
| **race-timer.lua** | Lap timer: practice and timed race modes, delta-to-best, JSONL result saving |
| **vtx-manager.lua** | VTx frequency manager: 48 channels, pilot assignment, interference checking, raceband quick setup |
| **wind-calc.lua** | Wind component calculator: headwind/crosswind, wind rose, Beaufort scale, platform GO/NO-GO |

## General

| Script | Description |
|--------|-------------|
| **ax12-dashboard.lua** | Real-time dashboard: gimbals, switches, ELRS link quality, battery voltage |
| **compass.lua** | Compass rose with attitude indicator, IMU heading, touch recalibration |
| **battery-log.lua** | TX battery tracker: voltage graph, CSV logging, discharge rate, runtime estimation |
| **Game-simulator.lua** | FPV drone racing simulator game with gates and scoring |
| **elrsV3.lua** | ELRS configuration tool (standard EdgeTX) |

## Development

| Script | Description |
|--------|-------------|
| **test-api.lua** | API probe: dumps all global Lua symbols available in the VM |
| **shm-probe.lua** | Shared memory investigation: maps getShmVar/setShmVar IPC variables |

## Installation

Copy `.lua` files to the device:
```bash
scp lua-scripts/*.lua ax12:~/
ssh ax12 su 0 cp /c/Users/Kyle Adomavicius/*.lua /storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/
```

All scripts use the EdgeTX convention: `-- TNS|Name|TNE` header, `return { init=init, run=run }` module pattern.
