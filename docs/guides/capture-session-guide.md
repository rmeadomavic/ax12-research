# AX12 Capture Session — Operator Guide

Structured capture of control inputs for UMBUS protocol mapping.
The script records serial traffic while you physically manipulate
one control at a time.

## Prerequisites

- Flyshark / RadioMaster app must be running (it owns the serial port)
- Terminal with root access (Termux)

## Quick Start

```
su 0 python3 ~/ax12-research/tools/capture-session.py
```

Optional: set per-segment capture duration (default 8s):
```
su 0 python3 ~/ax12-research/tools/capture-session.py --duration 12
```

## Session Flow

### 1. Baseline (automatic)

The script starts by capturing 3 seconds of idle data. **Do not touch
any controls.** This provides the reference values for detecting which
channels change when you move a control.

### 2. Segments (interactive)

For each segment, the script will:

1. Ask you for a label (type a number for the preset list, or any name)
2. Ask you to return all controls to CENTER and press Enter
3. Wait 2 seconds for you to settle
4. Tell you to START moving the specified control
5. Capture for N seconds (default 8)
6. Show quality stats

### 3. Done

Type `done` to end the session. The script saves a manifest.json
with metadata and quality stats for every segment.

## What to Do Physically

### Gimbals (sticks)

For each axis (left-x, left-y, right-x, right-y):

```
CENTER --> full MIN --> pause 1s --> CENTER --> full MAX --> pause 1s --> CENTER
```

Move **slowly and deliberately**. The captures are at 25 Hz, so fast
movements are fine, but slow sweeps give cleaner data for mapping
the value range.

For circle captures (left-circle, right-circle):

```
CENTER --> slowly trace a full CLOCKWISE circle --> CENTER
```

### Switches

For each switch (sw-a, sw-b, etc.):

```
Position 1 --> pause 1s --> Position 2 --> pause 1s --> Position 3 --> pause 1s
```

Go through ALL positions. If it's a 2-position switch, just toggle
twice with pauses.

### Knobs / Pots

```
Full CCW --> slowly sweep to full CW --> pause 1s --> sweep back to CCW
```

### Trims

If trims exist, tap each direction several times with 1s pauses.

## Critical Rules

1. **ONE control at a time** — all others at center/default
2. **Pause at extremes** — gives us clean samples at min/max values
3. **Don't rush** — 8 seconds is plenty for one axis sweep
4. **Don't touch the screen** — app interactions create extra serial traffic

## Output

Each session creates `captures/session-YYYYMMDD-HHMMSS/` with:

| File | Description |
|------|-------------|
| `00-baseline.bin` | Raw serial bytes, idle state |
| `01-left-x.bin` | Raw serial bytes for that segment |
| `01-left-x.strace` | Strace text (for debugging) |
| `manifest.json` | Session metadata + quality stats |

### Quality Stats

After each segment, the script reports:

- **channel frames**: Number of 87-byte channel data frames captured
  (expect ~25/sec, so ~200 in an 8s capture)
- **valid/total**: CRC-validated frames. 98%+ is normal.
  Occasional CRC errors are strace framing artifacts, not data loss.

If you see **NO FRAMES CAPTURED**, the app may have restarted —
close and relaunch the script.

## Analyzing Results

```bash
# Decode a segment's frames
python3 tools/umbus.py captures/session-.../01-left-x.bin

# Parse via strace format
python3 tools/strace-parser.py captures/session-.../01-left-x.strace

# Compare baseline vs segment to find which channels moved
# (planned — use umbus.py for now)
```

## Suggested Capture Order

For a complete control map, capture these in order:

1. left-x (left stick horizontal)
2. left-y (left stick vertical)
3. right-x (right stick horizontal)
4. right-y (right stick vertical)
5. sw-a through sw-d (all switches)
6. Any knobs or pots
7. left-circle, right-circle (combined movements)

The single-axis captures are most important. Circle captures are
bonus data for validating the axis mapping.
