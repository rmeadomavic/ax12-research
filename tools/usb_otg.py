#!/data/data/com.termux/files/usr/bin/python3
"""
AX12 USB OTG Mode Switcher

Toggle between USB host mode (for keyboards, gamepads, flash drives)
and device/gadget mode (for ADB, file transfer to a PC).

MediaTek MT8788 uses three sysfs controls:
  1. device_host_gpio_attr — VBUS power GPIO (write-only)
  2. musb-hdrc cmode       — musb controller connection mode
  3. dual_role mode         — Type-C data role (dfp=host, ufp=device)

Run with:  su 0 python3 tools/usb_otg.py <enable|disable|status|devices>
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


# --- sysfs paths (MT8788-specific) ---

MUSB_BASE = Path("/sys/devices/platform/11200000.usb3/musb-hdrc")
HOST_GPIO_ATTR = Path("/sys/devices/platform/device_host_gpio/device_host_gpio_attr")
OTG_STATE = Path("/sys/devices/virtual/switch/otg_state/state")
USB_DEVICES_DIR = Path("/sys/bus/usb/devices")

# dual_role path — may or may not exist on every MT8788 build
DUAL_ROLE_CANDIDATES = [
    Path("/sys/class/dual_role_usb/otg_default/mode"),
    Path("/sys/devices/platform/11200000.usb3/dual_role_usb/mode"),
]


@dataclass
class SysfsWrite:
    """A single sysfs write operation."""
    path: Path
    value: str
    label: str
    required: bool = True


def find_dual_role_path() -> Path | None:
    """Find the dual_role mode sysfs path if it exists."""
    for candidate in DUAL_ROLE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def sysfs_read(path: Path) -> str | None:
    """Read a sysfs attribute, returning None on failure."""
    try:
        return path.read_text().strip()
    except (OSError, PermissionError):
        return None


def sysfs_write(path: Path, value: str) -> bool:
    """Write a value to a sysfs attribute. Returns True on success."""
    try:
        path.write_text(value)
        return True
    except (OSError, PermissionError) as e:
        return False


def apply_writes(writes: list[SysfsWrite]) -> bool:
    """Apply a sequence of sysfs writes, reporting each result."""
    all_ok = True
    for w in writes:
        if not w.path.exists() and not w.required:
            print(f"  [ skip ] {w.label}: path not found ({w.path})")
            continue
        if sysfs_write(w.path, w.value):
            print(f"  [  ok  ] {w.label} = {w.value}")
        else:
            tag = " FAIL " if w.required else " warn "
            print(f"  [{tag}] {w.label}: could not write '{w.value}' to {w.path}")
            if w.required:
                all_ok = False
    return all_ok


# --- Commands ---

def cmd_enable() -> int:
    """Enable USB host mode (OTG)."""
    print("Enabling USB host mode...")

    dual_role = find_dual_role_path()
    writes = [
        SysfsWrite(HOST_GPIO_ATTR, "1", "host GPIO (VBUS power)"),
        SysfsWrite(MUSB_BASE / "cmode", "1", "musb cmode"),
        SysfsWrite(
            dual_role or DUAL_ROLE_CANDIDATES[0],
            "dfp",
            "dual_role mode",
            required=False,
        ),
    ]

    ok = apply_writes(writes)
    print()
    if ok:
        print("USB host mode enabled — plug in a USB device.")
    else:
        print("Some writes failed. Host mode may not be fully active.")
    return 0 if ok else 1


def cmd_disable() -> int:
    """Revert to USB device/gadget mode."""
    print("Disabling USB host mode (reverting to device mode)...")

    dual_role = find_dual_role_path()
    writes = [
        SysfsWrite(HOST_GPIO_ATTR, "0", "host GPIO (VBUS power)"),
        SysfsWrite(MUSB_BASE / "cmode", "0", "musb cmode"),
        SysfsWrite(
            dual_role or DUAL_ROLE_CANDIDATES[0],
            "ufp",
            "dual_role mode",
            required=False,
        ),
    ]

    ok = apply_writes(writes)
    print()
    if ok:
        print("USB device mode restored — ADB/MTP available.")
    else:
        print("Some writes failed. Device mode may not be fully reverted.")
    return 0 if ok else 1


def cmd_status() -> int:
    """Show current USB OTG state."""
    print("USB OTG Status")
    print("=" * 44)

    mode = sysfs_read(MUSB_BASE / "mode")
    cmode = sysfs_read(MUSB_BASE / "cmode")
    vbus = sysfs_read(MUSB_BASE / "vbus")
    otg = sysfs_read(OTG_STATE)

    dual_role = find_dual_role_path()
    dr_mode = sysfs_read(dual_role) if dual_role else None

    is_host = (otg == "1") or (mode and "a_host" in mode)
    role_str = "HOST" if is_host else "DEVICE"

    print(f"  Role:       {role_str}")
    print(f"  OTG mode:   {mode or '(unreadable)'}")
    print(f"  cmode:      {cmode or '(unreadable)'}")
    print(f"  VBUS:       {vbus or '(unreadable)'}")
    print(f"  OTG switch: {otg or '(unreadable)'}")
    if dual_role:
        print(f"  dual_role:  {dr_mode or '(unreadable)'}")
    else:
        print(f"  dual_role:  (not present on this build)")

    # Show connected devices if in host mode
    if is_host:
        print()
        cmd_devices()

    return 0


def cmd_devices() -> int:
    """List connected USB devices (lsusb equivalent)."""
    if not USB_DEVICES_DIR.exists():
        print("No USB device sysfs found.")
        return 1

    print("Connected USB Devices")
    print("-" * 44)

    found = 0
    for entry in sorted(USB_DEVICES_DIR.iterdir()):
        # Real USB devices have names like "1-1", "1-1.2", "usb1"
        # Skip interfaces (contain colons like "1-1:1.0")
        if ":" in entry.name:
            continue

        vid = sysfs_read(entry / "idVendor")
        pid = sysfs_read(entry / "idProduct")
        manufacturer = sysfs_read(entry / "manufacturer") or ""
        product = sysfs_read(entry / "product") or ""

        if vid is None:
            continue

        found += 1
        desc = f"{manufacturer} {product}".strip() or "(unknown)"
        print(f"  {entry.name:12s}  {vid}:{pid}  {desc}")

    if found == 0:
        print("  (no devices connected)")

    return 0


# --- Entry point ---

COMMANDS = {
    "enable": cmd_enable,
    "disable": cmd_disable,
    "status": cmd_status,
    "devices": cmd_devices,
}

USAGE = f"""\
Usage: usb_otg.py <command>

Commands:
  enable   — Switch to USB host mode (power VBUS, accept devices)
  disable  — Revert to USB device mode (ADB, MTP)
  status   — Show current USB OTG state
  devices  — List connected USB devices
"""


def main() -> int:
    if os.getuid() != 0:
        print("Error: must run as root (su 0 python3 usb_otg.py ...)")
        return 1

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(USAGE)
        return 2

    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
