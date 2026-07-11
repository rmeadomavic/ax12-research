# AX12 Pre-Demo Test Verification Sheet

> Run through this checklist in 15 minutes to verify all demos work.
> Last updated: 2026-04-14

---

## Prerequisites

- AX12 powered on and connected to WiFi
- Tailscale running on AX12 (IP: 100.87.134.108)
- Headphones available (for FM radio test)
- Laptop on same Tailscale network
- HDMI cable available (for HDMI test)

---

## Test 1: SSH Connectivity

**What to do:**
```bash
ssh ax12 "echo ok"
```

**Expected result:** Prints `ok` with no errors.

**Troubleshooting:**
- If timeout: Verify AX12 is on WiFi. Open Termux on the AX12 and run `tailscale status`.
- If connection refused: Restart sshd in Termux: open Termux app, run `sshd`.
- If host key error: `ssh-keygen -R 100.87.134.108` then retry.

---

## Test 2: Web Dashboard

**What to do:**
```bash
ssh ax12 "python3 ~/ax12-research/tools/demo_server.py --port 8082 &"
```
Then open in browser: **http://100.87.134.108:8082**

**Expected result:** Browser shows a device info page with system stats, IP addresses, and AX12 status.

**Troubleshooting:**
- If page does not load: Check that port 8082 is not already in use: `ssh ax12 "ss -tlnp | grep 8082"`
- Kill existing process: `ssh ax12 "pkill -f demo_server"` then restart.
- If "module not found": `ssh ax12 "pip install flask"` (if the server uses Flask).

---

## Test 3: FM Radio

**What to do:**
1. Plug headphones into the AX12 3.5mm jack (headphone wire acts as antenna).
2. Run:
```bash
ssh ax12 "su 0 PATH=/data/data/com.termux/files/usr/bin:\$PATH python3 ~/ax12-research/tools/fm_radio.py listen -f 101.1"
```

**Expected result:** Audio from FM station 101.1 plays through headphones. Console shows tuner status.

**Troubleshooting:**
- If no audio: Try a different frequency (e.g., 97.9, 103.5). Check that headphones are fully inserted.
- If permission denied: Ensure `su 0` is working -- the FM chip requires root.
- If "No FM device found": The FM chip may need a kernel module. Try: `ssh ax12 "su 0 cat /proc/modules | grep fm"`

---

## Test 4: Location (network position — NOT GNSS)

> **Note:** This test reads Android's location service, which on the AX12 returns a **WiFi/network-derived** position (`fused`/`network` providers). The MT6631 GNSS core acquires **zero satellites** — no GPS antenna is populated on the PCB (see [hardware map](hardware/hardware-map.md)). This test only works on a network the device can geolocate against; it produces no usable position in the field.

**What to do:**
```bash
ssh ax12 "python3 ~/ax12-research/tools/gps_tool.py position"
```

**Expected result:** Prints a latitude/longitude from network positioning (typically 15-20 m accuracy on known WiFi) with a Google Maps link. This is **not** a satellite fix.

**Troubleshooting:**
- If "no fix": there is no GNSS fix to be had — the receiver hears no satellites (no antenna). A network position requires the device be online against a geolocatable network.
- If "device not found": location service may need root: `ssh ax12 "su 0 python3 ~/ax12-research/tools/gps_tool.py position"`
- To confirm the GNSS receiver itself is dead: `su 0 am start -n com.mediatek.ygps/.YgpsActivity` shows sats *in view* (almanac dots) with **blank SNR** — zero signal.

---

## Test 5: Model Backup

**What to do:**
```bash
ssh ax12 "su 0 /data/data/com.termux/files/usr/bin/python3 ~/ax12-research/tools/model_tool.py list"
```

**Expected result:** Prints a list of stored radio models and templates with names and IDs.

**Troubleshooting:**
- If empty list: No models saved yet. Run a backup first: `ssh ax12 "su 0 /data/data/com.termux/files/usr/bin/python3 ~/ax12-research/tools/model_tool.py backup"`
- If permission error: The model files live in a root-only directory. Ensure `su 0` is present.

---

## Test 6: DOOM

**What to do:**
1. On the AX12, open the **Termux:X11** app first (it must be running).
2. Then run:
```bash
ssh ax12 "bash ~/ax12-research/scripts/doom-demo.sh"
```

**Expected result:** DOOM launches on the AX12 screen. Gimbals control movement and aiming.

**Troubleshooting:**
- If black screen: Make sure Termux:X11 is open and in the foreground before running the script.
- If "prboom not found": Install it: `ssh ax12 "pkg install prboom-plus"`
- If no gimbal input: The UMBUS-to-input bridge may not be running. Check the script output for errors.

---

## Test 7: CoT/ATAK Bridge

> **Note:** The ATAK/CoT bridge moved to the [`ax12-tac-tools`](https://github.com/rmeadomavic/ax12-tac-tools) repo; clone it alongside this one (paths below assume `~/ax12-tac-tools`).

**What to do:**
```bash
ssh ax12 "bash ~/ax12-tac-tools/scripts/atak-bridge.sh --test"
```

**Expected result:** Console shows Cursor-on-Target XML messages being generated with coordinates and timestamps. Note: self-position here comes from network location, not GNSS (no GPS antenna populated) — usable only where the device can geolocate against a network.

**Troubleshooting:**
- If "GPS not available": Run Test 4 first to confirm a network position is available, then retry. (There is no satellite fix on this device — no antenna.)
- If script not found: Check path: `ssh ax12 "ls ~/ax12-tac-tools/scripts/atak-bridge.sh"`
- If no output: Add verbose flag if available, or check stderr: `ssh ax12 "bash ~/ax12-tac-tools/scripts/atak-bridge.sh --test 2>&1"`

---

## Test 8: Calibrator Web Interface

**What to do:**
Open in browser: **http://100.87.134.108:8080**

**Expected result:** Live web page showing real-time gimbal positions, switch states, and potentiometer values updating as you move controls.

**Troubleshooting:**
- If page does not load: The calibrator server may not be running. Start it: `ssh ax12 "python3 ~/ax12-research/tools/calibrator-web/server.py --port 8080 &"`
- If data is stale/frozen: The UMBUS reader may have disconnected. Restart the server.
- Check if port is in use: `ssh ax12 "ss -tlnp | grep 8080"`

---

## Test 9: Meshtastic App

**What to do:**
On the AX12 touchscreen, open the **Meshtastic** app from the app drawer.

**Expected result:** App launches and shows the Meshtastic interface. If a LoRa node is paired via Bluetooth, it connects and shows the mesh.

**Troubleshooting:**
- If app crashes: Force stop and reopen. Check that Bluetooth is enabled in Android Settings.
- If no node found: Ensure a Meshtastic-compatible LoRa node is powered on and in Bluetooth range.
- If not installed: Install from APK or F-Droid.

---

## Test 10: Lua Scripts

**What to do:**
1. On the AX12, switch to the EdgeTX/RadioMaster radio interface.
2. Navigate: **System menu > Lua Scripts > Tools**
3. Select any available script from the list.

**Expected result:** The Lua script runs and displays output on the radio screen (e.g., race timer, telemetry display, widget).

**Troubleshooting:**
- If "No scripts found": Scripts should be on the SD card at `/SCRIPTS/TOOLS/`. Verify via: `ssh ax12 "ls /sdcard/SCRIPTS/TOOLS/"`
- If script errors: Check the script is compatible with the EdgeTX version on the AX12.

---

## Test 11: USB Gamepad Mode

**What to do:**
```bash
ssh ax12 "su 0 /data/data/com.termux/files/usr/bin/python3 ~/ax12-research/tools/usb_gamepad.py status"
```

**Expected result:** Shows current USB gadget state (enabled/disabled) and configuration.

**Troubleshooting:**
- **WARNING:** Do NOT enable gamepad mode unless the AX12 is connected to a PC via USB-C. Enabling without a connection may cause USB issues.
- If "gadget not configured": The USB gadget kernel module may not be loaded. Check: `ssh ax12 "su 0 ls /config/usb_gadget/"`
- If "permission denied": Requires root -- ensure `su 0` is in the command.

---

## Test 12: HDMI Output

**What to do:**
1. Plug a Mini HDMI cable from the AX12 Mini HDMI port to an external monitor or TV.

**Expected result:** The AX12 screen mirrors to the external display.

**Troubleshooting:**
- If no signal: Try unplugging and replugging. Some displays need the cable connected before the AX12 boots.
- If wrong resolution: Go to Android Settings > Display and adjust resolution.
- Some HDMI adapters are not compatible -- use a direct Mini HDMI to HDMI cable.

---

## Test 13: Miracast / Screen Cast

**What to do:**
1. On the AX12, go to **Settings > Connected devices > Cast** (or **Settings > Display > Cast**).
2. Tap the target display (e.g., LG TV).
3. Accept the connection on the TV if prompted.

**Expected result:** AX12 screen wirelessly mirrors to the TV.

**Troubleshooting:**
- If TV not listed: Ensure the TV and AX12 are on the same WiFi network. TV must support Miracast.
- If connection drops: Miracast can be flaky. Retry or fall back to HDMI (Test 12).
- Some TVs require enabling screen mirroring in TV settings first.

---

## Quick Reference -- Test Summary

| # | Test | Command/Action | Pass Criteria |
|---|------|---------------|---------------|
| 1 | SSH | `ssh ax12 "echo ok"` | Prints "ok" |
| 2 | Web Dashboard | Browser :8082 | Page loads |
| 3 | FM Radio | fm_radio.py listen | Audio plays |
| 4 | Location (network) | gps_tool.py position | Network position (no satellite fix) |
| 5 | Model Backup | model_tool.py list | Models listed |
| 6 | DOOM | doom-demo.sh | Game on screen |
| 7 | CoT/ATAK | atak-bridge.sh --test | CoT XML output |
| 8 | Calibrator | Browser :8080 | Live data |
| 9 | Meshtastic | Open app | App launches |
| 10 | Lua Scripts | EdgeTX menu | Script runs |
| 11 | USB Gamepad | usb_gamepad.py status | State shown |
| 12 | HDMI | Plug cable | Display mirrors |
| 13 | Miracast | Settings > Cast | Screen mirrors |

---

*All 13 tests passing = ready to demo. If any test fails, fix it before showing anyone.*
