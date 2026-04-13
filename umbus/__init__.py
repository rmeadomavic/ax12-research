"""
UMBUS protocol library for the RadioMaster AX12.

Decode, encode, and validate UMBUS frames — the proprietary serial protocol
between the AX12's Android SoC (MT8788) and its AT32 microcontroller.

Quick start::

    from umbus import UMBUSDecoder, UMBUSFrame, FrameType

    decoder = UMBUSDecoder()
    for frame in decoder.feed(raw_bytes):
        print(frame.summary())
        if frame.frame_type == FrameType.CHANNEL_DATA:
            print(frame.gimbals, frame.channels)

Protocol reference:
    https://github.com/rmeadomavic/ax12-research/blob/main/docs/protocol/umbus-protocol.md
"""

__version__ = "0.1.0"

from umbus.constants import (
    SYNC_BYTE,
    CHANNEL_CENTER,
    CHANNEL_MIN,
    CHANNEL_MAX,
    SWITCH_HIGH,
    SWITCH_ALT,
    NUM_GIMBALS,
    GIMBAL_OFFSET,
    CHANNEL_OFFSET,
    SOURCE_MCU,
    SOURCE_APP,
    HEARTBEAT_MCU_FIXED,
    HEARTBEAT_APP_FIXED,
    CMD_07_FIXED,
    CMD_0E_FIXED,
    CHANNEL_HEADER,
    ELRS_CRSF_ADDR_RADIO,
    ELRS_CRSF_ADDR_TX,
    ELRS_CRSF_TYPE_HANDSET,
    ELRS_SUBCMD_TIMING,
    ELRS_INVALID_MARKER,
)
from umbus.frame import FrameType, FRAME_SIZES, UMBUSAddress, UMBUSFrame
from umbus.crc import (
    CRC8_TABLE,
    CRC_INIT_VALUES,
    compute_crc8,
    compute_checksum,
    verify_checksum,
)
from umbus.decoder import UMBUSDecoder
from umbus.encoder import UMBUSEncoder
from umbus.utils import parse_strace_hex, describe_channel_value

__all__ = [
    # Version
    "__version__",
    # Core classes
    "UMBUSDecoder",
    "UMBUSEncoder",
    "UMBUSFrame",
    # Enums
    "FrameType",
    "UMBUSAddress",
    # Frame size table
    "FRAME_SIZES",
    # CRC
    "CRC8_TABLE",
    "CRC_INIT_VALUES",
    "compute_crc8",
    "compute_checksum",
    "verify_checksum",
    # Constants
    "SYNC_BYTE",
    "CHANNEL_CENTER",
    "CHANNEL_MIN",
    "CHANNEL_MAX",
    "SWITCH_HIGH",
    "SWITCH_ALT",
    "NUM_GIMBALS",
    "GIMBAL_OFFSET",
    "CHANNEL_OFFSET",
    "SOURCE_MCU",
    "SOURCE_APP",
    "HEARTBEAT_MCU_FIXED",
    "HEARTBEAT_APP_FIXED",
    "CMD_07_FIXED",
    "CMD_0E_FIXED",
    "CHANNEL_HEADER",
    "ELRS_CRSF_ADDR_RADIO",
    "ELRS_CRSF_ADDR_TX",
    "ELRS_CRSF_TYPE_HANDSET",
    "ELRS_SUBCMD_TIMING",
    "ELRS_INVALID_MARKER",
    # Utilities
    "parse_strace_hex",
    "describe_channel_value",
]
