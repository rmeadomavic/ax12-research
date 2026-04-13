# AX12 Tool Usage Guide

Comprehensive reference for every tool in `tools/`. All tools use Python stdlib only and run on the AX12 directly.

**Root rule:** Tools that access `/dev/ttyS0` require root (`su 0`).
**Serial rule:** Never open ttyS0 directly while the Flyshark app is running — use strace-based tools instead.

---

## Protocol Analysis

### umbus.py — Core Protocol Library

The foundational UMBUS decoder/encoder. Every other tool imports this.

**Purpose:** Parse and construct UMBUS frames — the proprietary protocol between the Android SoC and AT32 MCU.

**Prerequisites:** None (stdlib only).

**Usage:**

```bash
# Parse frames from a binary capture file
python3 tools/umbus.py captures/session-20250101-120000/01-left-x.bin

# Parse from stdin (pipe from other tools)
python3 tools/umbus.py -

# Live serial read (requires root, DO NOT use while Flyshark is running)
su 0 python3 tools/umbus.py --live
```

**As a library:**

```python
from umbus import UMBUSDecoder, UMBUSEncoder, FrameType

decoder = UMBUSDecoder()
for frame in decoder.feed(raw_bytes):
    print(frame.summary())
    if frame.frame_type == FrameType.CHANNEL_DATA:
        print(f"  Gimbals: {frame.gimbals}")
        print(f"  Channels: {frame.channels}")

# Construct frames
encoder = UMBUSEncoder
frame = encoder.channel_data(gimbals=[100, -200, 0, 50])
```

**Example output:**

```
UMBUSFrame(CHANNEL_DATA, 87B)  [MCU→App]
  Gimbals: G0=   +3  G1=   -1  G2= -328  G3=   +1
  Channels: CH00=CENTER, CH01=CENTER, CH02=CENTER, ...
```

**Caveats:**
- `--live` mode opens ttyS0 directly — only use when the Flyshark app is stopped.
- MCU heartbeat (7B, type 0x08) has no checksum byte; CRC validation is skipped for it.
- CRC init values differ by frame type: 0x00 (most), 0x7F (type 0x10), 0x32 (type 0x15).

---

### strace-parser.py — Strace Frame Parser

**Purpose:** Extract and decode UMBUS frames from strace output files. This is the safe way to analyze serial traffic captured while the Flyshark app is running.

**Prerequisites:** Strace output captured with `-tt -e trace=read,write -x -s 256`.

**Usage:**

```bash
# Parse a saved strace log
python3 tools/strace-parser.py captures/idle-strace.txt

# Pipe from live strace (non-destructive monitoring)
su 0 strace -tt -e trace=read,write -e read=103 -e write=103 -p <PID> 2>&1 \
  | python3 tools/strace-parser.py -
```

**Example output:**

```
Parsed 847 syscall records

Reads:  523 calls, 12847 bytes (MCU → App)
Writes: 324 calls, 3892 bytes (App → MCU)
Time span: 07:05:03.963555 → 07:05:38.142003

Decoded 412 UMBUS frames:
  CHANNEL_DATA: 250
  HEARTBEAT_MCU: 68
  ELRS_TELEM: 50
  ...

--- Example CHANNEL_DATA (MCU→App, 07:05:04.003123) ---
UMBUSFrame(CHANNEL_DATA, 87B)  [MCU→App]
  Gimbals: G0=   +3  G1=   -1  G2= -328  G3=   +1
  0000  a6 57 10 02 04 01 fa ff  02 00 ...
```

**Caveats:**
- Handles both hex dump format (`| offset hex... |`) and escaped string format (`\xa6\x57...`).
- If no syscall records are found, falls back to raw hex extraction.

---

### simulator.py — Traffic Simulator

**Purpose:** Generate synthetic UMBUS traffic for offline development and testing without the physical radio.

**Prerequisites:** Requires `captures/timed-frames.json` for replay mode.

**Usage:**

```bash
# Replay captured traffic at real-time speed
python3 tools/simulator.py replay

# Replay at full speed (no timing delays)
python3 tools/simulator.py replay --fast

# Generate 10 seconds of synthetic traffic
python3 tools/simulator.py generate

# Generate 30 seconds with sine-wave gimbal movement
python3 tools/simulator.py generate --seconds 30 --pattern sine

# Pipe binary output to other tools
python3 tools/simulator.py pipe | python3 tools/umbus.py -
python3 tools/simulator.py pipe --seconds 5 --pattern sweep | python3 tools/umbus.py -
```

**Gimbal patterns:** `idle` (small drift), `sine` (smooth oscillation), `sweep` (linear min-max).

**Example output (generate):**

```
Generated 478 frames over 10.0s (pattern: idle)

[   0.000s] UMBUSFrame(CHANNEL_DATA, 87B)  G=[0, 0, -328, 0]
[   0.200s] UMBUSFrame(ELRS_TELEM, 21B)
[   0.250s] UMBUSFrame(HEARTBEAT_MCU, 7B)
...

--- Generated: {'CHANNEL_DATA': 250, 'HEARTBEAT_MCU': 40, ...}
--- Integrity: 478 frames, 0 bad checksums (100.0% clean)
```

**Caveats:**
- No root required. No hardware required.
- Generated traffic matches the observed 2-second bus cycle timing from real captures.

---

## Live Monitoring

### monitor.py — TUI Channel Visualizer

**Purpose:** Real-time terminal-based visualization of UMBUS channel data. Shows gimbal positions and channel values with color-coded delta tracking.

**Prerequisites:** Root access. Flyshark app must NOT be running (exclusive serial access).

**Usage:**

```bash
su 0 python3 tools/monitor.py
```

**Example output:**

```
  AX12 SERIAL MONITOR  |  frame #1523  |  Ctrl+C quit
  Decoded: 1523  Skip: 0B

  GIMBALS (signed):
    G0 [░░░░░░░░░░█░░░░░░░░░]    +3
    G1 [░░░░░░░░░█░░░░░░░░░░]    -1
    G2 [░░░░░█░░░░░░░░░░░░░░]  -328
    G3 [░░░░░░░░░░█░░░░░░░░░]    +1

  CHANNELS (unsigned):
    [ 0] [████████░░░░░░░░] 32768  Δ    +0
    [ 1] [████████░░░░░░░░] 32768  Δ    +0
    ...
```

**Caveats:**
- Opens ttyS0 directly — **do NOT run while Flyshark is running**. Two readers corrupt both streams.
- Updates at ~33 fps (30ms sleep between renders).
- Press Ctrl+C to stop; cursor visibility is restored on exit.

---

### umbus_server.py — SSE Server

**Purpose:** Reusable service layer that reads UMBUS frames from serial, broadcasts via Server-Sent Events (SSE), and exposes a REST API. Other web-based tools (calibrator, live-mapper, live_dashboard) build on top of this.

**Prerequisites:** Root for live mode. `captures/timed-frames.json` for demo mode.

**Usage (standalone):**

```bash
# Live from serial
su 0 python3 tools/umbus_server.py

# Demo mode with captured data
python3 tools/umbus_server.py --demo
```

Then open `http://<device-ip>:8081` in a browser.

**Usage (as library):**

```python
from umbus_server import UMBUSService

svc = UMBUSService(port=8081, demo=False)
svc.add_route('POST', '/api/my-action', my_handler)
svc.set_html(my_html_string)
svc.run()
```

**API endpoints:**
- `GET /` — Serves the configured HTML page
- `GET /stream` — SSE stream (events: `frame`, `status`, `log`)
- `GET /api/state` — Current config JSON
- Custom routes via `svc.add_route()`

**Caveats:**
- SSE broadcasts are throttled to ~12 Hz (every 2nd channel frame).
- Config is persisted to `docs/control-map.json`.
- Standalone mode shows a minimal live monitor UI.

---

### live_dashboard.py — Real-Time Web Dashboard

**Purpose:** Full-featured web dashboard showing gimbal stick positions, channel bars, switch states, and frame statistics in real time.

**Prerequisites:** Root for live mode. Built on `umbus_server.py`.

**Usage:**

```bash
# Live from serial
su 0 python3 tools/live_dashboard.py

# Demo mode
python3 tools/live_dashboard.py --demo
```

Then open `http://<device-ip>:8081` in a browser.

**Features:**
- 2D stick position visualizers (left/right gimbal pads)
- Per-gimbal bidirectional bars with labels (Yaw, Throttle, Roll, Pitch)
- 16-channel bar display with numeric values
- Switch state indicators (ON/MID/OFF) for channels 4-11
- Frame counter, FPS display, connection status
- Dark theme, responsive layout

**Caveats:**
- Gimbal indices are interleaved across sticks, not contiguous: Left stick uses G0 (X) and G2 (Y); Right stick uses G3 (X) and G1 (Y).
- Opens ttyS0 directly in live mode — stop Flyshark first, or use `--demo`.

---

### build-dashboard.py — Static HTML Dashboard Generator

**Purpose:** Generate a self-contained HTML file with embedded capture data and animated protocol visualization.

**Prerequisites:** `captures/timed-frames.json` must exist.

**Usage:**

```bash
python3 tools/build-dashboard.py > dashboard.html
```

**Caveats:**
- Output is a single HTML file with all data, CSS, and JS inline.
- No root required — reads from captured data only.
- The generated file is the repo's `dashboard.html`.

---

## Capture Tools

### capture-session.py — Interactive Capture Recording

**Purpose:** Guided, interactive capture session. Walks the operator through recording one control at a time with labeled segments and quality validation.

**Prerequisites:** Root access. Flyshark app must be running (captures via strace on the app's serial FD).

**Usage:**

```bash
su 0 python3 tools/capture-session.py
su 0 python3 tools/capture-session.py --duration 10
```

**Session flow:**
1. Auto-discovers the process holding ttyS0
2. Captures a 3-second baseline (hands off)
3. Prompts for control labels (numeric shortcuts or custom names)
4. Records each segment with a 2-second settle period
5. Validates CRC integrity in real time
6. Saves binary + strace + manifest

**Output structure:**

```
captures/session-YYYYMMDD-HHMMSS/
    00-baseline.bin / .strace
    01-left-x.bin / .strace
    02-left-y.bin / .strace
    ...
    manifest.json
```

**Suggested labels:** left-x, left-y, right-x, right-y, left-circle, right-circle, sw-a through sw-d, knob-l, knob-r.

**Caveats:**
- Interactive — requires keyboard input during the session.
- Uses strace (safe) — does not open ttyS0 directly.
- Default segment duration is 8 seconds. Baseline is 3 seconds.
- Type "done" to end the session.

---

### batch-capture.py — Non-Interactive Timed Capture

**Purpose:** Automated capture of all standard controls on a timer. The operator watches the screen for instructions and moves controls when prompted — no keyboard input needed after launch.

**Prerequisites:** Root access. Flyshark app must be running.

**Usage:**

```bash
su 0 python3 tools/batch-capture.py
```

**Session flow:**
1. Displays total estimated time (~2-3 minutes)
2. Counts down before each segment (5s instruction + 3s countdown)
3. Captures 11 segments automatically: baseline, 4 gimbal axes, 4 switches, 2 knobs
4. Each segment records for 8 seconds (baseline: 5 seconds)

**Example output:**

```
  === NEXT: LEFT-X ===
  Return all controls to CENTER first.
  >>> Move LEFT STICK LEFT and RIGHT (yaw axis) <<<
  Starting in 5...
    >>> 3 <<<
    >>> 2 <<<
    >>> 1 <<<
  >>> RECORDING — Move LEFT STICK LEFT and RIGHT (yaw axis) <<<
  [ok] 198 channel frames, 210/212 valid (99.1%)
  Saved: 01-left-x.bin (8234 bytes)
  [2/11] complete
```

**Caveats:**
- Non-interactive but requires visual attention (watch screen for control prompts).
- Imports functions from `capture-session.py` (hyphenated filename handled via importlib).
- Uses strace (safe) — does not open ttyS0 directly.
- Same output structure as `capture-session.py`.

---

### calibrator.py — Interactive Gimbal/Switch Calibrator

**Purpose:** 3-phase calibration wizard with a web UI. Captures center positions, discovers value ranges, then maps each physical control to its channel index through guided prompts.

**Prerequisites:** Root for live mode. Built on `umbus_server.py`.

**Usage:**

```bash
# Live from serial
su 0 python3 tools/calibrator.py

# Demo mode with captured data
su 0 python3 tools/calibrator.py --demo
```

Then open `http://<device-ip>:8081` in a browser.

**Calibration phases:**
1. **Center** — Capture neutral position automatically (3 seconds, ~75 frames)
2. **Range** — Move all controls to discover min/max values
3. **Map** — One-at-a-time wizard identifies which physical control (yaw, throttle, SA, SB, etc.) maps to which channel index

**Controls mapped:** 4 gimbal axes, 6 switches (SA-SF), 2 scroll wheels (S1-S2), 4 trims (T1-T4, optional), 6 front buttons.

**Caveats:**
- Thresholds: gimbal detection requires >150 delta from center; channel detection requires >500 delta.
- Config persists to `docs/control-map.json` across sessions.
- Opens ttyS0 directly in live mode — stop Flyshark first, or use `--demo`.

---

### live-mapper.py — Live Control-to-Channel Mapper

**Purpose:** Real-time web-based control mapping tool. Displays live gimbal/channel state and runs an interactive wizard to identify which physical control corresponds to each channel.

**Prerequisites:** Root for live mode. Flyshark app must NOT be running (exclusive serial access).

**Usage:**

```bash
# Live from serial
su 0 python3 tools/live-mapper.py

# Demo mode
su 0 python3 tools/live-mapper.py --demo
```

Then open `http://<device-ip>:8081` in a browser.

**Caveats:**
- Similar to `calibrator.py` but a standalone implementation with its own SSE infrastructure.
- Opens ttyS0 directly — stop Flyshark first, or use `--demo`.

---

## Hardware Tools

### fm_radio.py — MT6631 FM Radio Controller

**Purpose:** Control the MT6631 FM radio chip via `/dev/fm` ioctls. Discovered through reverse-engineering the stock FM Radio app.

**Prerequisites:** Root access. SELinux context is set automatically.

**Usage:**

```bash
# Get chip info
su 0 python3 tools/fm_radio.py info

# Power up and listen to a station
su 0 python3 tools/fm_radio.py listen -f 98.5

# Tune to a frequency (keeps radio on)
su 0 python3 tools/fm_radio.py powerup -f 100.0

# Scan the FM band for stations
su 0 python3 tools/fm_radio.py scan

# Probe all ioctl numbers (discovery/debug)
su 0 python3 tools/fm_radio.py probe

# Get current status
su 0 python3 tools/fm_radio.py status
```

**Example output (scan):**

```
[+] Chip ID: 0x6631 (MT6631)
[*] Scanning FM band (87.5 - 108.0 MHz)...
   98.5 MHz  RSSI: -45
  101.1 MHz  RSSI: -52
  104.3 MHz  RSSI: -48

[+] Found 3 potential stations
```

**Caveats:**
- The `listen` command attempts to set up audio routing via `tinymix` — audio output may not work on all configurations.
- Scan uses 500 kHz steps for speed; some weak stations may be missed.
- Ioctl interface uses magic byte `0xf5` with 8-byte `struct fm_tune_parm`.
- The tune command tries multiple ioctl NR values (0x02, 0x08, 0x01) as a fallback.

---

### latency-test.py — HDMI Latency Measurement

**Purpose:** Serve an HTML page with a high-precision millisecond counter for measuring HDMI pipeline latency between a laptop and the AX12's HDMI input.

**Prerequisites:** A laptop with Chrome and HDMI output. A phone camera for measurement.

**Usage:**

```bash
# Serve on default port
python3 tools/latency-test.py

# Custom port
python3 tools/latency-test.py --port 9090

# Enable WebSocket relay for automated measurement
python3 tools/latency-test.py --ws-port 8081
```

**Measurement procedure:**
1. Open `http://<laptop-ip>:8080` in Chrome on the laptop
2. Connect laptop HDMI out to AX12 Mini HDMI In
3. Photograph both screens simultaneously with a phone camera
4. Time difference between displays = pipeline latency

**Features:**
- HH:MM:SS.mmm counter at 200px, white on black
- Frame counter and measured FPS
- Green flash every 5 seconds (visual sync point for video analysis)
- Optional WebSocket bridge for automated measurement

**Caveats:**
- No root required — runs a plain HTTP server.
- WebSocket server is a minimal RFC 6455 implementation (stdlib only).
- The WebSocket relay is experimental and intended for automated measurement setups.

---

## Integration Tools

### cot_bridge.py — ATAK Cursor-on-Target Bridge

**Purpose:** Read MAVLink telemetry from serial (ELRS passthrough) and broadcast Cursor-on-Target (CoT) XML to ATAK via UDP. Places the drone on ATAK's map in real time.

**Prerequisites:** Root for serial access. ATAK running and listening on UDP port 4242.

**Usage:**

```bash
# Live from serial (ttyS1 at 460800 baud)
su 0 python3 tools/cot_bridge.py

# Synthetic test data (orbits null island)
su 0 python3 tools/cot_bridge.py --test

# Custom callsign and port
su 0 python3 tools/cot_bridge.py --uid MyDrone --atak-port 4243

# All options
su 0 python3 tools/cot_bridge.py \
    --port /dev/ttyS1 \
    --baud 460800 \
    --atak-host 127.0.0.1 \
    --atak-port 4242 \
    --uid ELRS-Drone-1 \
    --interval 2.0
```

**CoT type:** `a-f-A-M-F-Q` (friendly air military fixed-wing UAV).

**Example output:**

```
[cot_bridge] Opened /dev/ttyS1 at 460800 baud
[cot_bridge] Sending CoT to 127.0.0.1:4242 every 2.0s
[cot_bridge] UID: ELRS-Drone-1
[cot_bridge] CoT sent: 34.05234,-118.24368 150m LOITER
[cot_bridge] CoT sent: 34.05235,-118.24370 151m LOITER
```

**Caveats:**
- Reads from `/dev/ttyS1` (MCU debug serial), not ttyS0.
- Includes a full MAVLink v1/v2 parser (incremental, handles stream sync).
- Falls back to synthetic data if serial open fails or data times out (5 seconds).
- Serial is configured via raw termios: 8N1, no flow control.
- Default send interval is 2 seconds; ATAK typically expects 1-5 Hz.

---

### test_cot.py — CoT Test Sender

**Purpose:** Send a single test CoT event to verify ATAK is receiving and rendering before running the full bridge.

**Prerequisites:** ATAK running and listening on UDP.

**Usage:**

```bash
# Send to default port (4242)
python3 tools/test_cot.py

# Custom port and callsign
python3 tools/test_cot.py --port 4243 --uid TestDrone
```

**Example output:**

```
[test_cot] Sent CoT to 127.0.0.1:4242
[test_cot] UID: ELRS-Drone-1
[test_cot] Position: 0.0, 0.0 (null island) @ 100m
[test_cot] XML (389 bytes):
<?xml version="1.0" encoding="UTF-8"?><event ...>...</event>
```

**Caveats:**
- No root required. No serial access.
- Sends a single datagram and exits — not a continuous stream.
- Position is hardcoded to null island (0, 0) at 100m altitude.

---

## Quick Reference

| Tool | Root? | Serial? | Web UI? | Interactive? |
|------|-------|---------|---------|-------------|
| umbus.py | Only `--live` | `--live` only | No | No |
| strace-parser.py | No | No (reads files) | No | No |
| simulator.py | No | No | No | No |
| monitor.py | Yes | Direct | No (TUI) | No |
| umbus_server.py | Yes (live) | Direct | Yes (:8081) | No |
| live_dashboard.py | Yes (live) | Direct | Yes (:8081) | No |
| build-dashboard.py | No | No | Generates HTML | No |
| capture-session.py | Yes | Strace (safe) | No | Yes |
| batch-capture.py | Yes | Strace (safe) | No | Visual only |
| calibrator.py | Yes (live) | Direct | Yes (:8081) | Yes (web) |
| live-mapper.py | Yes (live) | Direct | Yes (:8081) | Yes (web) |
| fm_radio.py | Yes | /dev/fm | No | No |
| latency-test.py | No | No | Yes (:8080) | No |
| cot_bridge.py | Yes | /dev/ttyS1 | No | No |
| test_cot.py | No | No | No | No |
