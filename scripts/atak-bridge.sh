#!/data/data/com.termux/files/usr/bin/bash
# ATAK CoT Bridge Launcher for RadioMaster AX12
# Streams pilot GPS position to ATAK as Cursor-on-Target
#
# Usage:
#   bash scripts/atak-bridge.sh                    # localhost:4242
#   bash scripts/atak-bridge.sh --host 239.2.3.1   # multicast
#   bash scripts/atak-bridge.sh --host 192.168.1.5  # specific ATAK device
#   bash scripts/atak-bridge.sh --test              # synthetic data (no GPS needed)
#
# Makes your transmitter appear on the ATAK map.
# Your drone controller now knows where YOU are.

PY=/data/data/com.termux/files/usr/bin/python3
BRIDGE=$HOME/ax12-research/tools/cot_bridge.py
GPS_TOOL=$HOME/ax12-research/tools/gps_tool.py

echo "========================================"
echo "  AX12 -> ATAK CoT Bridge"
echo "  RadioMaster AX12 Research Project"
echo "========================================"
echo

# Start GPS if not already running
echo "[1/3] Starting GPS..."
su 0 am start -n com.mediatek.ygps/.YgpsActivity > /dev/null 2>&1
sleep 1

# Check GPS position
echo "[2/3] Checking position..."
POS=$(su 0 $PY $GPS_TOOL position 2>/dev/null | grep -E 'Latitude|Longitude|Accuracy')
if [ -n "$POS" ]; then
    echo "$POS"
    echo
else
    echo "  No position fix yet (GPS warming up or indoors)"
    echo "  Bridge will use synthetic data until GPS locks"
    echo
fi

# Parse arguments
HOST="127.0.0.1"
PORT="4242"
UID_NAME="AX12-Pilot-1"
EXTRA_ARGS=""

while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST="$2"; shift 2;;
        --port) PORT="$2"; shift 2;;
        --uid)  UID_NAME="$2"; shift 2;;
        --test) EXTRA_ARGS="--test"; shift;;
        *) shift;;
    esac
done

echo "[3/3] Starting CoT bridge..."
echo "  Target: $HOST:$PORT"
echo "  UID: $UID_NAME"
echo "  CoT Type: a-f-G-U-C (friendly ground unit)"
echo
echo "  Your transmitter is now broadcasting position to ATAK."
echo "  Open ATAK and look for '$UID_NAME' on the map."
echo "  Press Ctrl+C to stop."
echo

su 0 $PY $BRIDGE     --atak-host $HOST     --atak-port $PORT     --uid $UID_NAME     --interval 2.0     $EXTRA_ARGS
