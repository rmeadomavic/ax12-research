# Scripts

Device-side scripts that run on the AX12 itself, as opposed to the host-side Python tools in `tools/`.

## Files

| Script | Language | Description |
|--------|----------|-------------|
| `ax12-dashboard.lua` | Lua 5.3 | On-device dashboard widget for the Flyshark Lua VM |

## Deploying to AX12

Copy Lua scripts to the AX12's script directory:

```bash
cp scripts/ax12-dashboard.lua /sdcard/AX12LUA/SCRIPTS/TOOLS/
```

Then open Flyshark → Tools menu to load and run the script.

See [docs/software/lua-api.md](../docs/software/lua-api.md) for the full Lua API reference.
