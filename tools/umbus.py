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
    FrameType.EXTENDED: 18,       # 0x10 = 16 but actual is 18 (2 extra bytes)
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
        return '\n'.join(parts)


# --- Checksum ---
# NOTE: The checksum algorithm has NOT been verified. Simple XOR, CRC8, and
# sum-based approaches all fail to match real captured frames. The last byte
# of each frame appears to be a checksum but the algorithm is unknown.
# Until identified, checksum validation is disabled (always returns True).

def verify_checksum(frame: bytes) -> bool:
    """Verify the checksum of a complete UMBUS frame.

    Currently always returns True — the checksum algorithm has not been
    reverse-engineered yet. The last byte of each frame varies in a way
    consistent with a checksum, but no standard algorithm (XOR, CRC8,
    sum mod 256) matches the captured data.
    """
    return True


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
        """Add placeholder checksum byte. The real algorithm is unknown."""
        data.append(0x00)  # Placeholder: real checksum algorithm TBD
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
