#!/data/data/com.termux/files/usr/bin/python3
"""
AX12 Model Share Tool

Export, summarize, share, and import .rcm radio model files for the
RadioMaster AX12 community.

Usage:
    su 0 python3 model_share.py export <file.rcm> [output.yaml]
    su 0 python3 model_share.py summary
    su 0 python3 model_share.py share <file.rcm>
    su 0 python3 model_share.py import <file.txt>

Commands:
    export   - Export model to human-readable YAML-like text format
    summary  - One-line summary of all models on the device
    share    - Generate a shareable text block (base64 + header comments)
    import   - Import a shared model from base64 text format

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
import base64
import os
import struct
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path


# --- Constants ---

RCM_MAGIC = 0x12345678

FLYSHARK_BASE = Path("/data/data/com.Flyshark.RadioMasterAX/files")
MODEL_DIR     = FLYSHARK_BASE / "rcModel"
TEMPLATE_DIR  = FLYSHARK_BASE / "rcTemplate"
ACTIVE_CFG    = FLYSHARK_BASE / "RcCfgFile.rcCfg"

ANDROID_USER_PREFIX = "/data/user/0/"
ANDROID_DATA_PREFIX = "/data/data/"

MODEL_TYPES = {
    0: "FixedWing",
    1: "DeltaWing",
    2: "Helicopter",
    3: "FPVDrone",
}

# Known field regions: (offset, length, name, description)
FIELD_MAP = [
    (0x000,   4, "magic",            "File magic number"),
    (0x004,   4, "created_ts",       "Creation timestamp"),
    (0x008, 200, "name",             "Model name"),
    (0x0D0, 252, "icon",             "Icon path (qrc:// URI)"),
    (0x1CC,   4, "modified_ts",      "Modified timestamp"),
    (0x1D0,  53, "unknown_1D0",      "Unknown region 0x1D0-0x204"),
    (0x205,   1, "model_type",       "Model type byte"),
]

KNOWN_END = max(off + length for off, length, _, _ in FIELD_MAP)

SHARE_HEADER = "--- AX12 MODEL SHARE ---"
SHARE_FOOTER = "--- END AX12 MODEL ---"


# --- Parsing helpers ---

def read_rcm(path):
    """Read an .rcm file and return raw bytes."""
    with open(path, "rb") as f:
        return f.read()


def parse_header(data):
    """Parse known header fields from raw bytes."""
    if len(data) < 0x206:
        raise ValueError("File too small ({} bytes, need >= 518)".format(len(data)))

    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != RCM_MAGIC:
        raise ValueError("Bad magic 0x{:08X} (expected 0x{:08X})".format(
            magic, RCM_MAGIC))

    created = struct.unpack_from("<I", data, 0x004)[0]
    name = data[0x008:0x008 + 200].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    icon = data[0x0D0:0x0D0 + 252].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    modified = struct.unpack_from("<I", data, 0x1CC)[0]
    model_type = data[0x205]

    return {
        "magic": magic,
        "created": created,
        "name": name,
        "icon": icon,
        "modified": modified,
        "model_type": model_type,
    }


def format_ts(unix_ts):
    """Format a unix timestamp for display."""
    if unix_ts == 0:
        return "(unset)"
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_date(unix_ts):
    """Format a unix timestamp as date only."""
    if unix_ts == 0:
        return "unknown"
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def type_name(val):
    """Return human-readable model type name."""
    return MODEL_TYPES.get(val, "Unknown({})".format(val))


def get_active_model():
    """Read the active model path from RcCfgFile.rcCfg."""
    if not ACTIVE_CFG.exists():
        return ""
    with open(ACTIVE_CFG, "rb") as f:
        data = f.read()
    raw = data[4:].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    if raw.startswith(ANDROID_USER_PREFIX):
        raw = ANDROID_DATA_PREFIX + raw[len(ANDROID_USER_PREFIX):]
    return raw


def scan_models():
    """Parse all .rcm model files (not templates)."""
    results = []
    if not MODEL_DIR.is_dir():
        return results
    for entry in sorted(MODEL_DIR.iterdir()):
        if entry.suffix == ".rcm":
            try:
                data = read_rcm(str(entry))
                header = parse_header(data)
                header["path"] = str(entry)
                header["file_size"] = len(data)
                results.append(header)
            except (ValueError, OSError) as e:
                print("  WARN: {}".format(e), file=sys.stderr)
    return results


def format_hex_block(data, offset, length, bytes_per_line=16):
    """Format a byte region as annotated hex lines."""
    lines = []
    chunk = data[offset:offset + length]
    for i in range(0, len(chunk), bytes_per_line):
        row = chunk[i:i + bytes_per_line]
        hex_str = " ".join("{:02X}".format(b) for b in row)
        ascii_str = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in row)
        addr = offset + i
        lines.append("    0x{:04X}: {:<48s}  |{}|".format(addr, hex_str, ascii_str))
    return lines


def classify_block(data, offset, length):
    """Identify common byte patterns in a block."""
    chunk = data[offset:offset + length]
    if not chunk:
        return None

    # Check if all same byte
    if len(set(chunk)) == 1:
        b = chunk[0]
        if b == 0x00:
            return "all zeros"
        elif b == 0xFF:
            return "all 0xFF"
        elif b == 0x7F:
            return "all 0x7F (channel endpoint default)"
        elif b == 0x64:
            return "all 0x64 (100% / rate default)"
        else:
            return "all 0x{:02X}".format(b)

    # Check for dominant patterns
    counts = {}
    for b in chunk:
        counts[b] = counts.get(b, 0) + 1

    dominant = max(counts, key=counts.get)
    ratio = counts[dominant] / len(chunk)
    if ratio > 0.8:
        if dominant == 0x7F:
            return "mostly 0x7F (channel endpoints, {:.0f}%)".format(ratio * 100)
        elif dominant == 0x64:
            return "mostly 0x64 (rate defaults, {:.0f}%)".format(ratio * 100)
        elif dominant == 0x00:
            return "mostly zeros ({:.0f}%)".format(ratio * 100)

    return None


# --- Export command ---

def cmd_export(args):
    """Export a model to human-readable YAML-like text format."""
    path = args.file
    data = read_rcm(path)
    header = parse_header(data)

    out_lines = []

    def emit(line=""):
        out_lines.append(line)

    emit("# AX12 Model Export")
    emit("# Exported: {}".format(
        datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")))
    emit("# Source: {}".format(os.path.basename(path)))
    emit("")

    # Header section
    emit("header:")
    emit("  name: \"{}\"".format(header["name"]))
    emit("  model_type: {} ({})".format(
        header["model_type"], type_name(header["model_type"])))
    emit("  created: {} (unix {})".format(
        format_ts(header["created"]), header["created"]))
    emit("  modified: {} (unix {})".format(
        format_ts(header["modified"]), header["modified"]))
    emit("  icon: \"{}\"".format(header["icon"]))
    emit("  file_size: {} bytes".format(len(data)))
    emit("  magic: 0x{:08X}".format(header["magic"]))
    emit("")

    # Known fields with decoded values
    emit("fields:")
    for offset, length, label, desc in FIELD_MAP:
        emit("  # {} ({} bytes at 0x{:04X})".format(desc, length, offset))
        emit("  {}:".format(label))

        if label == "magic":
            val = struct.unpack_from("<I", data, offset)[0]
            emit("    value: 0x{:08X}".format(val))
        elif label == "created_ts":
            val = struct.unpack_from("<I", data, offset)[0]
            emit("    value: {} ({})".format(val, format_ts(val)))
        elif label == "modified_ts":
            val = struct.unpack_from("<I", data, offset)[0]
            emit("    value: {} ({})".format(val, format_ts(val)))
        elif label == "name":
            name_str = data[offset:offset + length].split(b"\x00", 1)[0].decode(
                "utf-8", errors="replace")
            pad_len = length - len(name_str.encode("utf-8")) - 1  # -1 for null
            if pad_len < 0:
                pad_len = 0
            emit("    value: \"{}\"".format(name_str))
            emit("    padding: {} null bytes".format(pad_len))
        elif label == "icon":
            icon_str = data[offset:offset + length].split(b"\x00", 1)[0].decode(
                "utf-8", errors="replace")
            pad_len = length - len(icon_str.encode("utf-8")) - 1
            if pad_len < 0:
                pad_len = 0
            emit("    value: \"{}\"".format(icon_str))
            emit("    padding: {} null bytes".format(pad_len))
        elif label == "model_type":
            emit("    value: {} ({})".format(data[offset], type_name(data[offset])))
        else:
            # Unknown field - show hex with pattern analysis
            pattern = classify_block(data, offset, length)
            if pattern:
                emit("    pattern: {}".format(pattern))
            for line in format_hex_block(data, offset, length):
                emit(line)
        emit("")

    # Tail region (after known fields)
    if len(data) > KNOWN_END:
        tail_len = len(data) - KNOWN_END
        emit("tail:")
        emit("  # Unknown data after known fields ({} bytes at 0x{:04X})".format(
            tail_len, KNOWN_END))

        # Break tail into sub-blocks by pattern
        pos = KNOWN_END
        block_start = pos
        block_size = 32  # analyze in 32-byte chunks

        while pos < len(data):
            chunk_end = min(pos + block_size, len(data))
            pattern = classify_block(data, pos, chunk_end - pos)

            # Print hex for this chunk
            if pos == KNOWN_END or (pos - KNOWN_END) % 128 == 0:
                rel_offset = pos - KNOWN_END
                region_pattern = classify_block(
                    data, pos, min(128, len(data) - pos))
                if region_pattern:
                    emit("  # +0x{:04X}: {}".format(rel_offset, region_pattern))

            for line in format_hex_block(data, pos, chunk_end - pos):
                emit(line)
            pos = chunk_end

        emit("")

    # Summary
    emit("# Summary: {} ({}) - {} bytes total, {} known / {} unknown".format(
        header["name"], type_name(header["model_type"]),
        len(data),
        min(KNOWN_END, len(data)),
        max(0, len(data) - KNOWN_END)))

    output = "\n".join(out_lines) + "\n"

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print("Exported to {}".format(args.output))
    else:
        print(output, end="")


# --- Summary command ---

def cmd_summary(args):
    """One-line summary of all models on the device."""
    active = get_active_model()
    models = scan_models()

    if not models:
        print("No models found.")
        return

    for m in models:
        tag = " [ACTIVE]" if m["path"] == active else ""
        print("{} ({}, created {}) [{} bytes]{}".format(
            m["name"],
            type_name(m["model_type"]),
            format_date(m["created"]),
            m["file_size"],
            tag))


# --- Share command ---

def cmd_share(args):
    """Generate a shareable text block for a model."""
    path = args.file
    data = read_rcm(path)
    header = parse_header(data)

    encoded = base64.b64encode(data).decode("ascii")
    # Wrap base64 at 76 chars for readability
    wrapped = "\n".join(
        encoded[i:i + 76] for i in range(0, len(encoded), 76)
    )

    lines = []
    lines.append(SHARE_HEADER)
    lines.append("# Name: {}".format(header["name"]))
    lines.append("# Type: {} ({})".format(
        type_name(header["model_type"]), header["model_type"]))
    lines.append("# Created: {}".format(format_ts(header["created"])))
    lines.append("# Modified: {}".format(format_ts(header["modified"])))
    lines.append("# Size: {} bytes".format(len(data)))
    lines.append("# Format: RadioMaster AX12 .rcm (base64)")
    lines.append("#")
    lines.append("# Paste this entire block into model_share.py import")
    lines.append("# to add this model to your AX12.")
    lines.append("")
    lines.append(wrapped)
    lines.append("")
    lines.append(SHARE_FOOTER)

    output = "\n".join(lines) + "\n"

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print("Share block written to {}".format(args.output))
    else:
        print(output, end="")


# --- Import command ---

def cmd_import(args):
    """Import a shared model from a base64 text file."""
    path = args.file
    with open(path, "r") as f:
        content = f.read()

    # Strip comment lines and markers
    b64_lines = []
    in_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == SHARE_HEADER:
            in_block = True
            continue
        if stripped == SHARE_FOOTER:
            break
        if in_block and not stripped.startswith("#") and stripped:
            b64_lines.append(stripped)

    if not b64_lines:
        # Try treating the whole file as raw base64 (no markers)
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith("#") and stripped:
                b64_lines.append(stripped)

    if not b64_lines:
        print("ERROR: No base64 data found in {}".format(path), file=sys.stderr)
        sys.exit(1)

    b64_str = "".join(b64_lines)
    try:
        data = base64.b64decode(b64_str)
    except Exception as e:
        print("ERROR: Failed to decode base64: {}".format(e), file=sys.stderr)
        sys.exit(1)

    # Verify magic
    if len(data) < 4:
        print("ERROR: Decoded data too small ({} bytes)".format(len(data)),
              file=sys.stderr)
        sys.exit(1)

    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != RCM_MAGIC:
        print("ERROR: Bad magic 0x{:08X} (expected 0x{:08X})".format(
            magic, RCM_MAGIC), file=sys.stderr)
        sys.exit(1)

    header = parse_header(data)
    print("Decoded model:")
    print("  Name:     {}".format(header["name"]))
    print("  Type:     {}".format(type_name(header["model_type"])))
    print("  Created:  {}".format(format_ts(header["created"])))
    print("  Modified: {}".format(format_ts(header["modified"])))
    print("  Size:     {} bytes".format(len(data)))
    print()

    # Generate filename from creation timestamp (matches Flyshark convention)
    filename = "{}.rcm".format(header["created"])
    dest = MODEL_DIR / filename

    if dest.exists():
        print("WARNING: {} already exists!".format(dest))
        # Append a counter
        counter = 1
        while dest.exists():
            filename = "{}_{}.rcm".format(header["created"], counter)
            dest = MODEL_DIR / filename
            counter += 1
        print("  Using {} instead".format(filename))

    # Write the file
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(str(dest), "wb") as f:
        f.write(data)
    os.chmod(str(dest), 0o600)

    print("Saved to {}".format(dest))
    print("Restart the Flyshark app to see the new model.")


# --- Entry point ---

def main():
    parser = argparse.ArgumentParser(
        description="AX12 model share tool — export, share, and import .rcm files"
    )
    sub = parser.add_subparsers(dest="command")

    # export
    exp_p = sub.add_parser("export",
        help="Export model to human-readable text format")
    exp_p.add_argument("file", help="Path to .rcm file")
    exp_p.add_argument("output", nargs="?", default=None,
        help="Output file (default: stdout)")

    # summary
    sub.add_parser("summary",
        help="One-line summary of all models on the device")

    # share
    share_p = sub.add_parser("share",
        help="Generate a shareable base64 text block")
    share_p.add_argument("file", help="Path to .rcm file")
    share_p.add_argument("output", nargs="?", default=None,
        help="Output file (default: stdout)")

    # import
    imp_p = sub.add_parser("import",
        help="Import a shared model from base64 text")
    imp_p.add_argument("file", help="Path to shared text file")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "export": cmd_export,
        "summary": cmd_summary,
        "share": cmd_share,
        "import": cmd_import,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
