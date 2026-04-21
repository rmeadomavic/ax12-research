#!/usr/bin/env python3
"""
Telemetry Flight Recorder for RadioMaster AX12.

Records ELRS telemetry data from the UMBUS serial stream to timestamped
JSONL files for post-flight analysis.

Modes:
    record   - Capture live telemetry from serial (via strace) to JSONL
    replay   - Play back a recorded file at original speed
    stats    - Analyze a recorded file (durations, ranges, heatmaps)
    export   - Convert JSONL recording to CSV for spreadsheet analysis

Usage:
    python telem_recorder.py record [--duration SECS] [--output FILE]
    python telem_recorder.py record --demo [--duration SECS] [--output FILE]
    python telem_recorder.py replay <file.jsonl>
    python telem_recorder.py stats <file.jsonl>
    python telem_recorder.py export <file.jsonl> [--output FILE.csv]

Requires: umbus.py in the same directory (or on PYTHONPATH).
"""

import argparse
import json
import math
import os
import re
import signal
import struct
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus import (
    UMBUSDecoder,
    UMBUSEncoder,
    FrameType,
    CHANNEL_CENTER,
    SWITCH_HIGH,
    SWITCH_ALT,
    describe_channel_value,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_epoch() -> float:
    """Current time as a float epoch (seconds)."""
    return time.time()


def _ts_label() -> str:
    """Timestamp string for filenames: YYYYMMDD-HHMMSS."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _find_serial_fd() -> int | None:
    """Discover the serial port file descriptor used by the radio app.

    Scans /proc for the RadioMaster process holding /dev/ttyS0 open.
    Returns the fd number, or None if not found.
    """
    try:
        out = subprocess.check_output(
            ["su", "0", "sh", "-c",
             "ls -la /proc/*/fd 2>/dev/null | grep ttyS0 | head -5"],
            text=True, timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    # Lines look like: lrwx------ 1 root root 64 ... /proc/25255/fd/94 -> /dev/ttyS0
    for line in out.strip().splitlines():
        m = re.search(r'/proc/(\d+)/fd/(\d+)\s*->\s*/dev/ttyS0', line)
        if m:
            return int(m.group(2))
    return None


def _find_radio_pid() -> int | None:
    """Find the PID of the RadioMaster radio app."""
    try:
        out = subprocess.check_output(
            ["su", "0", "sh", "-c",
             "ls -la /proc/*/fd 2>/dev/null | grep ttyS0 | head -1"],
            text=True, timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    m = re.search(r'/proc/(\d+)/fd/', out)
    if m:
        return int(m.group(1))
    return None


def _extract_hex_from_strace_line(line: str) -> bytes | None:
    """Extract raw bytes from a single strace hex-dump line."""
    line = line.strip()
    # | 00000  a6 57 10 02 ...  .W.... |
    m = re.match(r'\|\s*[0-9a-fA-F]+\s+((?:[0-9a-fA-F]{2}\s+)+)', line)
    if m:
        return bytes(int(h, 16) for h in m.group(1).split())
    # Escaped string: "\xa6\x57..."
    hexes = re.findall(r'\\x([0-9a-fA-F]{2})', line)
    if hexes:
        return bytes(int(h, 16) for h in hexes)
    return None


def _frame_to_record(frame, t: float) -> dict:
    """Convert a decoded UMBUSFrame to a JSONL record dict."""
    ft = frame.frame_type
    rec: dict = {"t": round(t, 6)}

    if ft in (FrameType.CHANNEL_DATA, FrameType.IDLE):
        rec["type"] = "channel"
        g = frame.gimbals or []
        ch = frame.channels or []
        rec["data"] = {
            "gimbals": g,
            "channels": ch,
            "idle": ft == FrameType.IDLE,
        }
    elif ft == FrameType.ELRS_TELEM:
        rec["type"] = "elrs"
        info = frame.elrs_telemetry or {}
        rec["data"] = {
            "timing_us": info.get("timing_us", 0),
            "link_status": info.get("link_status", 0),
            "link_valid": info.get("link_valid", False),
            "seq": info.get("seq", 0),
        }
    elif ft == FrameType.EXTENDED:
        rec["type"] = "extended"
        info = frame.extended_telemetry or {}
        rec["data"] = {
            "sub_index": info.get("sub_index", 0),
            "descriptor": info.get("descriptor", 0),
            "value": info.get("value", 0),
        }
    else:
        rec["type"] = frame.type_name.lower()
        rec["data"] = {"raw_hex": frame.raw.hex()}

    return rec


# ---------------------------------------------------------------------------
# RECORD
# ---------------------------------------------------------------------------

def cmd_record(args: argparse.Namespace) -> None:
    """Record live telemetry to a JSONL file."""

    if args.demo:
        _record_demo(args)
        return

    pid = _find_radio_pid()
    if pid is None:
        print("ERROR: Cannot find radio app PID (is the radio app running?)")
        sys.exit(1)

    fd = _find_serial_fd()
    if fd is None:
        print("ERROR: Cannot find serial FD on /dev/ttyS0")
        sys.exit(1)

    outpath = args.output or os.path.join(
        os.path.expanduser("~/ax12-research/captures"),
        f"telem-{_ts_label()}.jsonl",
    )
    duration = args.duration or 30

    print(f"Recording PID {pid}, FD {fd} for {duration}s -> {outpath}")

    # Launch strace to tap the serial stream
    strace_cmd = [
        "su", "0", "strace", "-tt",
        "-e", "trace=read",
        f"-e", f"read={fd}",
        "-p", str(pid),
    ]

    decoder = UMBUSDecoder()
    frame_count = 0
    stop = False

    def _sigint(sig, frm):
        nonlocal stop
        stop = True

    old_handler = signal.signal(signal.SIGINT, _sigint)

    try:
        proc = subprocess.Popen(
            strace_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print("ERROR: 'su' or 'strace' not found. Are you on the AX12?")
        sys.exit(1)

    t_start = _now_epoch()

    try:
        with open(outpath, "w") as fout:
            hex_buf = bytearray()
            for line in proc.stdout:
                if stop or (_now_epoch() - t_start) >= duration:
                    break

                raw = _extract_hex_from_strace_line(line)
                if raw:
                    hex_buf.extend(raw)

                # Attempt to decode accumulated bytes
                if hex_buf:
                    t_now = _now_epoch()
                    for frame in decoder.feed(bytes(hex_buf)):
                        rec = _frame_to_record(frame, t_now)
                        fout.write(json.dumps(rec) + "\n")
                        frame_count += 1
                    hex_buf.clear()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        signal.signal(signal.SIGINT, old_handler)

    elapsed = _now_epoch() - t_start
    print(f"Done. {frame_count} frames in {elapsed:.1f}s -> {outpath}")
    print(f"Decoder stats: {decoder.stats}")


def _record_demo(args: argparse.Namespace) -> None:
    """Generate synthetic telemetry data for testing."""

    outpath = args.output or os.path.join(
        os.path.expanduser("~/ax12-research/captures"),
        f"telem-demo-{_ts_label()}.jsonl",
    )
    duration = args.duration or 10
    t_start = _now_epoch()
    frame_count = 0

    print(f"Generating {duration}s of synthetic telemetry -> {outpath}")

    encoder = UMBUSEncoder()

    with open(outpath, "w") as fout:
        t = t_start
        seq_ch = 0
        seq_elrs = 0

        while (t - t_start) < duration:
            elapsed = t - t_start
            phase = elapsed / duration  # 0..1

            # --- Channel data at 25 Hz ---
            # Simulate gimbal sweep: sine wave on G0/G1, triangle on G2, step on G3
            g0 = int(4000 * math.sin(2 * math.pi * elapsed / 5.0))
            g1 = int(3000 * math.cos(2 * math.pi * elapsed / 7.0))
            g2 = int(2000 * (2 * abs((elapsed % 4.0) / 4.0 - 0.5) * 2 - 1))
            g3 = 1000 if (int(elapsed) % 3 == 0) else -1000

            channels = [CHANNEL_CENTER] * 32
            # CH0-3: follow gimbals (unsigned mapped from signed)
            channels[0] = max(0, min(65535, CHANNEL_CENTER + g0))
            channels[1] = max(0, min(65535, CHANNEL_CENTER + g1))
            channels[2] = max(0, min(65535, CHANNEL_CENTER + g2))
            channels[3] = max(0, min(65535, CHANNEL_CENTER + g3))
            # CH4: switch toggles
            channels[4] = SWITCH_HIGH if int(elapsed) % 2 == 0 else CHANNEL_CENTER
            # CH5: ramp
            channels[5] = int(65535 * phase)

            raw_ch = encoder.channel_data(
                gimbals=[g0, g1, g2, g3], channels=channels, seq=seq_ch
            )
            decoder_tmp = UMBUSDecoder()
            for frame in decoder_tmp.feed(raw_ch):
                rec = _frame_to_record(frame, t)
                fout.write(json.dumps(rec) + "\n")
                frame_count += 1
            seq_ch = (seq_ch + 1) & 0xFF
            t += 0.04  # 25 Hz

            # --- ELRS telemetry at 5 Hz (every 5th channel frame) ---
            if seq_ch % 5 == 0:
                # Simulate link quality degrading then recovering
                link_quality = max(0, min(65535,
                    int(200 + 100 * math.sin(2 * math.pi * elapsed / 8.0))))
                timing = 20000  # 50 Hz packet rate
                raw_elrs = encoder.elrs_telemetry(
                    timing_us=timing, link_status=link_quality, seq=seq_elrs
                )
                for frame in UMBUSDecoder().feed(raw_elrs):
                    rec = _frame_to_record(frame, t)
                    fout.write(json.dumps(rec) + "\n")
                    frame_count += 1
                seq_elrs = (seq_elrs + 1) & 0xFF

            # --- Extended telemetry at ~3 Hz (every 8th channel frame) ---
            if seq_ch % 8 == 0:
                for si in range(3):
                    raw_ext = encoder.extended_telemetry(
                        sub_index=si,
                        value=int(1000 + 500 * math.sin(
                            2 * math.pi * elapsed / 6.0 + si)),
                    )
                    for frame in UMBUSDecoder().feed(raw_ext):
                        rec = _frame_to_record(frame, t)
                        fout.write(json.dumps(rec) + "\n")
                        frame_count += 1

    elapsed = _now_epoch() - t_start
    print(f"Done. {frame_count} frames in {duration}s (generated in {elapsed:.1f}s)")
    print(f"Output: {outpath}")


# ---------------------------------------------------------------------------
# REPLAY
# ---------------------------------------------------------------------------

def cmd_replay(args: argparse.Namespace) -> None:
    """Replay a recorded JSONL file at original speed."""

    path = args.file
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    records = []
    with open(path, "r") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping line {lineno}: {e}")

    if not records:
        print("No records found in file.")
        sys.exit(1)

    t0 = records[0]["t"]
    total_duration = records[-1]["t"] - t0
    print(f"Replaying {len(records)} frames over {total_duration:.1f}s")
    print(f"Press Ctrl+C to stop.\n")

    wall_start = _now_epoch()

    try:
        for i, rec in enumerate(records):
            # Wait for correct relative time
            target_wall = wall_start + (rec["t"] - t0)
            now = _now_epoch()
            if target_wall > now:
                time.sleep(target_wall - now)

            rtype = rec.get("type", "?")
            data = rec.get("data", {})
            elapsed = rec["t"] - t0

            if rtype == "channel":
                g = data.get("gimbals", [])
                idle = data.get("idle", False)
                g_str = "  ".join(f"G{j}={v:+5d}" for j, v in enumerate(g))
                tag = " [IDLE]" if idle else ""
                print(f"[{elapsed:7.3f}s] CHANNEL{tag}  {g_str}")

            elif rtype == "elrs":
                valid = "OK" if data.get("link_valid") else "INVALID"
                timing = data.get("timing_us", 0)
                rate = 1_000_000 / timing if timing else 0
                link = data.get("link_status", 0)
                print(f"[{elapsed:7.3f}s] ELRS     "
                      f"link={link} ({valid})  "
                      f"timing={timing}us ({rate:.0f}Hz)  "
                      f"seq={data.get('seq', 0)}")

            elif rtype == "extended":
                si = data.get("sub_index", 0)
                val = data.get("value", 0)
                desc = data.get("descriptor", 0)
                print(f"[{elapsed:7.3f}s] EXTENDED "
                      f"sub={si}  desc=0x{desc:02X}  "
                      f"value={val} (0x{val:04X})")

            else:
                print(f"[{elapsed:7.3f}s] {rtype.upper():8s} {data}")

    except KeyboardInterrupt:
        pass

    wall_elapsed = _now_epoch() - wall_start
    print(f"\nReplay finished. {len(records)} frames, {wall_elapsed:.1f}s wall time.")


# ---------------------------------------------------------------------------
# STATS
# ---------------------------------------------------------------------------

def cmd_stats(args: argparse.Namespace) -> None:
    """Analyze a recorded JSONL file and print statistics."""

    path = args.file
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not records:
        print("No records found.")
        sys.exit(1)

    # --- Basic info ---
    t0 = records[0]["t"]
    t1 = records[-1]["t"]
    duration = t1 - t0

    type_counts: Counter = Counter()
    for rec in records:
        type_counts[rec.get("type", "unknown")] += 1

    print("=" * 60)
    print("  TELEMETRY RECORDING ANALYSIS")
    print("=" * 60)
    print(f"  File:      {os.path.basename(path)}")
    print(f"  Start:     {datetime.fromtimestamp(t0, tz=timezone.utc).isoformat()}")
    print(f"  Duration:  {duration:.2f}s")
    print(f"  Frames:    {len(records)}")
    print()
    print("  Frame counts by type:")
    for ftype, count in type_counts.most_common():
        rate = count / duration if duration > 0 else 0
        print(f"    {ftype:12s}  {count:6d}  ({rate:5.1f}/s)")
    print()

    # --- Channel analysis ---
    ch_records = [r for r in records if r.get("type") == "channel"]
    if ch_records:
        _print_channel_stats(ch_records, duration)

    # --- ELRS analysis ---
    elrs_records = [r for r in records if r.get("type") == "elrs"]
    if elrs_records:
        _print_elrs_stats(elrs_records)

    # --- Extended analysis ---
    ext_records = [r for r in records if r.get("type") == "extended"]
    if ext_records:
        _print_extended_stats(ext_records)

    # --- Gimbal heatmap ---
    if ch_records:
        _print_gimbal_heatmap(ch_records, duration)


def _print_channel_stats(ch_records: list, duration: float) -> None:
    """Print channel value statistics."""
    print("-" * 60)
    print("  CHANNEL DATA")
    print("-" * 60)

    # Collect per-gimbal stats
    gimbal_data: dict[int, list[int]] = defaultdict(list)
    channel_data: dict[int, list[int]] = defaultdict(list)

    idle_count = 0
    for rec in ch_records:
        data = rec.get("data", {})
        if data.get("idle"):
            idle_count += 1
        for i, v in enumerate(data.get("gimbals", [])):
            gimbal_data[i].append(v)
        for i, v in enumerate(data.get("channels", [])):
            channel_data[i].append(v)

    active_count = len(ch_records) - idle_count
    print(f"  Total:  {len(ch_records)} frames "
          f"({active_count} active, {idle_count} idle)")
    rate = len(ch_records) / duration if duration > 0 else 0
    print(f"  Rate:   {rate:.1f} frames/s")
    print()

    # Gimbal ranges
    print("  Gimbal ranges (signed 16-bit):")
    print(f"    {'Axis':<6s}  {'Min':>7s}  {'Max':>7s}  {'Avg':>7s}  {'StdDev':>7s}")
    for gi in sorted(gimbal_data.keys()):
        vals = gimbal_data[gi]
        mn, mx = min(vals), max(vals)
        avg = sum(vals) / len(vals)
        variance = sum((v - avg) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance)
        print(f"    G{gi:<5d}  {mn:>+7d}  {mx:>+7d}  {avg:>+7.0f}  {std:>7.0f}")
    print()

    # Channel ranges (only show channels that changed)
    print("  Channel ranges (unsigned 16-bit, active channels only):")
    print(f"    {'Chan':<6s}  {'Min':>7s}  {'Max':>7s}  {'Avg':>7s}  {'Range':>7s}")
    for ci in sorted(channel_data.keys()):
        vals = channel_data[ci]
        mn, mx = min(vals), max(vals)
        if mn == mx:
            continue  # Skip static channels
        avg = sum(vals) / len(vals)
        rng = mx - mn
        print(f"    CH{ci:<4d}  {mn:>7d}  {mx:>7d}  {avg:>7.0f}  {rng:>7d}")
    print()


def _print_elrs_stats(elrs_records: list) -> None:
    """Print ELRS link quality statistics."""
    print("-" * 60)
    print("  ELRS LINK TELEMETRY")
    print("-" * 60)

    link_vals = []
    timing_vals = []
    valid_count = 0
    invalid_count = 0

    for rec in elrs_records:
        data = rec.get("data", {})
        if data.get("link_valid"):
            valid_count += 1
            link_vals.append(data.get("link_status", 0))
        else:
            invalid_count += 1
        timing_vals.append(data.get("timing_us", 0))

    print(f"  Frames:   {len(elrs_records)} "
          f"({valid_count} valid, {invalid_count} invalid)")

    if link_vals:
        avg_link = sum(link_vals) / len(link_vals)
        print(f"  Link status:")
        print(f"    Min:  {min(link_vals)}")
        print(f"    Max:  {max(link_vals)}")
        print(f"    Avg:  {avg_link:.0f}")
    else:
        print("  Link status:  no valid readings")

    if timing_vals:
        # Show unique timing intervals (usually constant)
        unique_timings = sorted(set(timing_vals))
        for tv in unique_timings:
            rate = 1_000_000 / tv if tv else 0
            count = timing_vals.count(tv)
            print(f"  Timing:   {tv}us ({rate:.0f}Hz) x{count}")

    print()


def _print_extended_stats(ext_records: list) -> None:
    """Print extended telemetry statistics."""
    print("-" * 60)
    print("  EXTENDED TELEMETRY")
    print("-" * 60)

    by_sub: dict[int, list[int]] = defaultdict(list)
    for rec in ext_records:
        data = rec.get("data", {})
        si = data.get("sub_index", 0)
        by_sub[si].append(data.get("value", 0))

    print(f"  Frames: {len(ext_records)}")
    print()
    print(f"  {'Sub':>4s}  {'Count':>6s}  {'Min':>7s}  {'Max':>7s}  {'Avg':>7s}")
    for si in sorted(by_sub.keys()):
        vals = by_sub[si]
        mn, mx = min(vals), max(vals)
        avg = sum(vals) / len(vals)
        print(f"  {si:>4d}  {len(vals):>6d}  {mn:>7d}  {mx:>7d}  {avg:>7.0f}")
    print()


def _print_gimbal_heatmap(ch_records: list, duration: float) -> None:
    """Print a text-based gimbal usage heatmap.

    Divides each gimbal's range into 5 zones and shows time spent in each.
    """
    print("-" * 60)
    print("  GIMBAL USAGE HEATMAP")
    print("-" * 60)

    # Zones: far-left, left, center, right, far-right
    # Thresholds for signed 16-bit: -32768..32767
    zones = [
        ("far-neg", -32768, -6554),
        ("neg",     -6554,  -1310),
        ("center",  -1310,   1310),
        ("pos",      1310,   6554),
        ("far-pos",  6554,  32767),
    ]
    zone_labels = [z[0] for z in zones]

    gimbal_data: dict[int, list[int]] = defaultdict(list)
    for rec in ch_records:
        for i, v in enumerate(rec.get("data", {}).get("gimbals", [])):
            gimbal_data[i].append(v)

    if not gimbal_data:
        print("  No gimbal data.")
        print()
        return

    n_frames = len(ch_records)
    frame_time = duration / n_frames if n_frames > 0 else 0

    for gi in sorted(gimbal_data.keys()):
        vals = gimbal_data[gi]
        zone_counts = [0] * len(zones)
        for v in vals:
            for zi, (_, lo, hi) in enumerate(zones):
                if lo <= v <= hi:
                    zone_counts[zi] += 1
                    break
            else:
                # Clamp to edges
                if v < zones[0][1]:
                    zone_counts[0] += 1
                else:
                    zone_counts[-1] += 1

        total = sum(zone_counts)
        print(f"  G{gi}:")
        bar_width = 30
        for zi, label in enumerate(zone_labels):
            pct = zone_counts[zi] / total * 100 if total > 0 else 0
            t_sec = zone_counts[zi] * frame_time
            filled = int(pct / 100 * bar_width)
            bar = "#" * filled + "." * (bar_width - filled)
            print(f"    {label:>8s}  [{bar}] {pct:5.1f}%  ({t_sec:.1f}s)")
        print()


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

def cmd_export(args: argparse.Namespace) -> None:
    """Export JSONL recording to CSV."""

    path = args.file
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    outpath = args.output
    if not outpath:
        outpath = os.path.splitext(path)[0] + ".csv"

    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not records:
        print("No records found.")
        sys.exit(1)

    # Determine max gimbal/channel counts
    max_gimbals = 0
    max_channels = 0
    for rec in records:
        if rec.get("type") == "channel":
            data = rec.get("data", {})
            max_gimbals = max(max_gimbals, len(data.get("gimbals", [])))
            max_channels = max(max_channels, len(data.get("channels", [])))

    # Build CSV
    headers = ["epoch", "relative_s", "type"]
    # Gimbal columns
    for i in range(max_gimbals):
        headers.append(f"gimbal_{i}")
    # Channel columns
    for i in range(max_channels):
        headers.append(f"channel_{i}")
    # ELRS columns
    headers.extend(["elrs_timing_us", "elrs_link_status", "elrs_link_valid",
                     "elrs_seq"])
    # Extended columns
    headers.extend(["ext_sub_index", "ext_descriptor", "ext_value"])
    # Idle flag
    headers.append("idle")

    t0 = records[0]["t"]

    with open(outpath, "w") as fout:
        fout.write(",".join(headers) + "\n")

        for rec in records:
            t = rec["t"]
            rtype = rec.get("type", "")
            data = rec.get("data", {})
            rel = t - t0

            row = [f"{t:.6f}", f"{rel:.6f}", rtype]

            # Gimbal values
            gimbals = data.get("gimbals", [])
            for i in range(max_gimbals):
                row.append(str(gimbals[i]) if i < len(gimbals) else "")

            # Channel values
            channels = data.get("channels", [])
            for i in range(max_channels):
                row.append(str(channels[i]) if i < len(channels) else "")

            # ELRS
            if rtype == "elrs":
                row.append(str(data.get("timing_us", "")))
                row.append(str(data.get("link_status", "")))
                row.append(str(data.get("link_valid", "")))
                row.append(str(data.get("seq", "")))
            else:
                row.extend(["", "", "", ""])

            # Extended
            if rtype == "extended":
                row.append(str(data.get("sub_index", "")))
                row.append(str(data.get("descriptor", "")))
                row.append(str(data.get("value", "")))
            else:
                row.extend(["", "", ""])

            # Idle
            row.append(str(data.get("idle", "")))

            fout.write(",".join(row) + "\n")

    print(f"Exported {len(records)} records to {outpath}")
    print(f"Columns: {len(headers)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Telemetry Flight Recorder for RadioMaster AX12",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s record                  # Record 30s from live serial
  %(prog)s record --duration 60    # Record 60s
  %(prog)s record --demo           # Generate synthetic test data
  %(prog)s replay capture.jsonl    # Replay at original speed
  %(prog)s stats capture.jsonl     # Print analysis
  %(prog)s export capture.jsonl    # Convert to CSV
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # record
    p_rec = sub.add_parser("record", help="Capture telemetry to JSONL")
    p_rec.add_argument("--duration", type=float, default=None,
                       help="Recording duration in seconds (default: 30)")
    p_rec.add_argument("--output", "-o", help="Output file path")
    p_rec.add_argument("--demo", action="store_true",
                       help="Generate synthetic data instead of live capture")

    # replay
    p_rep = sub.add_parser("replay", help="Replay recorded file at original speed")
    p_rep.add_argument("file", help="JSONL recording file")

    # stats
    p_sta = sub.add_parser("stats", help="Analyze recorded file")
    p_sta.add_argument("file", help="JSONL recording file")

    # export
    p_exp = sub.add_parser("export", help="Export to CSV")
    p_exp.add_argument("file", help="JSONL recording file")
    p_exp.add_argument("--output", "-o", help="Output CSV path")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "record": cmd_record,
        "replay": cmd_replay,
        "stats": cmd_stats,
        "export": cmd_export,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
