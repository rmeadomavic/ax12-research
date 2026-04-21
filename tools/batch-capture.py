#!/data/data/com.termux/files/usr/bin/python3
"""
AX12 Batch Capture — non-interactive control input recording.

Runs through all standard controls automatically on a timer.
The operator watches the screen and moves controls when prompted.
No keyboard input required — just print instructions and capture.

Usage:
    su 0 /data/data/com.termux/files/usr/bin/python3 ~/ax12-research/tools/batch-capture.py

Output:
    captures/session-YYYYMMDD-HHMMSS/
        00-baseline.bin / .strace
        01-left-x.bin / .strace
        ...
        manifest.json
"""

import os
import sys
import json
import time
from datetime import datetime, timezone

import importlib.util

_tools_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _tools_dir)

# capture-session.py has a hyphen — can't use normal import
_spec = importlib.util.spec_from_file_location(
    'capture_session', os.path.join(_tools_dir, 'capture-session.py')
)
_cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cs)

find_serial_reader = _cs.find_serial_reader
capture_strace = _cs.capture_strace
save_segment = _cs.save_segment
print_quality = _cs.print_quality
print_baseline_snapshot = _cs.print_baseline_snapshot
CAPTURES_DIR = _cs.CAPTURES_DIR

SEGMENT_DURATION = 8
BASELINE_DURATION = 5
INSTRUCTION_PAUSE = 5
COUNTDOWN_SECS = 3

# Ordered segments: (label, instruction)
SEGMENTS = [
    ('baseline',  'Keep ALL controls at CENTER — do not touch anything'),
    ('left-x',    'Move LEFT STICK LEFT and RIGHT (yaw axis)'),
    ('left-y',    'Move LEFT STICK UP and DOWN (throttle axis)'),
    ('right-x',   'Move RIGHT STICK LEFT and RIGHT (roll axis)'),
    ('right-y',   'Move RIGHT STICK UP and DOWN (pitch axis)'),
    ('sw-a',      'Toggle SWITCH A through all positions'),
    ('sw-b',      'Toggle SWITCH B through all positions'),
    ('sw-c',      'Toggle SWITCH C through all positions'),
    ('sw-d',      'Toggle SWITCH D through all positions'),
    ('knob-l',    'Rotate LEFT KNOB full sweep left to right'),
    ('knob-r',    'Rotate RIGHT KNOB full sweep left to right'),
]


def big_countdown(seconds):
    """Print a large countdown to screen."""
    for i in range(seconds, 0, -1):
        sys.stdout.write(f'\r    >>> {i} <<<   ')
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write('\r' + ' ' * 30 + '\r')
    sys.stdout.flush()


def show_instruction(label, instruction, is_baseline=False):
    """Display the upcoming segment instruction with countdown."""
    print()
    print('=' * 56)
    print(f'  === NEXT: {label.upper()} ===')
    print('=' * 56)
    print()
    if not is_baseline:
        print('  Return all controls to CENTER first.')
        print()
    print(f'  >>> {instruction} <<<')
    print()

    # Count down the instruction pause
    for i in range(INSTRUCTION_PAUSE, COUNTDOWN_SECS, -1):
        sys.stdout.write(f'\r  Starting in {i}... ')
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write('\r' + ' ' * 30 + '\r')
    sys.stdout.flush()

    # Big countdown for the final 3 seconds
    big_countdown(COUNTDOWN_SECS)

    print(f'  >>> RECORDING — {instruction} <<<')


def main():
    if os.getuid() != 0:
        print('ERROR: Must run as root:')
        print('  su 0 /data/data/com.termux/files/usr/bin/python3 '
              '~/ax12-research/tools/batch-capture.py')
        sys.exit(1)

    pid, fd = find_serial_reader()
    if pid is None:
        print('ERROR: No process has /dev/ttyS0 open.')
        print('Is the Flyshark/RadioMaster app running?')
        sys.exit(1)

    print(f'Serial reader: PID {pid}, FD {fd}')

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    session_dir = os.path.join(CAPTURES_DIR, f'session-{ts}')
    os.makedirs(session_dir, exist_ok=True)
    print(f'Session dir: {session_dir}')

    manifest = {
        'session_id': ts,
        'device': 'RadioMaster AX12',
        'mode': 'batch',
        'started': datetime.now(timezone.utc).isoformat(),
        'pid': pid,
        'serial_fd': fd,
        'segment_duration': SEGMENT_DURATION,
        'segments': [],
    }

    n_segments = len(SEGMENTS)
    total_time = (
        BASELINE_DURATION
        + (n_segments - 1) * SEGMENT_DURATION
        + n_segments * (INSTRUCTION_PAUSE + COUNTDOWN_SECS)
    )
    print()
    print('=' * 56)
    print('  AX12 BATCH CAPTURE')
    print('=' * 56)
    print()
    print(f'  {n_segments} segments, ~{total_time // 60}m{total_time % 60}s total')
    print()
    print('  RULES:')
    print('   1. Watch the screen for instructions')
    print('   2. Move ONLY the indicated control')
    print('   3. Slow, deliberate, full-range movements')
    print('   4. Return to center between segments')
    print()
    print('  Starting in 5 seconds...')
    time.sleep(5)

    start_time = time.monotonic()

    for seg_num, (label, instruction) in enumerate(SEGMENTS):
        is_baseline = (seg_num == 0)
        duration = BASELINE_DURATION if is_baseline else SEGMENT_DURATION

        show_instruction(label, instruction, is_baseline=is_baseline)

        raw, lines, frames, stats = capture_strace(pid, fd, duration)
        save_segment(session_dir, seg_num, label, raw, lines, stats)

        manifest['segments'].append({
            'index': seg_num,
            'label': label,
            'filename': f'{seg_num:02d}-{label}',
            'duration_requested': duration,
            **stats,
        })

        print_quality(stats)
        if is_baseline:
            print_baseline_snapshot(frames)
        print(f'  Saved: {seg_num:02d}-{label}.bin ({stats["read_bytes"]} bytes)')
        print(f'  [{seg_num + 1}/{n_segments}] complete')

    elapsed = time.monotonic() - start_time

    # Save manifest
    manifest['ended'] = datetime.now(timezone.utc).isoformat()
    manifest['total_segments'] = len(SEGMENTS)
    manifest['elapsed_seconds'] = round(elapsed, 1)

    manifest_path = os.path.join(session_dir, 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
        f.write('\n')

    # Summary
    print()
    print('=' * 56)
    print(f'  BATCH CAPTURE COMPLETE')
    print(f'  {len(SEGMENTS)} segments in {elapsed:.0f}s')
    print(f'  Output: {session_dir}/')
    print()

    total_ch = sum(s.get('channel_frames', 0) for s in manifest['segments'])
    total_bad = sum(s.get('frames_bad_crc', 0) for s in manifest['segments'])
    total_bytes = sum(s.get('read_bytes', 0) for s in manifest['segments'])
    print(f'  Total channel frames: {total_ch}')
    print(f'  Total bytes captured: {total_bytes}')
    if total_bad:
        print(f'  Total CRC errors:     {total_bad}')
    print()
    print('  To analyze:')
    print(f'    python3 tools/umbus.py {session_dir}/01-left-x.bin')
    print('=' * 56)


if __name__ == '__main__':
    main()
