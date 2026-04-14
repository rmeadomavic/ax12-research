#!/usr/bin/env python3
"""
Parse UMBUS frames from strace output.

Extracts hex data from strace read/write dumps and decodes UMBUS frames.

Usage:
    # From a saved strace file:
    python strace-parser.py captures/idle-strace.txt

    # Export decoded frames as JSON (matches captures/frames.json format):
    python strace-parser.py --json captures/idle-strace.txt > frames.json

    # From live strace (pipe):
    su 0 strace -tt -e trace=read,write -e read=FD -e write=FD -p PID 2>&1 | python strace-parser.py -
"""
import json
import sys
import os
import re
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus import UMBUSDecoder, FrameType, describe_channel_value


def extract_hex_from_strace(text: str) -> bytes:
    """
    Extract raw bytes from strace hex dump output.

    Handles the format produced by strace -e read=FD / -e write=FD:
        | 00000  a6 57 10 02 04 01 fa ff  02 00 fa ff 06 00 00 00  .W.............. |
        | 00010  00 00 00 80 00 80 00 80  00 80 00 80 00 80 00 80  ................ |
    """
    result = bytearray()

    for line in text.split('\n'):
        line = line.strip()

        # Match strace hex dump lines: | offset hex... ascii... |
        match = re.match(r'\|\s*[0-9a-fA-F]+\s+((?:[0-9a-fA-F]{2}\s+)+)', line)
        if match:
            hex_str = match.group(1)
            for h in hex_str.split():
                if len(h) == 2:
                    try:
                        result.append(int(h, 16))
                    except ValueError:
                        continue
            continue

        # Also handle escaped string format from strace:
        # read(103, "\xa6\x57\x10\x02...", 4096) = 87
        hex_matches = re.findall(r'\\x([0-9a-fA-F]{2})', line)
        if hex_matches:
            for h in hex_matches:
                result.append(int(h, 16))

    return bytes(result)


def parse_strace_syscalls(text: str) -> list[dict]:
    """
    Parse strace output into syscall records with timestamps.

    Returns list of dicts: {timestamp, syscall, fd, direction, size, hex_data}
    """
    records = []
    current_record = None
    hex_lines = []

    for line in text.split('\n'):
        line = line.rstrip()

        # Match syscall line, with optional [pid XXXXX] prefix:
        #   07:05:03.963555 read(103, "...", 4096) = 87
        #   [pid 14372] 07:05:03.963555 read(94, "...", 32768) = 7
        syscall_match = re.match(
            r'(?:\[pid\s+\d+\]\s+)?(\d{2}:\d{2}:\d{2}\.\d+)\s+(read|write)\((\d+),',
            line
        )
        if syscall_match:
            # Save previous record
            if current_record and hex_lines:
                current_record['hex_data'] = extract_hex_from_strace('\n'.join(hex_lines))
                records.append(current_record)

            timestamp = syscall_match.group(1)
            syscall = syscall_match.group(2)
            fd = int(syscall_match.group(3))

            # Extract return value (bytes transferred)
            ret_match = re.search(r'=\s*(\d+)', line)
            size = int(ret_match.group(1)) if ret_match else 0

            current_record = {
                'timestamp': timestamp,
                'syscall': syscall,
                'fd': fd,
                'direction': 'MCU→App' if syscall == 'read' else 'App→MCU',
                'size': size,
            }
            hex_lines = []
            continue

        # Hex dump line
        if line.strip().startswith('|') or '\\x' in line:
            hex_lines.append(line)

    # Don't forget the last record
    if current_record and hex_lines:
        current_record['hex_data'] = extract_hex_from_strace('\n'.join(hex_lines))
        records.append(current_record)

    return records


def frame_to_dict(frame) -> dict:
    """Convert a UMBUSFrame to the captures/frames.json dict format.

    Keys: t (type byte), n (type name), s (size), h (hex), ok (checksum),
    and for channel data frames: g (gimbals), ch (channels).
    """
    d = {
        't': frame.frame_type,
        'n': frame.type_name,
        's': len(frame.raw),
        'h': frame.raw.hex(),
        'ok': frame.checksum_valid,
    }
    if frame.gimbals is not None:
        d['g'] = frame.gimbals
    if frame.channels is not None:
        d['ch'] = frame.channels
    return d


def decode_frames_from_text(text: str) -> tuple:
    """Decode UMBUS frames from strace text.

    Returns (decoder, frames_list) where frames_list contains UMBUSFrame objects.
    """
    records = parse_strace_syscalls(text)
    decoder = UMBUSDecoder()
    frames = []

    if records:
        for record in records:
            hex_data = record.get('hex_data', b'')
            if hex_data:
                for frame in decoder.feed(hex_data):
                    frames.append(frame)
    else:
        raw = extract_hex_from_strace(text)
        if raw:
            for frame in decoder.feed(raw):
                frames.append(frame)

    return decoder, frames


def export_json(frames, total_bytes: int) -> str:
    """Export frames as JSON matching the captures/frames.json format."""
    return json.dumps({
        'bytes': total_bytes,
        'frames': [frame_to_dict(f) for f in frames],
    })


def main():
    args = sys.argv[1:]
    json_mode = '--json' in args
    if json_mode:
        args.remove('--json')

    if not args:
        print("Usage: python strace-parser.py [--json] <strace-output.txt>")
        print("       su 0 strace ... 2>&1 | python strace-parser.py [--json] -")
        print()
        print("Options:")
        print("  --json    Export decoded frames as JSON (captures/frames.json format)")
        sys.exit(1)

    if args[0] == '-':
        text = sys.stdin.read()
    else:
        with open(args[0], 'r') as f:
            text = f.read()

    if json_mode:
        decoder, frames = decode_frames_from_text(text)
        total_bytes = sum(len(f.raw) for f in frames)
        print(export_json(frames, total_bytes))
        return

    # Parse syscall records
    records = parse_strace_syscalls(text)
    if not records:
        # Fall back to raw hex extraction
        print("No syscall records found, trying raw hex extraction...")
        raw = extract_hex_from_strace(text)
        if not raw:
            print("No hex data found in input.")
            sys.exit(1)
        decoder = UMBUSDecoder()
        for frame in decoder.feed(raw):
            print(frame.summary())
            print()
        print(f"Stats: {decoder.stats}")
        return

    print(f"Parsed {len(records)} syscall records\n")

    # Statistics
    read_count = sum(1 for r in records if r['syscall'] == 'read')
    write_count = sum(1 for r in records if r['syscall'] == 'write')
    read_bytes = sum(r['size'] for r in records if r['syscall'] == 'read')
    write_bytes = sum(r['size'] for r in records if r['syscall'] == 'write')

    print(f"Reads:  {read_count} calls, {read_bytes} bytes (MCU → App)")
    print(f"Writes: {write_count} calls, {write_bytes} bytes (App → MCU)")

    # Time span
    if len(records) >= 2:
        t0 = records[0]['timestamp']
        t1 = records[-1]['timestamp']
        print(f"Time span: {t0} → {t1}")

    print()

    # Decode all frames
    decoder = UMBUSDecoder()
    frame_types = Counter()
    all_frames = []

    # Combine all hex data and decode
    for record in records:
        hex_data = record.get('hex_data', b'')
        if hex_data:
            for frame in decoder.feed(hex_data):
                frame_types[frame.type_name] += 1
                all_frames.append((record, frame))

    print(f"Decoded {len(all_frames)} UMBUS frames:")
    for name, count in frame_types.most_common():
        print(f"  {name}: {count}")
    print()

    # Show first few frames of each type
    shown_types = set()
    for record, frame in all_frames:
        if frame.type_name not in shown_types:
            shown_types.add(frame.type_name)
            print(f"--- Example {frame.type_name} ({record['direction']}, {record['timestamp']}) ---")
            print(frame.summary())
            print(frame.hexdump())
            print()

    print(f"\nDecoder stats: {decoder.stats}")


if __name__ == '__main__':
    main()
