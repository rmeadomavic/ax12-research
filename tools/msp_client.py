#!/usr/bin/env python3
"""
Betaflight MSP (MultiWii Serial Protocol) Client for AX12

Reads flight controller status via MSP over ELRS Backpack or direct TCP.
Designed for the RadioMaster AX12 as a companion display / telemetry tool.

Protocol: MSP v1 ($M< request / $M> response)
Transport: UDP 14550 (ELRS Backpack) or TCP (Betaflight Configurator proxy)

Python stdlib only. No external dependencies.

Usage:
    python3 msp_client.py status              # FC armed state, mode, sensors, CPU
    python3 msp_client.py battery             # Voltage, current, mAh, cells
    python3 msp_client.py info                # Board, firmware, build date
    python3 msp_client.py pid                 # PID controller values
    python3 msp_client.py rates               # Rates profile (RC rate, super rate, expo)
    python3 msp_client.py monitor             # Continuous status display
    python3 msp_client.py --demo status       # Simulated responses for testing
    python3 msp_client.py --demo monitor      # Simulated continuous display
"""

import argparse
import os
import random
import select
import socket
import struct
import sys
import time

# ──────────────────────────────────────────────────────────────────────
# MSP Command IDs
# ──────────────────────────────────────────────────────────────────────

MSP_FC_VARIANT    = 2
MSP_FC_VERSION    = 3
MSP_BOARD_INFO    = 4
MSP_BUILD_DATE    = 5
MSP_STATUS        = 101
MSP_RAW_IMU       = 102
MSP_RC            = 105
MSP_ATTITUDE      = 108
MSP_ALTITUDE      = 109
MSP_ANALOG        = 110
MSP_PID           = 112
MSP_RC_TUNING     = 111
MSP_STATUS_EX     = 150

# ──────────────────────────────────────────────────────────────────────
# Betaflight flight mode flags (bit positions in mode_flags u32)
# ──────────────────────────────────────────────────────────────────────

FLIGHT_MODES = {
    0:  "ARM",
    1:  "ANGLE",
    2:  "HORIZON",
    3:  "MAG",
    5:  "HEADFREE",
    6:  "HEADADJ",
    10: "GPS_HOME",
    11: "GPS_HOLD",
    12: "PASSTHRU",
    15: "FAILSAFE",
    17: "BEEPER",
    19: "OSD_DISABLE",
    20: "TELEMETRY",
    26: "ANTI_GRAVITY",
    28: "ACRO_TRAINER",
    36: "LAUNCH",
    37: "TURTLE",
}

# Sensor flags (bits in sensor_flags u16)
SENSOR_FLAGS = {
    0: "ACC",
    1: "BARO",
    2: "MAG",
    3: "GPS",
    4: "RANGEFINDER",
    5: "GYRO",
}

# ──────────────────────────────────────────────────────────────────────
# MSP Protocol Core
# ──────────────────────────────────────────────────────────────────────

class MSPError(Exception):
    """MSP protocol or transport error."""
    pass


def msp_checksum(size, cmd, payload):
    """XOR checksum: size ^ cmd ^ payload[0] ^ payload[1] ^ ..."""
    crc = size ^ cmd
    for b in payload:
        crc ^= b
    return crc & 0xFF


def msp_encode_request(cmd, payload=b''):
    """
    Build an MSP v1 request frame.

    Format: '$' 'M' '<' <size> <cmd> [payload...] <checksum>
    """
    size = len(payload)
    crc = msp_checksum(size, cmd, payload)
    return b'$M<' + bytes([size, cmd]) + payload + bytes([crc])


def msp_decode_response(data):
    """
    Decode an MSP v1 response frame.

    Returns (cmd, payload) or raises MSPError.
    Expects data starting with '$M>' or '$M!'.
    """
    if len(data) < 5:
        raise MSPError(f"Response too short: {len(data)} bytes")

    # Find the start of MSP frame
    idx = data.find(b'$M')
    if idx < 0:
        raise MSPError("No MSP header found in response")

    data = data[idx:]

    if len(data) < 5:
        raise MSPError(f"Truncated MSP frame after header search")

    direction = data[2:3]
    if direction == b'!':
        raise MSPError("FC returned error response ($M!)")
    if direction != b'>':
        raise MSPError(f"Unexpected direction byte: {direction!r}")

    size = data[3]
    cmd = data[4]

    if len(data) < 5 + size + 1:
        raise MSPError(f"Incomplete payload: expected {size} bytes, got {len(data) - 6}")

    payload = data[5:5 + size]
    recv_crc = data[5 + size]
    calc_crc = msp_checksum(size, cmd, payload)

    if recv_crc != calc_crc:
        raise MSPError(f"Checksum mismatch: got 0x{recv_crc:02x}, expected 0x{calc_crc:02x}")

    return cmd, payload


# ──────────────────────────────────────────────────────────────────────
# Transport Layer
# ──────────────────────────────────────────────────────────────────────

class MSPTransport:
    """Base class for MSP transports."""

    def send_request(self, cmd, payload=b''):
        raise NotImplementedError

    def receive_response(self, timeout=2.0):
        raise NotImplementedError

    def query(self, cmd, payload=b'', timeout=2.0):
        """Send request and return (cmd, payload) response."""
        self.send_request(cmd, payload)
        return self.receive_response(timeout)

    def close(self):
        pass


class TCPTransport(MSPTransport):
    """MSP over TCP (Betaflight Configurator proxy or direct serial bridge)."""

    def __init__(self, host, port, connect_timeout=5.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(connect_timeout)
        try:
            self.sock.connect((host, port))
        except socket.error as e:
            raise MSPError(f"TCP connect to {host}:{port} failed: {e}")
        self.sock.settimeout(None)

    def send_request(self, cmd, payload=b''):
        frame = msp_encode_request(cmd, payload)
        self.sock.sendall(frame)

    def receive_response(self, timeout=2.0):
        self.sock.settimeout(timeout)
        try:
            buf = b''
            # Read until we get a complete frame
            while True:
                chunk = self.sock.recv(256)
                if not chunk:
                    raise MSPError("Connection closed by remote")
                buf += chunk
                # Check if we have a complete frame
                idx = buf.find(b'$M')
                if idx >= 0 and len(buf) >= idx + 5:
                    size = buf[idx + 3]
                    needed = idx + 5 + size + 1
                    if len(buf) >= needed:
                        return msp_decode_response(buf[idx:needed])
        except socket.timeout:
            raise MSPError("Response timeout")
        finally:
            self.sock.settimeout(None)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class UDPTransport(MSPTransport):
    """MSP over UDP (ELRS Backpack WiFi encapsulation)."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', 0))

    def send_request(self, cmd, payload=b''):
        frame = msp_encode_request(cmd, payload)
        self.sock.sendto(frame, (self.host, self.port))

    def receive_response(self, timeout=2.0):
        ready = select.select([self.sock], [], [], timeout)
        if not ready[0]:
            raise MSPError("UDP response timeout")
        data, addr = self.sock.recvfrom(1024)
        return msp_decode_response(data)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────
# Demo Transport (simulated FC responses)
# ──────────────────────────────────────────────────────────────────────

class DemoTransport(MSPTransport):
    """
    Simulated MSP responses for demo / development / testing.
    Generates realistic Betaflight telemetry with gentle drift.
    """

    def __init__(self):
        self._t0 = time.time()
        self._armed = True
        self._mode = "ANGLE"
        self._vbat_base = 15.8  # 4S starting voltage
        self._mah_consumed = 0
        self._last_cmd = None

    def _elapsed(self):
        return time.time() - self._t0

    def send_request(self, cmd, payload=b''):
        self._last_cmd = cmd

    def receive_response(self, timeout=2.0):
        cmd = self._last_cmd
        t = self._elapsed()

        if cmd == MSP_STATUS or cmd == MSP_STATUS_EX:
            return cmd, self._build_status(t)
        elif cmd == MSP_ANALOG:
            return cmd, self._build_analog(t)
        elif cmd == MSP_FC_VARIANT:
            return cmd, b'BTFL'
        elif cmd == MSP_FC_VERSION:
            return cmd, bytes([4, 5, 1])  # Betaflight 4.5.1
        elif cmd == MSP_BOARD_INFO:
            # board_id(4) + hw_rev(2) + fc_type(1)
            return cmd, b'S405' + struct.pack('<HB', 0, 0)
        elif cmd == MSP_BUILD_DATE:
            return cmd, b'Apr 10 2026' + b'\x00' + b'12:34:56' + b'\x00'
        elif cmd == MSP_PID:
            return cmd, self._build_pid()
        elif cmd == MSP_RC_TUNING:
            return cmd, self._build_rc_tuning()
        elif cmd == MSP_ATTITUDE:
            return cmd, self._build_attitude(t)
        elif cmd == MSP_ALTITUDE:
            return cmd, self._build_altitude(t)
        elif cmd == MSP_RC:
            return cmd, self._build_rc()
        elif cmd == MSP_RAW_IMU:
            return cmd, self._build_imu(t)
        else:
            # Unknown command - return empty payload
            return cmd, b''

    def _build_status(self, t):
        """
        MSP_STATUS response: 11 bytes
        u16 cycle_time, u16 i2c_errors, u16 sensor_flags,
        u32 mode_flags, u8 current_pid_profile
        """
        cycle_time = 125 + random.randint(-5, 5)  # ~8kHz gyro loop
        i2c_errors = 0
        # ACC + GYRO always present, MAG sometimes
        sensor_flags = (1 << 0) | (1 << 5)  # ACC + GYRO
        if random.random() > 0.1:
            sensor_flags |= (1 << 2)  # MAG

        mode_flags = 0
        if self._armed:
            mode_flags |= (1 << 0)  # ARM
        if self._mode == "ANGLE":
            mode_flags |= (1 << 1)  # ANGLE
        elif self._mode == "HORIZON":
            mode_flags |= (1 << 2)  # HORIZON

        profile = 0

        return struct.pack('<HHH', cycle_time, i2c_errors, sensor_flags) + \
               struct.pack('<I', mode_flags) + \
               struct.pack('<B', profile)

    def _build_analog(self, t):
        """
        MSP_ANALOG: 7 bytes
        u8 vbat (unit: 0.1V), u16 mah_drawn, u16 rssi, u16 amperage (0.01A)
        """
        # Voltage sag simulation over time
        sag = min(t * 0.003, 2.0)  # Slow discharge
        vbat_v = max(self._vbat_base - sag + random.uniform(-0.05, 0.05), 12.0)
        vbat = int(vbat_v * 10)

        self._mah_consumed = min(int(t * 5), 1500)  # ~5 mAh/s
        mah = self._mah_consumed

        rssi = max(950 + random.randint(-30, 10) - int(t * 0.5), 0)  # Slow RSSI drift
        amperage = 1500 + random.randint(-200, 200)  # ~15A average

        return struct.pack('<B', vbat) + struct.pack('<HHH', mah, rssi, amperage)

    def _build_pid(self):
        """
        MSP_PID: 30 bytes (10 axes x 3 values: P, I, D)
        Standard Betaflight defaults for a 5" quad.
        """
        # [P, I, D] for: ROLL, PITCH, YAW, ALT, POS, POSR, NAVR, LEVEL, MAG, VEL
        pids = [
            [45, 80, 40],   # ROLL
            [47, 84, 42],   # PITCH
            [45, 90,  0],   # YAW
            [ 0,  0,  0],   # ALT (unused in Betaflight acro)
            [ 0,  0,  0],   # POS
            [ 0,  0,  0],   # POSR
            [ 0,  0,  0],   # NAVR
            [50, 50, 75],   # LEVEL
            [ 0,  0,  0],   # MAG
            [ 0,  0,  0],   # VEL
        ]
        data = b''
        for row in pids:
            data += struct.pack('<BBB', *row)
        return data

    def _build_rc_tuning(self):
        """
        MSP_RC_TUNING: variable length, we return the commonly used fields.
        u8 rc_rate, u8 rc_expo, u8 roll_pitch_rate (deprecated),
        u8 yaw_rate, u8 dyn_thr_pid, u8 throttle_mid, u8 throttle_expo,
        u16 tpa_breakpoint, u8 rc_yaw_expo,
        u8 rcRate_yaw, u8 rcRollRate, u8 rcPitchRate, u8 rcYawRate
        """
        rc_rate = 100       # 1.00
        rc_expo = 0         # 0.00
        roll_pitch_rate = 0 # deprecated
        yaw_rate = 100
        dyn_thr_pid = 65
        throttle_mid = 50
        throttle_expo = 0
        tpa_breakpoint = 1500
        rc_yaw_expo = 0
        rcRate_yaw = 100
        rcRollRate = 70     # 0.70 super rate
        rcPitchRate = 70
        rcYawRate = 70

        return struct.pack('<BBBBBBBHBBBBB',
                           rc_rate, rc_expo, roll_pitch_rate,
                           yaw_rate, dyn_thr_pid, throttle_mid, throttle_expo,
                           tpa_breakpoint, rc_yaw_expo,
                           rcRate_yaw, rcRollRate, rcPitchRate, rcYawRate)

    def _build_attitude(self, t):
        """MSP_ATTITUDE: i16 roll, i16 pitch, i16 yaw (0.1 deg units)."""
        roll = int(5 * 10 * (0.5 + 0.5 * random.random()))
        pitch = int(3 * 10 * (0.5 + 0.5 * random.random()))
        yaw = int((t * 10) % 3600)
        return struct.pack('<hhh', roll, pitch, yaw)

    def _build_altitude(self, t):
        """MSP_ALTITUDE: i32 alt_cm, i16 vario_cm_s."""
        alt = int(1000 + 200 * (0.5 + 0.5 * random.random()))  # ~10m
        vario = int(50 * (random.random() - 0.5))
        return struct.pack('<ih', alt, vario)

    def _build_rc(self):
        """MSP_RC: 8 channels x u16."""
        channels = [
            1500 + random.randint(-5, 5),   # Roll
            1500 + random.randint(-5, 5),   # Pitch
            1500 + random.randint(-20, 20), # Throttle
            1500 + random.randint(-5, 5),   # Yaw
            1800,                            # AUX1 (arm switch)
            1000,                            # AUX2
            1000,                            # AUX3
            1000,                            # AUX4
        ]
        return struct.pack('<' + 'H' * len(channels), *channels)

    def _build_imu(self, t):
        """MSP_RAW_IMU: 9 x i16 (acc xyz, gyro xyz, mag xyz)."""
        acc = [random.randint(-50, 50), random.randint(-50, 50), 512 + random.randint(-20, 20)]
        gyro = [random.randint(-10, 10), random.randint(-10, 10), random.randint(-10, 10)]
        mag = [random.randint(-100, 100), random.randint(-100, 100), random.randint(300, 400)]
        return struct.pack('<' + 'h' * 9, *(acc + gyro + mag))


# ──────────────────────────────────────────────────────────────────────
# Response Parsers
# ──────────────────────────────────────────────────────────────────────

def parse_status(payload):
    """Parse MSP_STATUS / MSP_STATUS_EX."""
    if len(payload) < 11:
        return {"error": f"Status payload too short: {len(payload)} bytes"}

    cycle_time, i2c_errors, sensor_flags = struct.unpack_from('<HHH', payload, 0)
    mode_flags = struct.unpack_from('<I', payload, 6)[0]
    pid_profile = payload[10]

    # CPU load percentage (cycle_time based: 125us = 100% of 8kHz loop)
    cpu_pct = min((cycle_time / 125.0) * 100.0, 999.9)

    # Decode active sensors
    sensors = []
    for bit, name in sorted(SENSOR_FLAGS.items()):
        if sensor_flags & (1 << bit):
            sensors.append(name)

    # Decode active flight modes
    modes = []
    for bit, name in sorted(FLIGHT_MODES.items()):
        if mode_flags & (1 << bit):
            modes.append(name)

    armed = bool(mode_flags & 1)

    return {
        "armed": armed,
        "flight_modes": modes,
        "sensors": sensors,
        "cycle_time_us": cycle_time,
        "cpu_load_pct": round(cpu_pct, 1),
        "i2c_errors": i2c_errors,
        "pid_profile": pid_profile,
        "mode_flags_raw": f"0x{mode_flags:08x}",
        "sensor_flags_raw": f"0x{sensor_flags:04x}",
    }


def parse_analog(payload):
    """Parse MSP_ANALOG."""
    if len(payload) < 7:
        return {"error": f"Analog payload too short: {len(payload)} bytes"}

    vbat_raw = payload[0]
    mah, rssi, amperage = struct.unpack_from('<HHH', payload, 1)

    vbat = vbat_raw / 10.0
    amps = amperage / 100.0

    # Estimate cell count from voltage
    if vbat > 0:
        cells = max(1, round(vbat / 3.7))
        cell_v = vbat / cells
    else:
        cells = 0
        cell_v = 0.0

    return {
        "voltage": round(vbat, 1),
        "cell_voltage": round(cell_v, 2),
        "cell_count": cells,
        "current_a": round(amps, 2),
        "mah_consumed": mah,
        "rssi": rssi,
        "power_w": round(vbat * amps, 1),
    }


def parse_fc_variant(payload):
    """Parse MSP_FC_VARIANT - 4 byte ASCII identifier."""
    return payload[:4].decode('ascii', errors='replace')


def parse_fc_version(payload):
    """Parse MSP_FC_VERSION - 3 bytes: major, minor, patch."""
    if len(payload) < 3:
        return "?.?.?"
    return f"{payload[0]}.{payload[1]}.{payload[2]}"


def parse_board_info(payload):
    """Parse MSP_BOARD_INFO."""
    if len(payload) < 4:
        return {"board_id": "????"}
    board_id = payload[:4].decode('ascii', errors='replace')
    hw_rev = 0
    if len(payload) >= 6:
        hw_rev = struct.unpack_from('<H', payload, 4)[0]
    return {
        "board_id": board_id,
        "hardware_revision": hw_rev,
    }


def parse_build_date(payload):
    """Parse MSP_BUILD_DATE - null-terminated date and time strings."""
    text = payload.decode('ascii', errors='replace')
    parts = text.split('\x00')
    date_str = parts[0] if parts else "unknown"
    time_str = parts[1] if len(parts) > 1 else ""
    return f"{date_str} {time_str}".strip()


def parse_pid(payload):
    """Parse MSP_PID - 10 axes x 3 bytes (P, I, D)."""
    axes = ["ROLL", "PITCH", "YAW", "ALT", "POS", "POSR", "NAVR", "LEVEL", "MAG", "VEL"]
    result = {}
    for i, name in enumerate(axes):
        offset = i * 3
        if offset + 3 <= len(payload):
            p, ii, d = payload[offset], payload[offset + 1], payload[offset + 2]
            if p or ii or d:  # Only show non-zero axes
                result[name] = {"P": p, "I": ii, "D": d}
    return result


def parse_rc_tuning(payload):
    """Parse MSP_RC_TUNING."""
    if len(payload) < 13:
        return {"error": f"RC tuning payload too short: {len(payload)} bytes"}

    vals = struct.unpack_from('<BBBBBBBHBBBBB', payload, 0)
    rc_rate, rc_expo, _, yaw_rate, dyn_thr_pid, thr_mid, thr_expo, \
        tpa_bp, rc_yaw_expo, rcRate_yaw, roll_rate, pitch_rate, yaw_super = vals

    return {
        "rc_rate": rc_rate / 100.0,
        "rc_expo": rc_expo / 100.0,
        "roll_super_rate": roll_rate / 100.0,
        "pitch_super_rate": pitch_rate / 100.0,
        "yaw_super_rate": yaw_super / 100.0,
        "rc_yaw_expo": rc_yaw_expo / 100.0,
        "tpa_rate": dyn_thr_pid / 100.0,
        "tpa_breakpoint": tpa_bp,
        "throttle_mid": thr_mid / 100.0,
        "throttle_expo": thr_expo / 100.0,
    }


def parse_attitude(payload):
    """Parse MSP_ATTITUDE."""
    if len(payload) < 6:
        return {"error": "Attitude payload too short"}
    roll, pitch, yaw = struct.unpack_from('<hhh', payload, 0)
    return {
        "roll_deg": roll / 10.0,
        "pitch_deg": pitch / 10.0,
        "yaw_deg": yaw,
    }


def parse_altitude(payload):
    """Parse MSP_ALTITUDE."""
    if len(payload) < 6:
        return {"error": "Altitude payload too short"}
    alt_cm, vario = struct.unpack_from('<ih', payload, 0)
    return {
        "altitude_m": alt_cm / 100.0,
        "vario_m_s": vario / 100.0,
    }


# ──────────────────────────────────────────────────────────────────────
# Display Formatters
# ──────────────────────────────────────────────────────────────────────

def fmt_kv(label, value, unit="", width=22):
    """Format a key-value pair for display."""
    if unit:
        return f"  {label:<{width}} {value} {unit}"
    return f"  {label:<{width}} {value}"


def display_status(transport):
    """Query and display FC status."""
    cmd, payload = transport.query(MSP_STATUS)
    status = parse_status(payload)

    if "error" in status:
        print(f"  Error: {status['error']}")
        return status

    armed_str = "ARMED" if status["armed"] else "DISARMED"
    armed_color = "\033[91m" if status["armed"] else "\033[92m"
    reset = "\033[0m"

    print(f"\n  === FC STATUS ===")
    print(f"  {armed_color}{armed_str}{reset}")
    print()
    print(fmt_kv("Flight Modes:", ", ".join(status["flight_modes"]) or "NONE"))
    print(fmt_kv("Sensors:", ", ".join(status["sensors"])))
    print(fmt_kv("Cycle Time:", status["cycle_time_us"], "us"))
    print(fmt_kv("CPU Load:", f"{status['cpu_load_pct']}%"))
    print(fmt_kv("I2C Errors:", status["i2c_errors"]))
    print(fmt_kv("PID Profile:", status["pid_profile"]))
    print()

    return status


def display_battery(transport):
    """Query and display battery status."""
    cmd, payload = transport.query(MSP_ANALOG)
    bat = parse_analog(payload)

    if "error" in bat:
        print(f"  Error: {bat['error']}")
        return bat

    # Color voltage by cell health
    cell_v = bat["cell_voltage"]
    if cell_v >= 3.7:
        color = "\033[92m"  # green
    elif cell_v >= 3.5:
        color = "\033[93m"  # yellow
    else:
        color = "\033[91m"  # red
    reset = "\033[0m"

    print(f"\n  === BATTERY ===")
    print(fmt_kv("Pack Voltage:", f"{color}{bat['voltage']}V{reset} ({bat['cell_count']}S)"))
    print(fmt_kv("Cell Voltage:", f"{color}{bat['cell_voltage']}V{reset}"))
    print(fmt_kv("Current:", f"{bat['current_a']}A"))
    print(fmt_kv("Power:", f"{bat['power_w']}W"))
    print(fmt_kv("Consumed:", f"{bat['mah_consumed']} mAh"))
    print(fmt_kv("RSSI:", bat["rssi"]))
    print()

    return bat


def display_info(transport):
    """Query and display board / firmware info."""
    _, variant_payload = transport.query(MSP_FC_VARIANT)
    variant = parse_fc_variant(variant_payload)

    _, version_payload = transport.query(MSP_FC_VERSION)
    version = parse_fc_version(version_payload)

    _, board_payload = transport.query(MSP_BOARD_INFO)
    board = parse_board_info(board_payload)

    _, build_payload = transport.query(MSP_BUILD_DATE)
    build_date = parse_build_date(build_payload)

    print(f"\n  === BOARD INFO ===")
    print(fmt_kv("Firmware:", f"{variant} {version}"))
    print(fmt_kv("Board:", board["board_id"]))
    print(fmt_kv("HW Revision:", board["hardware_revision"]))
    print(fmt_kv("Build Date:", build_date))
    print()

    return {
        "variant": variant,
        "version": version,
        "board": board,
        "build_date": build_date,
    }


def display_pid(transport):
    """Query and display PID controller values."""
    _, payload = transport.query(MSP_PID)
    pids = parse_pid(payload)

    print(f"\n  === PID CONTROLLER ===")
    print(f"  {'AXIS':<10} {'P':>5} {'I':>5} {'D':>5}")
    print(f"  {'-'*10} {'-'*5} {'-'*5} {'-'*5}")
    for axis, vals in pids.items():
        print(f"  {axis:<10} {vals['P']:>5} {vals['I']:>5} {vals['D']:>5}")
    print()

    return pids


def display_rates(transport):
    """Query and display rates profile."""
    _, payload = transport.query(MSP_RC_TUNING)
    rates = parse_rc_tuning(payload)

    if "error" in rates:
        print(f"  Error: {rates['error']}")
        return rates

    print(f"\n  === RATES PROFILE ===")
    print(fmt_kv("RC Rate:", rates["rc_rate"]))
    print(fmt_kv("RC Expo:", rates["rc_expo"]))
    print(fmt_kv("Roll Super Rate:", rates["roll_super_rate"]))
    print(fmt_kv("Pitch Super Rate:", rates["pitch_super_rate"]))
    print(fmt_kv("Yaw Super Rate:", rates["yaw_super_rate"]))
    print(fmt_kv("RC Yaw Expo:", rates["rc_yaw_expo"]))
    print()
    print(fmt_kv("TPA Rate:", rates["tpa_rate"]))
    print(fmt_kv("TPA Breakpoint:", rates["tpa_breakpoint"]))
    print(fmt_kv("Throttle Mid:", rates["throttle_mid"]))
    print(fmt_kv("Throttle Expo:", rates["throttle_expo"]))
    print()

    return rates


def display_monitor(transport, interval=1.0):
    """Continuous status display -- status + battery + attitude."""
    print("\n  MSP Monitor (Ctrl+C to stop)\n")

    iteration = 0
    try:
        while True:
            lines = []

            # Status
            try:
                _, s_payload = transport.query(MSP_STATUS)
                status = parse_status(s_payload)
                armed = status.get("armed", False)
                modes = ", ".join(status.get("flight_modes", [])) or "NONE"
                cpu = status.get("cpu_load_pct", 0)
            except MSPError as e:
                armed = False
                modes = f"ERR: {e}"
                cpu = 0

            # Battery
            try:
                _, a_payload = transport.query(MSP_ANALOG)
                bat = parse_analog(a_payload)
                vbat = bat.get("voltage", 0)
                cell_v = bat.get("cell_voltage", 0)
                amps = bat.get("current_a", 0)
                mah = bat.get("mah_consumed", 0)
                rssi = bat.get("rssi", 0)
            except MSPError as e:
                vbat = cell_v = amps = mah = rssi = 0

            # Attitude
            try:
                _, att_payload = transport.query(MSP_ATTITUDE)
                att = parse_attitude(att_payload)
                roll = att.get("roll_deg", 0)
                pitch = att.get("pitch_deg", 0)
                yaw = att.get("yaw_deg", 0)
            except MSPError as e:
                roll = pitch = yaw = 0

            # Color codes
            armed_str = "\033[91mARMED\033[0m" if armed else "\033[92mDISARMED\033[0m"
            if cell_v >= 3.7:
                v_color = "\033[92m"
            elif cell_v >= 3.5:
                v_color = "\033[93m"
            else:
                v_color = "\033[91m"
            rst = "\033[0m"

            # Build display
            # Clear screen every iteration for clean display
            if iteration > 0:
                # Move up enough lines to overwrite
                sys.stdout.write(f"\033[10A")

            print(f"  {armed_str}  |  Modes: {modes:<30}")
            print(f"  Battery: {v_color}{vbat:.1f}V{rst} ({cell_v:.2f}V/cell)  |  {amps:.1f}A  |  {mah} mAh  |  RSSI: {rssi}")
            print(f"  Attitude: R={roll:+6.1f}  P={pitch:+6.1f}  Y={yaw:+6.1f}")
            print(f"  CPU: {cpu:.0f}%  |  Loop: {status.get('cycle_time_us', 0)}us")
            print(f"  Sensors: {', '.join(status.get('sensors', []))}")
            print(f"  {'─' * 60}")
            # Voltage bar
            bar_width = 40
            if cell_v > 0:
                fill = int(max(0, min(1, (cell_v - 3.3) / (4.2 - 3.3))) * bar_width)
            else:
                fill = 0
            bar = f"  [{v_color}{'█' * fill}{'░' * (bar_width - fill)}{rst}] {cell_v:.2f}V/cell"
            print(bar)
            print(f"  {'─' * 60}")
            # Timestamp
            ts = time.strftime("%H:%M:%S")
            print(f"  Updated: {ts}  (interval: {interval}s)")
            print()

            iteration += 1
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n  Monitor stopped.")


# ──────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────────────

def create_transport(args):
    """Create the appropriate transport based on CLI args."""
    if args.demo:
        print("  [DEMO MODE - simulated responses]")
        return DemoTransport()

    if args.tcp:
        host, port = args.tcp.split(':') if ':' in args.tcp else (args.tcp, '5761')
        print(f"  Connecting via TCP to {host}:{port}...")
        return TCPTransport(host, int(port))
    else:
        host = args.host
        port = args.port
        print(f"  Using UDP transport {host}:{port}...")
        return UDPTransport(host, port)


def main():
    parser = argparse.ArgumentParser(
        description="Betaflight MSP Client for AX12",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  status    FC armed state, flight modes, sensors, CPU load
  battery   Pack voltage, current draw, mAh consumed, cell count
  info      Board type, firmware version, build date
  pid       PID controller values (P/I/D per axis)
  rates     Rates profile (RC rate, super rate, expo)
  monitor   Continuous status + battery + attitude display
  all       Run status + battery + info

examples:
  python3 msp_client.py --demo status
  python3 msp_client.py --demo monitor
  python3 msp_client.py --tcp 192.168.4.1:5761 status
  python3 msp_client.py --host 192.168.4.1 --port 14550 battery
        """,
    )
    parser.add_argument('command', choices=['status', 'battery', 'info', 'pid', 'rates', 'monitor', 'all'],
                        help='Command to execute')
    parser.add_argument('--demo', action='store_true',
                        help='Use simulated MSP responses for testing')
    parser.add_argument('--tcp', metavar='HOST:PORT',
                        help='Connect via TCP (e.g., 192.168.4.1:5761)')
    parser.add_argument('--host', default='192.168.4.1',
                        help='UDP target host (default: 192.168.4.1)')
    parser.add_argument('--port', type=int, default=14550,
                        help='UDP target port (default: 14550)')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Monitor refresh interval in seconds (default: 1.0)')

    args = parser.parse_args()

    print(f"\n  MSP Client v1.0 - AX12 Betaflight Telemetry")
    print(f"  {'=' * 46}")

    transport = create_transport(args)

    try:
        if args.command == 'status':
            display_status(transport)
        elif args.command == 'battery':
            display_battery(transport)
        elif args.command == 'info':
            display_info(transport)
        elif args.command == 'pid':
            display_pid(transport)
        elif args.command == 'rates':
            display_rates(transport)
        elif args.command == 'monitor':
            display_monitor(transport, interval=args.interval)
        elif args.command == 'all':
            display_status(transport)
            display_battery(transport)
            display_info(transport)
    except MSPError as e:
        print(f"\n  MSP Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  Interrupted.")
    finally:
        transport.close()


if __name__ == '__main__':
    main()
