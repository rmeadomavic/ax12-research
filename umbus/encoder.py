"""
UMBUS frame encoder.

Construct valid UMBUS frames for sending to the AT32 MCU. Each method
returns complete frame bytes including sync byte and CRC-8 checksum.
"""

import struct

from umbus.constants import (
    CHANNEL_CENTER,
    CHANNEL_HEADER,
    CMD_07_FIXED,
    CMD_0E_FIXED,
    ELRS_CRSF_ADDR_RADIO,
    ELRS_CRSF_ADDR_TX,
    ELRS_CRSF_TYPE_HANDSET,
    ELRS_SUBCMD_TIMING,
    HEARTBEAT_APP_FIXED,
    HEARTBEAT_MCU_FIXED,
    NUM_GIMBALS,
    SYNC_BYTE,
)
from umbus.crc import CRC_INIT_VALUES, compute_crc8
from umbus.frame import FrameType


class UMBUSEncoder:
    """Construct UMBUS frames for sending to the MCU.

    Example::

        encoder = UMBUSEncoder()
        frame = encoder.heartbeat_app()
        serial_port.write(frame)
    """

    @staticmethod
    def _finalize(data: bytearray) -> bytes:
        """Append CRC-8/MAXIM checksum and return immutable bytes."""
        frame_type = data[1] if len(data) > 1 else 0
        init = CRC_INIT_VALUES.get(frame_type, 0x00)
        crc = compute_crc8(bytes(data[1:]), init)
        data.append(crc)
        return bytes(data)

    @staticmethod
    def heartbeat_app() -> bytes:
        """Build an App heartbeat frame (exact bytes from captures)."""
        return HEARTBEAT_APP_FIXED

    @staticmethod
    def keepalive() -> bytes:
        """Build a keep-alive frame (0x07)."""
        return CMD_07_FIXED

    @staticmethod
    def poll() -> bytes:
        """Build a polling/status request frame (0x0E)."""
        return CMD_0E_FIXED

    @staticmethod
    def channel_data(
        gimbals: list[int] | None = None,
        channels: list[int] | None = None,
        seq: int = 0,
    ) -> bytes:
        """Build a CHANNEL_DATA frame (0x57, 87 bytes).

        Args:
            gimbals: 4 signed 16-bit gimbal values (default all zeros).
            channels: Up to 32 unsigned 16-bit channel values
                      (default all ``CHANNEL_CENTER``).
            seq: Sequence counter byte (0-255).

        Returns:
            Complete 87-byte frame with valid checksum.
        """
        g = gimbals if gimbals is not None else [0, 0, 0, 0]
        ch = channels if channels is not None else [CHANNEL_CENTER] * 32

        g = (g + [0] * NUM_GIMBALS)[:NUM_GIMBALS]
        ch = (ch + [CHANNEL_CENTER] * 32)[:32]

        buf = bytearray()
        buf.append(SYNC_BYTE)
        buf.append(FrameType.CHANNEL_DATA)
        buf.extend(CHANNEL_HEADER)
        for v in g:
            buf.extend(struct.pack("<h", max(-32768, min(32767, v))))
        buf.extend(b"\x00\x00\x00\x00")  # bytes 14-17: unknown
        for v in ch:
            buf.extend(struct.pack("<H", max(0, min(65535, v))))
        buf.append(0x00)          # byte 82: unknown
        buf.append(seq & 0xFF)    # byte 83: sequence counter

        while len(buf) < 86:
            buf.append(0x00)

        return UMBUSEncoder._finalize(buf)

    @staticmethod
    def heartbeat_mcu() -> bytes:
        """Build an MCU heartbeat frame (7 bytes, no checksum)."""
        return HEARTBEAT_MCU_FIXED

    @staticmethod
    def extended_telemetry(
        sub_index: int = 0,
        descriptor: int = 0x06,
        value: int = 0,
    ) -> bytes:
        """Build an EXTENDED telemetry frame (0x10, 18 bytes).

        Args:
            sub_index: Sub-channel index (0, 1, or 2).
            descriptor: Descriptor byte (default ``0x06`` from captures).
            value: 16-bit telemetry value.

        Returns:
            Complete 18-byte frame with valid checksum.
        """
        buf = bytearray()
        buf.append(SYNC_BYTE)
        buf.append(FrameType.EXTENDED)
        buf.extend([0x02, 0x04])
        buf.append(descriptor & 0xFF)
        buf.append(sub_index & 0xFF)
        buf.extend([0x00, 0x00])
        buf.extend(struct.pack("<H", value & 0xFFFF))
        buf.extend([0x00] * 7)

        return UMBUSEncoder._finalize(buf)

    @staticmethod
    def elrs_telemetry(
        timing_us: int = 20000,
        link_status: int = 0,
        seq: int = 0,
    ) -> bytes:
        """Build an ELRS_TELEM frame (0x15, 21 bytes).

        Args:
            timing_us: Timing interval in microseconds (default 20000 = 50Hz).
            link_status: Link status word (``0xFFFF`` = invalid).
            seq: Sequence counter.

        Returns:
            Complete 21-byte frame with valid checksum.
        """
        buf = bytearray()
        buf.append(SYNC_BYTE)
        buf.append(FrameType.ELRS_TELEM)
        buf.extend([0xC3, 0x02])
        buf.append(0x00)
        buf.append(ELRS_CRSF_ADDR_RADIO)
        buf.append(0x0A)
        buf.append(ELRS_CRSF_TYPE_HANDSET)
        buf.append(ELRS_CRSF_ADDR_RADIO)
        buf.append(ELRS_CRSF_ADDR_TX)
        buf.append(ELRS_SUBCMD_TIMING)
        buf.extend([0x00, 0x00])
        buf.extend(struct.pack(">H", timing_us & 0xFFFF))
        buf.extend(struct.pack("<H", link_status & 0xFFFF))
        buf.append(seq & 0xFF)
        buf.extend([0x00, 0x00])

        return UMBUSEncoder._finalize(buf)
