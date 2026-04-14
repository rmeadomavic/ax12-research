#!/usr/bin/env python3
"""
ELRS/CRSF Telemetry Decoder and Display Tool

Decodes ELRS telemetry from UMBUS 0x15 and 0x10 frames, displaying
link statistics, timing data, and CRSF passthrough fields.

Modes:
    live      - Monitor live telemetry via strace on /dev/ttyS0
    decode    - Decode telemetry from timed-frames.json capture file
    simulate  - Generate and decode synthetic telemetry via simulator

Output formats:
    table     - Human-readable formatted table (default)
    json      - Machine-readable JSON output

Usage:
    python3 elrs_decoder.py live                     # live monitoring
    python3 elrs_decoder.py decode                   # decode capture file
    python3 elrs_decoder.py decode --file FILE       # decode specific file
    python3 elrs_decoder.py simulate                 # synthetic telemetry
    python3 elrs_decoder.py simulate --seconds 5     # 5 seconds synthetic
    python3 elrs_decoder.py simulate --linked        # simulate active link
    python3 elrs_decoder.py decode --format json     # JSON output

Requires root for live mode (strace access to serial port).
Python stdlib only.
"""

import json
import os
import struct
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from umbus import (
    UMBUSDecoder, UMBUSEncoder, UMBUSFrame, FrameType,
    ELRS_CRSF_ADDR_RADIO, ELRS_CRSF_ADDR_TX,
    ELRS_CRSF_TYPE_HANDSET, ELRS_SUBCMD_TIMING,
    ELRS_INVALID_MARKER, compute_crc8, CRC_INIT_VALUES,
)


# ===================================================================
# Constants
# ===================================================================

# CRSF frame types we might encounter
class CRSFType(IntEnum):
    GPS = 0x02
    BATTERY = 0x08
    LINK_STATISTICS = 0x14
    RC_CHANNELS = 0x16
    LINK_STATS_RX = 0x1C
    LINK_STATS_TX = 0x1D
    ATTITUDE = 0x1E
    FLIGHT_MODE = 0x21
    HANDSET = 0x3A

# ELRS RF mode names
RF_MODE_NAMES = {
    0: "4 Hz",
    1: "25 Hz",
    2: "50 Hz",
    3: "100 Hz",
    4: "150 Hz",
    5: "200 Hz",
    6: "250 Hz",
    7: "500 Hz",
    8: "1000 Hz",
}

# TX power table (ELRS)
TX_POWER_TABLE = {
    0: "Dynamic",
    1: "10 mW",
    2: "25 mW",
    3: "50 mW",
    4: "100 mW",
    5: "250 mW",
    6: "500 mW",
    7: "1000 mW",
    8: "2000 mW",
}

# Extended telemetry sub-index meanings (from observation)
EXTENDED_SUB_INDEX = {
    0: "RSSI/Signal",
    1: "LQ/Rate",
    2: "SNR/Power",
}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMED_FRAMES_PATH = os.path.join(REPO_ROOT, 'captures', 'timed-frames.json')


# ===================================================================
# Data Classes
# ===================================================================

@dataclass
class ELRSLinkStatus:
    """Decoded ELRS link telemetry from a single 0x15 frame."""
    timestamp_ms: float = 0.0
    # CRSF addressing
    crsf_addr: int = 0
    crsf_type: int = 0
    crsf_dest: int = 0
    crsf_origin: int = 0
    crsf_size: int = 0
    # Sub-command
    sub_cmd: int = 0
    # Data fields
    data_field1: int = 0          # bytes 11-12 (LE): varies with link
    timing_us: int = 0            # bytes 13-14 (BE): packet interval
    link_status_raw: int = 0      # bytes 15-16 (LE): status word
    link_valid: bool = False
    # Sequence
    seq: int = 0
    # Extra bytes (18-19): internal module state
    extra_byte_18: int = 0
    extra_byte_19: int = 0
    # Derived
    packet_rate_hz: float = 0.0
    # CRC
    checksum_valid: bool = True

    # Hypothesized field mappings (populated when link is active)
    rssi_dbm: Optional[int] = None
    lq_percent: Optional[int] = None
    snr_db: Optional[int] = None
    tx_power: Optional[str] = None

    def derive_fields(self):
        """Compute derived fields from raw data."""
        if self.timing_us > 0:
            self.packet_rate_hz = 1_000_000.0 / self.timing_us
        else:
            self.packet_rate_hz = 0.0

        # When link is active, attempt to extract RSSI/LQ from data_field1
        # Based on protocol analysis:
        # - data_field1 low byte might be offset/update counter
        # - data_field1 high byte might encode signal info
        # These are hypotheses pending active-link capture validation
        if self.link_valid and self.data_field1 != 0:
            low = self.data_field1 & 0xFF
            high = (self.data_field1 >> 8) & 0xFF
            # Hypothesis: low byte = timing offset, high byte = RSSI indicator
            if high > 0:
                self.rssi_dbm = -(high)  # dBm stored as positive, displayed negative
            if self.link_status_raw != ELRS_INVALID_MARKER:
                # link_status might encode LQ in low byte
                lq_candidate = self.link_status_raw & 0xFF
                if 0 <= lq_candidate <= 100:
                    self.lq_percent = lq_candidate

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = {
            'timestamp_ms': self.timestamp_ms,
            'crsf': {
                'addr': f'0x{self.crsf_addr:02X}',
                'type': f'0x{self.crsf_type:02X}',
                'type_name': CRSFType(self.crsf_type).name if self.crsf_type in CRSFType._value2member_map_ else 'UNKNOWN',
                'dest': f'0x{self.crsf_dest:02X}',
                'origin': f'0x{self.crsf_origin:02X}',
                'size': self.crsf_size,
            },
            'sub_cmd': f'0x{self.sub_cmd:02X}',
            'sub_cmd_name': 'TIMING' if self.sub_cmd == ELRS_SUBCMD_TIMING else 'UNKNOWN',
            'timing': {
                'interval_us': self.timing_us,
                'packet_rate_hz': round(self.packet_rate_hz, 1),
            },
            'link': {
                'valid': self.link_valid,
                'status_raw': f'0x{self.link_status_raw:04X}',
                'data_field1': f'0x{self.data_field1:04X}',
            },
            'seq': self.seq,
            'extra': {
                'byte_18': f'0x{self.extra_byte_18:02X}',
                'byte_19': f'0x{self.extra_byte_19:02X}',
            },
            'checksum_valid': self.checksum_valid,
        }
        # Add signal fields if available
        if self.rssi_dbm is not None:
            d['signal'] = {
                'rssi_dbm': self.rssi_dbm,
                'lq_percent': self.lq_percent,
                'snr_db': self.snr_db,
                'tx_power': self.tx_power,
            }
        return d


@dataclass
class ExtendedTelemetry:
    """Decoded extended telemetry from a single 0x10 frame."""
    timestamp_ms: float = 0.0
    descriptor: int = 0
    sub_index: int = 0
    value: int = 0
    # Full raw payload for deeper analysis
    raw_payload: bytes = b''
    checksum_valid: bool = True

    @property
    def sub_index_name(self) -> str:
        return EXTENDED_SUB_INDEX.get(self.sub_index, f'Unknown({self.sub_index})')

    def to_dict(self) -> dict:
        return {
            'timestamp_ms': self.timestamp_ms,
            'descriptor': f'0x{self.descriptor:02X}',
            'sub_index': self.sub_index,
            'sub_index_name': self.sub_index_name,
            'value': self.value,
            'value_hex': f'0x{self.value:04X}',
            'raw_hex': self.raw_payload.hex(),
            'checksum_valid': self.checksum_valid,
        }


@dataclass
class TelemetryState:
    """Aggregated telemetry state from multiple frames."""
    # ELRS link (from 0x15)
    last_elrs: Optional[ELRSLinkStatus] = None
    elrs_count: int = 0
    elrs_invalid_count: int = 0
    elrs_seq_gaps: int = 0
    _last_elrs_seq: int = -1

    # Extended telemetry (from 0x10)
    extended_values: dict = field(default_factory=dict)  # sub_index -> last value
    extended_count: int = 0

    # History for rate calculation
    _elrs_timestamps: deque = field(default_factory=lambda: deque(maxlen=50))
    _extended_timestamps: deque = field(default_factory=lambda: deque(maxlen=50))

    # Discovery: track unique values seen
    _data_field1_values: set = field(default_factory=set)
    _link_status_values: set = field(default_factory=set)
    _byte18_values: set = field(default_factory=set)
    _byte19_values: set = field(default_factory=set)

    def update_elrs(self, status: ELRSLinkStatus):
        """Update state with new ELRS telemetry frame."""
        self.last_elrs = status
        self.elrs_count += 1
        self._elrs_timestamps.append(status.timestamp_ms)

        if not status.link_valid:
            self.elrs_invalid_count += 1

        # Track sequence gaps
        if self._last_elrs_seq >= 0:
            expected = (self._last_elrs_seq + 1) & 0xFF
            if status.seq != expected:
                self.elrs_seq_gaps += 1
        self._last_elrs_seq = status.seq

        # Discovery tracking
        self._data_field1_values.add(status.data_field1)
        self._link_status_values.add(status.link_status_raw)
        self._byte18_values.add(status.extra_byte_18)
        self._byte19_values.add(status.extra_byte_19)

    def update_extended(self, ext: ExtendedTelemetry):
        """Update state with new extended telemetry frame."""
        self.extended_values[ext.sub_index] = ext.value
        self.extended_count += 1
        self._extended_timestamps.append(ext.timestamp_ms)

    @property
    def elrs_rate_hz(self) -> float:
        """Measured ELRS frame rate from timestamps."""
        if len(self._elrs_timestamps) < 2:
            return 0.0
        span = self._elrs_timestamps[-1] - self._elrs_timestamps[0]
        if span <= 0:
            return 0.0
        return (len(self._elrs_timestamps) - 1) * 1000.0 / span

    @property
    def extended_rate_hz(self) -> float:
        """Measured extended telemetry frame rate from timestamps."""
        if len(self._extended_timestamps) < 2:
            return 0.0
        span = self._extended_timestamps[-1] - self._extended_timestamps[0]
        if span <= 0:
            return 0.0
        return (len(self._extended_timestamps) - 1) * 1000.0 / span

    def discoveries(self) -> dict:
        """Report field value diversity (for reverse engineering)."""
        return {
            'data_field1_unique': len(self._data_field1_values),
            'data_field1_samples': sorted(list(self._data_field1_values))[:10],
            'link_status_unique': len(self._link_status_values),
            'link_status_samples': sorted(list(self._link_status_values))[:10],
            'byte18_unique': len(self._byte18_values),
            'byte19_unique': len(self._byte19_values),
        }


# ===================================================================
# Decoder
# ===================================================================

class ELRSDecoder:
    """
    Decode ELRS/CRSF telemetry from UMBUS frames.

    Wraps UMBUSDecoder, filtering for telemetry frame types (0x15, 0x10)
    and extracting all available fields.
    """

    def __init__(self):
        self.umbus = UMBUSDecoder()
        self.state = TelemetryState()

    def decode_elrs_frame(self, frame: UMBUSFrame, timestamp_ms: float = 0.0) -> Optional[ELRSLinkStatus]:
        """Decode a 0x15 ELRS telemetry frame into structured data."""
        if frame.frame_type != FrameType.ELRS_TELEM:
            return None
        if len(frame.raw) < 20:
            return None

        status = ELRSLinkStatus(
            timestamp_ms=timestamp_ms,
            crsf_addr=frame.raw[5],
            crsf_size=frame.raw[6],
            crsf_type=frame.raw[7],
            crsf_dest=frame.raw[8],
            crsf_origin=frame.raw[9],
            sub_cmd=frame.raw[10],
            data_field1=struct.unpack_from('<H', frame.raw, 11)[0],
            timing_us=struct.unpack_from('>H', frame.raw, 13)[0],
            link_status_raw=struct.unpack_from('<H', frame.raw, 15)[0],
            link_valid=(struct.unpack_from('<H', frame.raw, 15)[0] != ELRS_INVALID_MARKER),
            seq=frame.raw[17],
            extra_byte_18=frame.raw[18] if len(frame.raw) > 18 else 0,
            extra_byte_19=frame.raw[19] if len(frame.raw) > 19 else 0,
            checksum_valid=frame.checksum_valid,
        )
        status.derive_fields()
        self.state.update_elrs(status)
        return status

    def decode_extended_frame(self, frame: UMBUSFrame, timestamp_ms: float = 0.0) -> Optional[ExtendedTelemetry]:
        """Decode a 0x10 extended telemetry frame."""
        if frame.frame_type != FrameType.EXTENDED:
            return None
        if len(frame.raw) < 18:
            return None

        ext = ExtendedTelemetry(
            timestamp_ms=timestamp_ms,
            descriptor=frame.raw[4],
            sub_index=frame.raw[5],
            value=struct.unpack_from('<H', frame.raw, 8)[0],
            raw_payload=frame.raw[4:-1],  # exclude sync, type, and checksum
            checksum_valid=frame.checksum_valid,
        )
        self.state.update_extended(ext)
        return ext

    def feed(self, data: bytes, timestamp_ms: float = 0.0):
        """Feed raw bytes and yield decoded telemetry objects."""
        for frame in self.umbus.feed(data):
            if frame.frame_type == FrameType.ELRS_TELEM:
                result = self.decode_elrs_frame(frame, timestamp_ms)
                if result:
                    yield ('elrs', result)
            elif frame.frame_type == FrameType.EXTENDED:
                result = self.decode_extended_frame(frame, timestamp_ms)
                if result:
                    yield ('extended', result)


# ===================================================================
# Display Formatters
# ===================================================================

# ANSI color codes for terminal output
class Color:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'

    @staticmethod
    def enabled():
        """Check if color output should be used."""
        if os.environ.get('NO_COLOR'):
            return False
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


def signal_bar(value, max_val=100, width=20):
    """Create an ASCII signal strength bar."""
    if value is None or value < 0:
        return '[' + '?' * width + ']'
    filled = int((min(value, max_val) / max_val) * width)
    bar = '#' * filled + '-' * (width - filled)
    return f'[{bar}]'


def rssi_bar(rssi_dbm, width=20):
    """Create RSSI bar (-120 dBm = empty, -30 dBm = full)."""
    if rssi_dbm is None:
        return '[' + '.' * width + '] N/A'
    # Map -120..-30 to 0..100
    pct = max(0, min(100, (rssi_dbm + 120) * 100 // 90))
    filled = int(pct * width / 100)
    bar = '#' * filled + '-' * (width - filled)
    return f'[{bar}] {rssi_dbm} dBm'


class TableFormatter:
    """Format telemetry as a human-readable table."""

    def __init__(self, use_color=True):
        self.use_color = use_color and Color.enabled()
        self._frame_count = 0

    def _c(self, code, text):
        if self.use_color:
            return f'{code}{text}{Color.RESET}'
        return text

    def format_header(self):
        lines = []
        lines.append(self._c(Color.BOLD, '=' * 72))
        lines.append(self._c(Color.BOLD + Color.CYAN,
                             '  ELRS/CRSF Telemetry Decoder - RadioMaster AX12'))
        lines.append(self._c(Color.BOLD, '=' * 72))
        lines.append('')
        return '\n'.join(lines)

    def format_elrs(self, status):
        """Format a single ELRS telemetry frame."""
        self._frame_count += 1
        lines = []

        # Timestamp and frame info
        ts = f'{status.timestamp_ms/1000.0:.3f}s'
        valid_str = self._c(Color.GREEN, 'VALID') if status.link_valid else self._c(Color.RED, 'INVALID')
        crc_str = self._c(Color.GREEN, 'OK') if status.checksum_valid else self._c(Color.RED, 'BAD')

        lines.append(self._c(Color.BOLD, f'--- ELRS Frame #{self._frame_count} [{ts}] ---'))
        lines.append(f'  CRSF: addr=0x{status.crsf_addr:02X} type=0x{status.crsf_type:02X}'
                     f' ({"HANDSET" if status.crsf_type == CRSFType.HANDSET else "?"}) '
                     f'size={status.crsf_size}')
        lines.append(f'  Route: 0x{status.crsf_dest:02X} <- 0x{status.crsf_origin:02X}'
                     f'  Sub-cmd: 0x{status.sub_cmd:02X}'
                     f' ({"TIMING" if status.sub_cmd == ELRS_SUBCMD_TIMING else "?"})')
        lines.append(f'  Link: {valid_str}  CRC: {crc_str}  Seq: {status.seq}')

        # Timing
        lines.append(self._c(Color.YELLOW, '  Timing:'))
        lines.append(f'    Interval: {status.timing_us} us'
                     f'  Rate: {status.packet_rate_hz:.0f} Hz')

        # Raw data fields
        lines.append(self._c(Color.YELLOW, '  Data Fields:'))
        lines.append(f'    Field1: 0x{status.data_field1:04X} ({status.data_field1})')
        lines.append(f'    Link Status: 0x{status.link_status_raw:04X}'
                     f' ({"timeout/invalid" if not status.link_valid else "active"})')
        lines.append(f'    Extra[18]: 0x{status.extra_byte_18:02X} ({status.extra_byte_18})')
        lines.append(f'    Extra[19]: 0x{status.extra_byte_19:02X} ({status.extra_byte_19})')

        # Signal quality (if link active)
        if status.rssi_dbm is not None:
            lines.append(self._c(Color.YELLOW, '  Signal (hypothesized):'))
            lines.append(f'    RSSI: {rssi_bar(status.rssi_dbm)}')
            if status.lq_percent is not None:
                lines.append(f'    LQ:   {signal_bar(status.lq_percent)} {status.lq_percent}%')
            if status.snr_db is not None:
                lines.append(f'    SNR:  {status.snr_db} dB')
            if status.tx_power is not None:
                lines.append(f'    TX:   {status.tx_power}')

        lines.append('')
        return '\n'.join(lines)

    def format_extended(self, ext):
        """Format a single extended telemetry frame."""
        ts = f'{ext.timestamp_ms/1000.0:.3f}s'
        lines = []
        lines.append(self._c(Color.DIM,
            f'  [EXT {ts}] sub={ext.sub_index} ({ext.sub_index_name})'
            f'  desc=0x{ext.descriptor:02X}'
            f'  val={ext.value} (0x{ext.value:04X})'
            f'  raw={ext.raw_payload.hex()}'))
        return '\n'.join(lines)

    def format_summary(self, state):
        """Format the aggregated telemetry summary."""
        lines = []
        lines.append('')
        lines.append(self._c(Color.BOLD, '=' * 72))
        lines.append(self._c(Color.BOLD + Color.CYAN, '  Telemetry Summary'))
        lines.append(self._c(Color.BOLD, '=' * 72))

        # ELRS stats
        lines.append(self._c(Color.YELLOW, '\n  ELRS (0x15) Statistics:'))
        lines.append(f'    Frames received:  {state.elrs_count}')
        lines.append(f'    Invalid (no-link): {state.elrs_invalid_count}'
                     f' ({state.elrs_invalid_count*100//max(1,state.elrs_count)}%)')
        lines.append(f'    Sequence gaps:    {state.elrs_seq_gaps}')
        lines.append(f'    Measured rate:    {state.elrs_rate_hz:.1f} Hz (expected: 5 Hz)')

        if state.last_elrs:
            lines.append(f'    Packet interval:  {state.last_elrs.timing_us} us'
                         f' ({state.last_elrs.packet_rate_hz:.0f} Hz air rate)')

        # Extended stats
        lines.append(self._c(Color.YELLOW, '\n  Extended (0x10) Statistics:'))
        lines.append(f'    Frames received:  {state.extended_count}')
        lines.append(f'    Measured rate:    {state.extended_rate_hz:.1f} Hz (expected: ~3 Hz)')
        lines.append(f'    Sub-channels seen: {list(state.extended_values.keys())}')
        for idx, val in sorted(state.extended_values.items()):
            lines.append(f'      [{idx}] {EXTENDED_SUB_INDEX.get(idx, "?")}:'
                         f' {val} (0x{val:04X})')

        # Discovery report
        disc = state.discoveries()
        lines.append(self._c(Color.YELLOW, '\n  Field Diversity (for reverse engineering):'))
        lines.append(f'    data_field1: {disc["data_field1_unique"]} unique values')
        if disc['data_field1_samples']:
            samples = [f'0x{v:04X}' for v in disc['data_field1_samples'][:8]]
            lines.append(f'      samples: {" ".join(samples)}')
        lines.append(f'    link_status: {disc["link_status_unique"]} unique values')
        if disc['link_status_samples']:
            samples = [f'0x{v:04X}' for v in disc['link_status_samples'][:8]]
            lines.append(f'      samples: {" ".join(samples)}')
        lines.append(f'    byte_18: {disc["byte18_unique"]} unique values')
        lines.append(f'    byte_19: {disc["byte19_unique"]} unique values')

        # Interpretation
        lines.append(self._c(Color.YELLOW, '\n  Interpretation:'))
        if state.elrs_invalid_count == state.elrs_count and state.elrs_count > 0:
            lines.append(self._c(Color.RED, '    No receiver linked - all frames show timeout'))
        elif state.elrs_invalid_count > 0:
            pct = state.elrs_invalid_count * 100 // state.elrs_count
            lines.append(f'    Link intermittent - {pct}% invalid frames')
        elif state.elrs_count > 0:
            lines.append(self._c(Color.GREEN, '    Link active - all frames valid'))
        else:
            lines.append('    No ELRS frames received')

        if disc['byte18_unique'] > 1:
            lines.append(f'    byte_18 varies ({disc["byte18_unique"]} values) - likely FHSS hop state')
        if disc['byte19_unique'] > 1:
            lines.append(f'    byte_19 varies ({disc["byte19_unique"]} values) - likely entropy/CRC seed')

        lines.append('')
        return '\n'.join(lines)


class JSONFormatter:
    """Format telemetry as JSON."""

    def __init__(self):
        self._frames = []

    def add_elrs(self, status):
        self._frames.append({'type': 'elrs', 'data': status.to_dict()})

    def add_extended(self, ext):
        self._frames.append({'type': 'extended', 'data': ext.to_dict()})

    def finalize(self, state):
        """Return final JSON output."""
        output = {
            'frames': self._frames,
            'summary': {
                'elrs_count': state.elrs_count,
                'elrs_invalid_count': state.elrs_invalid_count,
                'elrs_seq_gaps': state.elrs_seq_gaps,
                'elrs_measured_rate_hz': round(state.elrs_rate_hz, 2),
                'extended_count': state.extended_count,
                'extended_measured_rate_hz': round(state.extended_rate_hz, 2),
                'extended_values': {str(k): v for k, v in state.extended_values.items()},
            },
            'discoveries': state.discoveries(),
        }
        # Convert sets in discoveries to lists for JSON
        for key in output['discoveries']:
            if isinstance(output['discoveries'][key], set):
                output['discoveries'][key] = sorted(list(output['discoveries'][key]))
        return json.dumps(output, indent=2)


# ===================================================================
# Mode: Decode from capture file
# ===================================================================

def mode_decode(filepath, fmt='table', max_frames=0):
    """Decode telemetry from a timed-frames.json capture file."""
    if not os.path.exists(filepath):
        print(f'Error: Capture file not found: {filepath}', file=sys.stderr)
        sys.exit(1)

    with open(filepath) as f:
        entries = json.load(f)

    decoder = ELRSDecoder()

    if fmt == 'table':
        formatter = TableFormatter()
        print(formatter.format_header())
        print(f'  Source: {filepath}')
        print(f'  Frames in capture: {len(entries)}')
        print()

        for entry in entries:
            ts_ms, _size, hexstr = entry[0], entry[1], entry[2]
            raw = bytes.fromhex(hexstr)

            for kind, obj in decoder.feed(raw, timestamp_ms=ts_ms):
                if kind == 'elrs':
                    print(formatter.format_elrs(obj))
                elif kind == 'extended':
                    print(formatter.format_extended(obj))

                if max_frames > 0 and decoder.state.elrs_count >= max_frames:
                    break
            if max_frames > 0 and decoder.state.elrs_count >= max_frames:
                break

        print(formatter.format_summary(decoder.state))

    elif fmt == 'json':
        json_fmt = JSONFormatter()
        for entry in entries:
            ts_ms, _size, hexstr = entry[0], entry[1], entry[2]
            raw = bytes.fromhex(hexstr)

            for kind, obj in decoder.feed(raw, timestamp_ms=ts_ms):
                if kind == 'elrs':
                    json_fmt.add_elrs(obj)
                elif kind == 'extended':
                    json_fmt.add_extended(obj)

        print(json_fmt.finalize(decoder.state))


# ===================================================================
# Mode: Simulate
# ===================================================================

def mode_simulate(duration=5.0, fmt='table', linked=False):
    """Generate and decode synthetic ELRS telemetry."""
    from simulator import TrafficGenerator

    gen = TrafficGenerator()
    frames = gen.generate(duration)

    decoder = ELRSDecoder()

    # If simulating a linked receiver, modify ELRS frames
    modified_frames = []
    for t, frame_bytes in frames:
        if len(frame_bytes) >= 2 and frame_bytes[1] == FrameType.ELRS_TELEM:
            if linked:
                # Simulate active link with synthetic signal values
                buf = bytearray(frame_bytes)
                # data_field1: simulate RSSI ~-65 dBm in high byte
                struct.pack_into('<H', buf, 11, 0x4100)  # high=0x41=65 -> -65 dBm
                # timing: keep 20000us (50Hz)
                # link_status: simulate LQ ~95%
                struct.pack_into('<H', buf, 15, 95)  # LQ hypothesis
                # Recompute checksum
                init = CRC_INIT_VALUES.get(FrameType.ELRS_TELEM, 0x00)
                buf[-1] = compute_crc8(bytes(buf[1:-1]), init)
                frame_bytes = bytes(buf)
            modified_frames.append((t, frame_bytes))
        else:
            modified_frames.append((t, frame_bytes))

    if fmt == 'table':
        formatter = TableFormatter()
        print(formatter.format_header())
        print(f'  Mode: Simulated ({duration:.1f}s, {"linked" if linked else "idle"})')
        print(f'  Generated {len(modified_frames)} total frames')
        print()

        for t, frame_bytes in modified_frames:
            ts_ms = t * 1000.0
            for kind, obj in decoder.feed(frame_bytes, timestamp_ms=ts_ms):
                if kind == 'elrs':
                    print(formatter.format_elrs(obj))
                elif kind == 'extended':
                    print(formatter.format_extended(obj))

        print(formatter.format_summary(decoder.state))

    elif fmt == 'json':
        json_fmt = JSONFormatter()
        for t, frame_bytes in modified_frames:
            ts_ms = t * 1000.0
            for kind, obj in decoder.feed(frame_bytes, timestamp_ms=ts_ms):
                if kind == 'elrs':
                    json_fmt.add_elrs(obj)
                elif kind == 'extended':
                    json_fmt.add_extended(obj)

        print(json_fmt.finalize(decoder.state))


# ===================================================================
# Mode: Live monitoring via strace
# ===================================================================

def mode_live(fmt='table', duration=0):
    """Monitor live ELRS telemetry from /dev/ttyS0 via strace.

    Uses strace to sniff serial data without requiring direct port access
    (the app holds the port lock). Requires root.
    """
    import glob
    import re

    # Check root
    if os.geteuid() != 0:
        print('Error: Live mode requires root (for strace).', file=sys.stderr)
        print('Run with: su -c "python3 elrs_decoder.py live"', file=sys.stderr)
        sys.exit(1)

    # Find the process holding ttyS0
    tty_pid = None
    for fd_dir in glob.glob('/proc/*/fd'):
        try:
            pid = fd_dir.split('/')[2]
            if not pid.isdigit():
                continue
            for fd_link in glob.glob(f'{fd_dir}/*'):
                try:
                    target = os.readlink(fd_link)
                    if '/dev/ttyS0' in target:
                        tty_pid = pid
                        break
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            continue
        if tty_pid:
            break

    if not tty_pid:
        print('Error: No process found with /dev/ttyS0 open.', file=sys.stderr)
        print('Is the FlyShark app running?', file=sys.stderr)
        sys.exit(1)

    print(f'Found ttyS0 held by PID {tty_pid}', file=sys.stderr)

    # Start strace
    cmd = ['strace', '-p', tty_pid, '-e', 'trace=read', '-e', 'read=3,4,5,6,7,8,9,10',
           '-s', '256', '-x']
    if duration > 0:
        cmd = ['timeout', str(duration)] + cmd

    decoder = ELRSDecoder()

    if fmt == 'table':
        formatter = TableFormatter()
        print(formatter.format_header())
        print(f'  Mode: Live (strace on PID {tty_pid})')
        print(f'  Press Ctrl+C to stop')
        print()
    else:
        json_fmt = JSONFormatter()

    hex_pattern = re.compile(r'\\x([0-9a-fA-F]{2})')

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                bufsize=1, universal_newlines=True)

        for line in proc.stderr:
            # Parse strace output for read() data
            if 'read(' not in line and '|' not in line:
                continue

            # Extract hex bytes from strace format
            hex_matches = hex_pattern.findall(line)
            if not hex_matches:
                # Try hex dump format (indented lines with hex pairs)
                parts = line.strip().split()
                hex_bytes_found = []
                for p in parts:
                    if len(p) == 2:
                        try:
                            hex_bytes_found.append(int(p, 16))
                        except ValueError:
                            continue
                if hex_bytes_found:
                    raw = bytes(hex_bytes_found)
                else:
                    continue
            else:
                raw = bytes(int(h, 16) for h in hex_matches)

            ts_ms = time.time() * 1000.0

            for kind, obj in decoder.feed(raw, timestamp_ms=ts_ms):
                if fmt == 'table':
                    if kind == 'elrs':
                        print(formatter.format_elrs(obj))
                    elif kind == 'extended':
                        print(formatter.format_extended(obj))
                else:
                    if kind == 'elrs':
                        json_fmt.add_elrs(obj)
                    elif kind == 'extended':
                        json_fmt.add_extended(obj)

    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            pass

    if fmt == 'table':
        print(formatter.format_summary(decoder.state))
    else:
        print(json_fmt.finalize(decoder.state))


# ===================================================================
# CLI Entry Point
# ===================================================================

def main():
    args = sys.argv[1:]

    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    mode = args[0]
    fmt = 'table'
    filepath = TIMED_FRAMES_PATH
    duration = 5.0
    max_frames = 0
    linked = False

    # Parse common flags
    i = 1
    while i < len(args):
        if args[i] == '--format' and i + 1 < len(args):
            fmt = args[i + 1]
            i += 2
        elif args[i] == '--file' and i + 1 < len(args):
            filepath = args[i + 1]
            i += 2
        elif args[i] == '--seconds' and i + 1 < len(args):
            duration = float(args[i + 1])
            i += 2
        elif args[i] == '--max-frames' and i + 1 < len(args):
            max_frames = int(args[i + 1])
            i += 2
        elif args[i] == '--linked':
            linked = True
            i += 1
        elif args[i] == '--no-color':
            os.environ['NO_COLOR'] = '1'
            i += 1
        else:
            i += 1

    if mode == 'decode':
        mode_decode(filepath, fmt, max_frames)
    elif mode == 'simulate':
        mode_simulate(duration, fmt, linked)
    elif mode == 'live':
        mode_live(fmt, int(duration))
    else:
        print(f'Unknown mode: {mode}', file=sys.stderr)
        print('Use: decode, simulate, or live', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
