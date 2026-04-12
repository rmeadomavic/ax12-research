# UMBUS Checksum Algorithm Investigation

## Result: CRC-8/MAXIM (Dallas 1-Wire CRC)

The UMBUS checksum is **CRC-8/MAXIM**, also known as the Dallas 1-Wire CRC or DOW CRC.

| Parameter | Value |
|-----------|-------|
| Algorithm | CRC-8/MAXIM |
| Polynomial | 0x31 (normal) / 0x8C (Koopman/reflected) |
| Direction | LSB-first (reflected) |
| Init value | 0x00 for most types (see exceptions below) |
| XOR out | 0x00 |
| Check | `CRC(frame[1:-1]) == frame[-1]` |

### Computation

```python
# 256-byte lookup table, polynomial 0x8C (reflected)
CRC8_TABLE = [
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
]

def umbus_crc8(data: bytes, init: int = 0x00) -> int:
    crc = init
    for byte in data:
        crc = CRC8_TABLE[byte ^ crc]
    return crc

def umbus_checksum(frame: bytes, init: int = 0x00) -> int:
    """Compute checksum for a complete UMBUS frame.
    CRC covers bytes[1:-1] (excludes sync byte and checksum byte)."""
    return umbus_crc8(frame[1:-1], init)

def umbus_verify(frame: bytes, init: int = 0x00) -> bool:
    """Verify the checksum of a complete UMBUS frame."""
    return umbus_checksum(frame, init) == frame[-1]
```

### Byte Range

The CRC covers **all bytes except the sync byte (byte[0]) and the checksum byte (last byte)**:

```
frame = [sync] [type/len] [header...] [payload...] [checksum]
         skip   ^---- CRC covers this range ----^   compare
```

Equivalent to: `CRC8_Table_Get(frame, 1, frame_length - 2)` in the firmware.

### Init Values by Frame Type

Most frame types use init=0x00. The MCU's extended telemetry and ELRS relay subsystems use non-zero init values, likely due to a per-subsystem CRC seed on the AT32 MCU side.

| Type | Init | Direction | Verified | Notes |
|------|------|-----------|----------|-------|
| 0x57 | 0x00 | MCU->App | 246/247 | Channel data |
| 0x0E | 0x00 | App->MCU | 1/1 | Poll/status |
| 0x07 | 0x00 | App->MCU | 1/1 | Keep-alive |
| 0x0C | 0x00 | App->MCU | 1/1 | Config/state |
| 0x08 | 0x00 | App->MCU | 1/1 | App heartbeat |
| 0x10 | 0x7F | MCU->App | 30/30 | Extended telemetry |
| 0x15 | 0x32 | MCU->App | 49/50 | ELRS RF telemetry |
| 0x08 | N/A  | MCU->App | 0/40 | MCU heartbeat (see note) |

**MCU heartbeat note:** The 7-byte MCU heartbeat (`a6 08 10 02 04 03 00`) has byte[1]=0x08 suggesting an 8-byte frame, but only 7 bytes appear between sync markers. The expected 8th byte (CRC with init=0x00) would be 0x11. The checksum byte appears to be absent from the MCU's heartbeat transmission.

### Dual-Check Fallback

The `UMBUS_Decode` function maintains two parallel accumulators:
1. **CRC-8/MAXIM** (struct offset 0x34) -- primary check
2. **Running XOR** (struct offset 0x35) -- fallback check

On the TX side (`UMBUS_EndPack`), the CRC is used as the checksum byte for 0xA6/0xA7 format packets, and the XOR is used for 0xA3 format packets. On the RX side, both are tried -- if the CRC doesn't match, the XOR is checked before declaring a checksum error.

## Binary Analysis Details

### Symbols Found

| Symbol | Address | Size | Description |
|--------|---------|------|-------------|
| `CRC8_Table` | 0x2015DC | 256B | Lookup table (data) |
| `CRC8_Table_Get` | 0x14FBB70 | 64B | CRC computation function |
| `crc8` | 0x16A4784 | 48B | Standalone CRC-8 (poly 0xD5, different) |
| `crc8_BA` | 0x16A47B4 | 48B | CRSF CRC-8 (poly 0xBA, different) |
| `UMBUS_Decode` | 0x152E48C | 1332B | RX state machine with CRC check |
| `UMBUS_Fill` | 0x152EB9C | 108B | Payload data accumulator |
| `UMBUS_StartPack` | 0x152E9F4 | 424B | TX packet header builder |
| `UMBUS_EndPack` | 0x152EC08 | 160B | TX packet finalizer (appends CRC) |

### Other CRC Tables in Binary

The library contains three distinct CRC-8 lookup tables:

1. **CRC8_Table** (0x2015DC): Polynomial 0x8C reflected (0x31 normal) -- **used by UMBUS**
2. **crc8 table** (0x13DED1C): Polynomial 0xD5 (CRC-8/DVB-S2) -- used elsewhere
3. **crc8_BA table** (0x13DEE1C): Polynomial 0xBA (CRSF CRC-8) -- used for CRSF protocol

### Key Disassembly: CRC8_Table_Get

```
CRC8_Table_Get(data, offset, length):
  if length < 1: return 0
  crc = 0
  ptr = data + offset
  loop:
    byte = *ptr++
    crc = CRC8_Table[byte ^ crc]
    if --length != 0: goto loop
  return crc
```

### Key Disassembly: UMBUS_Fill CRC Update

```
UMBUS_Fill(umbus, data, length):
  for each byte in data:
    umbus->crc  = CRC8_Table[byte ^ umbus->crc]   // offset 0x36
    umbus->xor ^= byte                             // offset 0x37
  call TX callback
```

### Key Disassembly: UMBUS_Decode Checksum Verify (State 4)

```
// At 0x152E648:
if (umbus->crc_rx == received_byte)    // offset 0x34
    goto packet_valid;
if (umbus->xor_rx == received_byte)    // offset 0x35
    goto packet_valid;
// else: "UMBUS-RX CHECKSUM ERROR %x : %x"
```

## Verification Script

```python
# Verify all frames in a capture
CRC_INITS = {
    0x57: 0x00,  # channel data
    0x0E: 0x00,  # poll
    0x07: 0x00,  # keepalive
    0x0C: 0x00,  # config
    0x10: 0x7F,  # extended telemetry
    0x15: 0x32,  # ELRS telemetry
}

def verify_frame(frame: bytes) -> bool:
    frame_type = frame[1]
    init = CRC_INITS.get(frame_type, 0x00)
    return umbus_crc8(frame[1:-1], init) == frame[-1]
```

## Capture Statistics

From `idle-raw-10s.bin` (23,531 bytes):

| Type | Frames | CRC Match | Failures | Failure Cause |
|------|--------|-----------|----------|---------------|
| 0x57 | 247 | 246 | 1 | Framing error (next byte = 0x57 not 0xa6) |
| 0x10 | 30 | 30 | 0 | -- |
| 0x15 | 50 | 49 | 1 | Framing error (checksum byte = 0xa6 = sync) |
| 0x08 | 40 | N/A | 40 | Missing checksum byte in 7B frame |

Total verification rate (excluding 0x08 MCU heartbeat): **325/327 = 99.4%**

Both failures show clear signs of capture framing errors (sync byte collision), not algorithm issues.
