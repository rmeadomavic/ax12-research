# Getting Started with AX12 Research Tools

A practical guide to setting up your RadioMaster AX12 for protocol exploration
and control-input analysis. You will need about 30 minutes and basic comfort
with a terminal.

## Prerequisites

- RadioMaster AX12 running stock RadioMasterOS (Android 9)
- Flyshark / RadioMaster app installed and working normally
- A computer on the same WiFi network as the AX12
- Root access enabled (the AX12 ships as a userdebug build -- no exploit needed)

If you have not rooted your AX12 or installed Termux yet, follow the
[Root and Developer Setup Guide](root-guide.md) first. It covers developer
options, Termux installation, SSH, and ADB setup.

## Quick Setup

Once Termux and SSH are running (per the root guide above):

1. **Connect from your laptop:**
   ```
   ssh u0_aXXX@<ax12-ip> -p 8022
   ```
   Replace `u0_aXXX` with your Termux username (`whoami` inside Termux)
   and `<ax12-ip>` with the AX12's WiFi address.

2. **Verify root access:**
   ```
   su 0 id
   ```
   You should see `uid=0(root)`. The AX12 uses Android-style `su` --
   always write `su 0 <command>`, never `sudo`.

3. **Clone the repo:**
   ```
   cd ~
   git clone https://github.com/rmeadomavic/ax12-research.git
   cd ax12-research
   ```
   All tools are Python 3.13 stdlib-only -- no pip packages to install.

## First Steps

Make sure Flyshark is running on the AX12 before starting any of these.
The tools monitor serial traffic passively via strace; they never open the
serial port directly.

### 1. Launch the Live Dashboard

The dashboard shows real-time gimbal positions, channel bars, switch states,
and frame statistics in a browser.

```
su 0 python3 tools/live_dashboard.py
```

This starts a web server on port 8081. Open `http://<ax12-ip>:8081` in a
browser on your laptop (or Chrome opens automatically on the AX12 itself).
Move the sticks and flip switches -- you should see the values update at 25 Hz.

To try it without a live serial connection, use demo mode:

```
su 0 python3 tools/live_dashboard.py --demo
```

### 2. Record a Capture Session

A capture session walks you through moving one control at a time so you can
map which UMBUS channels correspond to which physical inputs.

```
su 0 python3 tools/capture-session.py
```

The script records 8 seconds per control (adjustable with `--duration`).
Follow the on-screen prompts: hold still for baseline, then move the
requested stick or switch. Captures are saved under `captures/`.

See the full [Capture Session Guide](capture-session-guide.md) for details.

### 3. Parse and Analyze Frames

Feed a saved strace log into the parser to decode every UMBUS frame:

```
python3 tools/strace-parser.py captures/idle-strace.txt
```

Or pipe live strace output directly:

```
su 0 strace -tt -e read,write -p <PID> -x -s 512 2>&1 | python3 tools/strace-parser.py -
```

Find the Flyshark process PID with:

```
su 0 ls -la /proc/*/fd/* 2>/dev/null | grep ttyS0
```

## Understanding UMBUS

UMBUS is the internal serial protocol between the AX12's Android SoC and its
AT32 coprocessor MCU, running at 921600 baud over `/dev/ttyS0`. Every frame
starts with sync byte `0xA6` and ends with a CRC-8 checksum. The MCU sends
channel data (gimbal positions, switches) to the app at 25 Hz, and the app
sends configuration and polling frames back.

For the full frame format, checksum details, and per-type breakdowns, see the
[UMBUS Protocol Specification](../protocol/umbus-protocol.md).

## Available Tools

| Tool | Purpose |
|------|---------|
| `live_dashboard.py` | Web-based real-time channel monitor |
| `capture-session.py` | Guided control-input recording |
| `strace-parser.py` | Decode UMBUS frames from strace logs |
| `monitor.py` | Terminal-based live channel visualization |
| `calibrator.py` | Control surface calibration and axis mapping |
| `live-mapper.py` | Interactive real-time control-to-channel mapping |
| `simulator.py` | Generate synthetic UMBUS traffic for offline work |
| `batch-capture.py` | Non-interactive automated capture |
| `cot_bridge.py` | MAVLink to Cursor-on-Target (ATAK) bridge |

For usage details, flags, and examples for every tool, see the
[Tool Usage Reference](tool-usage.md).

## Hardware

The AX12 packs a MediaTek MT8788 SoC, an AT32 coprocessor, 12 I2C buses,
SPI for the ELRS RF module, HDMI I/O, and a full IMU. If you want to explore
the peripherals, sensors, or device tree, start with the
[Hardware Map](../hardware/hardware-map.md).

## Contributing

Found a new frame type? Mapped an unknown channel? Captured something
interesting? Contributions of captures, protocol findings, and tooling
improvements are welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) for
guidelines on code style, commit format, and what to include with captures.
