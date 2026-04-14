# AX12 Lua Scripts

Custom Lua scripts for the RadioMaster AX12. All scripts use the EdgeTX convention: `-- TNS|Name|TNE` header, `return { init=init, run=run }` module pattern.

**Run from:** RadioMaster App > System Menu > Lua Scripts > Tools

**Install:** Copy `.lua` files to `/storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/` on the device.

## Tactical / Military

| Script | Lines | Description |
|--------|-------|-------------|
| **tak-osd** | 285 | TAK/ATAK-style HUD: GPS coords, MGRS grid, compass, RSSI/LQ, armed status, mission timer |
| **ccip** | 350 | CCIP targeting reticle: physics-based impact point prediction, range rings, drift vector, RELEASE cue |
| **mgrs-tool** | ~400 | MGRS coordinate converter: WGS84 to UTM/MGRS, waypoint save, distance/bearing |
| **preflight** | ~370 | 12-item pre-flight checklist: auto-check from telemetry, GO/NO-GO status, category badges |
| **mission-timer** | 338 | 6-phase mission timer: STARTUP/LAUNCH/TRANSIT/ON STATION/RTB/RECOVERY with auto-advance |
| **nineline** | 237 | 9-Line CAS brief template: auto-fill target elevation and location from GPS/MGRS |
| **freq-decon** | 253 | RF frequency deconfliction: 900MHz/2.4GHz/5.8GHz bands, conflict detection, auto-assign |

## FPV / Racing

| Script | Lines | Description |
|--------|-------|-------------|
| **bf-osd** | 760 | Betaflight-style OSD: artificial horizon, compass tape, battery, RSSI, altitude, speed, FPV/military style toggle |
| **race-timer** | 512 | Lap timer: practice and timed race modes, delta-to-best coloring, JSONL result saving |
| **vtx-manager** | 626 | VTx frequency manager: 48 channels across 6 bands, pilot assignment, interference checking |
| **wind-calc** | 432 | Wind component calculator: headwind/crosswind, wind rose, Beaufort scale, platform GO/NO-GO |
| **training** | 303 | 6 training exercises: HOVER, BOX, FIGURE 8, ORBIT, SPEED RUN, LANDING with scoring |
| **Game-simulator** | ~400 | FPV drone racing simulator game with 3D gates and scoring |

## General / Utility

| Script | Lines | Description |
|--------|-------|-------------|
| **ax12-dashboard** | ~250 | Real-time dashboard: gimbals, switches, ELRS link quality, battery voltage |
| **compass** | 460 | Compass rose with attitude indicator, IMU heading, touch recalibration |
| **battery-log** | 317 | TX battery tracker: voltage graph, CSV logging, discharge rate, runtime estimation |
| **site-manager** | 368 | Flying site database: GPS save, distance/bearing, JSON persistence |
| **elrsV3** | ~800 | ELRS v3 configuration tool (standard EdgeTX community script) |

## Development / Debug

| Script | Lines | Description |
|--------|-------|-------------|
| **test-api** | ~100 | API probe: dumps all global Lua symbols available in the AX12 VM |
| **shm-probe** | ~150 | Shared memory investigation: maps getShmVar/setShmVar IPC variables |
