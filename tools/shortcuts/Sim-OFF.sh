#!/data/data/com.termux/files/usr/bin/bash
# Termux:Widget shortcut -- tap to stop sim-mode and restore the radio.
# Kills the joystick daemon and relaunches RadioMasterOS so RC works again.
~/ax12-research/tools/sim-mode.sh stop
su 0 monkey -p com.Flyshark.RadioMasterAX -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
echo "RC restored (RadioMasterOS relaunched)."
sleep 2
