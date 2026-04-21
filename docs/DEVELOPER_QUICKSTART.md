# Developer Quick Start

Get productive with AX12 development in 10 minutes.

## Prerequisites

- RadioMaster AX12 (factory root — userdebug build, no Magisk needed)
- Termux installed + SSH configured
- WiFi/Tailscale for remote access

## Connect

```bash
ssh -p 8022 u0_a86@<tailscale-ip>
# or with SSH alias:
ssh ax12
```

## Run Your First Tool

```bash
# 20-point system diagnostic
python3 ~/ax12-research/tools/system_test.py

# GPS position with Google Maps link
python3 ~/ax12-research/tools/gps_tool.py position

# List radio models
su 0 /data/data/com.termux/files/usr/bin/python3 ~/ax12-research/tools/model_tool.py list

# Scan WiFi networks
python3 ~/ax12-research/tools/wifi_scanner.py scan

# Test MAVLink bridge (synthetic quadcopter)
python3 ~/ax12-research/tools/mavlink_bridge.py test --duration 10
```

## Run Lua Scripts

1. Open RadioMaster app on AX12 touchscreen
2. System Menu > Lua Scripts > Tools
3. Select any script (26+ available)

Start with: **Quick Ref** (index), **Dashboard** (live data), **Training** (exercises)

## Develop Python Tools

```bash
cd ~/ax12-research
python3 tools/simulator.py generate --seconds 5
python3 tools/test_umbus.py  # 105 tests
```

All Python is stdlib only. No pip needed.

## Develop Lua Scripts

```bash
cat > ~/my_script.lua << 'LUA'
-- TNS|My Script|TNE
local function init() end
local function run(event)
    lcd.clear()
    lcd.drawText(10, 10, "Hello AX12!", BOLD)
    return 0
end
return { init=init, run=run }
LUA
su 0 cp ~/my_script.lua /storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/
```

## Key Constraints

- **Python stdlib only** -- no pip, no external packages
- **Never read /dev/ttyS0 directly** -- use strace to monitor serial
- **Root via `su 0`** -- not `sudo`
- **Termux Python**: `/data/data/com.termux/files/usr/bin/python3`
- **Root lacks Termux PATH** -- use full paths with `su 0`

## Architecture

```
SSH Session (Termux, u0_a86)
  +-- Python tools (tools/*.py) -- subprocess, struct, socket, json
  +-- Lua scripts (AX12LUA/SCRIPTS/TOOLS/) -- runs in Flyshark VM
  +-- Shell scripts (scripts/*.sh) -- launchers and automation
```

## Need Help?

- [UMBUS Protocol Spec](docs/protocol/umbus-protocol.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- github.com/rmeadomavic/ax12-research/issues
