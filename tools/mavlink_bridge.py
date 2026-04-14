#!/data/data/com.termux/files/usr/bin/python3
"""
MAVLink WiFi Passthrough Bridge for QGroundControl / Mission Planner

Bridges MAVLink between the ELRS Backpack WiFi (UDP 14550) and a local
TCP server (port 5760), enabling QGC/Mission Planner on the AX12 to
connect to the flight controller via the ELRS Backpack's MAVLink stream.

This is the tool that makes QGroundControl actually work on the AX12 -
the feature RadioMaster promised but never delivered.

Architecture:
    Vehicle -> ELRS TX -> Backpack WiFi AP (10.0.0.1:14550 UDP)
                           |
                   [mavlink_bridge.py]
                           |
                   TCP server :5760 <- QGC/Mission Planner

Modes:
    bridge  - UDP 14550 <-> TCP 5760 bidirectional passthrough
    monitor - passive MAVLink traffic display (no TCP server)
    serial  - /dev/ttyS1 serial <-> TCP 5760 bidirectional passthrough
    test    - synthetic heartbeats on TCP 5760 (verify QGC connects)

Usage:
    python3 tools/mavlink_bridge.py bridge                    # default
    python3 tools/mavlink_bridge.py bridge --udp-host 10.0.0.1
    python3 tools/mavlink_bridge.py monitor                   # sniff only
    python3 tools/mavlink_bridge.py serial --baud 460800      # serial mode
    python3 tools/mavlink_bridge.py test                      # synthetic data
    su 0 python3 tools/mavlink_bridge.py serial               # root for serial

Stdlib only. No pymavlink dependency.
"""

import argparse
import math
import os
import select
import signal
import socket
import struct
import sys
import threading
import time

try:
    import termios
except ImportError:
    termios = None


# ===================================================================
# MAVLink Constants
# ===================================================================

MAVLINK_V1_START = 0xFE
MAVLINK_V2_START = 0xFD

MAVLINK_V1_HEADER_LEN = 6
MAVLINK_V1_CRC_LEN = 2
MAVLINK_V2_HEADER_LEN = 10
MAVLINK_V2_CRC_LEN = 2

# Message IDs
MSG_HEARTBEAT = 0
MSG_SYS_STATUS = 1
MSG_GPS_RAW_INT = 24
MSG_ATTITUDE = 30
MSG_GLOBAL_POSITION_INT = 33
MSG_RC_CHANNELS = 65
MSG_VFR_HUD = 74
MSG_COMMAND_LONG = 76
MSG_COMMAND_ACK = 77
MSG_STATUSTEXT = 253
MSG_HOME_POSITION = 242
MSG_BATTERY_STATUS = 147

# CRC extras for checksum validation
CRC_EXTRA = {
    MSG_HEARTBEAT: 50,
    MSG_SYS_STATUS: 124,
    MSG_GPS_RAW_INT: 24,
    MSG_ATTITUDE: 39,
    MSG_GLOBAL_POSITION_INT: 104,
    MSG_RC_CHANNELS: 118,
    MSG_VFR_HUD: 20,
    MSG_COMMAND_LONG: 152,
    MSG_COMMAND_ACK: 143,
    MSG_STATUSTEXT: 83,
    MSG_HOME_POSITION: 104,
    MSG_BATTERY_STATUS: 154,
}

# Human-readable message names
MSG_NAMES = {
    MSG_HEARTBEAT: "HEARTBEAT",
    MSG_SYS_STATUS: "SYS_STATUS",
    MSG_GPS_RAW_INT: "GPS_RAW_INT",
    MSG_ATTITUDE: "ATTITUDE",
    MSG_GLOBAL_POSITION_INT: "GLOBAL_POSITION_INT",
    MSG_RC_CHANNELS: "RC_CHANNELS",
    MSG_VFR_HUD: "VFR_HUD",
    MSG_COMMAND_LONG: "COMMAND_LONG",
    MSG_COMMAND_ACK: "COMMAND_ACK",
    MSG_STATUSTEXT: "STATUSTEXT",
    MSG_HOME_POSITION: "HOME_POSITION",
    MSG_BATTERY_STATUS: "BATTERY_STATUS",
}

# ArduCopter custom_mode -> flight mode name
COPTER_MODES = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO",
    4: "GUIDED", 5: "LOITER", 6: "RTL", 7: "CIRCLE",
    9: "LAND", 11: "DRIFT", 13: "SPORT", 14: "FLIP",
    15: "AUTOTUNE", 16: "POSHOLD", 17: "BRAKE", 18: "THROW",
    19: "AVOID_ADSB", 20: "GUIDED_NOGPS", 21: "SMART_RTL",
    22: "FLOWHOLD", 23: "FOLLOW", 24: "ZIGZAG", 25: "SYSTEMID",
    26: "AUTOROTATE", 27: "AUTO_RTL",
}

# ArduPlane custom_mode -> flight mode name
PLANE_MODES = {
    0: "MANUAL", 1: "CIRCLE", 2: "STABILIZE", 3: "TRAINING",
    4: "ACRO", 5: "FBWA", 6: "FBWB", 7: "CRUISE",
    8: "AUTOTUNE", 10: "AUTO", 11: "RTL", 12: "LOITER",
    14: "AVOID_ADSB", 15: "GUIDED", 17: "QSTABILIZE",
    18: "QHOVER", 19: "QLOITER", 20: "QLAND", 21: "QRTL",
    22: "QAUTOTUNE", 23: "QACRO", 24: "THERMAL",
}

# ArduRover custom_mode -> flight mode name
ROVER_MODES = {
    0: "MANUAL", 1: "ACRO", 3: "STEERING", 4: "HOLD",
    5: "LOITER", 6: "FOLLOW", 7: "SIMPLE", 10: "AUTO",
    11: "RTL", 12: "SMART_RTL", 15: "GUIDED",
}

MAV_TYPE_NAMES = {
    0: "GENERIC", 1: "FIXED_WING", 2: "QUADROTOR", 3: "COAXIAL",
    4: "HELICOPTER", 5: "ANTENNA_TRACKER", 6: "GCS",
    10: "GROUND_ROVER", 11: "SURFACE_BOAT", 12: "SUBMARINE",
    13: "HEXAROTOR", 14: "OCTOROTOR", 15: "TRICOPTER",
    19: "VTOL_TILTROTOR", 20: "VTOL_FIXEDROTOR", 27: "DODECAROTOR",
}

MAV_STATE_NAMES = {
    0: "UNINIT", 1: "BOOT", 2: "CALIBRATING", 3: "STANDBY",
    4: "ACTIVE", 5: "CRITICAL", 6: "EMERGENCY", 7: "POWEROFF",
    8: "FLIGHT_TERMINATION",
}

MAV_AUTOPILOT_NAMES = {
    0: "GENERIC", 3: "ARDUPILOTMEGA", 4: "OPENPILOT", 8: "INVALID",
    12: "PX4", 14: "GENERIC_WAYPOINTS_ONLY",
}


# ===================================================================
# MAVLink Parser (from cot_bridge.py, extended)
# ===================================================================

class MAVLinkFrame:
    """Parsed MAVLink frame with raw bytes preserved for forwarding."""
    __slots__ = ('version', 'msg_id', 'sysid', 'compid', 'payload',
                 'seq', 'raw')

    def __init__(self, version, msg_id, sysid, compid, payload, seq, raw):
        self.version = version
        self.msg_id = msg_id
        self.sysid = sysid
        self.compid = compid
        self.payload = payload
        self.seq = seq
        self.raw = raw  # complete raw bytes for forwarding


class MAVLinkParser:
    """Incremental MAVLink v1/v2 frame parser.

    Feed raw bytes via feed(). Yields complete MAVLinkFrame objects.
    Preserves raw bytes for transparent forwarding.
    """

    def __init__(self):
        self._buf = bytearray()
        self.bytes_parsed = 0
        self.frames_parsed = 0
        self.sync_errors = 0

    def feed(self, data):
        """Feed raw bytes; yield parsed MAVLinkFrame objects."""
        self._buf.extend(data)
        self.bytes_parsed += len(data)

        while True:
            v1 = self._find_byte(MAVLINK_V1_START)
            v2 = self._find_byte(MAVLINK_V2_START)

            if v1 < 0 and v2 < 0:
                if len(self._buf) > 1:
                    self._buf = self._buf[-1:]
                return

            if v1 < 0:
                start_pos = v2
            elif v2 < 0:
                start_pos = v1
            else:
                start_pos = min(v1, v2)

            if start_pos > 0:
                self.sync_errors += start_pos
                del self._buf[:start_pos]

            if self._buf[0] == MAVLINK_V1_START:
                frame = self._try_parse_v1()
            else:
                frame = self._try_parse_v2()

            if frame is None:
                return
            self.frames_parsed += 1
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
        return MAVLinkFrame(
            version=1,
            msg_id=raw[5],
            sysid=raw[3],
            compid=raw[4],
            payload=raw[MAVLINK_V1_HEADER_LEN:MAVLINK_V1_HEADER_LEN + payload_len],
            seq=raw[2],
            raw=raw,
        )

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
        return MAVLinkFrame(
            version=2,
            msg_id=msg_id,
            sysid=raw[5],
            compid=raw[6],
            payload=raw[MAVLINK_V2_HEADER_LEN:MAVLINK_V2_HEADER_LEN + payload_len],
            seq=raw[4],
            raw=raw,
        )


# ===================================================================
# MAVLink Message Decoders
# ===================================================================

def decode_heartbeat(payload):
    """Decode HEARTBEAT (msg 0). Returns dict or None."""
    if len(payload) < 9:
        return None
    custom_mode, mav_type, autopilot, base_mode, status, mav_ver = \
        struct.unpack('<IBBBBB', payload[:9])
    armed = bool(base_mode & 0x80)

    # Select mode table based on vehicle type
    if mav_type in (1,):
        mode_name = PLANE_MODES.get(custom_mode, "MODE_%d" % custom_mode)
    elif mav_type in (10, 11):
        mode_name = ROVER_MODES.get(custom_mode, "MODE_%d" % custom_mode)
    else:
        mode_name = COPTER_MODES.get(custom_mode, "MODE_%d" % custom_mode)

    return {
        'custom_mode': custom_mode,
        'mav_type': mav_type,
        'mav_type_name': MAV_TYPE_NAMES.get(mav_type, "TYPE_%d" % mav_type),
        'autopilot': MAV_AUTOPILOT_NAMES.get(autopilot, "AP_%d" % autopilot),
        'base_mode': base_mode,
        'armed': armed,
        'flight_mode': mode_name,
        'system_status': status,
        'status_name': MAV_STATE_NAMES.get(status, "STATE_%d" % status),
        'mav_version': mav_ver,
    }


def decode_global_position_int(payload):
    """Decode GLOBAL_POSITION_INT (msg 33). Returns dict or None."""
    if len(payload) < 28:
        return None
    fields = struct.unpack('<IiiiihhhH', payload[:28])
    time_boot_ms, lat, lon, alt, rel_alt, vx, vy, vz, hdg = fields
    gs = (vx ** 2 + vy ** 2) ** 0.5 / 100.0
    return {
        'lat': lat / 1e7,
        'lon': lon / 1e7,
        'alt_msl': alt / 1000.0,
        'alt_agl': rel_alt / 1000.0,
        'groundspeed': gs,
        'heading': hdg / 100.0 if hdg != 0xFFFF else 0.0,
        'vz': vz / 100.0,
    }


def decode_sys_status(payload):
    """Decode SYS_STATUS (msg 1). Returns dict or None.

    Layout (32 bytes):
        uint32 onboard_control_sensors_present   [0]
        uint32 onboard_control_sensors_enabled   [1]
        uint32 onboard_control_sensors_health    [2]
        uint16 load                              [3]
        uint16 voltage_battery (mV)              [4]
        int16  current_battery (cA)              [5]
        int8   battery_remaining (%)             -- see note
        ...
    Note: MAVLink SYS_STATUS has battery_remaining as int8 after
    current_battery. We use a simplified unpack for the fields we need.
    """
    if len(payload) < 18:
        return None
    # Unpack just the fields we need: 3xI + H + H + h = 18 bytes
    fields = struct.unpack('<IIIHHh', payload[:18])
    battery_remaining = -1
    if len(payload) >= 19:
        battery_remaining = struct.unpack('b', payload[18:19])[0]
    return {
        'voltage_battery': fields[4] / 1000.0,  # mV -> V
        'current_battery': fields[5] / 100.0,    # cA -> A
        'battery_remaining': battery_remaining,   # %
    }


def decode_gps_raw_int(payload):
    """Decode GPS_RAW_INT (msg 24). Returns dict or None."""
    if len(payload) < 30:
        return None
    fields = struct.unpack('<QiiiHHBBBB', payload[:30])
    return {
        'fix_type': fields[6],
        'satellites_visible': fields[7],
        'lat': fields[1] / 1e7,
        'lon': fields[2] / 1e7,
        'alt': fields[3] / 1000.0,
        'hdop': fields[4] / 100.0,
        'vdop': fields[5] / 100.0,
    }


def decode_vfr_hud(payload):
    """Decode VFR_HUD (msg 74). Returns dict or None."""
    if len(payload) < 20:
        return None
    fields = struct.unpack('<ffffhH', payload[:20])
    return {
        'airspeed': fields[0],
        'groundspeed': fields[1],
        'heading': fields[2],
        'throttle': fields[3],
        'alt': fields[4],
        'climb': fields[5] / 100.0,
    }


def decode_attitude(payload):
    """Decode ATTITUDE (msg 30). Returns dict or None."""
    if len(payload) < 28:
        return None
    fields = struct.unpack('<Iffffff', payload[:28])
    return {
        'roll': math.degrees(fields[1]),
        'pitch': math.degrees(fields[2]),
        'yaw': math.degrees(fields[3]),
    }


def decode_statustext(payload):
    """Decode STATUSTEXT (msg 253). Returns dict or None."""
    if len(payload) < 2:
        return None
    severity = payload[0]
    text = payload[1:51]  # max 50 chars
    try:
        text = text.split(b'\x00', 1)[0].decode('utf-8', errors='replace')
    except Exception:
        text = str(text)
    severity_names = {0: "EMERGENCY", 1: "ALERT", 2: "CRITICAL", 3: "ERROR",
                      4: "WARNING", 5: "NOTICE", 6: "INFO", 7: "DEBUG"}
    return {
        'severity': severity,
        'severity_name': severity_names.get(severity, "SEV_%d" % severity),
        'text': text,
    }


DECODERS = {
    MSG_HEARTBEAT: decode_heartbeat,
    MSG_GLOBAL_POSITION_INT: decode_global_position_int,
    MSG_SYS_STATUS: decode_sys_status,
    MSG_GPS_RAW_INT: decode_gps_raw_int,
    MSG_VFR_HUD: decode_vfr_hud,
    MSG_ATTITUDE: decode_attitude,
    MSG_STATUSTEXT: decode_statustext,
}


# ===================================================================
# MAVLink Packet Builder (for test mode synthetic data)
# ===================================================================

class MAVLinkBuilder:
    """Build MAVLink v2 packets for synthetic test data."""

    def __init__(self, sysid=1, compid=1):
        self.sysid = sysid
        self.compid = compid
        self.seq = 0

    def _crc_accumulate(self, data, crc=0xFFFF):
        """X.25 CRC-16 accumulate."""
        for byte in data:
            tmp = byte ^ (crc & 0xFF)
            tmp ^= (tmp << 4) & 0xFF
            crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)
            crc &= 0xFFFF
        return crc

    def build_v2(self, msg_id, payload):
        """Build a complete MAVLink v2 frame."""
        payload_len = len(payload)
        header = struct.pack('<BBBBBBBHB',
                             MAVLINK_V2_START,
                             payload_len,
                             0,  # incompat_flags
                             0,  # compat_flags
                             self.seq & 0xFF,
                             self.sysid,
                             self.compid,
                             msg_id & 0xFFFF,
                             (msg_id >> 16) & 0xFF)
        self.seq += 1

        # CRC over everything except start byte
        crc_data = header[1:] + payload
        crc_extra = CRC_EXTRA.get(msg_id, 0)
        crc = self._crc_accumulate(crc_data)
        crc = self._crc_accumulate(bytes([crc_extra]), crc)

        return header + payload + struct.pack('<H', crc)

    def heartbeat(self, custom_mode=0, mav_type=2, autopilot=3,
                  base_mode=0x80 | 0x10, system_status=4, mav_version=3):
        """Build a HEARTBEAT message."""
        payload = struct.pack('<IBBBBB',
                              custom_mode, mav_type, autopilot,
                              base_mode, system_status, mav_version)
        return self.build_v2(MSG_HEARTBEAT, payload)

    def global_position_int(self, lat, lon, alt_msl, alt_agl,
                             heading=0.0, gs=0.0, vz=0.0):
        """Build a GLOBAL_POSITION_INT message."""
        time_boot = int(time.monotonic() * 1000) & 0xFFFFFFFF
        hdg = int(heading * 100) if heading >= 0 else 0xFFFF
        vx = int(gs * 100 * math.cos(math.radians(heading)))
        vy = int(gs * 100 * math.sin(math.radians(heading)))
        payload = struct.pack('<IiiiihhhH',
                              time_boot,
                              int(lat * 1e7),
                              int(lon * 1e7),
                              int(alt_msl * 1000),
                              int(alt_agl * 1000),
                              vx, vy, int(vz * 100), hdg)
        return self.build_v2(MSG_GLOBAL_POSITION_INT, payload)

    def sys_status(self, voltage=12.6, current=5.0, remaining=75):
        """Build a SYS_STATUS message.

        Layout: 3xI + H + H + h + b + 5xH + h + H = 31 bytes
        """
        payload = struct.pack('<IIIHHhbHHHHHhH',
                              0x0003FFFF,  # onboard sensors present
                              0x0003FFFF,  # onboard sensors enabled
                              0x0003FFFF,  # onboard sensors health
                              500,         # load (0.5%)
                              int(voltage * 1000),  # voltage mV
                              int(current * 100),   # current cA
                              remaining,             # battery remaining %
                              0, 0, 0, 0, 0, 0, 0)
        return self.build_v2(MSG_SYS_STATUS, payload)

    def vfr_hud(self, airspeed=0.0, groundspeed=0.0, heading=0,
                throttle=0, alt=0.0, climb=0.0):
        """Build a VFR_HUD message."""
        payload = struct.pack('<ffffhH',
                              airspeed, groundspeed, float(heading),
                              float(throttle),
                              int(alt), int(climb * 100))
        return self.build_v2(MSG_VFR_HUD, payload)

    def gps_raw_int(self, lat, lon, alt, fix_type=3, sats=12):
        """Build a GPS_RAW_INT message."""
        payload = struct.pack('<QiiiHHBBBB',
                              int(time.time() * 1e6),  # usec
                              int(lat * 1e7),
                              int(lon * 1e7),
                              int(alt * 1000),
                              120,   # eph (HDOP * 100)
                              120,   # epv (VDOP * 100)
                              fix_type,
                              sats,
                              0, 0)
        return self.build_v2(MSG_GPS_RAW_INT, payload)

    def attitude(self, roll=0.0, pitch=0.0, yaw=0.0):
        """Build an ATTITUDE message."""
        payload = struct.pack('<Iffffff',
                              int(time.monotonic() * 1000) & 0xFFFFFFFF,
                              math.radians(roll),
                              math.radians(pitch),
                              math.radians(yaw),
                              0.0, 0.0, 0.0)
        return self.build_v2(MSG_ATTITUDE, payload)


# ===================================================================
# Serial Port (reused from cot_bridge.py)
# ===================================================================

def open_serial(port, baudrate):
    """Open serial port with raw termios. Returns fd."""
    if termios is None:
        raise RuntimeError("termios not available")
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    baud_map = {
        9600: termios.B9600, 19200: termios.B19200,
        38400: termios.B38400, 57600: termios.B57600,
        115200: termios.B115200, 230400: termios.B230400,
        460800: termios.B460800, 921600: termios.B921600,
    }
    speed = baud_map.get(baudrate)
    if speed is None:
        os.close(fd)
        raise ValueError("Unsupported baudrate: %d" % baudrate)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL | speed
    attrs[3] = 0
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    attrs[4] = speed
    attrs[5] = speed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


# ===================================================================
# Display / Statistics
# ===================================================================

class Stats:
    """Track message rates and vehicle state for display."""

    def __init__(self):
        self.lock = threading.Lock()
        self.msg_counts = {}       # msg_id -> count
        self.msg_rates = {}        # msg_id -> msgs/sec
        self.last_rate_time = time.monotonic()
        self.last_rate_counts = {}
        self.total_bytes_in = 0
        self.total_bytes_out = 0
        self.total_frames = 0
        self.tcp_clients = 0
        self.uptime_start = time.monotonic()

        # Vehicle state
        self.heartbeat = None
        self.position = None
        self.sys_status = None
        self.gps = None
        self.attitude = None
        self.vfr_hud = None
        self.last_statustext = None

    def record_frame(self, frame, direction='in'):
        """Record a parsed frame for statistics."""
        with self.lock:
            self.total_frames += 1
            mid = frame.msg_id
            self.msg_counts[mid] = self.msg_counts.get(mid, 0) + 1

            if direction == 'in':
                self.total_bytes_in += len(frame.raw)
            else:
                self.total_bytes_out += len(frame.raw)

            # Decode known messages for state tracking
            decoder = DECODERS.get(mid)
            if decoder:
                decoded = decoder(frame.payload)
                if decoded:
                    if mid == MSG_HEARTBEAT and decoded.get('mav_type', 0) != 6:
                        self.heartbeat = decoded
                    elif mid == MSG_GLOBAL_POSITION_INT:
                        self.position = decoded
                    elif mid == MSG_SYS_STATUS:
                        self.sys_status = decoded
                    elif mid == MSG_GPS_RAW_INT:
                        self.gps = decoded
                    elif mid == MSG_ATTITUDE:
                        self.attitude = decoded
                    elif mid == MSG_VFR_HUD:
                        self.vfr_hud = decoded
                    elif mid == MSG_STATUSTEXT:
                        self.last_statustext = decoded

    def update_rates(self):
        """Calculate per-message rates. Call once per second."""
        now = time.monotonic()
        dt = now - self.last_rate_time
        if dt < 0.5:
            return
        with self.lock:
            for mid, count in self.msg_counts.items():
                prev = self.last_rate_counts.get(mid, 0)
                self.msg_rates[mid] = (count - prev) / dt
            self.last_rate_counts = dict(self.msg_counts)
            self.last_rate_time = now

    def format_display(self):
        """Format a multi-line status display."""
        with self.lock:
            uptime = time.monotonic() - self.uptime_start
            lines = []
            lines.append("")
            lines.append("=" * 60)
            lines.append("  MAVLink Bridge Status")
            lines.append("=" * 60)

            # Uptime and throughput
            mins, secs = divmod(int(uptime), 60)
            hrs, mins = divmod(mins, 60)
            lines.append("  Uptime: %02d:%02d:%02d  |  Frames: %d  |  TCP clients: %d" %
                         (hrs, mins, secs, self.total_frames, self.tcp_clients))
            bps_in = self.total_bytes_in / max(uptime, 1)
            bps_out = self.total_bytes_out / max(uptime, 1)
            lines.append("  Bytes in: {:,} ({:.0f} B/s)  |  Bytes out: {:,} ({:.0f} B/s)".format(
                         self.total_bytes_in, bps_in, self.total_bytes_out, bps_out))
            lines.append("-" * 60)

            # Heartbeat info
            hb = self.heartbeat
            if hb:
                armed_str = "ARMED" if hb['armed'] else "DISARMED"
                lines.append("  Vehicle: %s  |  %s  |  %s" %
                             (hb['mav_type_name'], hb['autopilot'], armed_str))
                lines.append("  Mode: %s  |  Status: %s" %
                             (hb['flight_mode'], hb['status_name']))
            else:
                lines.append("  Vehicle: waiting for heartbeat...")

            # Position
            pos = self.position
            if pos:
                lines.append("  Pos: %.6f, %.6f  |  Alt: %.1fm MSL / %.1fm AGL" %
                             (pos['lat'], pos['lon'], pos['alt_msl'], pos['alt_agl']))
                lines.append("  GS: %.1f m/s  |  Hdg: %.0f deg  |  Vz: %.1f m/s" %
                             (pos['groundspeed'], pos['heading'], pos['vz']))

            # GPS
            gps = self.gps
            if gps:
                fix_names = {0: "No GPS", 1: "No Fix", 2: "2D", 3: "3D",
                             4: "DGPS", 5: "RTK Float", 6: "RTK Fixed"}
                fix = fix_names.get(gps['fix_type'], "Fix=%d" % gps['fix_type'])
                lines.append("  GPS: %s  |  Sats: %d  |  HDOP: %.1f" %
                             (fix, gps['satellites_visible'], gps['hdop']))

            # Battery
            ss = self.sys_status
            if ss:
                lines.append("  Batt: %.1fV  |  %.1fA  |  %d%%" %
                             (ss['voltage_battery'], ss['current_battery'],
                              ss['battery_remaining']))

            # Attitude
            att = self.attitude
            if att:
                lines.append("  Att: R=%.1f  P=%.1f  Y=%.1f" %
                             (att['roll'], att['pitch'], att['yaw']))

            # VFR HUD
            vfr = self.vfr_hud
            if vfr:
                lines.append("  HUD: AS=%.1f  GS=%.1f  Thr=%.0f%%" %
                             (vfr['airspeed'], vfr['groundspeed'], vfr['throttle']))

            # Status text
            st = self.last_statustext
            if st:
                lines.append("  Msg: [%s] %s" % (st['severity_name'], st['text']))

            lines.append("-" * 60)

            # Message rates table
            lines.append("  Message Rates:")
            sorted_msgs = sorted(self.msg_rates.items(),
                                 key=lambda x: x[1], reverse=True)
            for mid, rate in sorted_msgs:
                if rate > 0.01:
                    name = MSG_NAMES.get(mid, "MSG_%d" % mid)
                    count = self.msg_counts.get(mid, 0)
                    lines.append("    %-30s %6.1f Hz  (%s total)" %
                                 (name, rate, "{:,}".format(count)))

            lines.append("=" * 60)
            return "\n".join(lines)


# ===================================================================
# TCP Server for QGC/Mission Planner
# ===================================================================

class TCPServer:
    """Multi-client TCP server for GCS connections.

    Accepts connections on a given port and manages bidirectional data flow.
    Thread-safe client list for concurrent read/write.
    """

    def __init__(self, host, port, stats, on_client_data=None):
        self.host = host
        self.port = port
        self.stats = stats
        self.on_client_data = on_client_data  # callback(data: bytes)
        self.server_sock = None
        self.clients = []  # list of socket objects
        self.clients_lock = threading.Lock()
        self.running = False

    def start(self):
        """Start the TCP server in a background thread."""
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.settimeout(1.0)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(5)
        self.running = True

        t = threading.Thread(target=self._accept_loop, daemon=True,
                             name="tcp-accept")
        t.start()
        print("[bridge] TCP server listening on %s:%d" % (self.host, self.port))

    def stop(self):
        """Stop server and close all clients."""
        self.running = False
        with self.clients_lock:
            for c in self.clients:
                try:
                    c.close()
                except Exception:
                    pass
            self.clients.clear()
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

    def send_to_all(self, data):
        """Send data to all connected TCP clients."""
        with self.clients_lock:
            dead = []
            for c in self.clients:
                try:
                    c.sendall(data)
                except (OSError, BrokenPipeError):
                    dead.append(c)
            for c in dead:
                self._remove_client(c)

    def _accept_loop(self):
        """Accept incoming TCP connections."""
        while self.running:
            try:
                client_sock, addr = self.server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            client_sock.settimeout(0.5)
            client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            with self.clients_lock:
                self.clients.append(client_sock)
                self.stats.tcp_clients = len(self.clients)

            print("[bridge] TCP client connected: %s:%d (%d total)" %
                  (addr[0], addr[1], self.stats.tcp_clients))

            # Start a reader thread for this client (GCS -> vehicle)
            t = threading.Thread(target=self._client_reader,
                                 args=(client_sock, addr),
                                 daemon=True,
                                 name="tcp-read-%s:%d" % (addr[0], addr[1]))
            t.start()

    def _client_reader(self, sock, addr):
        """Read data from a TCP client (GCS commands) and forward upstream."""
        while self.running:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                self.stats.total_bytes_out += len(data)
                if self.on_client_data:
                    self.on_client_data(data)
            except socket.timeout:
                continue
            except (OSError, ConnectionResetError):
                break

        self._remove_client(sock)
        print("[bridge] TCP client disconnected: %s:%d (%d total)" %
              (addr[0], addr[1], self.stats.tcp_clients))

    def _remove_client(self, sock):
        """Remove a client socket from the list."""
        with self.clients_lock:
            if sock in self.clients:
                self.clients.remove(sock)
                self.stats.tcp_clients = len(self.clients)
            try:
                sock.close()
            except Exception:
                pass


# ===================================================================
# Bridge Mode: UDP <-> TCP
# ===================================================================

class BridgeMode:
    """Bridge MAVLink between UDP (ELRS Backpack) and TCP (QGC)."""

    def __init__(self, udp_host, udp_port, tcp_host, tcp_port,
                 display_interval):
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.display_interval = display_interval
        self.running = False
        self.stats = Stats()
        self.parser = MAVLinkParser()

        # UDP socket for ELRS Backpack
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_sock.settimeout(1.0)
        self.udp_remote = None  # will be set when we get first UDP packet

        # TCP server for QGC
        self.tcp_server = TCPServer(tcp_host, tcp_port, self.stats,
                                    on_client_data=self._tcp_to_udp)

    def _tcp_to_udp(self, data):
        """Forward GCS TCP data back to vehicle via UDP."""
        if self.udp_remote:
            try:
                self.udp_sock.sendto(data, self.udp_remote)
            except OSError as e:
                print("[bridge] UDP send error: %s" % e)

    def run(self):
        """Main bridge loop."""
        self.running = True
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

        # Bind UDP to receive from Backpack
        self.udp_sock.bind(('0.0.0.0', self.udp_port))
        print("[bridge] UDP listening on 0.0.0.0:%d" % self.udp_port)
        print("[bridge] Expecting ELRS Backpack at %s" % self.udp_host)
        print("[bridge] Ctrl+C to stop")
        print()

        self.tcp_server.start()
        last_display = 0

        try:
            while self.running:
                # Read UDP data
                try:
                    data, addr = self.udp_sock.recvfrom(4096)
                except socket.timeout:
                    data = None
                    addr = None
                except OSError:
                    break

                if data:
                    # Track remote for bidirectional forwarding
                    self.udp_remote = addr

                    # Parse for stats/display
                    for frame in self.parser.feed(data):
                        self.stats.record_frame(frame, 'in')

                    # Forward raw UDP data to all TCP clients
                    self.tcp_server.send_to_all(data)

                # Periodic display
                now = time.monotonic()
                if now - last_display >= self.display_interval:
                    self.stats.update_rates()
                    sys.stdout.write(self.stats.format_display())
                    sys.stdout.flush()
                    last_display = now
        finally:
            self.tcp_server.stop()
            self.udp_sock.close()
            print("\n[bridge] Shutdown. %d frames bridged." % self.stats.total_frames)

    def _signal(self, signum, frame):
        print("\n[bridge] Signal %d, shutting down..." % signum)
        self.running = False


# ===================================================================
# Monitor Mode: Passive traffic display
# ===================================================================

class MonitorMode:
    """Passively monitor MAVLink traffic on UDP."""

    def __init__(self, udp_host, udp_port, display_interval, verbose):
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.display_interval = display_interval
        self.verbose = verbose
        self.running = False
        self.stats = Stats()
        self.parser = MAVLinkParser()

    def run(self):
        self.running = True
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        sock.bind(('0.0.0.0', self.udp_port))

        print("[monitor] Listening on UDP 0.0.0.0:%d" % self.udp_port)
        print("[monitor] Ctrl+C to stop")
        print()

        last_display = 0

        try:
            while self.running:
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    data = None
                except OSError:
                    break

                if data:
                    for frame in self.parser.feed(data):
                        self.stats.record_frame(frame, 'in')
                        if self.verbose:
                            self._print_frame(frame)

                now = time.monotonic()
                if now - last_display >= self.display_interval:
                    self.stats.update_rates()
                    if not self.verbose:
                        sys.stdout.write(self.stats.format_display())
                        sys.stdout.flush()
                    last_display = now
        finally:
            sock.close()
            print("\n[monitor] Done. %d frames seen." % self.stats.total_frames)

    def _print_frame(self, frame):
        """Print a single frame in verbose mode."""
        name = MSG_NAMES.get(frame.msg_id, "MSG_%d" % frame.msg_id)
        decoder = DECODERS.get(frame.msg_id)
        decoded = decoder(frame.payload) if decoder else None
        ts = time.strftime("%H:%M:%S")

        if decoded:
            if frame.msg_id == MSG_HEARTBEAT:
                d = decoded
                arm = "ARMED" if d['armed'] else "DISARMED"
                print("  %s [%d/%d] %s  %s %s %s" %
                      (ts, frame.sysid, frame.compid, name,
                       d['mav_type_name'], d['flight_mode'], arm))
            elif frame.msg_id == MSG_GLOBAL_POSITION_INT:
                d = decoded
                print("  %s [%d/%d] %s  %.6f,%.6f  alt=%.1fm  gs=%.1fm/s" %
                      (ts, frame.sysid, frame.compid, name,
                       d['lat'], d['lon'], d['alt_msl'], d['groundspeed']))
            elif frame.msg_id == MSG_STATUSTEXT:
                d = decoded
                print("  %s [%d/%d] %s  [%s] %s" %
                      (ts, frame.sysid, frame.compid, name,
                       d['severity_name'], d['text']))
            else:
                items = " ".join("%s=%s" % (k, v) for k, v in decoded.items()
                                 if not isinstance(v, str) or len(v) < 20)
                print("  %s [%d/%d] %s  %s" %
                      (ts, frame.sysid, frame.compid, name, items))
        else:
            print("  %s [%d/%d] %s  (%dB)" %
                  (ts, frame.sysid, frame.compid, name, len(frame.payload)))

    def _signal(self, signum, frame):
        self.running = False


# ===================================================================
# Serial Mode: /dev/ttyS1 <-> TCP
# ===================================================================

class SerialMode:
    """Bridge serial MAVLink (/dev/ttyS1) to TCP for QGC."""

    def __init__(self, serial_port, baudrate, tcp_host, tcp_port,
                 display_interval):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.display_interval = display_interval
        self.running = False
        self.stats = Stats()
        self.parser = MAVLinkParser()
        self.serial_fd = -1

        self.tcp_server = TCPServer(tcp_host, tcp_port, self.stats,
                                    on_client_data=self._tcp_to_serial)

    def _tcp_to_serial(self, data):
        """Forward GCS TCP data to serial port."""
        if self.serial_fd >= 0:
            try:
                os.write(self.serial_fd, data)
            except OSError as e:
                print("[serial] Write error: %s" % e)

    def run(self):
        self.running = True
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

        try:
            self.serial_fd = open_serial(self.serial_port, self.baudrate)
            print("[serial] Opened %s at %d baud" %
                  (self.serial_port, self.baudrate))
        except (OSError, RuntimeError) as e:
            print("[serial] Failed to open %s: %s" % (self.serial_port, e))
            print("[serial] Try: su 0 python3 tools/mavlink_bridge.py serial")
            return

        self.tcp_server.start()
        last_display = 0

        try:
            while self.running:
                try:
                    readable, _, _ = select.select([self.serial_fd], [], [], 0.2)
                except (OSError, ValueError):
                    break

                if readable:
                    try:
                        data = os.read(self.serial_fd, 4096)
                    except OSError:
                        data = b''
                    if data:
                        for frame in self.parser.feed(data):
                            self.stats.record_frame(frame, 'in')
                        self.tcp_server.send_to_all(data)

                now = time.monotonic()
                if now - last_display >= self.display_interval:
                    self.stats.update_rates()
                    sys.stdout.write(self.stats.format_display())
                    sys.stdout.flush()
                    last_display = now
        finally:
            self.tcp_server.stop()
            if self.serial_fd >= 0:
                os.close(self.serial_fd)
            print("\n[serial] Shutdown. %d frames bridged." % self.stats.total_frames)

    def _signal(self, signum, frame):
        self.running = False


# ===================================================================
# Test Mode: Synthetic MAVLink on TCP
# ===================================================================

class TestMode:
    """Generate synthetic MAVLink data and serve via TCP.

    Simulates a quadcopter in LOITER mode orbiting a point, so QGC
    can connect and display a moving vehicle. Validates the full pipeline
    without requiring an actual vehicle or ELRS Backpack.
    """

    def __init__(self, tcp_host, tcp_port, display_interval, duration):
        self.display_interval = display_interval
        self.duration = duration
        self.running = False
        self.stats = Stats()
        self.parser = MAVLinkParser()
        self.builder = MAVLinkBuilder(sysid=1, compid=1)
        self.tcp_server = TCPServer(tcp_host, tcp_port, self.stats,
                                    on_client_data=self._handle_gcs_data)
        self.gcs_parser = MAVLinkParser()

    def _handle_gcs_data(self, data):
        """Parse GCS commands for display purposes."""
        for frame in self.gcs_parser.feed(data):
            name = MSG_NAMES.get(frame.msg_id, "MSG_%d" % frame.msg_id)
            print("[test] GCS -> Vehicle: %s (sysid=%d)" % (name, frame.sysid))

    def run(self):
        self.running = True
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

        # Synthetic orbit parameters
        # Fort Bragg / Camp Mackall area -- near Camp Mackall, NC
        center_lat = 35.1395
        center_lon = -79.0064
        orbit_radius = 0.002  # ~220m
        orbit_period = 120.0  # seconds
        base_alt = 50.0

        self.tcp_server.start()

        print("[test] Generating synthetic MAVLink data")
        print("[test] Orbit center: %s, %s" % (center_lat, center_lon))
        print("[test] Connect QGC/Mission Planner to TCP 127.0.0.1:%d" %
              self.tcp_server.port)
        if self.duration > 0:
            print("[test] Running for %ds" % self.duration)
        print("[test] Ctrl+C to stop")
        print()

        t0 = time.monotonic()
        last_display = 0
        hb_interval = 1.0       # heartbeat at 1 Hz
        pos_interval = 0.2      # position at 5 Hz
        status_interval = 1.0   # sys_status at 1 Hz
        att_interval = 0.1      # attitude at 10 Hz

        next_hb = t0
        next_pos = t0
        next_status = t0
        next_att = t0

        try:
            while self.running:
                now = time.monotonic()
                elapsed = now - t0

                if self.duration > 0 and elapsed > self.duration:
                    print("\n[test] Duration %ds reached." % self.duration)
                    break

                # Orbit math
                angle = (elapsed / orbit_period) * 2 * math.pi
                lat = center_lat + orbit_radius * math.sin(angle)
                lon = center_lon + orbit_radius * math.cos(angle)
                alt = base_alt + 5.0 * math.sin(elapsed / 10.0)
                heading = math.degrees(angle + math.pi / 2) % 360
                gs = 2 * math.pi * orbit_radius * 111000 / orbit_period

                data_out = bytearray()

                # Heartbeat at 1 Hz
                if now >= next_hb:
                    pkt = self.builder.heartbeat(
                        custom_mode=5,  # LOITER
                        mav_type=2,     # QUADROTOR
                        base_mode=0x80 | 0x10 | 0x04,  # armed + custom + guided
                    )
                    data_out.extend(pkt)
                    next_hb = now + hb_interval

                # Position at 5 Hz
                if now >= next_pos:
                    pkt = self.builder.global_position_int(
                        lat=lat, lon=lon,
                        alt_msl=alt, alt_agl=alt,
                        heading=heading, gs=gs,
                    )
                    data_out.extend(pkt)

                    pkt2 = self.builder.gps_raw_int(
                        lat=lat, lon=lon, alt=alt,
                        fix_type=3, sats=14,
                    )
                    data_out.extend(pkt2)

                    pkt3 = self.builder.vfr_hud(
                        groundspeed=gs, airspeed=gs,
                        heading=int(heading),
                        throttle=45,
                        alt=alt, climb=0.5 * math.cos(elapsed / 10.0),
                    )
                    data_out.extend(pkt3)
                    next_pos = now + pos_interval

                # SYS_STATUS at 1 Hz
                if now >= next_status:
                    drain = elapsed / 600.0  # drain over 10 minutes
                    voltage = 12.6 - drain * 1.0
                    remaining = max(0, int(100 - drain * 100))
                    pkt = self.builder.sys_status(
                        voltage=voltage,
                        current=12.0,
                        remaining=remaining,
                    )
                    data_out.extend(pkt)
                    next_status = now + status_interval

                # Attitude at 10 Hz
                if now >= next_att:
                    roll = 5.0 * math.sin(elapsed / 3.0)
                    pitch = 3.0 * math.cos(elapsed / 4.0)
                    pkt = self.builder.attitude(
                        roll=roll, pitch=pitch, yaw=heading,
                    )
                    data_out.extend(pkt)
                    next_att = now + att_interval

                # Send to TCP clients and parse for stats
                if data_out:
                    raw = bytes(data_out)
                    self.tcp_server.send_to_all(raw)
                    for frame in self.parser.feed(raw):
                        self.stats.record_frame(frame, 'out')

                # Display
                if now - last_display >= self.display_interval:
                    self.stats.update_rates()
                    sys.stdout.write(self.stats.format_display())
                    sys.stdout.flush()
                    last_display = now

                # Sleep to next event
                next_event = min(next_hb, next_pos, next_status, next_att)
                sleep_time = max(0, next_event - time.monotonic())
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 0.05))
        finally:
            self.tcp_server.stop()
            print("[test] Shutdown complete.")

    def _signal(self, signum, frame):
        self.running = False


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        prog='mavlink_bridge',
        description='MAVLink WiFi passthrough bridge for QGroundControl',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 tools/mavlink_bridge.py bridge\n"
            "      Bridge ELRS Backpack UDP 14550 to TCP 5760 for QGC\n"
            "\n"
            "  python3 tools/mavlink_bridge.py bridge --udp-host 10.0.0.1\n"
            "      Specify Backpack IP explicitly\n"
            "\n"
            "  python3 tools/mavlink_bridge.py monitor\n"
            "      Passively display MAVLink traffic\n"
            "\n"
            "  python3 tools/mavlink_bridge.py monitor --verbose\n"
            "      Show every individual MAVLink frame\n"
            "\n"
            "  python3 tools/mavlink_bridge.py serial --baud 460800\n"
            "      Bridge /dev/ttyS1 serial to TCP 5760\n"
            "\n"
            "  python3 tools/mavlink_bridge.py test\n"
            "      Generate synthetic MAVLink data for QGC testing\n"
            "\n"
            "  python3 tools/mavlink_bridge.py test --duration 30\n"
            "      Run test mode for 30 seconds then exit\n"
            "\n"
            "QGC Connection:\n"
            "  In QGroundControl, add a TCP comm link:\n"
            "    Host: 127.0.0.1\n"
            "    Port: 5760\n"
        ),
    )

    sub = parser.add_subparsers(dest='mode', help='Operating mode')

    # Bridge mode
    p_bridge = sub.add_parser('bridge',
                              help='UDP 14550 <-> TCP 5760 passthrough')
    p_bridge.add_argument('--udp-host', default='10.0.0.1',
                          help='ELRS Backpack IP (default: 10.0.0.1)')
    p_bridge.add_argument('--udp-port', type=int, default=14550,
                          help='MAVLink UDP port (default: 14550)')
    p_bridge.add_argument('--tcp-host', default='127.0.0.1',
                          help='TCP listen address (default: 127.0.0.1)')
    p_bridge.add_argument('--tcp-port', type=int, default=5760,
                          help='TCP listen port (default: 5760)')
    p_bridge.add_argument('--display', type=float, default=2.0,
                          help='Status display interval (default: 2s)')

    # Monitor mode
    p_mon = sub.add_parser('monitor',
                           help='Passive MAVLink traffic display')
    p_mon.add_argument('--udp-host', default='10.0.0.1',
                       help='ELRS Backpack IP (default: 10.0.0.1)')
    p_mon.add_argument('--udp-port', type=int, default=14550,
                       help='MAVLink UDP port (default: 14550)')
    p_mon.add_argument('--verbose', '-v', action='store_true',
                       help='Show every individual frame')
    p_mon.add_argument('--display', type=float, default=2.0,
                       help='Status display interval (default: 2s)')

    # Serial mode
    p_ser = sub.add_parser('serial',
                           help='/dev/ttyS1 serial <-> TCP 5760')
    p_ser.add_argument('--port', default='/dev/ttyS1',
                       help='Serial port (default: /dev/ttyS1)')
    p_ser.add_argument('--baud', type=int, default=460800,
                       help='Serial baud rate (default: 460800)')
    p_ser.add_argument('--tcp-host', default='127.0.0.1',
                       help='TCP listen address (default: 127.0.0.1)')
    p_ser.add_argument('--tcp-port', type=int, default=5760,
                       help='TCP listen port (default: 5760)')
    p_ser.add_argument('--display', type=float, default=2.0,
                       help='Status display interval (default: 2s)')

    # Test mode
    p_test = sub.add_parser('test',
                            help='Synthetic MAVLink data on TCP 5760')
    p_test.add_argument('--tcp-host', default='127.0.0.1',
                        help='TCP listen address (default: 127.0.0.1)')
    p_test.add_argument('--tcp-port', type=int, default=5760,
                        help='TCP listen port (default: 5760)')
    p_test.add_argument('--display', type=float, default=2.0,
                        help='Status display interval (default: 2s)')
    p_test.add_argument('--duration', type=float, default=0,
                        help='Auto-stop after N seconds (0=run forever)')

    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        sys.exit(1)

    if args.mode == 'bridge':
        mode = BridgeMode(
            udp_host=args.udp_host,
            udp_port=args.udp_port,
            tcp_host=args.tcp_host,
            tcp_port=args.tcp_port,
            display_interval=args.display,
        )
    elif args.mode == 'monitor':
        mode = MonitorMode(
            udp_host=args.udp_host,
            udp_port=args.udp_port,
            display_interval=args.display,
            verbose=args.verbose,
        )
    elif args.mode == 'serial':
        mode = SerialMode(
            serial_port=args.port,
            baudrate=args.baud,
            tcp_host=args.tcp_host,
            tcp_port=args.tcp_port,
            display_interval=args.display,
        )
    elif args.mode == 'test':
        mode = TestMode(
            tcp_host=args.tcp_host,
            tcp_port=args.tcp_port,
            display_interval=args.display,
            duration=args.duration,
        )

    mode.run()


if __name__ == '__main__':
    main()
