#!/data/data/com.termux/files/usr/bin/bash
# sim-mode.sh start|stop|status  --  AX12 gimbals -> Android joystick (Velocidrone)
# start: stop RC app (frees ttyS0), open uinput, run the umbus->joystick daemon
# stop : kill daemon. Relaunch RadioMasterOS afterward to fly for real.
REPO="$HOME/ax12-research"
case "$1" in
  start)
    termux-wake-lock 2>/dev/null   # survive Android doze when switched to the sim
    su 0 am force-stop com.Flyshark.RadioMasterAX
    su 0 chmod 666 /dev/uinput
    pkill -f umbus_joystick 2>/dev/null; sleep 0.4
    cd "$REPO" && python3 tools/umbus_joystick.py --daemonize
    sleep 1.5
    if pgrep -f umbus_joystick >/dev/null; then
      echo "sim-mode ON  pid=$(pgrep -f umbus_joystick | tr '\n' ' ')"
      cat "$HOME/joy.log" 2>/dev/null
      echo "-> open Velocidrone, calibrate controller (move sticks), map axes + arm switch."
    else
      echo "FAILED to start:"; cat "$HOME/joy.log" 2>/dev/null
    fi ;;
  stop)
    pkill -f umbus_joystick && echo "sim-mode OFF. Relaunch RadioMasterOS to restore RC." || echo "was not running"
    termux-wake-unlock 2>/dev/null ;;
  status)
    if pgrep -f umbus_joystick >/dev/null; then
      echo "running: pid=$(pgrep -f umbus_joystick | tr '\n' ' ')"
    else
      echo "stopped"
    fi ;;
  *) echo "usage: sim-mode.sh start|stop|status" ;;
esac
