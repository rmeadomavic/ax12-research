# Velocidrone / FPV Sim Mode on the AX12

Run an FPV simulator (Velocidrone Mobile, etc.) **on the AX12 itself**, using the
AX12's own gimbals as the controller. The gimbals are exposed to Android as a
standard virtual joystick via `/dev/uinput`, so any sim that supports a game
controller just sees a gamepad.

This is the **on-device** direction. It is the opposite of `tools/usb_gamepad.py`,
which presents the AX12 as a USB-HID gamepad to an *external* PC.

## The problem it solves

The gimbals are read by the AT32 MCU and sent to Android over UMBUS on
`/dev/ttyS0`. Nothing exposes them to Android's input stack natively, so a sim
running on the AX12 sees no controller. Two naive states both fail:

- **RC app closed:** `/dev/ttyS0` is readable, but the MCU only streams
  `CHANNEL_DATA` (0x57) at ~6 Hz — too choppy to fly.
- **RC app open:** the MCU streams its full ~25 Hz, but RadioMasterOS takes an
  exclusive `TIOCEXCL` lock on `ttyS0`, so nothing else can read it. (A root
  override only fragments the byte stream and breaks RC.)

## The trick

Impersonate the app. The daemon replays the App-to-MCU `poll` (0x0E),
`heartbeat_app`, and `keepalive` (0x07) frames from `umbus.encoder` at 10 Hz.
The MCU then streams its full ~25 Hz `CHANNEL_DATA` **to us**, with the RC app
closed and the port ours alone. Measured: 24.9 Hz channel data.

Those gimbal values are written to `/dev/uinput` as a 4-axis + 4-button joystick.
Android's EventHub picks it up and classifies it as an external joystick
(SOURCE_JOYSTICK), so the sim enumerates it like a plugged-in gamepad.

## Usage

One-time per boot is handled by the launcher (it chmods `/dev/uinput`).

```bash
tools/sim-mode.sh start    # stop RC app, run the bridge (start with sticks centered)
tools/sim-mode.sh status
tools/sim-mode.sh stop     # then relaunch RadioMasterOS to restore RC
```

Then open the sim, calibrate the controller (move sticks full range), assign
axes, and fly.

### One-tap launcher (Termux:Widget)

Copy the shortcut scripts to `~/.shortcuts/` and add the Termux:Widget to your
home screen for tap-to-run icons:

```bash
mkdir -p ~/.shortcuts
cp tools/shortcuts/Sim-ON.sh tools/shortcuts/Sim-OFF.sh ~/.shortcuts/
chmod +x ~/.shortcuts/Sim-ON.sh ~/.shortcuts/Sim-OFF.sh
```

## Notes

- **Gimbal map:** G0 left-X (yaw), G1 right-Y (pitch), G2 left-Y (throttle),
  G3 right-X (roll). Raw swing is only ~±500. Switches on CH14-17.
- **Axes:** ABS_X / ABS_Y / ABS_RX / ABS_RY, raw range ±1023, Android normalizes
  to ±1.0. Switches map to joystick buttons 1-4.
- **Drift / auto-center:** the self-centering axes (yaw/pitch/roll) are
  auto-centered at startup and given a 6-count deadzone, so a centered stick
  reports exactly 0. Throttle is pass-through. **Start sim-mode with the sticks
  centered** — the daemon samples center at launch.
- Requires factory root (`su`), kernel uinput (`/dev/uinput`), Python 3.
  Legacy uinput ABI (kernel 4.4, no `UI_DEV_SETUP`).
