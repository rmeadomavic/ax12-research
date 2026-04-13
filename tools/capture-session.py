#!/usr/bin/env python3
"""
AX12 Capture Session — structured control input recording.

Guides the operator through capturing one control at a time with
labeled segments. Records serial traffic via strace (never opens
ttyS0 directly), validates UMBUS frames in real-time, and produces
clean binary captures + session manifest.

Usage:
    su 0 python3 ~/ax12-research/tools/capture-session.py
    su 0 python3 ~/ax12-research/tools/capture-session.py --duration 10

Output:
    captures/session-YYYYMMDD-HHMMSS/
        00-baseline.bin          # idle reference capture
        00-baseline.strace       # raw strace output (for strace-parser.py)
        01-left-x.bin            # labeled segment binary
        01-left-x.strace         # raw strace output
        ...
        manifest.json            # session metadata + per-segment quality stats

Downstream:
    python3 tools/umbus.py captures/session-.../01-left-x.bin
    python3 tools/strace-parser.py captures/session-.../01-left-x.strace
"""

import os
import sys
import re
import json
import time
import signal
import select
import subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus import UMBUSDecoder, FrameType, SYNC_BYTE, CHANNEL_CENTER

CAPTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'captures'
)
DEFAULT_DURATION = 8
BASELINE_DURATION = 3
SETTLE_SECONDS = 2

# Suggested controls — operator can also type custom labels
SUGGESTED = [
    ('left-x',    'Left stick X (yaw)'),
    ('left-y',    'Left stick Y (throttle)'),
    ('right-x',   'Right stick X (roll)'),
    ('right-y',   'Right stick Y (pitch)'),
    ('left-circle',  'Left stick full circle'),
    ('right-circle', 'Right stick full circle'),
    ('sw-a',      'Switch A (all positions)'),
    ('sw-b',      'Switch B (all positions)'),
    ('sw-c',      'Switch C (all positions)'),
    ('sw-d',      'Switch D (all positions)'),
    ('knob-l',    'Left knob/pot (full sweep)'),
    ('knob-r',    'Right knob/pot (full sweep)'),
]


# --- PID / FD discovery ---

def find_serial_reader():
    """Find the PID and FD of the process that has /dev/ttyS0 open.

    Returns (pid, fd) or (None, None).
    """
    try:
        out = subprocess.check_output(
            ['sh', '-c', 'ls -la /proc/*/fd/* 2>/dev/null | grep ttyS0'],
            text=True, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None, None

    for line in out.strip().split('\n'):
        m = re.search(r'/proc/(\d+)/fd/(\d+)\s*->\s*/dev/ttyS0', line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None


# --- Strace data parsing ---

_C_ESCAPES = {
    'n': 0x0A, 'r': 0x0D, 't': 0x09, 'f': 0x0C,
    'v': 0x0B, 'b': 0x08, 'a': 0x07,
    '\\': 0x5C, '"': 0x22,
}


def parse_strace_data(s):
    """Parse raw bytes from a strace data string.

    Handles \\xNN hex escapes (-x flag), \\NNN octal escapes (default),
    C escapes (\\n, \\t, etc.), and raw printable ASCII characters.
    """
    buf = bytearray()
    i = 0
    n = len(s)
    while i < n:
        if s[i] == '\\' and i + 1 < n:
            c = s[i + 1]
            if c == 'x' and i + 3 < n:
                try:
                    buf.append(int(s[i + 2:i + 4], 16))
                except ValueError:
                    pass
                i += 4
            elif c in '01234567':
                j = i + 2
                while j < min(n, i + 4) and s[j] in '01234567':
                    j += 1
                buf.append(int(s[i + 1:j], 8) & 0xFF)
                i = j
            elif c in _C_ESCAPES:
                buf.append(_C_ESCAPES[c])
                i += 2
            else:
                i += 2
        else:
            buf.append(ord(s[i]))
            i += 1
    return bytes(buf)


# Match strace syscall lines (with or without [pid N] prefix)
_SYSCALL_RE = re.compile(
    r'(?:\[pid\s+\d+\]\s+)?'
    r'(\d{2}:\d{2}:\d{2}\.\d+)\s+'
    r'(read|write)\((\d+),\s+'
    r'"((?:[^"\\]|\\.)*)"'
)


# --- Capture engine ---

def capture_strace(pid, fd, duration):
    """Run strace for `duration` seconds and collect serial data.

    Uses strace -x to get hex-escaped byte strings from the app's
    read() calls on the serial FD. Feeds bytes through UMBUSDecoder
    for real-time CRC validation.

    Returns (raw_bytes, strace_lines, frames, stats).
    """
    cmd = [
        'strace', '-tt',
        '-e', 'trace=read,write',
        '-x', '-s', '256',
        '-p', str(pid),
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )

    raw_reads = bytearray()
    raw_writes = bytearray()
    strace_lines = []
    decoder = UMBUSDecoder()
    frames = []
    leftover = b''

    start = time.monotonic()
    try:
        while time.monotonic() - start < duration:
            readable, _, _ = select.select([proc.stderr], [], [], 0.1)
            if not readable:
                continue

            chunk = os.read(proc.stderr.fileno(), 16384)
            if not chunk:
                break

            leftover += chunk
            while b'\n' in leftover:
                line_bytes, leftover = leftover.split(b'\n', 1)
                line = line_bytes.decode('utf-8', errors='replace')
                strace_lines.append(line)

                m = _SYSCALL_RE.match(line)
                if not m or int(m.group(3)) != fd:
                    continue

                data = parse_strace_data(m.group(4))
                if m.group(2) == 'read':
                    raw_reads.extend(data)
                    for frame in decoder.feed(data):
                        frames.append(frame)
                else:
                    raw_writes.extend(data)

            # Progress indicator
            elapsed = time.monotonic() - start
            n_ch = sum(
                1 for f in frames
                if f.frame_type in (FrameType.CHANNEL_DATA, FrameType.IDLE)
                and f.checksum_valid
            )
            sys.stdout.write(
                f'\r  Recording... {elapsed:.0f}/{duration}s '
                f'[{n_ch} channel frames]'
            )
            sys.stdout.flush()
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    sys.stdout.write('\r' + ' ' * 60 + '\r')
    sys.stdout.flush()

    valid = sum(1 for f in frames if f.checksum_valid)
    ch = sum(
        1 for f in frames
        if f.frame_type in (FrameType.CHANNEL_DATA, FrameType.IDLE)
        and f.checksum_valid
    )

    stats = {
        'read_bytes': len(raw_reads),
        'write_bytes': len(raw_writes),
        'frames_total': decoder.frames_decoded,
        'frames_valid': valid,
        'frames_bad_crc': decoder.frames_bad_checksum,
        'bytes_skipped': decoder.bytes_skipped,
        'channel_frames': ch,
        'duration_actual': round(time.monotonic() - start, 2),
    }

    return bytes(raw_reads), strace_lines, frames, stats


# --- File output ---

def save_segment(session_dir, seg_num, label, raw_bytes, strace_lines, stats):
    """Save segment data: binary capture + strace text."""
    prefix = f'{seg_num:02d}-{label}'

    bin_path = os.path.join(session_dir, f'{prefix}.bin')
    with open(bin_path, 'wb') as f:
        f.write(raw_bytes)

    strace_path = os.path.join(session_dir, f'{prefix}.strace')
    with open(strace_path, 'w') as f:
        for line in strace_lines:
            f.write(line + '\n')

    return prefix


def print_quality(stats):
    """Print a one-line quality summary for a segment."""
    total = stats['frames_total']
    if total == 0:
        print('  [!] NO FRAMES CAPTURED — check that the app is running')
        return

    valid = stats['frames_valid']
    bad = stats['frames_bad_crc']
    ch = stats['channel_frames']
    pct = valid / total * 100

    if bad > total * 0.05:
        print(f'  [!] {ch} ch frames, {bad} CRC errors ({100 - pct:.1f}%) — noisy capture')
    else:
        print(f'  [ok] {ch} channel frames, {valid}/{total} valid ({pct:.1f}%)')


def print_baseline_snapshot(frames):
    """Show gimbal/channel values from baseline for sanity check."""
    last = None
    for f in reversed(frames):
        if f.frame_type in (FrameType.CHANNEL_DATA, FrameType.IDLE) and f.checksum_valid:
            last = f
            break
    if last is None:
        return

    g = last.gimbals
    if g:
        print(f'  Gimbals: [{g[0]:+d}, {g[1]:+d}, {g[2]:+d}, {g[3]:+d}]')

    ch = last.channels
    if ch:
        non_center = []
        for i, v in enumerate(ch):
            if v != CHANNEL_CENTER:
                non_center.append(f'CH{i}={v}')
        if non_center:
            print(f'  Non-center channels: {", ".join(non_center)}')


# --- Main session ---

def main():
    if os.getuid() != 0:
        print('ERROR: Must run as root:')
        print('  su 0 python3 ~/ax12-research/tools/capture-session.py')
        sys.exit(1)

    pid, fd = find_serial_reader()
    if pid is None:
        print('ERROR: No process has /dev/ttyS0 open.')
        print('Is the Flyshark/RadioMaster app running?')
        sys.exit(1)

    print(f'Serial reader: PID {pid}, FD {fd}')

    # Parse optional --duration flag
    duration = DEFAULT_DURATION
    if '--duration' in sys.argv:
        idx = sys.argv.index('--duration')
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            duration = int(sys.argv[idx + 1])

    # Create session directory
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    session_dir = os.path.join(CAPTURES_DIR, f'session-{ts}')
    os.makedirs(session_dir, exist_ok=True)
    print(f'Session dir: {session_dir}\n')

    manifest = {
        'session_id': ts,
        'device': 'RadioMaster AX12',
        'started': datetime.now(timezone.utc).isoformat(),
        'pid': pid,
        'serial_fd': fd,
        'default_duration': duration,
        'segments': [],
    }

    print('=' * 52)
    print('  AX12 CONTROL CAPTURE SESSION')
    print('=' * 52)
    print()
    print('  RULES:')
    print('   1. One control at a time')
    print('   2. All other controls at CENTER / default')
    print('   3. Slow, deliberate movements')
    print('   4. Full throw: min -> center -> max -> center')
    print('   5. Pause ~1s at each extreme')
    print()
    print('  Suggested labels:')
    for i, (label, desc) in enumerate(SUGGESTED, 1):
        print(f'   {i:2d}. {label:14s}  {desc}')
    print(f'   (or type any custom label)')
    print()

    # --- Baseline ---
    input('>>> Return ALL controls to CENTER, press Enter for baseline... ')
    print(f'  Capturing baseline ({BASELINE_DURATION}s)...')
    raw, lines, frames, stats = capture_strace(pid, fd, BASELINE_DURATION)
    save_segment(session_dir, 0, 'baseline', raw, lines, stats)
    manifest['segments'].append({
        'index': 0, 'label': 'baseline', 'type': 'baseline', **stats,
    })
    print_quality(stats)
    print_baseline_snapshot(frames)

    # --- Segment loop ---
    seg_num = 0
    try:
        while True:
            print()
            label_input = input(
                f'[Segment {seg_num + 1}] Label (number, name, or "done"): '
            ).strip()

            if not label_input:
                continue
            if label_input.lower() in ('done', 'quit', 'exit', 'q'):
                break

            # Allow numeric shortcut
            if label_input.isdigit():
                idx = int(label_input) - 1
                if 0 <= idx < len(SUGGESTED):
                    label_input = SUGGESTED[idx][0]
                    print(f'  -> {label_input}')

            # Sanitize for filename
            safe_label = re.sub(r'[^a-zA-Z0-9_-]', '-', label_input)
            safe_label = re.sub(r'-+', '-', safe_label).strip('-')
            if not safe_label:
                safe_label = 'segment'

            seg_num += 1

            # Optional custom duration
            dur_input = input(
                f'  Duration [{duration}s]: '
            ).strip()
            seg_duration = int(dur_input) if dur_input.isdigit() else duration

            input('  Controls at CENTER, press Enter when ready... ')

            # Settle period — let operator position hands
            print(f'  Settling ({SETTLE_SECONDS}s)...')
            time.sleep(SETTLE_SECONDS)

            print(f'  >>> NOW: Move "{label_input}" through full range <<<')
            raw, lines, frames, stats = capture_strace(pid, fd, seg_duration)
            prefix = save_segment(session_dir, seg_num, safe_label, raw, lines, stats)
            manifest['segments'].append({
                'index': seg_num,
                'label': label_input,
                'filename': prefix,
                'duration_requested': seg_duration,
                **stats,
            })
            print_quality(stats)
            print(f'  Saved: {prefix}.bin ({stats["read_bytes"]} bytes)')

    except KeyboardInterrupt:
        print('\n\n  Session interrupted.')

    # --- Save manifest ---
    manifest['ended'] = datetime.now(timezone.utc).isoformat()
    manifest['total_segments'] = seg_num

    manifest_path = os.path.join(session_dir, 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
        f.write('\n')

    # --- Summary ---
    print()
    print('=' * 52)
    print(f'  Session complete: {seg_num} segment(s) captured')
    print(f'  Output: {session_dir}/')
    print()
    if seg_num > 0:
        total_ch = sum(
            s.get('channel_frames', 0) for s in manifest['segments']
        )
        total_bad = sum(
            s.get('frames_bad_crc', 0) for s in manifest['segments']
        )
        print(f'  Total channel frames: {total_ch}')
        if total_bad:
            print(f'  Total CRC errors:     {total_bad} (framing artifacts)')
        print()
        print('  To analyze a segment:')
        print(f'    python3 tools/umbus.py {session_dir}/01-*.bin')
        print(f'    python3 tools/strace-parser.py {session_dir}/01-*.strace')
    print('=' * 52)


if __name__ == '__main__':
    main()
