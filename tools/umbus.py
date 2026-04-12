"""
UMBUS Protocol Library for RadioMaster AX12

Decode and encode UMBUS frames — the proprietary protocol used for
communication between the Android SoC (MT8788) and the AT32 MCU.

Usage:
    from umbus import UMBUSDecoder, UMBUSFrame

    decoder = UMBUSDecoder()
    for frame in decoder.feed(raw_bytes):
        print(frame)
        if frame.frame_type == FrameType.CHANNEL_DATA:
            print(f"  Gimbals: {frame.gimbals}")
            print(f"  Channels: {frame.channels}")

Protocol reference: docs/umbus-protocol.md
"""

from enum import IntEnum
from dataclasses import dataclass, field
from typing import Iterator, Optional
import struct


# --- Constants ---

SYNC_BYTE = 0xA6

# UMBUS addresses
class UMBUSAddress(IntEnum):
    RC = 0x01       # Radio controller (AT32 MCU)
    FC = 0x02       # Flight controller
    GIMBAL = 0x03   # Camera gimbal


# Frame types (second byte after sync)
# The second byte serves double duty as type ID AND frame length (total bytes)
# for most frame types. See docs/umbus-protocol.md for details.
class FrameType(IntEnum):
    CHANNEL_DATA  = 0x57   # 87 bytes: gimbal + channel + switch data (MCU→App, 25Hz)
    HEARTBEAT_MCU = 0x08   # 7-8 bytes: heartbeat (MCU→App 7B @ 4Hz, App→MCU 8B @ 1Hz)
    EXTENDED      = 0x10   # 18 bytes: extended telemetry, 3 sub-channels (MCU→App, ~3Hz)
    ELRS_TELEM    = 0x15   # 21 bytes: ELRS/RF link telemetry (MCU→App, 5Hz)
    CMD_07        = 0x07   # 7 bytes: keep-alive ping (App→MCU, 0.5Hz)
    CMD_0C        = 0x0C   # 12 bytes: config/state (App→MCU, 1Hz)
    CMD_0E        = 0x0E   # 14 bytes: polling/status request (App→MCU, 2Hz)
    IDLE          = 0x77   # 87 bytes: idle-mode channel data (same structure as 0x57)


# Known frame sizes (total including sync byte)
# For most types, size == the type/length byte itself. Exceptions noted.
FRAME_SIZES = {
    FrameType.CHANNEL_DATA: 87,   # 0x57 = 87 decimal ✓
    FrameType.HEARTBEAT_MCU: 7,   # MCU sends 7B; App sends 8B (disambiguate by header bytes)
    FrameType.EXTENDED: 18,       # 0x10 = 16 decimal but actual frame is 18 bytes
    FrameType.ELRS_TELEM: 21,     # 0x15 = 21 decimal ✓
    FrameType.CMD_07: 7,          # 0x07 = 7 decimal ✓
    FrameType.CMD_0C: 12,         # 0x0C = 12 decimal ✓
    FrameType.CMD_0E: 14,         # 0x0E = 14 decimal ✓
    FrameType.IDLE: 87,           # Same structure as CHANNEL_DATA
}

# Known fixed frame contents (for identification/validation)
HEARTBEAT_MCU_FIXED = bytes.fromhex('a6 08 10 02 04 03 00'.replace(' ', ''))
HEARTBEAT_APP_FIXED = bytes.fromhex('a6 08 35 04 05 01 80 84'.replace(' ', ''))
CMD_0E_FIXED = bytes.fromhex('a6 0e 10 04 02 02 06 83 df 00 00 00 00 2f'.replace(' ', ''))
CMD_07_FIXED = bytes.fromhex('a6 07 2b 04 ff 01 f4'.replace(' ', ''))

# Frame header bytes 2-3 encode source
# MCU frames: byte 3 = 0x02, App frames: byte 3 = 0x04
SOURCE_MCU = 0x02
SOURCE_APP = 0x04

# Channel data frame header (bytes 2-5 after sync+type)
CHANNEL_HEADER = bytes([0x10, 0x02, 0x04, 0x01])

# Channel constants
CHANNEL_CENTER = 0x8000  # 32768
CHANNEL_MIN = 0x0000
CHANNEL_MAX = 0xFFFF
SWITCH_HIGH = 0xFE0C     # 65036
SWITCH_ALT  = 0xFF9C     # 65436

NUM_GIMBALS = 4           # 4 gimbal axes (2 sticks x 2 axes)
GIMBAL_OFFSET = 6         # Gimbal data starts at byte 6
CHANNEL_OFFSET = 18       # Output channels start at byte 18

# ELRS telemetry (0x15) constants
ELRS_CRSF_ADDR_RADIO = 0xEA       # CRSF_ADDRESS_RADIO_TRANSMITTER
ELRS_CRSF_ADDR_TX    = 0xEE       # CRSF_ADDRESS_CRSF_TRANSMITTER
ELRS_CRSF_TYPE_HANDSET = 0x3A     # CRSF_FRAMETYPE_HANDSET
ELRS_SUBCMD_TIMING   = 0x10       # CRSF_HANDSET_SUBCMD_TIMING
ELRS_INVALID_MARKER  = 0xFFFF     # Link status invalid/timeout sentinel


# --- Data Classes ---

@dataclass
class UMBUSFrame:
    """A parsed UMBUS frame."""
    frame_type: int
    raw: bytes
    checksum_valid: bool = True

    @property
    def type_name(self) -> str:
        try:
            return FrameType(self.frame_type).name
        except ValueError:
            return f"UNKNOWN_0x{self.frame_type:02X}"

    @property
    def gimbals(self) -> Optional[list[int]]:
        """Extract 4 signed 16-bit gimbal values (only for channel data frames)."""
        if self.frame_type not in (FrameType.CHANNEL_DATA, FrameType.IDLE):
            return None
        if len(self.raw) < GIMBAL_OFFSET + NUM_GIMBALS * 2:
            return None
        values = []
        for i in range(NUM_GIMBALS):
            offset = GIMBAL_OFFSET + i * 2
            val = struct.unpack_from('<h', self.raw, offset)[0]  # signed 16-bit LE
            values.append(val)
        return values

    @property
    def channels(self) -> Optional[list[int]]:
        """Extract unsigned 16-bit channel values (only for channel data frames)."""
        if self.frame_type not in (FrameType.CHANNEL_DATA, FrameType.IDLE):
            return None
        if len(self.raw) < CHANNEL_OFFSET + 2:
            return None
        values = []
        # Parse from channel offset to end of frame (minus 3: unknown byte, seq counter, checksum)
        for offset in range(CHANNEL_OFFSET, len(self.raw) - 3, 2):
            if offset + 2 > len(self.raw):
                break
            val = struct.unpack_from('<H', self.raw, offset)[0]  # unsigned 16-bit LE
            values.append(val)
        return values

    @property
    def all_values(self) -> Optional[list[int]]:
        """Extract ALL 16-bit values from the frame (bytes 6 to end-1)."""
        if self.frame_type not in (FrameType.CHANNEL_DATA, FrameType.IDLE):
            return None
        values = []
        for offset in range(6, len(self.raw) - 1, 2):
            if offset + 2 > len(self.raw):
                break
            val = struct.unpack_from('<H', self.raw, offset)[0]
            values.append(val)
        return values

    @property
    def source(self) -> Optional[str]:
        """Identify frame direction from header bytes 2-3.

        Most frames use byte 3: 0x02 = MCU, 0x04 = App.
        Exception: EXTENDED (0x10) uses reversed header 02 04 but is MCU→App.
        """
        if len(self.raw) < 4:
            return None
        b2, b3 = self.raw[2], self.raw[3]
        # EXTENDED telemetry uses reversed header (02 04) but is MCU→App
        if self.frame_type == FrameType.EXTENDED and b2 == 0x02 and b3 == 0x04:
            return 'MCU→App'
        if b3 == SOURCE_MCU:
            return 'MCU→App'
        elif b3 == SOURCE_APP:
            return 'App→MCU'
        return None

    @property
    def elrs_telemetry(self) -> Optional[dict]:
        """Parse ELRS/RF telemetry fields (only for 0x15 frames).

        Returns dict with CRSF address, frame type, sub-command, timing
        interval, link status, and sequence counter.
        See docs/elrs-telemetry-analysis.md for field details.
        """
        if self.frame_type != FrameType.ELRS_TELEM:
            return None
        if len(self.raw) < 18:
            return None
        crsf_addr = self.raw[5]
        crsf_size = self.raw[6]
        crsf_type = self.raw[7]
        crsf_dest = self.raw[8]
        crsf_origin = self.raw[9]
        sub_cmd = self.raw[10]
        data_field1 = struct.unpack_from('<H', self.raw, 11)[0]
        timing_us = struct.unpack_from('>H', self.raw, 13)[0]  # big-endian 0x4E20
        link_status = struct.unpack_from('<H', self.raw, 15)[0]
        seq = self.raw[17]
        return {
            'crsf_addr': crsf_addr,
            'crsf_size': crsf_size,
            'crsf_type': crsf_type,
            'crsf_dest': crsf_dest,
            'crsf_origin': crsf_origin,
            'sub_cmd': sub_cmd,
            'data_field1': data_field1,
            'timing_us': timing_us,
            'link_status': link_status,
            'link_valid': link_status != ELRS_INVALID_MARKER,
            'seq': seq,
        }

    @property
    def extended_telemetry(self) -> Optional[dict]:
        """Parse extended telemetry fields (only for 0x10 frames).

        Returns dict with sub-index and value fields.
        See docs/umbus-protocol.md 0x10 section for field details.
        """
        if self.frame_type != FrameType.EXTENDED:
            return None
        if len(self.raw) < 18:
            return None
        descriptor = self.raw[4]
        sub_index = self.raw[5]
        value = struct.unpack_from('<H', self.raw, 8)[0]
        return {
            'descriptor': descriptor,
            'sub_index': sub_index,
            'value': value,
        }

    def hexdump(self, width: int = 16) -> str:
        """Return a hex dump of the raw frame."""
        lines = []
        for i in range(0, len(self.raw), width):
            chunk = self.raw[i:i+width]
            hex_part = ' '.join(f'{b:02x}' for b in chunk)
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            lines.append(f"  {i:04x}  {hex_part:<{width*3}}  {ascii_part}")
        return '\n'.join(lines)

    def __repr__(self) -> str:
        return f"UMBUSFrame({self.type_name}, {len(self.raw)}B)"

    def summary(self) -> str:
        """Human-readable summary of the frame contents."""
        parts = [repr(self)]
        src = self.source
        if src:
            parts[0] += f"  [{src}]"
        if self.gimbals is not None:
            g = self.gimbals
            parts.append(f"  Gimbals: G0={g[0]:+5d}  G1={g[1]:+5d}  G2={g[2]:+5d}  G3={g[3]:+5d}")
        if self.channels is not None:
            ch = self.channels
            ch_strs = []
            for i, v in enumerate(ch):
                if v == CHANNEL_CENTER:
                    ch_strs.append(f"CH{i:02d}=CENTER")
                elif v == SWITCH_HIGH:
                    ch_strs.append(f"CH{i:02d}=HIGH")
                elif v == SWITCH_ALT:
                    ch_strs.append(f"CH{i:02d}=ALT")
                else:
                    ch_strs.append(f"CH{i:02d}={v}")
            parts.append(f"  Channels: {', '.join(ch_strs)}")
        elrs = self.elrs_telemetry
        if elrs is not None:
            rate_hz = 1_000_000 / elrs['timing_us'] if elrs['timing_us'] else 0
            valid = "valid" if elrs['link_valid'] else "INVALID"
            parts.append(f"  CRSF: type=0x{elrs['crsf_type']:02X} sub_cmd=0x{elrs['sub_cmd']:02X}"
                         f" ({ELRS_SUBCMD_TIMING == elrs['sub_cmd'] and 'TIMING' or '?'})")
            parts.append(f"  Timing: {elrs['timing_us']}us ({rate_hz:.0f}Hz)"
                         f"  Link: {valid}  Seq: {elrs['seq']}")
        ext = self.extended_telemetry
        if ext is not None:
            parts.append(f"  Sub-index: {ext['sub_index']}  Descriptor: 0x{ext['descriptor']:02X}"
                         f"  Value: {ext['value']} (0x{ext['value']:04X})")
        if self.frame_type == FrameType.HEARTBEAT_MCU and len(self.raw) >= 4:
            if len(self.raw) == 8 and self.raw[2] == 0x35:
                parts.append("  App heartbeat response")
            elif len(self.raw) == 7:
                parts.append("  MCU heartbeat")
        if self.frame_type == FrameType.CMD_07:
            parts.append("  Keep-alive ping")
        if self.frame_type == FrameType.CMD_0C:
            parts.append("  Config/state")
        if self.frame_type == FrameType.CMD_0E:
            parts.append("  Poll/status request")
        return '\n'.join(parts)


# --- Checksum ---
# CRC-8/MAXIM (Dallas 1-Wire CRC), polynomial 0x31 normal / 0x8C reflected.
# Lookup table extracted from CRC8_Table symbol in libRadioMasterAX_arm64-v8a.so.
# See docs/checksum-investigation.md for full reverse-engineering details.

CRC8_TABLE = bytes([
    0x00, 0x5E, 0xBC, 0xE2, 0x61, 0x3F, 0xDD, 0x83,
    0xC2, 0x9C, 0x7E, 0x20, 0xA3, 0xFD, 0x1F, 0x41,
    0x9D, 0xC3, 0x21, 0x7F, 0xFC, 0xA2, 0x40, 0x1E,
    0x5F, 0x01, 0xE3, 0xBD, 0x3E, 0x60, 0x82, 0xDC,
    0x23, 0x7D, 0x9F, 0xC1, 0x42, 0x1C, 0xFE, 0xA0,
    0xE1, 0xBF, 0x5D, 0x03, 0x80, 0xDE, 0x3C, 0x62,
    0xBE, 0xE0, 0x02, 0x5C, 0xDF, 0x81, 0x63, 0x3D,
    0x7C, 0x22, 0xC0, 0x9E, 0x1D, 0x43, 0xA1, 0xFF,
    0x46, 0x18, 0xFA, 0xA4, 0x27, 0x79, 0x9B, 0xC5,
    0x84, 0xDA, 0x38, 0x66, 0xE5, 0xBB, 0x59, 0x07,
    0xDB, 0x85, 0x67, 0x39, 0xBA, 0xE4, 0x06, 0x58,
    0x19, 0x47, 0xA5, 0xFB, 0x78, 0x26, 0xC4, 0x9A,
    0x65, 0x3B, 0xD9, 0x87, 0x04, 0x5A, 0xB8, 0xE6,
    0xA7, 0xF9, 0x1B, 0x45, 0xC6, 0x98, 0x7A, 0x24,
    0xF8, 0xA6, 0x44, 0x1A, 0x99, 0xC7, 0x25, 0x7B,
    0x3A, 0x64, 0x86, 0xD8, 0x5B, 0x05, 0xE7, 0xB9,
    0x8C, 0xD2, 0x30, 0x6E, 0xED, 0xB3, 0x51, 0x0F,
    0x4E, 0x10, 0xF2, 0xAC, 0x2F, 0x71, 0x93, 0xCD,
    0x11, 0x4F, 0xAD, 0xF3, 0x70, 0x2E, 0xCC, 0x92,
    0xD3, 0x8D, 0x6F, 0x31, 0xB2, 0xEC, 0x0E, 0x50,
    0xAF, 0xF1, 0x13, 0x4D, 0xCE, 0x90, 0x72, 0x2C,
    0x6D, 0x33, 0xD1, 0x8F, 0x0C, 0x52, 0xB0, 0xEE,
    0x32, 0x6C, 0x8E, 0xD0, 0x53, 0x0D, 0xEF, 0xB1,
    0xF0, 0xAE, 0x4C, 0x12, 0x91, 0xCF, 0x2D, 0x73,
    0xCA, 0x94, 0x76, 0x28, 0xAB, 0xF5, 0x17, 0x49,
    0x08, 0x56, 0xB4, 0xEA, 0x69, 0x37, 0xD5, 0x8B,
    0x57, 0x09, 0xEB, 0xB5, 0x36, 0x68, 0x8A, 0xD4,
    0x95, 0xCB, 0x29, 0x77, 0xF4, 0xAA, 0x48, 0x16,
    0xE9, 0xB7, 0x55, 0x0B, 0x88, 0xD6, 0x34, 0x6A,
    0x2B, 0x75, 0x97, 0xC9, 0x4A, 0x14, 0xF6, 0xA8,
    0x74, 0x2A, 0xC8, 0x96, 0x15, 0x4B, 0xA9, 0xF7,
    0xB6, 0xE8, 0x0A, 0x54, 0xD7, 0x89, 0x6B, 0x35,
])

# Per-type CRC init values. Most types use 0x00.
# The MCU's extended telemetry and ELRS relay subsystems use non-zero seeds.
CRC_INIT_VALUES = {
    FrameType.EXTENDED:   0x7F,  # 0x10 extended telemetry
    FrameType.ELRS_TELEM: 0x32,  # 0x15 ELRS RF telemetry
}


def compute_crc8(data: bytes, init: int = 0x00) -> int:
    """Compute CRC-8/MAXIM over a byte sequence.

    Uses the Dallas 1-Wire polynomial 0x31 (reflected form 0x8C).
    """
    crc = init
    for byte in data:
        crc = CRC8_TABLE[byte ^ crc]
    return crc


def compute_checksum(frame: bytes) -> int:
    """Compute the expected checksum for a complete UMBUS frame.

    CRC covers bytes[1:-1] (excludes sync byte and checksum byte).
    Uses the per-type init value from CRC_INIT_VALUES.
    """
    frame_type = frame[1]
    init = CRC_INIT_VALUES.get(frame_type, 0x00)
    return compute_crc8(frame[1:-1], init)


def verify_checksum(frame: bytes) -> bool:
    """Verify the checksum of a complete UMBUS frame.

    Returns True if the CRC-8/MAXIM checksum matches.
    For the MCU heartbeat (7B with type 0x08), checksum validation is
    skipped because the frame appears to lack a checksum byte.
    """
    if len(frame) < 3:
        return False
    # MCU heartbeat: 7 bytes, no checksum byte (see docs/checksum-investigation.md)
    if frame[1] == 0x08 and len(frame) == 7 and frame[2] != 0x35:
        return True  # skip validation for MCU heartbeat
    return compute_checksum(frame) == frame[-1]


# --- Decoder ---

class UMBUSDecoder:
    """
    Streaming UMBUS frame decoder.

    Feed raw bytes and iterate over decoded frames:

        decoder = UMBUSDecoder()
        for frame in decoder.feed(data):
            print(frame.summary())
    """

    def __init__(self):
        self._buf = bytearray()
        self.frames_decoded = 0
        self.frames_bad_checksum = 0
        self.bytes_skipped = 0

    def feed(self, data: bytes) -> Iterator[UMBUSFrame]:
        """Feed raw bytes and yield decoded frames."""
        self._buf.extend(data)

        while True:
            # Find sync byte
            sync_idx = self._buf.find(bytes([SYNC_BYTE]))
            if sync_idx < 0:
                self.bytes_skipped += len(self._buf)
                self._buf.clear()
                return

            if sync_idx > 0:
                self.bytes_skipped += sync_idx
                del self._buf[:sync_idx]

            # Need at least 2 bytes (sync + type)
            if len(self._buf) < 2:
                return

            frame_type = self._buf[1]

            # Determine frame size
            # Special case: 0x08 can be 7B (MCU) or 8B (App), disambiguate
            if frame_type == 0x08 and len(self._buf) >= 4:
                if self._buf[2] == 0x35:  # App heartbeat header
                    frame_size = 8
                else:
                    frame_size = 7  # MCU heartbeat
            else:
                frame_size = FRAME_SIZES.get(frame_type)

            if frame_size is None:
                # Unknown frame type: the type byte IS the total length
                # for most UMBUS frames (0x57=87, 0x15=21, 0x0C=12, etc.)
                frame_size = frame_type
                if frame_size < 3 or frame_size > 256:
                    # Skip this sync byte
                    del self._buf[0]
                    self.bytes_skipped += 1
                    continue

            # Wait for full frame
            if len(self._buf) < frame_size:
                return

            raw = bytes(self._buf[:frame_size])
            del self._buf[:frame_size]

            # Verify checksum
            chk_valid = verify_checksum(raw)
            if not chk_valid:
                self.frames_bad_checksum += 1

            frame = UMBUSFrame(
                frame_type=frame_type,
                raw=raw,
                checksum_valid=chk_valid,
            )
            self.frames_decoded += 1
            yield frame

    def reset(self):
        """Reset decoder state."""
        self._buf.clear()
        self.frames_decoded = 0
        self.frames_bad_checksum = 0
        self.bytes_skipped = 0

    @property
    def stats(self) -> dict:
        return {
            "frames_decoded": self.frames_decoded,
            "frames_bad_checksum": self.frames_bad_checksum,
            "bytes_skipped": self.bytes_skipped,
            "buffer_size": len(self._buf),
        }


# --- Encoder ---

class UMBUSEncoder:
    """
    Construct UMBUS frames for sending to the MCU.

    Example:
        encoder = UMBUSEncoder()
        frame = encoder.heartbeat()
        serial_port.write(frame)
    """

    @staticmethod
    def _finalize(data: bytearray) -> bytes:
        """Append CRC-8/MAXIM checksum byte to the frame."""
        frame_type = data[1] if len(data) > 1 else 0
        init = CRC_INIT_VALUES.get(frame_type, 0x00)
        crc = compute_crc8(bytes(data[1:]), init)
        data.append(crc)
        return bytes(data)

    @staticmethod
    def heartbeat_app() -> bytes:
        """Build an App heartbeat frame (the exact bytes observed in captures)."""
        return HEARTBEAT_APP_FIXED

    @staticmethod
    def keepalive() -> bytes:
        """Build a keep-alive frame (0x07, the exact bytes observed in captures)."""
        return CMD_07_FIXED

    @staticmethod
    def poll() -> bytes:
        """Build a polling/status request frame (0x0E, the exact bytes observed in captures)."""
        return CMD_0E_FIXED

    @staticmethod
    def channel_data(gimbals: list[int] | None = None,
                     channels: list[int] | None = None,
                     seq: int = 0) -> bytes:
        """Build a CHANNEL_DATA frame (0x57, 87 bytes) with custom values.

        Args:
            gimbals: 4 signed 16-bit gimbal values (default: [0,0,0,0]).
            channels: Up to 32 unsigned 16-bit channel values (default: all CENTER).
            seq: Sequence counter byte (0-255).
        """
        g = gimbals if gimbals is not None else [0, 0, 0, 0]
        ch = channels if channels is not None else [CHANNEL_CENTER] * 32

        # Pad/truncate to expected counts
        g = (g + [0] * NUM_GIMBALS)[:NUM_GIMBALS]
        ch = (ch + [CHANNEL_CENTER] * 32)[:32]

        buf = bytearray()
        buf.append(SYNC_BYTE)                    # 0: sync
        buf.append(FrameType.CHANNEL_DATA)        # 1: type/length = 0x57
        buf.extend(CHANNEL_HEADER)                # 2-5: header 10 02 04 01
        for v in g:                               # 6-13: gimbals (s16le)
            buf.extend(struct.pack('<h', max(-32768, min(32767, v))))
        buf.extend(b'\x00\x00\x00\x00')          # 14-17: unknown (zeros)
        for v in ch:                              # 18-81: channels (u16le)
            buf.extend(struct.pack('<H', max(0, min(65535, v))))
        buf.append(0x00)                          # 82: unknown byte
        buf.append(seq & 0xFF)                    # 83: sequence counter

        # Pad to 86 bytes (before checksum)
        while len(buf) < 86:
            buf.append(0x00)

        return UMBUSEncoder._finalize(buf)

    @staticmethod
    def heartbeat_mcu() -> bytes:
        """Build an MCU heartbeat frame (7B, no checksum)."""
        return HEARTBEAT_MCU_FIXED

    @staticmethod
    def extended_telemetry(sub_index: int = 0, descriptor: int = 0x06,
                           value: int = 0) -> bytes:
        """Build an EXTENDED telemetry frame (0x10, 18 bytes).

        Args:
            sub_index: Sub-channel index (0, 1, or 2).
            descriptor: Descriptor byte (default 0x06 from captures).
            value: 16-bit telemetry value.
        """
        buf = bytearray()
        buf.append(SYNC_BYTE)                     # 0: sync
        buf.append(FrameType.EXTENDED)             # 1: type = 0x10
        buf.extend([0x02, 0x04])                   # 2-3: header (reversed for extended)
        buf.append(descriptor & 0xFF)              # 4: descriptor
        buf.append(sub_index & 0xFF)               # 5: sub-index
        buf.extend([0x00, 0x00])                   # 6-7: padding
        buf.extend(struct.pack('<H', value & 0xFFFF))  # 8-9: value
        buf.extend([0x00] * 7)                     # 10-16: padding

        return UMBUSEncoder._finalize(buf)

    @staticmethod
    def elrs_telemetry(timing_us: int = 20000, link_status: int = 0,
                       seq: int = 0) -> bytes:
        """Build an ELRS_TELEM frame (0x15, 21 bytes).

        Args:
            timing_us: Timing interval in microseconds (default 20000 = 50Hz).
            link_status: Link status word (0xFFFF = invalid).
            seq: Sequence counter.
        """
        buf = bytearray()
        buf.append(SYNC_BYTE)                     # 0: sync
        buf.append(FrameType.ELRS_TELEM)           # 1: type = 0x15
        buf.extend([0xc3, 0x02])                   # 2-3: header
        buf.append(0x00)                           # 4: padding
        buf.append(ELRS_CRSF_ADDR_RADIO)           # 5: CRSF addr 0xEA
        buf.append(0x0A)                           # 6: CRSF size
        buf.append(ELRS_CRSF_TYPE_HANDSET)         # 7: CRSF type 0x3A
        buf.append(ELRS_CRSF_ADDR_RADIO)           # 8: CRSF dest
        buf.append(ELRS_CRSF_ADDR_TX)              # 9: CRSF origin 0xEE
        buf.append(ELRS_SUBCMD_TIMING)             # 10: sub-cmd 0x10
        buf.extend([0x00, 0x00])                   # 11-12: data_field1
        buf.extend(struct.pack('>H', timing_us & 0xFFFF))  # 13-14: timing (big-endian)
        buf.extend(struct.pack('<H', link_status & 0xFFFF)) # 15-16: link status
        buf.append(seq & 0xFF)                     # 17: seq
        buf.extend([0x00, 0x00])                   # 18-19: padding

        return UMBUSEncoder._finalize(buf)


# --- Utility Functions ---

def parse_strace_hex(line: str) -> Optional[bytes]:
    """
    Parse hex data from strace output lines.

    Handles formats like:
        read(103, "\\xa6\\x57\\x10\\x02...", 4096) = 87
        | 00000  a6 57 10 02 04 01 ...  |
    """
    # Try strace escaped string format
    if '\\x' in line:
        import re
        hex_bytes = re.findall(r'\\x([0-9a-fA-F]{2})', line)
        if hex_bytes:
            return bytes(int(h, 16) for h in hex_bytes)

    # Try hex dump format
    line = line.strip()
    if line.startswith('|'):
        line = line.strip('|').strip()
    parts = line.split()
    hex_bytes = []
    for p in parts:
        if len(p) == 2:
            try:
                hex_bytes.append(int(p, 16))
            except ValueError:
                continue
    if hex_bytes:
        return bytes(hex_bytes)

    return None


def describe_channel_value(value: int) -> str:
    """Describe a channel value in human-readable terms."""
    if value == CHANNEL_CENTER:
        return "CENTER"
    elif value == SWITCH_HIGH:
        return "SW_HIGH"
    elif value == SWITCH_ALT:
        return "SW_ALT"
    elif value == CHANNEL_MIN:
        return "MIN"
    elif value == CHANNEL_MAX:
        return "MAX"
    else:
        # Show as percentage relative to center
        pct = (value - CHANNEL_CENTER) / CHANNEL_CENTER * 100
        return f"{value} ({pct:+.1f}%)"


# --- CLI ---

def main():
    """Command-line interface for parsing UMBUS data."""
    import sys
    import os

    if len(sys.argv) < 2:
        print("Usage: python umbus.py <file.bin|->")
        print("       python umbus.py --live    (read from ttyS0 as root)")
        print()
        print("Parse UMBUS frames from binary data or live serial port.")
        sys.exit(1)

    decoder = UMBUSDecoder()

    if sys.argv[1] == '--live':
        # Live mode: read from ttyS0
        fd = os.open('/dev/ttyS0', os.O_RDONLY | os.O_NONBLOCK)
        import time
        try:
            print("Reading from /dev/ttyS0... (Ctrl+C to stop)")
            while True:
                try:
                    data = os.read(fd, 4096)
                    for frame in decoder.feed(data):
                        print(frame.summary())
                        print()
                except BlockingIOError:
                    time.sleep(0.01)
        except KeyboardInterrupt:
            pass
        finally:
            os.close(fd)
    elif sys.argv[1] == '-':
        # Read from stdin
        data = sys.stdin.buffer.read()
        for frame in decoder.feed(data):
            print(frame.summary())
    else:
        # Read from file
        with open(sys.argv[1], 'rb') as f:
            data = f.read()
        for frame in decoder.feed(data):
            print(frame.summary())

    print(f"\n--- Stats: {decoder.stats}")


if __name__ == '__main__':
    main()
