"""
UMBUS frame types, sizes, and the UMBUSFrame dataclass.

Each UMBUS frame starts with sync byte 0xA6, followed by a type/length byte.
For most frame types, the type byte IS the total frame length in bytes.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional
import struct

from umbus.constants import (
    CHANNEL_CENTER,
    CHANNEL_OFFSET,
    ELRS_INVALID_MARKER,
    ELRS_SUBCMD_TIMING,
    GIMBAL_OFFSET,
    NUM_GIMBALS,
    SOURCE_APP,
    SOURCE_MCU,
    SWITCH_ALT,
    SWITCH_HIGH,
)


class UMBUSAddress(IntEnum):
    """UMBUS device addresses."""

    RC = 0x01       # Radio controller (AT32 MCU)
    FC = 0x02       # Flight controller
    GIMBAL = 0x03   # Camera gimbal


class FrameType(IntEnum):
    """UMBUS frame type identifiers.

    The second byte of each frame serves double duty as the type ID and
    (for most types) the total frame length. See the protocol spec for
    exceptions.
    """

    CHANNEL_DATA = 0x57    # 87 bytes: gimbal + channel + switch data (MCU->App, 25Hz)
    HEARTBEAT_MCU = 0x08   # 7-8 bytes: heartbeat (MCU->App 7B @ 4Hz, App->MCU 8B @ 1Hz)
    EXTENDED = 0x10        # 18 bytes: extended telemetry, 3 sub-channels (MCU->App, ~3Hz)
    ELRS_TELEM = 0x15      # 21 bytes: ELRS/RF link telemetry (MCU->App, 5Hz)
    CMD_07 = 0x07          # 7 bytes: keep-alive ping (App->MCU, 0.5Hz)
    CMD_0C = 0x0C          # 12 bytes: config/state (App->MCU, 1Hz)
    CMD_0E = 0x0E          # 14 bytes: polling/status request (App->MCU, 2Hz)
    IDLE = 0x77            # 87 bytes: idle-mode channel data (same structure as 0x57)


# Known frame sizes (total bytes including sync byte).
FRAME_SIZES: dict[int, int] = {
    FrameType.CHANNEL_DATA: 87,   # 0x57 = 87 decimal
    FrameType.HEARTBEAT_MCU: 7,   # MCU sends 7B; App sends 8B (disambiguated by header)
    FrameType.EXTENDED: 18,       # 0x10 = 16 decimal, but actual frame is 18 bytes
    FrameType.ELRS_TELEM: 21,     # 0x15 = 21 decimal
    FrameType.CMD_07: 7,          # 0x07 = 7 decimal
    FrameType.CMD_0C: 12,         # 0x0C = 12 decimal
    FrameType.CMD_0E: 14,         # 0x0E = 14 decimal
    FrameType.IDLE: 87,           # Same structure as CHANNEL_DATA
}


@dataclass
class UMBUSFrame:
    """A parsed UMBUS frame.

    Attributes:
        frame_type: The frame type byte (see :class:`FrameType`).
        raw: The complete raw frame bytes including sync and checksum.
        checksum_valid: Whether the CRC-8 checksum verified correctly.
    """

    frame_type: int
    raw: bytes
    checksum_valid: bool = True

    @property
    def type_name(self) -> str:
        """Human-readable frame type name."""
        try:
            return FrameType(self.frame_type).name
        except ValueError:
            return f"UNKNOWN_0x{self.frame_type:02X}"

    @property
    def gimbals(self) -> Optional[list[int]]:
        """Extract 4 signed 16-bit gimbal values (channel data frames only)."""
        if self.frame_type not in (FrameType.CHANNEL_DATA, FrameType.IDLE):
            return None
        if len(self.raw) < GIMBAL_OFFSET + NUM_GIMBALS * 2:
            return None
        values = []
        for i in range(NUM_GIMBALS):
            offset = GIMBAL_OFFSET + i * 2
            val = struct.unpack_from("<h", self.raw, offset)[0]
            values.append(val)
        return values

    @property
    def channels(self) -> Optional[list[int]]:
        """Extract unsigned 16-bit channel values (channel data frames only)."""
        if self.frame_type not in (FrameType.CHANNEL_DATA, FrameType.IDLE):
            return None
        if len(self.raw) < CHANNEL_OFFSET + 2:
            return None
        values = []
        for offset in range(CHANNEL_OFFSET, len(self.raw) - 3, 2):
            if offset + 2 > len(self.raw):
                break
            val = struct.unpack_from("<H", self.raw, offset)[0]
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
            val = struct.unpack_from("<H", self.raw, offset)[0]
            values.append(val)
        return values

    @property
    def source(self) -> Optional[str]:
        """Identify frame direction from header bytes.

        Returns ``'MCU->App'`` or ``'App->MCU'`` based on byte 3.

        Exception: EXTENDED (0x10) uses reversed header ``02 04`` but is
        MCU->App.
        """
        if len(self.raw) < 4:
            return None
        b2, b3 = self.raw[2], self.raw[3]
        if self.frame_type == FrameType.EXTENDED and b2 == 0x02 and b3 == 0x04:
            return "MCU->App"
        if b3 == SOURCE_MCU:
            return "MCU->App"
        elif b3 == SOURCE_APP:
            return "App->MCU"
        return None

    @property
    def elrs_telemetry(self) -> Optional[dict]:
        """Parse ELRS/RF telemetry fields (0x15 frames only).

        Returns a dict with CRSF address, frame type, sub-command, timing
        interval, link status, and sequence counter.
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
        data_field1 = struct.unpack_from("<H", self.raw, 11)[0]
        timing_us = struct.unpack_from(">H", self.raw, 13)[0]
        link_status = struct.unpack_from("<H", self.raw, 15)[0]
        seq = self.raw[17]
        return {
            "crsf_addr": crsf_addr,
            "crsf_size": crsf_size,
            "crsf_type": crsf_type,
            "crsf_dest": crsf_dest,
            "crsf_origin": crsf_origin,
            "sub_cmd": sub_cmd,
            "data_field1": data_field1,
            "timing_us": timing_us,
            "link_status": link_status,
            "link_valid": link_status != ELRS_INVALID_MARKER,
            "seq": seq,
        }

    @property
    def extended_telemetry(self) -> Optional[dict]:
        """Parse extended telemetry fields (0x10 frames only).

        Returns a dict with sub-index, descriptor, and value fields.
        """
        if self.frame_type != FrameType.EXTENDED:
            return None
        if len(self.raw) < 18:
            return None
        descriptor = self.raw[4]
        sub_index = self.raw[5]
        value = struct.unpack_from("<H", self.raw, 8)[0]
        return {
            "descriptor": descriptor,
            "sub_index": sub_index,
            "value": value,
        }

    def hexdump(self, width: int = 16) -> str:
        """Return a hex dump of the raw frame."""
        lines = []
        for i in range(0, len(self.raw), width):
            chunk = self.raw[i : i + width]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"  {i:04x}  {hex_part:<{width * 3}}  {ascii_part}")
        return "\n".join(lines)

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
            parts.append(
                f"  Gimbals: G0={g[0]:+5d}  G1={g[1]:+5d}  "
                f"G2={g[2]:+5d}  G3={g[3]:+5d}"
            )
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
            rate_hz = 1_000_000 / elrs["timing_us"] if elrs["timing_us"] else 0
            valid = "valid" if elrs["link_valid"] else "INVALID"
            parts.append(
                f"  CRSF: type=0x{elrs['crsf_type']:02X} "
                f"sub_cmd=0x{elrs['sub_cmd']:02X}"
                f" ({ELRS_SUBCMD_TIMING == elrs['sub_cmd'] and 'TIMING' or '?'})"
            )
            parts.append(
                f"  Timing: {elrs['timing_us']}us ({rate_hz:.0f}Hz)"
                f"  Link: {valid}  Seq: {elrs['seq']}"
            )
        ext = self.extended_telemetry
        if ext is not None:
            parts.append(
                f"  Sub-index: {ext['sub_index']}  "
                f"Descriptor: 0x{ext['descriptor']:02X}  "
                f"Value: {ext['value']} (0x{ext['value']:04X})"
            )
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
        return "\n".join(parts)
