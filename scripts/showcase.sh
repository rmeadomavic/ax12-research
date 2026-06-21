#!/data/data/com.termux/files/usr/bin/bash
# AX12 Demo Showcase Startup
# Run this to prep everything for a live demo

PY=/data/data/com.termux/files/usr/bin/python3

echo "======================================"
echo "  AX12 Research — Demo Startup"
echo "======================================"
echo

# 1. Start demo web server
echo "[1/5] Starting demo web server on port 8082..."
pkill -f 'demo_server.py' 2>/dev/null
nohup $PY ~/ax12-research/tools/demo_server.py --port 8082 > /dev/null 2>&1 &
echo "  -> http://100.87.134.108:8082"

# 2. Network location (NOT GNSS — no GPS antenna populated)
echo "[2/5] Reading network location (no GNSS antenna on board)..."
su 0 am start -n com.mediatek.ygps/.YgpsActivity > /dev/null 2>&1
sleep 1
POS=$($PY ~/ax12-research/tools/gps_tool.py position 2>/dev/null | grep Latitude)
echo "  -> $POS (WiFi/network, not a satellite fix)"

# 3. Check WiFi
echo "[3/5] Network status..."
IP=$(ip addr show tun0 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
echo "  -> Tailscale: $IP"
WIFI=$(su 0 dumpsys wifi 2>/dev/null | grep 'mWifiInfo SSID' | head -1 | sed 's/.*SSID: //' | cut -d, -f1)
echo "  -> WiFi: $WIFI"

# 4. List available demos
echo "[4/5] Available demos:"
echo "  Web Dashboard:     http://100.87.134.108:8082"
echo "  Calibrator:        http://100.87.134.108:8080"
echo "  DOOM:              bash scripts/doom-demo.sh"
echo "  Tactical tools:   github.com/rmeadomavic/ax12-tac-tools"
echo "  Net Location:      python3 tools/gps_tool.py position  (network, no GNSS)"
echo "  Model Backup:      su 0 $PY tools/model_tool.py list"
echo "  Meshtastic:        (open app on device)"
echo "  Lua Scripts:       (RadioMaster app > Lua Scripts > Tools)"

# 5. Count tools
LUA_COUNT=$(su 0 find /storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/ -name '*.lua' 2>/dev/null | wc -l)
PY_COUNT=$(ls ~/ax12-research/tools/*.py 2>/dev/null | wc -l)
echo
echo "[5/5] Inventory: $PY_COUNT Python tools, $LUA_COUNT Lua scripts"
echo
echo "======================================"
echo "  Ready to demo. Go impress people."
echo "======================================"
