#!/data/data/com.termux/files/usr/bin/python3
"""
AX12 Model Diff Tool

Compare, hexdump, and export .rcm radio model files used by the
Flyshark app on the RadioMaster AX12 transmitter.

Usage:
    su 0 python3 model_diff.py diff <file1.rcm> <file2.rcm>
    su 0 python3 model_diff.py hexdump <file.rcm>
    su 0 python3 model_diff.py export <file.rcm> [json]

Commands:
    diff     - Byte-level comparison of two model files
    hexdump  - Annotated hex dump with known field labels
    export   - Export model data as JSON

Requires root (su 0) — model files are owned by the Flyshark app.

RCM binary format (decoded offsets):
    0x000  uint32 LE   Magic (0x12345678)
    0x004  uint32 LE   Creation timestamp (unix)
    0x008  200 bytes   Model name (null-padded UTF-8)
    0x0D0  252 bytes   Icon path (null-padded UTF-8, qrc:// URI)
    0x1CC  uint32 LE   Modified timestamp (unix)
    0x205  uint8       Model type (0=FixedWing, 1=DeltaWing, 2=Helicopter, 3=FPVDrone)
"""

import argparse
import json
import os
import struct
import sys
from datetime import datetime, timezone


# --- Constants ---

RCM_MAGIC = 0x12345678

MODEL_TYPES = {
    0: "FixedWing",
    1: "DeltaWing",
    2: "Helicopter",
    3: "FPVDrone",
}

# Known field regions: (offset, length, name, parse_func_key)
FIELD_MAP = [
    (0x000, 4,   "magic",            "magic"),
    (0x004, 4,   "created_ts",       "timestamp"),
    (0x008, 200, "name",             "string"),
    (0x0D0, 252, "icon",             "string"),
    (0x1CC, 4,   "modified_ts",      "timestamp"),
    (0x1D0, 53,  "unknown_1D0_204",  None),
    (0x205, 1,   "model_type",       "model_type"),
]

# Build a sorted list of (start, end, label) for annotation
REGIONS = []
for offset, length, label, _ in FIELD_MAP:
    REGIONS.append((offset, offset + length, label))
REGIONS.sort(key=lambda r: r[0])


# --- Parsing helpers ---

def _parse_magic(data, offset):
    val = struct.unpack_from("<I", data, offset)[0]
    return "0x{:08X}".format(val)


def _parse_timestamp(data, offset):
    val = struct.unpack_from("<I", data, offset)[0]
    if val == 0:
        return {"raw": 0, "formatted": "(unset)"}
    dt = datetime.fromtimestamp(val, tz=timezone.utc)
    return {"raw": val, "formatted": dt.strftime("%Y-%m-%d %H:%M:%S UTC")}


def _parse_string(data, offset, length):
    raw = data[offset:offset + length]
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def _parse_model_type(data, offset):
    val = data[offset]
    return {"raw": val, "name": MODEL_TYPES.get(val, "Unknown({})".format(val))}


def parse_header(data):
    """Parse all known header fields from raw bytes."""
    if len(data) < 0x206:
        raise ValueError("File too small ({} bytes, need >= 518)".format(len(data)))

    magic_val = struct.unpack_from("<I", data, 0)[0]
    if magic_val != RCM_MAGIC:
        raise ValueError("Bad magic 0x{:08X} (expected 0x{:08X})".format(
            magic_val, RCM_MAGIC))

    return {
        "magic": _parse_magic(data, 0x000),
        "created": _parse_timestamp(data, 0x004),
        "name": _parse_string(data, 0x008, 200),
        "icon": _parse_string(data, 0x0D0, 252),
        "modified": _parse_timestamp(data, 0x1CC),
        "model_type": _parse_model_type(data, 0x205),
    }


def read_rcm(path):
    """Read an .rcm file and return raw bytes."""
    with open(path, "rb") as f:
        data = f.read()
    return data


def format_timestamp(unix_ts):
    """Format a unix timestamp for display."""
    if unix_ts == 0:
        return "(unset)"
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# --- Region lookup for hexdump annotation ---

def get_region_label(offset):
    """Return the field label for a given byte offset, or None."""
    for start, end, label in REGIONS:
        if start <= offset < end:
            return label
    return None


def get_region_boundary(offset):
    """Return label if this offset is the START of a known region."""
    for start, end, label in REGIONS:
        if offset == start:
            return label
    return None


# --- diff command ---

def cmd_diff(args):
    """Byte-level comparison of two .rcm model files."""
    path1, path2 = args.file1, args.file2
    data1 = read_rcm(path1)
    data2 = read_rcm(path2)

    name1 = os.path.basename(path1)
    name2 = os.path.basename(path2)

    header1 = parse_header(data1)
    header2 = parse_header(data2)

    print("=== Model Diff ===")
    print("  A: {} ({} bytes)".format(name1, len(data1)))
    print("  B: {} ({} bytes)".format(name2, len(data2)))
    print()

    # --- Header field comparison ---
    print("--- Header Fields ---")
    fields = [
        ("Name",     header1["name"],                          header2["name"]),
        ("Type",     header1["model_type"]["name"],            header2["model_type"]["name"]),
        ("Created",  header1["created"]["formatted"],          header2["created"]["formatted"]),
        ("Modified", header1["modified"]["formatted"],         header2["modified"]["formatted"]),
        ("Icon",     header1["icon"],                          header2["icon"]),
    ]

    any_header_diff = False
    for label, val1, val2 in fields:
        if val1 == val2:
            print("  {:<12} {} (same)".format(label + ":", val1))
        else:
            any_header_diff = True
            print("  {:<12}".format(label + ":"))
            print("    A: {}".format(val1))
            print("    B: {}".format(val2))

    if not any_header_diff:
        print("  (all header fields identical)")
    print()

    # --- Byte-level diff ---
    print("--- Byte Differences ---")
    max_len = max(len(data1), len(data2))
    min_len = min(len(data1), len(data2))

    if len(data1) != len(data2):
        print("  File sizes differ: A={} B={}".format(len(data1), len(data2)))
        print()

    # Collect diff ranges
    diff_ranges = []
    i = 0
    while i < max_len:
        b1 = data1[i] if i < len(data1) else None
        b2 = data2[i] if i < len(data2) else None
        if b1 != b2:
            # Start of a diff range
            start = i
            while i < max_len:
                b1 = data1[i] if i < len(data1) else None
                b2 = data2[i] if i < len(data2) else None
                if b1 == b2:
                    break
                i += 1
            diff_ranges.append((start, i))
        else:
            i += 1

    if not diff_ranges:
        print("  Files are byte-identical.")
        return

    print("  {} differing region(s) found:".format(len(diff_ranges)))
    print()

    for rng_start, rng_end in diff_ranges:
        region = get_region_label(rng_start)
        region_str = " [{}]".format(region) if region else ""
        print("  Offset 0x{:04X}-0x{:04X} ({} bytes){}".format(
            rng_start, rng_end - 1, rng_end - rng_start, region_str))

        # Show hex dump of the differing region (context: up to 48 bytes)
        show_start = rng_start
        show_end = min(rng_end, rng_start + 48)
        truncated = rng_end > show_end

        # A line
        a_bytes = []
        for j in range(show_start, show_end):
            if j < len(data1):
                a_bytes.append("{:02X}".format(data1[j]))
            else:
                a_bytes.append("--")

        # B line
        b_bytes = []
        for j in range(show_start, show_end):
            if j < len(data2):
                b_bytes.append("{:02X}".format(data2[j]))
            else:
                b_bytes.append("--")

        # Format in groups of 16
        for row_off in range(0, len(a_bytes), 16):
            chunk_a = a_bytes[row_off:row_off + 16]
            chunk_b = b_bytes[row_off:row_off + 16]
            addr = show_start + row_off
            print("    A 0x{:04X}: {}".format(addr, " ".join(chunk_a)))
            print("    B 0x{:04X}: {}".format(addr, " ".join(chunk_b)))

        if truncated:
            print("    ... ({} more bytes)".format(rng_end - show_end))
        print()

    # Summary
    total_diff_bytes = sum(e - s for s, e in diff_ranges)
    print("  Total: {} bytes differ out of {} (A) / {} (B)".format(
        total_diff_bytes, len(data1), len(data2)))


# --- hexdump command ---

def cmd_hexdump(args):
    """Annotated hex dump of a model file."""
    path = args.file
    data = read_rcm(path)
    header = parse_header(data)

    print("=== Annotated Hex Dump ===")
    print("  File: {} ({} bytes)".format(os.path.basename(path), len(data)))
    print("  Name: {}".format(header["name"]))
    print("  Type: {}".format(header["model_type"]["name"]))
    print()

    BYTES_PER_LINE = 16
    prev_label = None

    for offset in range(0, len(data), BYTES_PER_LINE):
        # Check if we're entering a new region
        boundary = get_region_boundary(offset)
        if boundary and boundary != prev_label:
            # Print region header
            for start, end, label in REGIONS:
                if label == boundary:
                    print("  --- {} (0x{:04X}-0x{:04X}, {} bytes) ---".format(
                        label, start, end - 1, end - start))
                    break
            prev_label = boundary

        # If we're between known regions, mark as unknown
        current_label = get_region_label(offset)
        if current_label is None and prev_label is not None:
            # Find how far the unknown region extends
            unknown_start = offset
            unknown_end = len(data)
            for start, end, label in REGIONS:
                if start > offset:
                    unknown_end = start
                    break
            print("  --- unknown (0x{:04X}-0x{:04X}, {} bytes) ---".format(
                unknown_start, unknown_end - 1, unknown_end - unknown_start))
            prev_label = None
        elif current_label is None and prev_label is None:
            # Still in unknown territory -- check if this is a new unknown block start
            # Only print the header for the first line of a new unknown block
            pass

        # Build hex and ASCII columns
        chunk = data[offset:offset + BYTES_PER_LINE]
        hex_parts = []
        ascii_parts = []
        for i, b in enumerate(chunk):
            hex_parts.append("{:02X}".format(b))
            if 0x20 <= b < 0x7F:
                ascii_parts.append(chr(b))
            else:
                ascii_parts.append(".")

        # Pad if last line is short
        while len(hex_parts) < BYTES_PER_LINE:
            hex_parts.append("  ")
            ascii_parts.append(" ")

        # Format hex with a gap every 8 bytes
        hex_left = " ".join(hex_parts[:8])
        hex_right = " ".join(hex_parts[8:])
        ascii_str = "".join(ascii_parts)

        # Inline annotation for special bytes
        annotation = ""
        if offset == 0x000:
            annotation = "  <- magic 0x{:08X}".format(
                struct.unpack_from("<I", data, 0)[0])
        elif offset == 0x004:
            ts = struct.unpack_from("<I", data, 4)[0]
            annotation = "  <- created {}".format(format_timestamp(ts))
        elif offset == 0x008:
            annotation = "  <- name start: \"{}\"".format(header["name"])
        elif offset == 0x0D0:
            annotation = "  <- icon start: \"{}\"".format(
                header["icon"][:40] + ("..." if len(header["icon"]) > 40 else ""))
        elif offset == 0x1CC:
            ts = struct.unpack_from("<I", data, 0x1CC)[0]
            annotation = "  <- modified {}".format(format_timestamp(ts))
        elif offset == 0x200:
            annotation = "  <- model_type at +5: {}".format(
                header["model_type"]["name"])

        print("  {:04X}  {} {}  |{}|{}".format(
            offset, hex_left, hex_right, ascii_str, annotation))

    print()
    print("  Known:   {} bytes mapped".format(
        sum(length for _, length, _, _ in FIELD_MAP)))
    file_end = len(data)
    known_end = max(offset + length for offset, length, _, _ in FIELD_MAP)
    if file_end > known_end:
        print("  Unknown: {} bytes after 0x{:04X}".format(
            file_end - known_end, known_end))
    print("  Total:   {} bytes".format(len(data)))


# --- export command ---

def cmd_export(args):
    """Export model data as JSON."""
    path = args.file
    data = read_rcm(path)
    header = parse_header(data)

    # Build export structure
    export = {
        "source_file": os.path.basename(path),
        "file_size": len(data),
        "header": {
            "magic": header["magic"],
            "name": header["name"],
            "icon": header["icon"],
            "model_type": header["model_type"],
            "created": header["created"],
            "modified": header["modified"],
        },
        "regions": [],
    }

    # Export each known region as hex
    for offset, length, label, _ in FIELD_MAP:
        chunk = data[offset:offset + length]
        export["regions"].append({
            "label": label,
            "offset": "0x{:04X}".format(offset),
            "length": length,
            "hex": chunk.hex(),
        })

    # Export any trailing unknown bytes
    known_end = max(offset + length for offset, length, _, _ in FIELD_MAP)
    if len(data) > known_end:
        tail = data[known_end:]
        export["regions"].append({
            "label": "unknown_tail",
            "offset": "0x{:04X}".format(known_end),
            "length": len(tail),
            "hex": tail.hex(),
        })

    print(json.dumps(export, indent=2))


# --- Entry point ---

def main():
    parser = argparse.ArgumentParser(
        description="AX12 model diff/hexdump/export tool for .rcm files"
    )
    sub = parser.add_subparsers(dest="command")

    diff_p = sub.add_parser("diff", help="Compare two .rcm model files")
    diff_p.add_argument("file1", help="First .rcm file")
    diff_p.add_argument("file2", help="Second .rcm file")

    hex_p = sub.add_parser("hexdump", help="Annotated hex dump of a .rcm file")
    hex_p.add_argument("file", help="Path to .rcm file")

    exp_p = sub.add_parser("export", help="Export model data as JSON")
    exp_p.add_argument("file", help="Path to .rcm file")
    exp_p.add_argument("format", nargs="?", default="json",
                       choices=["json"], help="Output format (default: json)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "diff": cmd_diff,
        "hexdump": cmd_hexdump,
        "export": cmd_export,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
