#!/data/data/com.termux/files/usr/bin/python3
"""
AX12 Model Backup/Restore Tool

List, inspect, backup, and restore .rcm model files used by the
Flyshark app on the RadioMaster AX12 transmitter.

Usage:
    su 0 python3 model_tool.py list
    su 0 python3 model_tool.py dump <path>
    su 0 python3 model_tool.py backup <output_dir>
    su 0 python3 model_tool.py restore <backup_dir>

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
import shutil
import struct
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path


# --- Constants ---

RCM_MAGIC = 0x12345678

FLYSHARK_BASE = Path("/data/data/com.Flyshark.RadioMasterAX/files")
MODEL_DIR     = FLYSHARK_BASE / "rcModel"
TEMPLATE_DIR  = FLYSHARK_BASE / "rcTemplate"
ACTIVE_CFG    = FLYSHARK_BASE / "RcCfgFile.rcCfg"

# Android uses /data/user/0/ symlink — normalize to /data/data/
ANDROID_USER_PREFIX = "/data/user/0/"
ANDROID_DATA_PREFIX = "/data/data/"


class ModelType(IntEnum):
    FixedWing  = 0
    DeltaWing  = 1
    Helicopter = 2
    FPVDrone   = 3


# --- Data Classes ---

@dataclass
class RCMHeader:
    """Parsed header from a .rcm model file."""
    magic: int
    created: int          # unix timestamp
    name: str
    icon: str
    modified: int         # unix timestamp
    model_type: int       # ModelType value
    file_size: int
    source_path: str

    @property
    def type_name(self) -> str:
        try:
            return ModelType(self.model_type).name
        except ValueError:
            return f"Unknown({self.model_type})"

    @property
    def created_str(self) -> str:
        if self.created == 0:
            return "(unset)"
        return datetime.fromtimestamp(self.created, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

    @property
    def modified_str(self) -> str:
        if self.modified == 0:
            return "(unset)"
        return datetime.fromtimestamp(self.modified, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )


def parse_rcm(path: str) -> RCMHeader:
    """Parse an .rcm file and return its header fields."""
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 0x206:
        raise ValueError(f"{path}: file too small ({len(data)} bytes, need >= 518)")

    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != RCM_MAGIC:
        raise ValueError(
            f"{path}: bad magic 0x{magic:08X} (expected 0x{RCM_MAGIC:08X})"
        )

    created = struct.unpack_from("<I", data, 4)[0]
    name = data[8:8 + 200].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    icon = data[0xD0:0xD0 + 252].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    modified = struct.unpack_from("<I", data, 0x1CC)[0]
    model_type = data[0x205]

    return RCMHeader(
        magic=magic,
        created=created,
        name=name,
        icon=icon,
        modified=modified,
        model_type=model_type,
        file_size=len(data),
        source_path=str(path),
    )


def get_active_model() -> str:
    """Read the active model path from RcCfgFile.rcCfg."""
    if not ACTIVE_CFG.exists():
        return ""
    with open(ACTIVE_CFG, "rb") as f:
        data = f.read()
    # Path starts at offset 4, null-padded
    raw = data[4:].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    # Normalize /data/user/0/ -> /data/data/
    if raw.startswith(ANDROID_USER_PREFIX):
        raw = ANDROID_DATA_PREFIX + raw[len(ANDROID_USER_PREFIX):]
    return raw


def scan_dir(directory: Path) -> list[RCMHeader]:
    """Parse all .rcm files in a directory."""
    results = []
    if not directory.is_dir():
        return results
    for entry in sorted(directory.iterdir()):
        if entry.suffix == ".rcm":
            try:
                results.append(parse_rcm(str(entry)))
            except (ValueError, OSError) as e:
                print(f"  WARN: {e}", file=sys.stderr)
    return results


# --- Commands ---

def cmd_list(args: argparse.Namespace) -> None:
    """List all models and templates with key metadata."""
    active = get_active_model()

    models = scan_dir(MODEL_DIR)
    templates = scan_dir(TEMPLATE_DIR)

    if not models and not templates:
        print("No models or templates found.")
        return

    # Models
    if models:
        print(f"Models ({MODEL_DIR}):")
        print(f"{'':2}{'Name':<24} {'Type':<12} {'Created':<24} {'File':<20} {'Active'}")
        print(f"{'':2}{'':-<24} {'':-<12} {'':-<24} {'':-<20} {'':-<6}")
        for m in models:
            fname = os.path.basename(m.source_path)
            is_active = " *" if m.source_path == active else ""
            print(
                f"{'':2}{m.name:<24} {m.type_name:<12} {m.created_str:<24} {fname:<20}{is_active}"
            )
        print()

    # Templates
    if templates:
        print(f"Templates ({TEMPLATE_DIR}):")
        print(f"{'':2}{'Name':<24} {'Type':<12} {'Created':<24} {'File':<20}")
        print(f"{'':2}{'':-<24} {'':-<12} {'':-<24} {'':-<20}")
        for t in templates:
            fname = os.path.basename(t.source_path)
            print(
                f"{'':2}{t.name:<24} {t.type_name:<12} {t.created_str:<24} {fname:<20}"
            )
        print()

    print(f"Active model: {active or '(none)'}")


def cmd_dump(args: argparse.Namespace) -> None:
    """Dump detailed fields from a single .rcm file."""
    header = parse_rcm(args.path)

    print(f"File:      {header.source_path}")
    print(f"Size:      {header.file_size} bytes")
    print(f"Magic:     0x{header.magic:08X}")
    print(f"Name:      {header.name}")
    print(f"Type:      {header.type_name} ({header.model_type})")
    print(f"Icon:      {header.icon}")
    print(f"Created:   {header.created_str}  (unix {header.created})")
    print(f"Modified:  {header.modified_str}  (unix {header.modified})")


def cmd_backup(args: argparse.Namespace) -> None:
    """Copy all model files and metadata to a backup directory."""
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    active = get_active_model()
    manifest = {
        "backup_time": datetime.now(tz=timezone.utc).isoformat(),
        "active_model": active,
        "models": [],
        "templates": [],
    }

    # Backup models
    model_out = out / "models"
    model_out.mkdir(exist_ok=True)
    for m in scan_dir(MODEL_DIR):
        fname = os.path.basename(m.source_path)
        dest = model_out / fname
        shutil.copy2(m.source_path, str(dest))
        entry = asdict(m)
        entry["is_active"] = (m.source_path == active)
        manifest["models"].append(entry)
        print(f"  Backed up model: {m.name} -> {dest}")

    # Backup templates
    tmpl_out = out / "templates"
    tmpl_out.mkdir(exist_ok=True)
    for t in scan_dir(TEMPLATE_DIR):
        fname = os.path.basename(t.source_path)
        dest = tmpl_out / fname
        shutil.copy2(t.source_path, str(dest))
        manifest["templates"].append(asdict(t))
        print(f"  Backed up template: {t.name} -> {dest}")

    # Backup active config
    if ACTIVE_CFG.exists():
        shutil.copy2(str(ACTIVE_CFG), str(out / "RcCfgFile.rcCfg"))
        print(f"  Backed up active config -> {out / 'RcCfgFile.rcCfg'}")

    # Write manifest
    manifest_path = out / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written to {manifest_path}")
    print(f"Backup complete: {len(manifest['models'])} models, "
          f"{len(manifest['templates'])} templates")


def cmd_restore(args: argparse.Namespace) -> None:
    """Restore model files from a backup directory."""
    backup = Path(args.backup_dir)
    manifest_path = backup / "manifest.json"

    if not manifest_path.exists():
        print(f"ERROR: No manifest.json in {backup}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    print(f"Backup from: {manifest['backup_time']}")
    print(f"  Models:    {len(manifest['models'])}")
    print(f"  Templates: {len(manifest['templates'])}")
    print()

    # Show what will be restored
    for m in manifest["models"]:
        active = " (active)" if m.get("is_active") else ""
        print(f"  Model: {m['name']} [{m.get('source_path', '?')}]{active}")
    for t in manifest["templates"]:
        print(f"  Template: {t['name']} [{t.get('source_path', '?')}]")
    print()

    # Confirm
    answer = input("Restore these files? This will overwrite existing models. [y/N] ")
    if answer.strip().lower() != "y":
        print("Aborted.")
        return

    # Restore models
    model_src = backup / "models"
    restored = 0
    if model_src.is_dir():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        for entry in model_src.iterdir():
            if entry.suffix == ".rcm":
                dest = MODEL_DIR / entry.name
                shutil.copy2(str(entry), str(dest))
                # Match original ownership: u0_a83 (Flyshark app)
                os.chmod(str(dest), 0o600)
                print(f"  Restored: {entry.name} -> {dest}")
                restored += 1

    # Restore templates
    tmpl_src = backup / "templates"
    if tmpl_src.is_dir():
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        for entry in tmpl_src.iterdir():
            if entry.suffix == ".rcm":
                dest = TEMPLATE_DIR / entry.name
                shutil.copy2(str(entry), str(dest))
                os.chmod(str(dest), 0o444)
                print(f"  Restored: {entry.name} -> {dest}")
                restored += 1

    # Restore active config
    cfg_backup = backup / "RcCfgFile.rcCfg"
    if cfg_backup.exists():
        shutil.copy2(str(cfg_backup), str(ACTIVE_CFG))
        print(f"  Restored active config")

    print(f"\nRestore complete: {restored} files restored.")
    print("NOTE: Restart the Flyshark app to pick up changes.")


# --- Entry point ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AX12 model backup/restore tool for .rcm files"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all models and templates")

    dump_p = sub.add_parser("dump", help="Dump fields from a .rcm file")
    dump_p.add_argument("path", help="Path to .rcm file")

    backup_p = sub.add_parser("backup", help="Backup all models to a directory")
    backup_p.add_argument("output_dir", help="Output directory for backup")

    restore_p = sub.add_parser("restore", help="Restore models from backup")
    restore_p.add_argument("backup_dir", help="Backup directory to restore from")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "list": cmd_list,
        "dump": cmd_dump,
        "backup": cmd_backup,
        "restore": cmd_restore,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
