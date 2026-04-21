#!/data/data/com.termux/files/usr/bin/python3
"""
USB HID Gamepad for RadioMaster AX12

Exposes the AX12's gimbals and switches as a standard USB HID gamepad.
The host PC sees 4 axes (16-bit signed) and 12 buttons — works with
any OS gamepad API (DirectInput, evdev, etc.) without drivers.

Architecture:
    UMBUS serial (AT32 MCU) --> strace snoop --> Python --> /dev/hidg0 --> USB host

Subcommands:
    enable   Configure USB gadget as HID+ADB composite device
    run      Stream UMBUS data to /dev/hidg0 as gamepad reports
    disable  Restore ADB-only USB configuration
    status   Show current USB gadget state

Usage:
    su 0 python3 usb_gamepad.py enable    # set up HID gadget
    su 0 python3 usb_gamepad.py run       # start streaming (Ctrl+C to stop)
    su 0 python3 usb_gamepad.py disable   # restore ADB-only
    su 0 python3 usb_gamepad.py status    # inspect current config

Requirements:
    - Root access (su 0)
    - Kernel CONFIG_USB_F_HID=y (built-in on AX12)
    - strace in PATH (/system/bin/strace)
    - SSH over Tailscale (USB reconfig does NOT affect SSH)
    - Python stdlib only (no pip packages)

UMBUS Channel Mapping:
    Gimbals (signed 16-bit, range ~+/-500):
        G0 = Left stick X  (Yaw)      -> Axis 0 (X)
        G1 = Right stick Y (Pitch)    -> Axis 1 (Y)
        G2 = Left stick Y  (Throttle) -> Axis 2 (Z)
        G3 = Right stick X (Roll)     -> Axis 3 (Rz)

    Switches (CH14-CH17, 500=active / 65036=off):
        SA = CH14 -> Button 1
        SB = CH15 -> Button 2
        SC = CH16 -> Button 3
        SD = CH17 -> Button 4

    Trims/Pots (if present):
        CH05-CH08 -> Buttons 5-8
        CH09-CH12 -> Buttons 9-12

HID Report Format (10 bytes):
    Byte 0-1:  Axis X  (int16 LE)  -32767..32767
    Byte 2-3:  Axis Y  (int16 LE)
    Byte 4-5:  Axis Z  (int16 LE)
    Byte 6-7:  Axis Rz (int16 LE)
    Byte 8-9:  Buttons (uint16 LE, 12 bits used)
"""

import os
import sys
import struct
import time
import subprocess
import re
import signal
import errno

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GADGET_BASE = "/config/usb_gadget/g1"
HID_FUNC = f"{GADGET_BASE}/functions/hid.gs0"
ADB_FUNC = f"{GADGET_BASE}/functions/ffs.adb"
CONFIG_DIR = f"{GADGET_BASE}/configs/b.1"
UDC_PATH = f"{GADGET_BASE}/UDC"
HIDG_DEV = "/dev/hidg0"

USB_VID = "0x0e8d"  # MediaTek
USB_PID_HID = "0x20ff"  # HID composite PID
USB_PID_ADB = "0x201c"  # Stock ADB PID

UDC_NAME = "musb-hdrc"

SERIAL_PORT = "/dev/ttyS0"
SERIAL_BAUD = 921600
STRACE_BIN = "/system/bin/strace"

# Gamepad report descriptor: 4 axes (16-bit signed), 12 buttons
# Standard HID 1.11 gamepad descriptor
REPORT_DESCRIPTOR = bytes([
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x05,        # Usage (Game Pad)
    0xA1, 0x01,        # Collection (Application)

    # --- 12 Buttons ---
    0x05, 0x09,        #   Usage Page (Button)
    0x19, 0x01,        #   Usage Minimum (Button 1)
    0x29, 0x0C,        #   Usage Maximum (Button 12)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x01,        #   Logical Maximum (1)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x0C,        #   Report Count (12)
    0x81, 0x02,        #   Input (Data, Var, Abs)

    # --- 4 bits padding to byte-align ---
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x04,        #   Report Count (4)
    0x81, 0x03,        #   Input (Const, Var, Abs)

    # --- 4 Axes (16-bit signed) ---
    0x05, 0x01,        #   Usage Page (Generic Desktop)
    0x09, 0x30,        #   Usage (X)
    0x09, 0x31,        #   Usage (Y)
    0x09, 0x32,        #   Usage (Z)
    0x09, 0x35,        #   Usage (Rz)
    0x16, 0x01, 0x80,  #   Logical Minimum (-32767)
    0x26, 0xFF, 0x7F,  #   Logical Maximum (32767)
    0x75, 0x10,        #   Report Size (16)
    0x95, 0x04,        #   Report Count (4)
    0x81, 0x02,        #   Input (Data, Var, Abs)

    0xC0,              # End Collection
])

# Report: 2 bytes buttons + 8 bytes axes = 10 bytes
REPORT_LENGTH = 10

# UMBUS gimbal range and HID axis range
GIMBAL_MAX = 500
HID_AXIS_MAX = 32767

# Switch values from UMBUS protocol
SW_ACTIVE = 500
SW_OFF = 65036

# Switch-to-button mapping: UMBUS channel index -> button bit index (0-based)
SWITCH_MAP = {
    14: 0,   # SA -> Button 1
    15: 1,   # SB -> Button 2
    16: 2,   # SC -> Button 3
    17: 3,   # SD -> Button 4
}

# Extra channel-to-button mapping for trims/pots (if non-center)
EXTRA_BUTTON_MAP = {
    5: 4,    # CH05 -> Button 5
    6: 5,    # CH06 -> Button 6
    7: 6,    # CH07 -> Button 7
    8: 7,    # CH08 -> Button 8
    9: 8,    # CH09 -> Button 9
    10: 9,   # CH10 -> Button 10
    11: 10,  # CH11 -> Button 11
    12: 11,  # CH12 -> Button 12
}

CHANNEL_CENTER = 0x8000  # 32768


# ---------------------------------------------------------------------------
# UMBUS decoder (inline minimal version to avoid import issues)
# ---------------------------------------------------------------------------

SYNC_BYTE = 0xA6

FRAME_SIZES = {
    0x57: 87,   # CHANNEL_DATA
    0x77: 87,   # IDLE
    0x08: 7,    # HEARTBEAT (MCU default)
    0x10: 18,   # EXTENDED
    0x15: 21,   # ELRS_TELEM
    0x07: 7,    # CMD_07
    0x0C: 12,   # CMD_0C
    0x0E: 14,   # CMD_0E
}

NUM_GIMBALS = 4
GIMBAL_OFFSET = 6
CHANNEL_OFFSET = 18


def decode_channel_frame(raw):
    """Extract gimbals and channels from a 0x57/0x77 frame.

    Returns (gimbals: list[int], channels: list[int]) or (None, None).
    """
    if len(raw) < 87:
        return None, None

    gimbals = []
    for i in range(NUM_GIMBALS):
        offset = GIMBAL_OFFSET + i * 2
        val = struct.unpack_from('<h', raw, offset)[0]
        gimbals.append(val)

    channels = []
    for offset in range(CHANNEL_OFFSET, len(raw) - 3, 2):
        if offset + 2 > len(raw):
            break
        val = struct.unpack_from('<H', raw, offset)[0]
        channels.append(val)

    return gimbals, channels


class MiniDecoder:
    """Minimal UMBUS frame decoder for the gamepad use case.

    Only cares about 0x57/0x77 channel data frames. Skips everything else.
    """

    def __init__(self):
        self._buf = bytearray()
        self.frames = 0

    def feed(self, data):
        """Feed raw bytes, yield (gimbals, channels) tuples."""
        self._buf.extend(data)

        while True:
            sync_idx = self._buf.find(bytes([SYNC_BYTE]))
            if sync_idx < 0:
                self._buf.clear()
                return
            if sync_idx > 0:
                del self._buf[:sync_idx]

            if len(self._buf) < 2:
                return

            frame_type = self._buf[1]

            # Disambiguate heartbeat sizes
            if frame_type == 0x08 and len(self._buf) >= 4:
                frame_size = 8 if self._buf[2] == 0x35 else 7
            else:
                frame_size = FRAME_SIZES.get(frame_type)

            if frame_size is None:
                frame_size = frame_type
                if frame_size < 3 or frame_size > 256:
                    del self._buf[0]
                    continue

            if len(self._buf) < frame_size:
                return

            raw = bytes(self._buf[:frame_size])
            del self._buf[:frame_size]

            if frame_type in (0x57, 0x77):
                gimbals, channels = decode_channel_frame(raw)
                if gimbals is not None:
                    self.frames += 1
                    yield gimbals, channels


# ---------------------------------------------------------------------------
# Strace hex parser
# ---------------------------------------------------------------------------

_HEX_DUMP_RE = re.compile(r'^\s*\|\s*[0-9a-fA-F]+\s+((?:[0-9a-fA-F]{2}\s+)+)')
_ESCAPED_RE = re.compile(r'\\x([0-9a-fA-F]{2})')


def parse_strace_line(line):
    """Extract raw bytes from a single strace output line.

    Handles two formats:
      1. Hex dump:   | 00000  a6 57 10 02 ...  .W.... |
      2. Escaped:    read(103, "\\xa6\\x57...", 4096) = 87
    """
    m = _HEX_DUMP_RE.match(line)
    if m:
        hex_str = m.group(1)
        try:
            return bytes(int(h, 16) for h in hex_str.split() if len(h) == 2)
        except ValueError:
            return None

    hex_bytes = _ESCAPED_RE.findall(line)
    if hex_bytes:
        return bytes(int(h, 16) for h in hex_bytes)

    return None


# ---------------------------------------------------------------------------
# HID report builder
# ---------------------------------------------------------------------------

def scale_gimbal(value, deadzone=15):
    """Scale UMBUS gimbal value (~+/-500) to HID axis (-32767..32767).

    Applies a small deadzone and clamps to the output range.
    """
    if abs(value) < deadzone:
        return 0
    # Linear scale with clamp
    scaled = int(value * HID_AXIS_MAX / GIMBAL_MAX)
    return max(-HID_AXIS_MAX, min(HID_AXIS_MAX, scaled))


def build_report(gimbals, channels):
    """Build a 10-byte HID gamepad report.

    Layout: [buttons_lo, buttons_hi, ax0_lo, ax0_hi, ax1_lo, ax1_hi,
             ax2_lo, ax2_hi, ax3_lo, ax3_hi]
    """
    # Axes: scale gimbals
    axes = [0, 0, 0, 0]
    if gimbals:
        for i in range(min(4, len(gimbals))):
            axes[i] = scale_gimbal(gimbals[i])

    # Buttons: 12-bit field
    buttons = 0
    if channels:
        # Primary switches (SA-SD on CH14-CH17)
        for ch_idx, btn_idx in SWITCH_MAP.items():
            if ch_idx < len(channels) and channels[ch_idx] == SW_ACTIVE:
                buttons |= (1 << btn_idx)

        # Extra channels -> buttons (non-center = pressed)
        for ch_idx, btn_idx in EXTRA_BUTTON_MAP.items():
            if ch_idx < len(channels) and channels[ch_idx] != CHANNEL_CENTER:
                buttons |= (1 << btn_idx)

    # Pack: uint16 buttons (LE) + 4x int16 axes (LE)
    return struct.pack('<H4h', buttons, axes[0], axes[1], axes[2], axes[3])


# ---------------------------------------------------------------------------
# Gadget management helpers
# ---------------------------------------------------------------------------

def sysfs_read(path):
    """Read a sysfs/configfs attribute."""
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


def sysfs_write(path, value):
    """Write a sysfs/configfs attribute. Returns True on success."""
    try:
        with open(path, 'w') as f:
            f.write(str(value))
        return True
    except (OSError, IOError) as e:
        print(f"  [FAIL] write '{value}' -> {path}: {e}")
        return False


def sysfs_write_bytes(path, data):
    """Write raw bytes to a sysfs/configfs attribute."""
    try:
        with open(path, 'wb') as f:
            f.write(data)
        return True
    except (OSError, IOError) as e:
        print(f"  [FAIL] write {len(data)} bytes -> {path}: {e}")
        return False


def list_function_links():
    """List function symlinks in the active config (f1, f2, ...)."""
    links = {}
    try:
        for entry in os.listdir(CONFIG_DIR):
            full = os.path.join(CONFIG_DIR, entry)
            if os.path.islink(full):
                target = os.readlink(full)
                links[entry] = target
    except OSError:
        pass
    return links


def remove_function_links():
    """Remove all function symlinks from the active config."""
    for name, target in list_function_links().items():
        path = os.path.join(CONFIG_DIR, name)
        try:
            os.unlink(path)
            print(f"  [ok] Removed {name} -> {os.path.basename(target)}")
        except OSError as e:
            print(f"  [FAIL] Remove {name}: {e}")


def unbind_udc():
    """Unbind the UDC (disconnect USB)."""
    current = sysfs_read(UDC_PATH)
    if current:
        print(f"  Unbinding UDC ({current})...")
        sysfs_write(UDC_PATH, "")
        time.sleep(0.3)
        return True
    print("  UDC already unbound")
    return True


def bind_udc():
    """Bind the UDC (reconnect USB)."""
    print(f"  Binding UDC ({UDC_NAME})...")
    if sysfs_write(UDC_PATH, UDC_NAME):
        time.sleep(0.5)
        return True
    return False


# ---------------------------------------------------------------------------
# Subcommand: enable
# ---------------------------------------------------------------------------

def cmd_enable():
    """Configure USB gadget as HID+ADB composite device."""
    print("=== USB HID Gamepad: Enable ===\n")

    # Step 1: Unbind UDC
    print("[1/6] Unbind UDC")
    unbind_udc()

    # Step 2: Remove existing function links
    print("\n[2/6] Remove existing function links")
    remove_function_links()

    # Step 3: Set device identifiers
    print("\n[3/6] Set device identifiers")
    sysfs_write(f"{GADGET_BASE}/idProduct", USB_PID_HID)
    print(f"  [ok] idProduct = {USB_PID_HID}")

    # Step 4: Write HID report descriptor and parameters
    print("\n[4/6] Configure HID function")
    if not os.path.isdir(HID_FUNC):
        print(f"  [FAIL] HID function dir not found: {HID_FUNC}")
        print("  Kernel must have CONFIG_USB_F_HID=y and function pre-created.")
        return 1

    ok = True
    ok &= sysfs_write(f"{HID_FUNC}/protocol", "0")
    print(f"  [{'ok' if ok else 'FAIL'}] protocol = 0 (none)")
    ok &= sysfs_write(f"{HID_FUNC}/subclass", "0")
    print(f"  [{'ok' if ok else 'FAIL'}] subclass = 0 (none)")
    ok &= sysfs_write(f"{HID_FUNC}/report_length", str(REPORT_LENGTH))
    print(f"  [{'ok' if ok else 'FAIL'}] report_length = {REPORT_LENGTH}")
    ok &= sysfs_write_bytes(f"{HID_FUNC}/report_desc", REPORT_DESCRIPTOR)
    print(f"  [{'ok' if ok else 'FAIL'}] report_desc = {len(REPORT_DESCRIPTOR)} bytes")

    if not ok:
        print("\n  WARNING: Some HID parameters failed to write.")
        print("  The gadget may not enumerate correctly on the host.")

    # Step 5: Link functions into config (HID first, then ADB)
    print("\n[5/6] Link functions")
    try:
        os.symlink(HID_FUNC, os.path.join(CONFIG_DIR, "f1"))
        print(f"  [ok] f1 -> hid.gs0")
    except OSError as e:
        print(f"  [FAIL] Link hid.gs0 as f1: {e}")
        return 1

    try:
        os.symlink(ADB_FUNC, os.path.join(CONFIG_DIR, "f2"))
        print(f"  [ok] f2 -> ffs.adb")
    except OSError as e:
        print(f"  [FAIL] Link ffs.adb as f2: {e}")
        # Non-fatal: HID still works without ADB
        print("  WARNING: ADB will not be available. HID-only mode.")

    # Step 6: Rebind UDC
    print("\n[6/6] Bind UDC")
    if not bind_udc():
        print("  [FAIL] Could not bind UDC!")
        return 1

    # chmod the HID device so non-root can write (optional convenience)
    time.sleep(0.5)
    if os.path.exists(HIDG_DEV):
        try:
            os.chmod(HIDG_DEV, 0o666)
            print(f"\n  [ok] chmod 666 {HIDG_DEV}")
        except OSError as e:
            print(f"\n  [warn] chmod {HIDG_DEV}: {e}")
    else:
        print(f"\n  [warn] {HIDG_DEV} not found (may take a moment to appear)")

    print("\n=== HID+ADB gadget enabled ===")
    print(f"  Host should see VID={USB_VID} PID={USB_PID_HID}")
    print(f"  Gamepad device: {HIDG_DEV}")
    print(f"  Run 'su 0 python3 usb_gamepad.py run' to start streaming")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: disable
# ---------------------------------------------------------------------------

def cmd_disable():
    """Restore ADB-only USB configuration."""
    print("=== USB HID Gamepad: Disable ===\n")

    # Step 1: Unbind UDC
    print("[1/4] Unbind UDC")
    unbind_udc()

    # Step 2: Remove function links
    print("\n[2/4] Remove function links")
    remove_function_links()

    # Step 3: Restore ADB-only config
    print("\n[3/4] Restore ADB-only config")
    sysfs_write(f"{GADGET_BASE}/idProduct", USB_PID_ADB)
    print(f"  [ok] idProduct = {USB_PID_ADB}")

    try:
        os.symlink(ADB_FUNC, os.path.join(CONFIG_DIR, "f1"))
        print(f"  [ok] f1 -> ffs.adb")
    except OSError as e:
        print(f"  [FAIL] Link ffs.adb: {e}")
        return 1

    # Step 4: Rebind UDC
    print("\n[4/4] Bind UDC")
    if not bind_udc():
        print("  [FAIL] Could not bind UDC!")
        return 1

    print("\n=== ADB-only gadget restored ===")
    print(f"  PID = {USB_PID_ADB}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status():
    """Show current USB gadget state."""
    print("=== USB Gadget Status ===\n")

    udc = sysfs_read(UDC_PATH)
    vid = sysfs_read(f"{GADGET_BASE}/idVendor")
    pid = sysfs_read(f"{GADGET_BASE}/idProduct")

    print(f"  UDC:        {udc or '(unbound)'}")
    print(f"  VID:        {vid or '?'}")
    print(f"  PID:        {pid or '?'}")

    is_hid = pid == USB_PID_HID
    is_adb = pid == USB_PID_ADB
    if is_hid:
        print(f"  Mode:       HID+ADB composite")
    elif is_adb:
        print(f"  Mode:       ADB only (stock)")
    else:
        print(f"  Mode:       Unknown PID")

    print(f"\n  Function links in {CONFIG_DIR}:")
    links = list_function_links()
    if links:
        for name, target in sorted(links.items()):
            func_name = os.path.basename(target)
            print(f"    {name} -> {func_name}")
    else:
        print(f"    (none)")

    # HID function state
    print(f"\n  HID function ({HID_FUNC}):")
    protocol = sysfs_read(f"{HID_FUNC}/protocol")
    subclass = sysfs_read(f"{HID_FUNC}/subclass")
    report_length = sysfs_read(f"{HID_FUNC}/report_length")
    print(f"    protocol:      {protocol}")
    print(f"    subclass:      {subclass}")
    print(f"    report_length: {report_length}")

    # Check report descriptor
    try:
        with open(f"{HID_FUNC}/report_desc", "rb") as f:
            desc = f.read()
        print(f"    report_desc:   {len(desc)} bytes")
        if desc == REPORT_DESCRIPTOR:
            print(f"    descriptor:    MATCHES gamepad descriptor")
        elif len(desc) == 0:
            print(f"    descriptor:    EMPTY (not configured)")
        else:
            print(f"    descriptor:    {len(desc)} bytes (different from gamepad)")
    except (OSError, IOError):
        print(f"    report_desc:   (unreadable)")

    # HID device node
    print(f"\n  Device node:")
    if os.path.exists(HIDG_DEV):
        import stat
        st = os.stat(HIDG_DEV)
        mode = stat.filemode(st.st_mode)
        print(f"    {HIDG_DEV}: {mode}")
    else:
        print(f"    {HIDG_DEV}: NOT PRESENT")

    # Flyshark process check
    print(f"\n  Flyshark (serial owner):")
    try:
        r = subprocess.run(
            ["su", "0", "sh", "-c", "pidof com.flyshark.flyshark"],
            capture_output=True, text=True, timeout=5
        )
        pid_str = r.stdout.strip()
        if pid_str:
            print(f"    PID: {pid_str} (RUNNING - strace snoop required)")
        else:
            print(f"    Not running (direct serial OK, but strace is safer)")
    except Exception:
        print(f"    (could not check)")

    return 0


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

def find_flyshark_serial_fd():
    """Find the file descriptor Flyshark uses for /dev/ttyS0.

    Returns (pid, fd) or (None, None).
    """
    try:
        r = subprocess.run(
            ["su", "0", "sh", "-c", "pidof com.flyshark.flyshark"],
            capture_output=True, text=True, timeout=5
        )
        pid_str = r.stdout.strip()
        if not pid_str:
            return None, None

        # Could be multiple PIDs; take the first
        pid = pid_str.split()[0]

        # Scan /proc/PID/fd for ttyS0
        fd_dir = f"/proc/{pid}/fd"
        r = subprocess.run(
            ["su", "0", "sh", "-c", f"ls -la {fd_dir}"],
            capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.split('\n'):
            if 'ttyS0' in line:
                parts = line.split()
                # The symlink name is the fd number
                for part in parts:
                    if part.isdigit() or (len(parts) > 8 and parts[8].isdigit()):
                        pass
                # Parse: lrwx------ ... 103 -> /dev/ttyS0
                m = re.search(r'\s(\d+)\s+->\s+/dev/ttyS0', line)
                if m:
                    return pid, m.group(1)

        return pid, None
    except Exception:
        return None, None


def start_strace(pid, fd):
    """Start strace snooping on Flyshark's serial reads.

    Returns a subprocess.Popen object whose stderr yields strace output.
    """
    cmd = [
        "su", "0", STRACE_BIN,
        "-tt",                        # timestamps
        "-e", f"trace=read",          # only read syscalls
        "-e", f"read={fd}",           # hex dump reads on this FD
        "-p", str(pid),               # attach to Flyshark
    ]
    print(f"  Starting strace: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,       # strace output goes to stderr
        bufsize=0,
    )
    return proc


def start_direct_read():
    """Open serial port directly (when Flyshark is not running).

    Returns an fd for os.read().
    """
    # Configure serial port
    subprocess.run(
        ["stty", "-F", SERIAL_PORT, str(SERIAL_BAUD), "raw", "-echo"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    fd = os.open(SERIAL_PORT, os.O_RDONLY | os.O_NONBLOCK)
    return fd


def cmd_run():
    """Stream UMBUS data to /dev/hidg0 as gamepad reports."""
    print("=== USB HID Gamepad: Run ===\n")

    # Check HID device
    if not os.path.exists(HIDG_DEV):
        print(f"  ERROR: {HIDG_DEV} not found.")
        print(f"  Run 'su 0 python3 usb_gamepad.py enable' first.")
        return 1

    # Open HID device for writing
    try:
        hid_fd = os.open(HIDG_DEV, os.O_WRONLY)
    except OSError as e:
        print(f"  ERROR: Cannot open {HIDG_DEV}: {e}")
        return 1

    # Determine data source: strace (Flyshark running) or direct serial
    fly_pid, fly_fd = find_flyshark_serial_fd()
    use_strace = fly_pid is not None and fly_fd is not None

    strace_proc = None
    serial_fd = None
    decoder = MiniDecoder()

    if use_strace:
        print(f"  Flyshark detected (PID {fly_pid}, FD {fly_fd})")
        print(f"  Using strace to snoop serial data\n")
        strace_proc = start_strace(fly_pid, fly_fd)
    else:
        if fly_pid:
            print(f"  WARNING: Flyshark running (PID {fly_pid}) but serial FD not found.")
            print(f"  Falling back to direct serial read — this may conflict!")
        else:
            print(f"  Flyshark not running — using direct serial read\n")
        serial_fd = start_direct_read()

    # Stats
    frames_sent = 0
    frames_err = 0
    last_status = time.monotonic()
    last_report_time = time.monotonic()
    report_interval = 1.0 / 25  # 25 Hz target rate
    last_gimbals = [0, 0, 0, 0]
    last_channels = []
    last_buttons = 0

    # Signal handler for clean shutdown
    running = [True]

    def signal_handler(sig, frame):
        running[0] = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("  Streaming gamepad reports to USB host")
    print("  Ctrl+C to stop\n")
    print(f"  {'Frames':>8s}  {'Errs':>5s}  {'X':>7s} {'Y':>7s} {'Z':>7s} {'Rz':>7s}  {'Buttons':>12s}")
    print(f"  {'------':>8s}  {'----':>5s}  {'-----':>7s} {'-----':>7s} {'-----':>7s} {'------':>7s}  {'-------':>12s}")

    try:
        strace_line_buf = b""

        while running[0]:
            now = time.monotonic()

            # --- Read data ---
            if strace_proc:
                # Read strace stderr (non-blocking via small reads)
                try:
                    chunk = strace_proc.stderr.read(4096)
                    if chunk is None or len(chunk) == 0:
                        # Process may have died
                        if strace_proc.poll() is not None:
                            print("\n  strace process exited!")
                            break
                        time.sleep(0.005)
                        continue
                except IOError:
                    time.sleep(0.005)
                    continue

                # Process strace output line by line
                strace_line_buf += chunk
                while b'\n' in strace_line_buf:
                    line, strace_line_buf = strace_line_buf.split(b'\n', 1)
                    line_str = line.decode('ascii', errors='replace')
                    raw = parse_strace_line(line_str)
                    if raw:
                        for gimbals, channels in decoder.feed(raw):
                            last_gimbals = gimbals
                            last_channels = channels

            elif serial_fd is not None:
                try:
                    data = os.read(serial_fd, 4096)
                    for gimbals, channels in decoder.feed(data):
                        last_gimbals = gimbals
                        last_channels = channels
                except BlockingIOError:
                    pass
                except OSError:
                    time.sleep(0.005)

            # --- Send HID reports at target rate ---
            if now - last_report_time >= report_interval:
                last_report_time = now
                report = build_report(last_gimbals, last_channels)

                try:
                    os.write(hid_fd, report)
                    frames_sent += 1
                except OSError as e:
                    frames_err += 1
                    if e.errno == errno.ESHUTDOWN:
                        print("\n  USB host disconnected!")
                        break

                # Status display every ~0.5s
                if now - last_status >= 0.5:
                    last_status = now
                    axes = struct.unpack_from('<4h', report, 2)
                    btns = struct.unpack_from('<H', report, 0)[0]
                    btn_str = format(btns, '012b')[::-1]  # LSB first for readability
                    active_btns = [str(i + 1) for i in range(12) if btns & (1 << i)]
                    btn_display = ','.join(active_btns) if active_btns else '-'
                    sys.stdout.write(
                        f"\r  {frames_sent:>8d}  {frames_err:>5d}  "
                        f"{axes[0]:>+7d} {axes[1]:>+7d} {axes[2]:>+7d} {axes[3]:>+7d}  "
                        f"[{btn_display:>12s}]"
                    )
                    sys.stdout.flush()

            # Small sleep to prevent busy-waiting
            if not use_strace:
                time.sleep(0.002)
            else:
                time.sleep(0.001)

    finally:
        print(f"\n\n  Stopping...")

        # Send a zeroed report (release all inputs)
        try:
            os.write(hid_fd, build_report([0, 0, 0, 0], [CHANNEL_CENTER] * 32))
        except OSError:
            pass

        os.close(hid_fd)

        if strace_proc:
            strace_proc.terminate()
            try:
                strace_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                strace_proc.kill()
            print(f"  strace stopped")

        if serial_fd is not None:
            os.close(serial_fd)
            print(f"  Serial port closed")

        print(f"\n  Total frames sent: {frames_sent}")
        print(f"  Write errors: {frames_err}")
        print(f"  UMBUS frames decoded: {decoder.frames}")

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMANDS = {
    "enable": cmd_enable,
    "disable": cmd_disable,
    "status": cmd_status,
    "run": cmd_run,
}

USAGE = """\
USB HID Gamepad for RadioMaster AX12

Usage: su 0 python3 usb_gamepad.py <command>

Commands:
  enable   Configure USB gadget as HID+ADB composite device
  run      Stream UMBUS data to /dev/hidg0 as gamepad reports
  disable  Restore ADB-only USB configuration
  status   Show current USB gadget state

Examples:
  su 0 python3 usb_gamepad.py enable     # configure HID gadget
  su 0 python3 usb_gamepad.py run        # start streaming
  su 0 python3 usb_gamepad.py disable    # restore stock config
"""


def main():
    if os.getuid() != 0:
        print("Error: must run as root")
        print("  su 0 python3 usb_gamepad.py <command>")
        return 1

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(USAGE)
        return 2

    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
