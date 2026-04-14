#!/data/data/com.termux/files/usr/bin/bash
# DOOM Demo Launcher for RadioMaster AX12
# Starts Chocolate Doom with Freedoom WAD and the gimbal controller
#
# Usage:
#   bash scripts/doom-demo.sh           # launch DOOM only
#   bash scripts/doom-demo.sh --control # launch DOOM + gimbal controller
#
# Prerequisites:
#   - Termux X11 app must be open (provides :0 display)
#   - For --control: RadioMaster app should NOT be running (serial port conflict)

set -e
REPO=$HOME/ax12-research
WAD=$HOME/downloads/freedoom-0.13.0/freedoom1.wad
DOOM=/data/data/com.termux/files/usr/bin/chocolate-doom
PY=/data/data/com.termux/files/usr/bin/python3
XDOTOOL=/data/data/com.termux/files/usr/bin/xdotool

# Also check for older WAD location
if [ ! -f "$WAD" ]; then
    WAD=$HOME/freedoom/freedoom-0.13.0/freedoom1.wad
fi

if [ ! -f "$WAD" ]; then
    echo "ERROR: No Freedoom WAD found. Run:"
    echo "  wget -O ~/downloads/freedoom.zip https://github.com/freedoom/freedoom/releases/download/v0.13.0/freedoom-0.13.0.zip"
    echo "  cd ~/downloads && unzip freedoom.zip"
    exit 1
fi

export DISPLAY=:0

# Kill any existing DOOM processes
pkill -f chocolate-doom 2>/dev/null || true
pkill -f doom-controller 2>/dev/null || true
sleep 0.5

echo "=== AX12 DOOM Demo =="
echo "WAD: $WAD"
echo "Display: $DISPLAY"

# Launch DOOM
echo "Starting Chocolate Doom..."
$DOOM -iwad "$WAD" -window -nomouse 2>/dev/null &
DOOM_PID=$!
echo "DOOM PID: $DOOM_PID"
sleep 2

# Fullscreen the window
echo "Fullscreening..."
WID=$($XDOTOOL search --name . 2>/dev/null | head -1)
if [ -n "$WID" ]; then
    $XDOTOOL windowmove --sync $WID 0 0
    $XDOTOOL windowsize --sync $WID 1280 720
    $XDOTOOL windowfocus --sync $WID
    echo "Window $WID fullscreened to 1280x720"
fi

if [ "$1" = "--control" ]; then
    # Check if RadioMaster app is running
    if su 0 pidof com.Flyshark.RadioMasterAX >/dev/null 2>&1; then
        echo "WARNING: RadioMaster app is running. Controller may conflict."
        echo "Consider: su 0 am force-stop com.Flyshark.RadioMasterAX"
    fi
    echo "Starting gimbal controller..."
    su 0 $PY $REPO/tools/doom-controller.py
else
    echo ""
    echo "DOOM is running! Controls:"
    echo "  Arrow keys: move/turn"
    echo "  Ctrl: fire"
    echo "  Space: use/open"
    echo "  Shift: run"
    echo ""
    echo "To add gimbal control: bash scripts/doom-demo.sh --control"
    echo "Press Enter to stop DOOM..."
    read
    kill $DOOM_PID 2>/dev/null
fi
