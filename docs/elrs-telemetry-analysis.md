# ELRS Telemetry Analysis: UMBUS 0x15 Frame vs CRSF Link Statistics

**Date:** 2026-04-12
**Analyst:** Reverse engineering from binary captures + native library disassembly

## Executive Summary

The UMBUS 0x15 frame does **NOT** carry a standard CRSF `FRAMETYPE_LINK_STATISTICS` (0x14) packet. Instead, it wraps a CRSF `FRAMETYPE_HANDSET` (0x3A) extended frame with sub-command `CRSF_HANDSET_SUBCMD_TIMING` (0x10). This is an ELRS-specific protocol extension for TX module-to-handset communication. The standard 10-byte `crsfLinkStatistics_t` struct fields (RSSI, LQ, SNR, etc.) are not present in their canonical form. The data is repackaged by the AT32 MCU before transmission over the UMBUS serial link.

## Data Sources

- **Raw capture:** `~/ax12-research/captures/idle-raw-10s.bin` (50 frames, 5 Hz, 10 seconds)
- **Native library:** `libRadioMasterAX_arm64-v8a.so` (disassembled at key functions)
- **CRSF protocol:** ExpressLRS `crsf_protocol.h`, Betaflight `crsf_protocol.h`, EdgeTX `crossfire.cpp`

## UMBUS 0x15 Frame Structure (21 bytes)

### Example frame (from question):
```
a6 15 c3 02 00 ea 0d 3a ea ee 10 00 00 4e 20 00 00 2a e5 97 8e
```

### Example frame (from binary capture):
```
a6 15 c3 02 00 ea 0a 3a ea ee 10 00 00 4e 20 00 00 1a 27 9f b7
```

### Byte-level breakdown

| Byte(s) | Value | Layer | Field | Notes |
|---------|-------|-------|-------|-------|
| 0 | `A6` | UMBUS | Sync byte | UMBUS protocol sync (0xA6 = standard frame) |
| 1 | `15` | UMBUS | Frame size | 0x15 = 21 bytes total |
| 2 | `C3` | UMBUS | Channel | 0xC3 = ELRS/CRSF data channel |
| 3 | `02` | UMBUS | Routing | Destination/routing field |
| 4 | `00` | UMBUS | Subfield | Flags or sub-address |
| 5 | `EA` | CRSF | Address | `CRSF_ADDRESS_RADIO_TRANSMITTER` (0xEA) |
| 6 | `0A`/`0D` | CRSF | Frame size | CRSF frame_size **OR** data field (varies between captures) |
| 7 | `3A` | CRSF | Type | `CRSF_FRAMETYPE_HANDSET` (0x3A) |
| 8 | `EA` | CRSF | Dest | Extended header: dest = `CRSF_ADDRESS_RADIO_TRANSMITTER` |
| 9 | `EE` | CRSF | Origin | Extended header: origin = `CRSF_ADDRESS_CRSF_TRANSMITTER` |
| 10 | `10` | CRSF | Sub-cmd | `CRSF_HANDSET_SUBCMD_TIMING` (0x10) |
| 11-12 | `00 00` | Data | Field 1 | Telemetry value (zero = no link in idle) |
| 13-14 | `4E 20` | Data | Field 2 | 0x4E20 = 20000 decimal (timing/rate value) |
| 15-16 | `00 00` | Data | Field 3 | Status/validity (0x0000=valid, 0xFFFF=invalid) |
| 17 | `xx` | UMBUS | Counter | Monotonically incrementing sequence number |
| 18-20 | `yy zz ww` | UMBUS | Checksum | UMBUS CRC/checksum (3 bytes) |

### UMBUS framing details (from UMBUS_GetPack disassembly at 0x152eca8)

The UMBUS library parses 0xA6 sync frames as:
- `frame[0]` = sync (0xA6)
- `frame[1]` = total frame size
- `frame[2]` = channel/type -> `_UMBUS_MSG.byte[0x4]`
- `frame[3]` = routing -> `_UMBUS_MSG.byte[0x10]`
- `frame[4]` = subfield -> `_UMBUS_MSG.byte[0x11]`
- `frame[5+]` = data payload -> `_UMBUS_MSG.ptr[0x8]`
- Data length = `frame[1] - 6`

For our 0x15 frame: data payload = bytes 5-19 (15 bytes), UMBUS CRC at byte 20.

## CRSF Protocol Reference

### Standard CRSF_FRAMETYPE_LINK_STATISTICS (0x14)

From `crsf_protocol.h` (ExpressLRS):

```c
typedef struct crsfPayloadLinkstatistics_s {
    uint8_t uplink_RSSI_1;         // dBm * -1 (e.g., 80 = -80 dBm)
    uint8_t uplink_RSSI_2;         // dBm * -1
    uint8_t uplink_Link_quality;   // 0-100%
    int8_t  uplink_SNR;            // dB
    uint8_t active_antenna;        // 0=ant1, 1=ant2
    uint8_t rf_Mode;               // enum: 0=4fps, 1=25Hz, 2=50Hz, ...
    uint8_t uplink_TX_Power;       // enum: 0=0mW, 1=10mW, 2=25mW, 3=100mW, ...
    uint8_t downlink_RSSI_1;       // dBm * -1
    uint8_t downlink_Link_quality; // 0-100%
    int8_t  downlink_SNR;          // dB
} PACKED crsfLinkStatistics_t;     // 10 bytes
```

Standard CRSF 0x14 frame on wire:
```
[sync=0xC8/addr] [len=0x0C] [type=0x14] [10 payload bytes] [CRC8]
```

### CRSF_FRAMETYPE_HANDSET (0x3A) - Used by AX12

This is an ELRS-specific extended frame type for TX module to handset communication. The sub-command byte `CRSF_HANDSET_SUBCMD_TIMING` (0x10) is defined in the ELRS crsf_protocol.h.

### CRSF V3 Link Statistics (0x1C / 0x1D)

From Betaflight `crsf_protocol.h`:
```c
// 0x1C: RX -> FC (downlink stats)
typedef struct crsfPayloadLinkstatisticsRx_s {
    uint8_t downlink_RSSI_1;
    uint8_t downlink_RSSI_1_percentage;
    uint8_t downlink_Link_quality;
    int8_t  downlink_SNR;
    uint8_t uplink_power;
} crsfLinkStatisticsRx_t; // 5 bytes

// 0x1D: TX -> FC (uplink stats)
typedef struct crsfPayloadLinkstatisticsTx_s {
    uint8_t uplink_RSSI;
    uint8_t uplink_RSSI_percentage;
    uint8_t uplink_Link_quality;
    int8_t  uplink_SNR;
    uint8_t downlink_power;
    uint8_t uplink_FPS;
} crsfLinkStatisticsTx_t; // 6 bytes
```

These frame types are NOT used in the AX12 UMBUS 0x15 frame either.

## Native Library Analysis

### Key symbols in libRadioMasterAX_arm64-v8a.so

| Function | Address | Role |
|----------|---------|------|
| `QElrsModule::packetLinkStatistics(const crsf_header_s*)` | 0x151e828 | Handles CRSF type 0x14 (standard link stats) |
| `QElrsModule::packRxed(crsf_header_s*, uint8_t*)` | 0x151e46c | CRSF type dispatch (jump table for types 0x02-0x3A) |
| `processCrossfireTelemetryFrame(uint8_t*)` | 0x1532380 | Telemetry UI value extraction |
| `CrsfSerial::serialDataIn(const uint8_t*, int)` | 0x14fc774 | CRSF frame parser |
| `AppComHub::umbusDataPackRxed(_UMBUS_MSG*)` | 0x14fdf7c | UMBUS message dispatcher |
| `UMBUS_GetPack` | 0x152eca8 | UMBUS frame parser |
| `AppComHub::sendPack(int, uint8_t*, int, int)` | PLT stub | Sends UMBUS frames (uses channel 0xC3 for CRSF) |

### QElrsModule::packetLinkStatistics disassembly (0x151e828)

Reads the standard `crsfLinkStatistics_t` struct from a `crsf_header_s` pointer:
- `ldur x10, [x1, #0x3]` -- loads payload[0:7] (8 bytes: RSSI1 through downlink_RSSI)
- `ldurh w9, [x1, #0xb]` -- loads payload[8:9] (downlink_LQ, downlink_SNR)
- Stores all 10 bytes at `this+0x1ED` (the module's link stats cache)
- Computes `downlink_RSSI / 10` using multiply-by-205-then-shift trick
- Reports downlink_LQ and downlink_RSSI/10 to `AppRadioControl`

This function would only be called if a CRSF type 0x14 frame arrived. In idle captures, we observe only type 0x3A (HANDSET) frames.

### QElrsModule::packRxed type dispatch (0x151e46c)

Uses a jump table at `0x20265A` (rodata) for types 0x02 through 0x3A:
- Type 0x02 (GPS) -> `packetGps` at 0x151e564
- Type 0x08 (Battery) -> `packBattery` at 0x151e618
- Type 0x14 (Link Stats) -> **inlined** `packetLinkStatistics` at 0x151e574
- Type 0x1E (Attitude) -> `packetAttitude` at 0x151e628
- Type 0x29 (Device Info) -> `packDeviceInf` (handled before switch)
- Type 0x2E (ELRS Status) -> `parseElrsInfoMessage` at 0x151e5d4
- Type 0x3A (Handset) -> handled by `processCrossfireTelemetryFrame` only

All types pass through `processCrossfireTelemetryFrame` for UI telemetry extraction.

### processCrossfireTelemetryFrame type 0x3A handler (0x1532ef8)

```arm64
ldrb w8, [x19, #0x3]       // data[3] - must be 0xEA (RADIO_TRANSMITTER dest)
cmp  w8, #0xea
b.ne skip
ldrb w8, [x19, #0x5]       // data[5] - must be 0x10 (SUBCMD_TIMING)
cmp  w8, #0x10
b.ne skip
ldur s0, [x19, #0x6]       // Load 4 bytes from data[6:9]
// ... NEON identity ops (sanitization) ...
fmov w8, s0                // Move to integer register
cmn  w8, #0x1              // Skip if all 0xFF (invalid marker)
b.eq skip
mov  w0, #0xa              // sensor_id = 10
bl   getCrossfireTelemetryValue<4>
```

This handler:
1. Validates dest address = 0xEA
2. Validates sub-command = 0x10 (TIMING)
3. Reads 4 bytes of sensor data at data[6:9]
4. Skips if data is all 0xFF (invalid marker)
5. Calls `getCrossfireTelemetryValue<4>` with sensor index 10

## Captured Data Analysis (50 frames, idle state)

### Constant bytes (same in all 50 frames)

| Byte | Value | Meaning |
|------|-------|---------|
| 0 | `A6` | UMBUS sync |
| 1 | `15` | Frame size = 21 |
| 2 | `C3` | CRSF channel |
| 3 | `02` | Routing |
| 4 | `00` | Subfield |
| 5 | `EA` | CRSF_ADDRESS_RADIO_TRANSMITTER |
| 6 | `0A` | Frame size or data (constant in this capture, 0x0D in other captures) |
| 7 | `3A` | CRSF_FRAMETYPE_HANDSET |
| 8 | `EA` | Dest address |
| 9 | `EE` | Origin: CRSF_ADDRESS_CRSF_TRANSMITTER |
| 10 | `10` | CRSF_HANDSET_SUBCMD_TIMING |
| 11 | `00` | Data: zero (no receiver linked) |
| 12 | `00` | Data: zero |
| 13 | `4E` | Data: 0x4E20 high byte (= 20000) |
| 14 | `20` | Data: 0x4E20 low byte |

### Variable bytes

| Byte | Values | Pattern |
|------|--------|---------|
| 15-16 | `00 00` (40/50 frames) | Normal: valid data / no downlink |
| 15-16 | `FF FF` (10/50 frames) | Every 5th frame: invalid/timeout marker |
| 17 | `1A`..`D6` | Incrementing counter; resets for FF-FF frames |
| 18-20 | varies | UMBUS checksum/CRC |

### The every-5th-frame pattern

Every 5th frame (indices 4, 9, 14, 19, 24, ...) has bytes 15-16 = `FF FF` and byte 17 carries a different counter value. The `FF FF` acts as an "invalid data" sentinel (the native library checks for all-0xFF before processing). This 1 Hz pattern may represent a periodic link quality assessment timeout when no receiver is connected.

## The 0x4E20 = 20000 Value

The constant value 20000 at bytes 13-14 is significant:
- **20000 microseconds = 20 ms** corresponds to a **50 Hz** packet rate
- ELRS 50 Hz mode has a 20ms packet interval
- This likely represents the current ELRS packet interval / air rate configuration
- In the `CRSF_HANDSET_SUBCMD_TIMING` context, this is the TX timing reference

## What You WON'T See in Idle Captures

Since no receiver is bound/connected during idle:
- **RSSI** values are zero or minimal (only internal module noise)
- **Link Quality** is 0% (no packets received/acknowledged)
- **SNR** is 0 dB (no signal to measure)
- Standard CRSF 0x14 `LINK_STATISTICS` frames may not be generated at all
- The HANDSET 0x3A frame with SUBCMD_TIMING still runs to maintain the timing reference

To capture meaningful RSSI/LQ/SNR data, a capture with a **bound and active receiver** is needed. When a receiver is connected, the varying fields in bytes 11-16 (currently zero) should populate with actual link quality measurements, and additional CRSF frame types (0x14 link stats, 0x1C/0x1D V3 stats) may appear.

## Recommendations for Further Investigation

1. **Capture with bound receiver:** Re-capture UMBUS 0x15 frames while connected to a receiver to see populated RSSI/LQ/SNR values
2. **Monitor byte 6 changes:** Track whether byte 6 (0x0A/0x0D) changes with signal conditions -- if so, it's likely uplink RSSI
3. **Look for CRSF 0x14 frames:** With a bound receiver, additional UMBUS frames with CRSF type 0x14 may appear alongside 0x3A
4. **Check UMBUS channel 0xC3 traffic:** Filter all UMBUS frames with channel 0xC3 to find any other CRSF frame types being transported
5. **Disassemble getCrossfireTelemetryValue<4>:** (at PLT 0x17bacb0) to determine exact field extraction from the 4-byte value

## Key Files

- `/data/data/com.termux/files/home/ax12-research/captures/idle-raw-10s.bin` - Raw binary capture
- `/data/data/com.termux/files/home/ax12-research/captures/idle-analysis.md` - Initial frame analysis
- `/data/data/com.termux/files/home/ax12-research/native-lib/lib/arm64-v8a/libRadioMasterAX_arm64-v8a.so` - Native library
