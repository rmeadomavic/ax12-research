#!/usr/bin/env python3
"""
UMBUS Traffic Simulator — Generate synthetic UMBUS traffic for offline testing.

Produces realistic UMBUS frame streams without requiring the physical radio.
Can replay captured data or generate synthetic traffic with configurable
gimbal movements, switch toggling, and telemetry patterns.

Modes:
    replay   — Replay timed-frames.json at original timing
    generate — Produce synthetic traffic matching real timing patterns
    pipe     — Write binary frames to stdout for piping to other tools

Usage:
    python3 tools/simulator.py replay              # replay captures at real speed
    python3 tools/simulator.py generate             # synthetic traffic, printed
    python3 tools/simulator.py generate --seconds 5 # 5 seconds of traffic
    python3 tools/simulator.py pipe | python3 tools/umbus.py -  # pipe to decoder

No root required. No hardware required.
"""

import json
import math
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from umbus import (
    CHANNEL_CENTER, FrameType, FRAME_SIZES, SWITCH_HIGH,
    UMBUSDecoder, UMBUSEncoder, UMBUSFrame,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMED_FRAMES = os.path.join(REPO_ROOT, 'captures', 'timed-frames.json')


# ===================================================================
# Traffic Generator
# ===================================================================

class TrafficGenerator:
    """Generate realistic UMBUS traffic patterns.

    Produces frames matching the observed idle timing:
      - 0x57 CHANNEL_DATA at 25 Hz
      - 0x08 MCU heartbeat at 4 Hz
      - 0x15 ELRS telemetry at 5 Hz
      - 0x10 EXTENDED telemetry at 3 Hz (bursts of 3)
      - App→MCU frames in 2-second cycle
    """

    def __init__(self):
        self.seq = 0
        self.t = 0.0           # elapsed seconds
        self.elrs_seq = 0

        # Gimbal simulation state
        self._gimbal_pattern = 'idle'  # 'idle', 'sine', 'sweep'
        self._gimbal_speed = 1.0

    def set_gimbal_pattern(self, pattern: str, speed: float = 1.0):
        """Set gimbal animation: 'idle', 'sine', 'sweep'."""
        self._gimbal_pattern = pattern
        self._gimbal_speed = speed

    def _gimbals_at(self, t: float) -> list[int]:
        """Compute gimbal values at time t."""
        if self._gimbal_pattern == 'idle':
            # Small random-looking drift (deterministic from time)
            return [
                int(3 * math.sin(t * 0.7)),
                int(-1 + 2 * math.sin(t * 0.3)),
                int(-328 + 5 * math.sin(t * 0.5)),
                int(1 + math.sin(t * 0.9)),
            ]
        elif self._gimbal_pattern == 'sine':
            s = self._gimbal_speed
            return [
                int(400 * math.sin(t * s)),
                int(400 * math.cos(t * s * 0.7)),
                int(400 * math.sin(t * s * 1.3)),
                int(400 * math.cos(t * s * 0.5)),
            ]
        elif self._gimbal_pattern == 'sweep':
            # Linear sweep from min to max
            phase = (t * self._gimbal_speed) % 4.0  # 4-second cycle
            if phase < 2.0:
                v = int(-500 + 500 * phase)
            else:
                v = int(500 - 500 * (phase - 2.0))
            return [v, -v, v // 2, -v // 2]
        return [0, 0, 0, 0]

    def _channels_at(self, t: float) -> list[int]:
        """Compute channel values at time t."""
        ch = [CHANNEL_CENTER] * 32

        # Simulate some switch positions (from real captures)
        ch[6] = 5          # observed in captures
        ch[7] = 65147      # observed in captures
        ch[14] = SWITCH_HIGH
        ch[15] = SWITCH_HIGH
        ch[17] = SWITCH_HIGH
        ch[29] = SWITCH_HIGH

        # Toggle a switch every 2 seconds
        cycle = int(t / 2.0) % 3
        if cycle == 1:
            ch[14] = 0  # switch low
        elif cycle == 2:
            ch[14] = CHANNEL_CENTER  # switch mid

        # Animate pot (S1) as slow sine
        ch[19] = int(CHANNEL_CENTER + CHANNEL_CENTER * 0.5 * math.sin(t * 0.2))

        return ch

    def generate(self, duration: float = 10.0) -> list[tuple[float, bytes]]:
        """Generate a stream of (timestamp_sec, frame_bytes) tuples.

        Matches the real 2-second bus cycle timing from docs.
        """
        frames = []
        t = 0.0
        dt_channel = 1.0 / 25.0      # 40ms
        dt_heartbeat = 1.0 / 4.0     # 250ms
        dt_elrs = 1.0 / 5.0          # 200ms
        dt_extended_cycle = 1.0       # burst every 1s

        next_channel = 0.0
        next_heartbeat = 0.25
        next_elrs = 0.2
        next_extended = 1.0
        next_app_poll = 0.25
        next_app_hb = 0.5
        next_app_keepalive = 1.0

        seq = 0
        elrs_seq = 0

        while t < duration:
            # Find next event
            next_t = min(next_channel, next_heartbeat, next_elrs,
                         next_extended, next_app_poll, next_app_hb,
                         next_app_keepalive, duration)

            if next_t >= duration:
                break

            t = next_t

            # Channel data (25 Hz) — highest priority
            if t >= next_channel:
                g = self._gimbals_at(t)
                ch = self._channels_at(t)
                frames.append((t, UMBUSEncoder.channel_data(
                    gimbals=g, channels=ch, seq=seq & 0xFF)))
                seq += 1
                next_channel = t + dt_channel

            # MCU heartbeat (4 Hz)
            if t >= next_heartbeat:
                frames.append((t, UMBUSEncoder.heartbeat_mcu()))
                next_heartbeat = t + dt_heartbeat

            # ELRS telemetry (5 Hz)
            if t >= next_elrs:
                frames.append((t, UMBUSEncoder.elrs_telemetry(
                    timing_us=20000, link_status=0, seq=elrs_seq & 0xFF)))
                elrs_seq += 1
                next_elrs = t + dt_elrs

            # Extended telemetry burst (3 frames at ~1Hz)
            if t >= next_extended:
                for si in range(3):
                    frames.append((t + si * 0.01,
                                   UMBUSEncoder.extended_telemetry(
                                       sub_index=si, value=si * 100)))
                next_extended = t + dt_extended_cycle

            # App→MCU: poll (2 Hz)
            if t >= next_app_poll:
                frames.append((t, UMBUSEncoder.poll()))
                next_app_poll = t + 0.5

            # App→MCU: heartbeat (1 Hz)
            if t >= next_app_hb:
                frames.append((t, UMBUSEncoder.heartbeat_app()))
                next_app_hb = t + 1.0

            # App→MCU: keepalive (0.5 Hz)
            if t >= next_app_keepalive:
                frames.append((t, UMBUSEncoder.keepalive()))
                next_app_keepalive = t + 2.0

            # Advance past current time to avoid infinite loop
            if next_channel <= t:
                next_channel = t + dt_channel

        # Sort by timestamp
        frames.sort(key=lambda x: x[0])
        return frames


# ===================================================================
# Replay
# ===================================================================

def replay_captured(realtime: bool = True):
    """Replay timed-frames.json, decoding and printing each frame."""
    with open(TIMED_FRAMES) as f:
        entries = json.load(f)

    decoder = UMBUSDecoder()
    start = time.time()
    prev_ts = 0

    print(f"Replaying {len(entries)} captured frames...")
    print()

    for ts_ms, _size, hexstr in entries:
        if realtime and ts_ms > prev_ts:
            delay = (ts_ms - prev_ts) / 1000.0
            elapsed = time.time() - start
            target = ts_ms / 1000.0
            if target > elapsed:
                time.sleep(target - elapsed)
        prev_ts = ts_ms

        raw = bytes.fromhex(hexstr)
        for frame in decoder.feed(raw):
            t_str = f"[{ts_ms/1000.0:8.3f}s]"
            print(f"{t_str} {frame.summary()}")

    print(f"\n--- Replay complete: {decoder.stats}")


# ===================================================================
# Generate
# ===================================================================

def generate_traffic(duration: float, pattern: str = 'idle', pipe: bool = False):
    """Generate synthetic UMBUS traffic."""
    gen = TrafficGenerator()
    gen.set_gimbal_pattern(pattern)
    frames = gen.generate(duration)

    if pipe:
        # Binary mode: write raw frames to stdout
        for _t, frame_bytes in frames:
            sys.stdout.buffer.write(frame_bytes)
        sys.stdout.buffer.flush()
        return

    # Pretty-print mode
    decoder = UMBUSDecoder()
    print(f"Generated {len(frames)} frames over {duration:.1f}s (pattern: {pattern})")
    print()

    from collections import Counter
    types = Counter()

    for t, frame_bytes in frames:
        for frame in decoder.feed(frame_bytes):
            types[frame.type_name] += 1
            t_str = f"[{t:8.3f}s]"
            # Only print channel data every 5th frame to reduce noise
            if frame.frame_type == FrameType.CHANNEL_DATA:
                if types['CHANNEL_DATA'] % 5 == 1:
                    print(f"{t_str} {repr(frame)}  G={frame.gimbals}")
            else:
                print(f"{t_str} {repr(frame)}")

    print(f"\n--- Generated: {dict(types.most_common())}")
    print(f"--- Decoder stats: {decoder.stats}")

    # Verify all frames decode cleanly
    total = sum(types.values())
    bad = decoder.frames_bad_checksum
    print(f"--- Integrity: {total} frames, {bad} bad checksums"
          f" ({100*(total-bad)/total:.1f}% clean)")


# ===================================================================
# CLI
# ===================================================================

def main():
    args = sys.argv[1:]

    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    mode = args[0]

    if mode == 'replay':
        no_wait = '--fast' in args
        replay_captured(realtime=not no_wait)

    elif mode == 'generate':
        duration = 10.0
        pattern = 'idle'
        for i, a in enumerate(args[1:], 1):
            if a == '--seconds' and i < len(args):
                duration = float(args[i + 1])
            elif a == '--pattern' and i < len(args):
                pattern = args[i + 1]
        generate_traffic(duration, pattern)

    elif mode == 'pipe':
        duration = 10.0
        pattern = 'idle'
        for i, a in enumerate(args[1:], 1):
            if a == '--seconds' and i < len(args):
                duration = float(args[i + 1])
            elif a == '--pattern' and i < len(args):
                pattern = args[i + 1]
        generate_traffic(duration, pattern, pipe=True)

    else:
        print(f"Unknown mode: {mode}")
        print("Use: replay, generate, or pipe")
        sys.exit(1)


if __name__ == '__main__':
    main()
