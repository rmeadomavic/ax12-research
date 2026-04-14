#!/data/data/com.termux/files/usr/bin/python3
"""
Hydra Detect Display Client for RadioMaster AX12

Displays real-time Hydra Detect object detection telemetry on the AX12
terminal. Receives data via MAVLink UDP from ELRS Backpack WiFi or
polls the Hydra REST API over Tailscale.

Data fields (MAVLink NAMED_VALUE_FLOAT/INT):
    HYD_FPS  - Detection framerate (float)
    HYD_CONF - Detection confidence 0-100 (float)
    HYD_TRK  - Active track count (int)
    HYD_LCK  - Lock status: 0=SEARCHING, 1=TRACKING, 2=LOCKED (int)
    HYD_CLS  - COCO class ID of primary target (int)

Modes:
    listen  - Passive MAVLink UDP listener on port 14550
    api     - Poll Hydra REST API over Tailscale
    demo    - Synthetic data for testing display

Usage:
    python3 hydra_display.py demo                   # test with fake data
    python3 hydra_display.py listen                  # ELRS Backpack WiFi
    python3 hydra_display.py listen --port 14551     # custom UDP port
    python3 hydra_display.py api --host 100.x.x.x   # Tailscale to Jetson
    python3 hydra_display.py api --host 10.0.0.1     # via ELRS WiFi AP

Python stdlib only. Reuses MAVLink parser pattern from cot_bridge.py.
"""

import argparse
import json
import math
import os
import random
import signal
import socket
import struct
import sys
import time

try:
    from urllib.request import urlopen, Request
    from urllib.error import URLError
except ImportError:
    urlopen = None


# ===================================================================
# MAVLink Constants
# ===================================================================

MAVLINK_V1_START = 0xFE
MAVLINK_V2_START = 0xFD

MAVLINK_V1_HEADER_LEN = 6
MAVLINK_V1_CRC_LEN = 2
MAVLINK_V2_HEADER_LEN = 10
MAVLINK_V2_CRC_LEN = 2

# MAVLink message IDs for Hydra telemetry
MSG_NAMED_VALUE_FLOAT = 251
MSG_NAMED_VALUE_INT = 252
MSG_HEARTBEAT = 0


# ===================================================================
# COCO Class Names (subset relevant to Hydra Detect)
# ===================================================================

COCO_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    6: "train",
    7: "truck",
    8: "boat",
    14: "bird",
    15: "cat",
    16: "dog",
    17: "horse",
    24: "backpack",
    25: "umbrella",
    63: "laptop",
    67: "cell phone",
    -1: "unknown",
}

# Lock status codes
LOCK_STATUS = {
    0: "SEARCHING",
    1: "TRACKING",
    2: "LOCKED",
}

LOCK_SYMBOLS = {
    0: "[ ]",
    1: "[~]",
    2: "[X]",
}


# ===================================================================
# MAVLink Parser (from cot_bridge.py)
# ===================================================================

class MAVLinkFrame:
    """Parsed MAVLink frame."""
    __slots__ = ('version', 'msg_id', 'sysid', 'compid', 'payload')

    def __init__(self, version, msg_id, sysid, compid, payload):
        self.version = version
        self.msg_id = msg_id
        self.sysid = sysid
        self.compid = compid
        self.payload = payload


class MAVLinkParser:
    """Incremental MAVLink v1/v2 frame parser.

    Feed raw bytes via feed(). Yields complete MAVLinkFrame objects.
    Handles stream synchronization and resync on corruption.
    """

    def __init__(self):
        self._buf = bytearray()

    def feed(self, data):
        """Feed raw bytes; yield parsed MAVLinkFrame objects."""
        self._buf.extend(data)

        while True:
            v1_pos = self._find_byte(MAVLINK_V1_START)
            v2_pos = self._find_byte(MAVLINK_V2_START)

            if v1_pos < 0 and v2_pos < 0:
                if len(self._buf) > 1:
                    self._buf = self._buf[-1:]
                return

            if v1_pos < 0:
                start_pos = v2_pos
            elif v2_pos < 0:
                start_pos = v1_pos
            else:
                start_pos = min(v1_pos, v2_pos)

            if start_pos > 0:
                del self._buf[:start_pos]

            start_byte = self._buf[0]

            if start_byte == MAVLINK_V1_START:
                frame = self._try_parse_v1()
            else:
                frame = self._try_parse_v2()

            if frame is None:
                return
            yield frame

    def _find_byte(self, byte):
        try:
            return self._buf.index(byte)
        except ValueError:
            return -1

    def _try_parse_v1(self):
        if len(self._buf) < MAVLINK_V1_HEADER_LEN:
            return None
        payload_len = self._buf[1]
        frame_len = MAVLINK_V1_HEADER_LEN + payload_len + MAVLINK_V1_CRC_LEN
        if len(self._buf) < frame_len:
            return None
        raw = bytes(self._buf[:frame_len])
        del self._buf[:frame_len]
        msg_id = raw[5]
        payload = raw[MAVLINK_V1_HEADER_LEN:MAVLINK_V1_HEADER_LEN + payload_len]
        return MAVLinkFrame(1, msg_id, raw[3], raw[4], payload)

    def _try_parse_v2(self):
        if len(self._buf) < MAVLINK_V2_HEADER_LEN:
            return None
        payload_len = self._buf[1]
        frame_len = MAVLINK_V2_HEADER_LEN + payload_len + MAVLINK_V2_CRC_LEN
        if len(self._buf) < frame_len:
            return None
        raw = bytes(self._buf[:frame_len])
        del self._buf[:frame_len]
        msg_id = raw[7] | (raw[8] << 8) | (raw[9] << 16)
        payload = raw[MAVLINK_V2_HEADER_LEN:MAVLINK_V2_HEADER_LEN + payload_len]
        return MAVLinkFrame(2, msg_id, raw[5], raw[6], payload)


# ===================================================================
# MAVLink Message Decoders
# ===================================================================

def decode_named_value_float(payload):
    """Decode NAMED_VALUE_FLOAT (msg 251).

    Payload layout (18 bytes):
        uint32  time_boot_ms
        char[10] name (null-padded)
        float   value
    """
    if len(payload) < 18:
        return None, None
    name = payload[4:14].split(b'\x00', 1)[0].decode('ascii', errors='replace')
    value = struct.unpack('<f', payload[14:18])[0]
    return name, value


def decode_named_value_int(payload):
    """Decode NAMED_VALUE_INT (msg 252).

    Payload layout (18 bytes):
        uint32  time_boot_ms
        char[10] name (null-padded)
        int32   value
    """
    if len(payload) < 18:
        return None, None
    name = payload[4:14].split(b'\x00', 1)[0].decode('ascii', errors='replace')
    value = struct.unpack('<i', payload[14:18])[0]
    return name, value


# ===================================================================
# Hydra Detection State
# ===================================================================

class HydraState:
    """Aggregated Hydra Detect telemetry state."""

    def __init__(self):
        self.fps = 0.0
        self.confidence = 0.0
        self.track_count = 0
        self.lock_status = 0  # 0=SEARCHING, 1=TRACKING, 2=LOCKED
        self.class_id = -1
        self.last_update = 0.0
        self.msg_count = 0
        self.heartbeat_count = 0
        self.source = "---"

    def update_from_mavlink(self, frame):
        """Update state from a parsed MAVLink frame."""
        if frame.msg_id == MSG_NAMED_VALUE_FLOAT:
            name, value = decode_named_value_float(frame.payload)
            if name == "HYD_FPS":
                self.fps = value
            elif name == "HYD_CONF":
                self.confidence = value
            else:
                return False
            self.last_update = time.monotonic()
            self.msg_count += 1
            return True

        elif frame.msg_id == MSG_NAMED_VALUE_INT:
            name, value = decode_named_value_int(frame.payload)
            if name == "HYD_TRK":
                self.track_count = value
            elif name == "HYD_LCK":
                self.lock_status = value
            elif name == "HYD_CLS":
                self.class_id = value
            else:
                return False
            self.last_update = time.monotonic()
            self.msg_count += 1
            return True

        elif frame.msg_id == MSG_HEARTBEAT:
            self.heartbeat_count += 1
            return True

        return False

    def update_from_api(self, data):
        """Update state from Hydra REST API JSON response."""
        self.fps = data.get("fps", 0.0)
        self.confidence = data.get("confidence", 0.0)
        self.track_count = data.get("track_count", 0)
        self.lock_status = data.get("lock_status", 0)
        self.class_id = data.get("class_id", -1)
        self.last_update = time.monotonic()
        self.msg_count += 1

    @property
    def stale(self):
        """True if no update received in last 3 seconds."""
        if self.last_update == 0:
            return True
        return (time.monotonic() - self.last_update) > 3.0

    @property
    def lock_name(self):
        return LOCK_STATUS.get(self.lock_status, "UNK(%d)" % self.lock_status)

    @property
    def lock_symbol(self):
        return LOCK_SYMBOLS.get(self.lock_status, "[?]")

    @property
    def class_name(self):
        return COCO_CLASSES.get(self.class_id, "class_%d" % self.class_id)

    @property
    def age_str(self):
        if self.last_update == 0:
            return "never"
        age = time.monotonic() - self.last_update
        if age < 1:
            return "<1s"
        return "%.0fs" % age


# ===================================================================
# Terminal Display
# ===================================================================

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
WHITE = "\033[37m"
CLEAR_SCREEN = "\033[2J"
HOME = "\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


def confidence_bar(pct, width=20):
    """Render a confidence percentage as a colored bar."""
    filled = int(pct / 100.0 * width)
    filled = max(0, min(width, filled))
    empty = width - filled

    if pct >= 70:
        color = GREEN
    elif pct >= 40:
        color = YELLOW
    else:
        color = RED

    bar = "%s%s%s%s%s" % (color, chr(9608) * filled, DIM, chr(9617) * empty, RESET)
    return bar


def lock_color(status):
    """Color code for lock status."""
    if status == 2:
        return GREEN
    elif status == 1:
        return YELLOW
    return RED


def render(state, mode_label):
    """Render the full display to terminal."""
    now_str = time.strftime("%H:%M:%S")
    if state.stale:
        stale_indicator = "%sSTALE%s" % (RED, RESET)
    else:
        stale_indicator = "%sLIVE%s" % (GREEN, RESET)
    lc = lock_color(state.lock_status)

    # Build display
    lines = []
    lines.append("%s%s" % (HOME, CLEAR_SCREEN))
    lines.append("%s%s+======================================+%s" % (BOLD, CYAN, RESET))
    lines.append("%s%s|%s   %s%sHYDRA DETECT%s  %s//  AX12 Display%s   %s%s|%s" % (
        BOLD, CYAN, RESET, BOLD, WHITE, RESET, DIM, RESET, BOLD, CYAN, RESET))
    lines.append("%s%s+======================================+%s" % (BOLD, CYAN, RESET))

    # Status row
    lines.append("%s%s|%s  Status: %s   Mode: %s%s%s" % (
        BOLD, CYAN, RESET, stale_indicator, DIM, mode_label, RESET))
    lines.append("%s%s|%s  Source: %s%s%s   Time: %s%s%s" % (
        BOLD, CYAN, RESET, DIM, state.source, RESET, DIM, now_str, RESET))
    lines.append("%s%s+--------------------------------------+%s" % (BOLD, CYAN, RESET))

    # Detection data
    lines.append("%s%s|%s" % (BOLD, CYAN, RESET))
    lines.append("%s%s|%s  %sFPS:%s        %s%6.1f%s f/s" % (
        BOLD, CYAN, RESET, BOLD, RESET, WHITE, state.fps, RESET))
    lines.append("%s%s|%s  %sTracks:%s     %s%6d%s" % (
        BOLD, CYAN, RESET, BOLD, RESET, WHITE, state.track_count, RESET))
    lines.append("%s%s|%s" % (BOLD, CYAN, RESET))

    # Lock status
    lines.append("%s%s|%s  %sLock:%s       %s%s %s%s" % (
        BOLD, CYAN, RESET, BOLD, RESET, lc, state.lock_symbol, state.lock_name, RESET))
    lines.append("%s%s|%s  %sTarget:%s     %s%s%s" % (
        BOLD, CYAN, RESET, BOLD, RESET, WHITE, state.class_name, RESET))
    lines.append("%s%s|%s" % (BOLD, CYAN, RESET))

    # Confidence with bar
    conf_str = "%5.1f%%" % state.confidence
    bar = confidence_bar(state.confidence)
    lines.append("%s%s|%s  %sConfidence:%s %s %s" % (
        BOLD, CYAN, RESET, BOLD, RESET, conf_str, bar))
    lines.append("%s%s|%s" % (BOLD, CYAN, RESET))
    lines.append("%s%s+--------------------------------------+%s" % (BOLD, CYAN, RESET))

    # Stats footer
    lines.append("%s%s|%s  Msgs: %s%d%s  HB: %s%d%s  Age: %s%s%s" % (
        BOLD, CYAN, RESET, DIM, state.msg_count, RESET,
        DIM, state.heartbeat_count, RESET, DIM, state.age_str, RESET))
    lines.append("%s%s+======================================+%s" % (BOLD, CYAN, RESET))
    lines.append("%s  Ctrl+C to exit%s" % (DIM, RESET))

    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()


# ===================================================================
# Data Sources
# ===================================================================

def run_listen(state, port):
    """Listen for MAVLink UDP packets on the given port."""
    state.source = "UDP:%d" % port
    parser = MAVLinkParser()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            for frame in parser.feed(data):
                state.update_from_mavlink(frame)
        except socket.timeout:
            pass
        render(state, "listen")
        time.sleep(0.1)


def run_api(state, host, port, interval):
    """Poll Hydra REST API for detection data."""
    base_url = "http://%s:%d/api" % (host, port)
    state.source = "API:%s:%d" % (host, port)

    while True:
        try:
            req = Request("%s/status" % base_url,
                          headers={"Accept": "application/json"})
            resp = urlopen(req, timeout=2)
            data = json.loads(resp.read().decode())
            state.update_from_api(data)
        except Exception:
            pass  # Don't crash on network errors, just show stale
        render(state, "api")
        time.sleep(interval)


def run_demo(state):
    """Generate synthetic Hydra Detect data for display testing."""
    state.source = "DEMO"
    t0 = time.monotonic()

    # Scenario phases: searching -> tracking -> locked -> lost -> repeat
    phases = [
        {"name": "searching", "duration": 4.0, "lock": 0, "tracks": 0,
         "cls": -1, "conf_range": (0, 10)},
        {"name": "acquiring", "duration": 3.0, "lock": 0, "tracks": 1,
         "cls": 0, "conf_range": (15, 40)},
        {"name": "tracking",  "duration": 5.0, "lock": 1, "tracks": 1,
         "cls": 0, "conf_range": (45, 70)},
        {"name": "locking",   "duration": 4.0, "lock": 1, "tracks": 2,
         "cls": 0, "conf_range": (70, 85)},
        {"name": "locked",    "duration": 6.0, "lock": 2, "tracks": 2,
         "cls": 0, "conf_range": (85, 97)},
        {"name": "vehicle",   "duration": 5.0, "lock": 2, "tracks": 3,
         "cls": 2, "conf_range": (80, 95)},
        {"name": "losing",    "duration": 3.0, "lock": 1, "tracks": 1,
         "cls": 2, "conf_range": (30, 55)},
        {"name": "lost",      "duration": 3.0, "lock": 0, "tracks": 0,
         "cls": -1, "conf_range": (0, 5)},
    ]

    cycle_duration = sum(p["duration"] for p in phases)

    while True:
        elapsed = time.monotonic() - t0
        cycle_pos = elapsed % cycle_duration

        # Find current phase
        acc = 0
        phase = phases[0]
        for p in phases:
            acc += p["duration"]
            if cycle_pos < acc:
                phase = p
                break

        # Simulate values with noise
        conf_lo, conf_hi = phase["conf_range"]
        base_conf = conf_lo + (conf_hi - conf_lo) * 0.5
        noise = random.gauss(0, (conf_hi - conf_lo) * 0.15)
        conf = max(0, min(100, base_conf + noise))

        # FPS varies with load
        base_fps = 15.0 if phase["tracks"] == 0 else 12.0 - phase["tracks"] * 0.8
        fps_noise = random.gauss(0, 0.5)
        fps = max(1.0, base_fps + fps_noise)

        state.fps = round(fps, 1)
        state.confidence = round(conf, 1)
        state.track_count = phase["tracks"]
        state.lock_status = phase["lock"]
        state.class_id = phase["cls"]
        state.last_update = time.monotonic()
        state.msg_count += 1

        render(state, "demo (%s)" % phase["name"])
        time.sleep(0.25)


# ===================================================================
# Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hydra Detect Display Client for AX12",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Modes:\n"
               "  listen   Passive MAVLink UDP listener (ELRS Backpack WiFi)\n"
               "  api      Poll Hydra REST API over Tailscale\n"
               "  demo     Synthetic data for testing the display\n"
    )
    sub = parser.add_subparsers(dest="mode")

    # listen mode
    p_listen = sub.add_parser("listen", help="MAVLink UDP listener")
    p_listen.add_argument("--port", type=int, default=14550,
                          help="UDP port to listen on (default: 14550)")

    # api mode
    p_api = sub.add_parser("api", help="Poll Hydra REST API")
    p_api.add_argument("--host", required=True,
                       help="Jetson IP (Tailscale or ELRS WiFi)")
    p_api.add_argument("--port", type=int, default=5000,
                       help="API port (default: 5000)")
    p_api.add_argument("--interval", type=float, default=0.5,
                       help="Poll interval in seconds (default: 0.5)")

    # demo mode
    sub.add_parser("demo", help="Synthetic test data")

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        sys.exit(1)

    state = HydraState()

    # Handle Ctrl+C gracefully
    def cleanup(sig, frame):
        sys.stdout.write("%s%s\n" % (SHOW_CURSOR, RESET))
        sys.stdout.flush()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    sys.stdout.write(HIDE_CURSOR)

    try:
        if args.mode == "listen":
            run_listen(state, args.port)
        elif args.mode == "api":
            run_api(state, args.host, args.port, args.interval)
        elif args.mode == "demo":
            run_demo(state)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("%s%s\n" % (SHOW_CURSOR, RESET))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
