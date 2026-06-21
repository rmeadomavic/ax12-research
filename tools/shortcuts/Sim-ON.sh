#!/data/data/com.termux/files/usr/bin/bash
# Termux:Widget shortcut -- tap to start Velocidrone sim-mode (gimbals -> joystick).
# Stops the RC app, runs the umbus->uinput bridge daemonized. Start with sticks centered.
~/ax12-research/tools/sim-mode.sh start
echo
echo "Now switch to Velocidrone. Run Sim-OFF when done."
sleep 3
