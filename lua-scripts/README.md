# AX12 Lua Scripts

Custom Lua scripts for the RadioMaster AX12. All scripts use the EdgeTX convention: `-- TNS|Name|TNE` header, `return { init=init, run=run }` module pattern.

**Run from:** RadioMaster App > System Menu > Lua Scripts > Tools

**Install:** Copy `.lua` files to `/storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/` on the device.

Tactical and flight ops scripts (TAK OSD, CCIP, 9-Line, MGRS, mission timer, preflight, wind calc, training, compass, battery log, site manager, and more) have moved to [`ax12-tac-tools`](https://github.com/rmeadomavic/ax12-tac-tools).

## FPV / Racing

| Script | Lines | Description |
|--------|-------|-------------|
| **race-timer** | 512 | Lap timer: practice and timed race modes, delta-to-best coloring, JSONL result saving |
| **vtx-manager** | 626 | VTx frequency manager: 48 channels across 6 bands, pilot assignment, interference checking |
| **Game-simulator** | ~400 | FPV drone racing simulator game with 3D gates and scoring |

## General / Utility

| Script | Lines | Description |
|--------|-------|-------------|
| **ax12-dashboard** | ~250 | Real-time dashboard: gimbals, switches, ELRS link quality, battery voltage |
| **elrsV3** | ~800 | ELRS v3 configuration tool (standard EdgeTX community script) |

## Development / Debug

| Script | Lines | Description |
|--------|-------|-------------|
| **test-api** | ~100 | API probe: dumps all global Lua symbols available in the AX12 VM |
| **shm-probe** | ~150 | Shared memory investigation: maps getShmVar/setShmVar IPC variables |
