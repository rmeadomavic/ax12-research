# AX12 Lua Scripting Environment

## Overview

The AX12 runs an embedded Lua 5.3 VM, patched with ROM table support originating from NodeMCU lineage. Scripts follow the OpenTX/EdgeTX convention of returning `{init=..., run=...}` tables and use the standard EdgeTX Lua API surface.

## Script Location

Scripts are stored at `/sdcard/AX12LUA/SCRIPTS/TOOLS/` (symlinked from `/storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/`).

## Installed Scripts

| Script | Lines | Purpose | License |
|--------|-------|---------|---------|
| `elrsV3.lua` | 955 | ELRS configurator (r15) | GPLv2 |
| `Game-simulator.lua` | 350 | FPV drone racing simulator | Unknown |

## Custom Lua Modules

RadioMaster exposes three custom C modules beyond the standard Lua library:

| Module | Opener Function | Purpose |
|--------|-----------------|---------|
| bitmap | `luaopen_bitmap` | LCD drawing / bitmap rendering |
| etxdir | `luaopen_etxdir` | Directory listing and file access |
| lvgl | `luaopen_lvgl` | LVGL UI widget framework |

## Standard EdgeTX API

The VM exposes the standard EdgeTX/OpenTX Lua API including:

- **Telemetry:** `crossfireTelemetryPush()`, `crossfireTelemetryPop()` — CRSF protocol bridge
- **LCD:** Drawing primitives (lines, rectangles, text, bitmaps)
- **Input:** `getValue()` for reading channels, switches, pots, and other sources
- **Model:** Model info queries

## Internal Symbols

Key symbols found in the native library related to Lua management:

| Symbol | Purpose |
|--------|---------|
| `luaScriptManager` | Script lifecycle management (load/run/stop) |
| `luaLoadScripts` | Script discovery and loading |
| `luaScriptsCount` | Number of loaded scripts |
| `luaLcdAllowed` | Flag: whether script can draw to LCD |
| `luaLcdBuffer` | LCD framebuffer for script rendering |
| `luaInputTelemetryFifo` | FIFO queue for incoming telemetry data |
| `luaElrsReqIdx` | ELRS request index for crossfire telemetry |

## Script Structure

Scripts follow the standard OpenTX/EdgeTX pattern:

```lua
local function init()
  -- Called once when the script is loaded
end

local function run(event)
  -- Called repeatedly while the script is active
  -- event: key/touch event or 0 for timer tick
end

return { init=init, run=run }
```

## Notes

- The Lua VM is 5.3, not 5.4 — be aware of integer/float division differences vs newer Lua
- ROM table support means some tables are stored in flash/ROM and are read-only
- The `luaSetGetSerialByte()` bridge symbol exists but serial functions (`serialRead`, `serialWrite`, `setSerialBaudrate`) are **dead stubs on the AX12** — `serialPutc`/`serialCrlf` are bare `ret` instructions, and the `serialRead` FIFO is never fed. No LUA serial mode in settings. Custom serial protocols from Lua are not possible on this hardware.
- Scripts can be managed through the Flyshark app's tool menu
