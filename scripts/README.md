# Lua Scripts

On-device Lua scripts for the RadioMaster AX12 Flyshark runtime.

## Deployment

1. Copy scripts to `/sdcard/AX12LUA/SCRIPTS/TOOLS/` (root may be needed for permissions)
2. Open the Flyshark app → **Tools** menu → select the script by name

## Scripts

| Script | Purpose |
|--------|---------|
| `ax12-dashboard.lua` | Custom dashboard: gimbals, channels, switches, battery, ELRS link stats. Color LCD with adaptive layout. |
| `test-api.lua` | Probes all Lua runtime globals and writes results to `/sdcard/AX12LUA/api-probe-results.txt` |
| `shm-probe.lua` | Tests `getShmVar`/`setShmVar` shared memory (100+ indices and string keys), writes to `/sdcard/AX12LUA/shm-probe-results.txt` |

## Script Structure

Every script must return a table with `init` and `run` callbacks:

```lua
-- TNS|Script Title|TNE
local function init()  end
local function run(event) --[[ called each frame ]] end
return { init=init, run=run }
```

The `-- TNS|Title|TNE` comment on line 1 sets the name shown in the Tools menu.

## EdgeTX API Compatibility

The Flyshark Lua VM implements a subset of the EdgeTX/OpenTX API.
Available: `lcd.*`, `getValue()`, `getFieldInfo()`, `model.*`, `getDateTime()`.
Missing or partial: `sportTelemetryPush/Pop`, `crossfireTelemetryPush`,
`setTelemetryValue`, `widget` lifecycle. Test on-device — some functions
exist but return nil. See [docs/software/lua-api.md](../docs/software/lua-api.md) for details.
