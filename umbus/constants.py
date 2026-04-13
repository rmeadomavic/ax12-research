"""
UMBUS protocol constants.

Sync bytes, channel values, frame headers, offsets, and ELRS/CRSF identifiers
extracted from captured traffic and the RadioMaster native library.
"""

# Sync byte — every UMBUS frame begins with 0xA6
SYNC_BYTE = 0xA6

# Channel value constants
CHANNEL_CENTER = 0x8000   # 32768
CHANNEL_MIN = 0x0000
CHANNEL_MAX = 0xFFFF
SWITCH_HIGH = 0xFE0C      # 65036
SWITCH_ALT = 0xFF9C       # 65436

# Channel data layout
NUM_GIMBALS = 4            # 4 gimbal axes (2 sticks x 2 axes)
GIMBAL_OFFSET = 6          # Gimbal data starts at byte 6
CHANNEL_OFFSET = 18        # Output channels start at byte 18

# Channel data frame header (bytes 2-5 after sync+type)
CHANNEL_HEADER = bytes([0x10, 0x02, 0x04, 0x01])

# Source identification (byte 3 of most frames)
SOURCE_MCU = 0x02          # MCU-originated frames
SOURCE_APP = 0x04          # App-originated frames

# Known fixed frame contents (for identification/validation)
HEARTBEAT_MCU_FIXED = bytes.fromhex("a6 08 10 02 04 03 00".replace(" ", ""))
HEARTBEAT_APP_FIXED = bytes.fromhex("a6 08 35 04 05 01 80 84".replace(" ", ""))
CMD_0E_FIXED = bytes.fromhex(
    "a6 0e 10 04 02 02 06 83 df 00 00 00 00 2f".replace(" ", "")
)
CMD_07_FIXED = bytes.fromhex("a6 07 2b 04 ff 01 f4".replace(" ", ""))

# ELRS telemetry (0x15) CRSF constants
ELRS_CRSF_ADDR_RADIO = 0xEA    # CRSF_ADDRESS_RADIO_TRANSMITTER
ELRS_CRSF_ADDR_TX = 0xEE       # CRSF_ADDRESS_CRSF_TRANSMITTER
ELRS_CRSF_TYPE_HANDSET = 0x3A  # CRSF_FRAMETYPE_HANDSET
ELRS_SUBCMD_TIMING = 0x10      # CRSF_HANDSET_SUBCMD_TIMING
ELRS_INVALID_MARKER = 0xFFFF   # Link status invalid/timeout sentinel
