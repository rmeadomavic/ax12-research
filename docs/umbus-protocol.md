# UMBUS Protocol Specification

RadioMaster's proprietary internal bus protocol for communication between the Android SoC (MT8788) and the AT32 MCU over UART.

**Transport:** `/dev/ttyS0` @ 921,600 baud, 8N1  
**Bandwidth:** ~2,414 bytes/sec (~19.3 kbps, ~2% of link capacity)  
**Direction ratio:** 97.9% MCU→App, 2.1% App→MCU

## Frame Format

Every UMBUS frame follows this structure:

```
┌──────┬──────────┬─────────┬─────────┬──────────┐
│ Sync │ Type/Len │ Header  │ Payload │ Checksum │
│ 0xA6 │ 1 byte   │ 2+ bytes│ variable│ 1 byte   │
└──────┴──────────┴─────────┴─────────┴──────────┘
```

- **Sync byte:** Always `0xA6`
- **Type/Length byte:** Serves as both frame type identifier AND total frame length for most types (e.g., `0x57` = type CHANNEL_DATA, total length = 87 bytes)
- **Header:** Encodes routing information (source/destination)
- **Payload:** Frame-type-specific data
- **Checksum:** Last byte, algorithm unknown (not simple XOR or CRC8)

### Header Encoding

Bytes 2-3 encode source/destination:

| Bytes 2-3 | Source | Context |
|-----------|--------|---------|
| `10 02` | MCU | Standard MCU→App frames (0x57, 0x08) |
| `10 04` | App | Standard App→MCU frames (0x0e, 0x0c) |
| `02 04` | MCU | Extended telemetry (0x10, reversed order) |
| `c3 02` | ELRS module | ELRS/RF telemetry (0x15) |
| `35 04` | App | Heartbeat response (0x08 App variant) |
| `2b 04` | App | Keep-alive (0x07) |

### UMBUS Addresses

| Constant | Value | Purpose |
|----------|-------|---------|
| `COM_UMBUS_ADD_RC` | — | Radio controller (AT32 MCU) |
| `COM_UMBUS_ADD_FC` | — | Flight controller (external) |
| `COM_UMBUS_ADD_GIMBAL` | — | Camera gimbal (external) |

## Frame Types

### MCU → App

#### 0x57 — Channel Data (25 Hz)

The primary data frame. Sent every 40ms, contains all gimbal axes and output channel values.

**Size:** 87 bytes  
**Header:** `10 02 04 01`

```
Offset  Size  Type     Description
------  ----  ----     -----------
0       1     u8       Sync (0xA6)
1       1     u8       Type (0x57)
2-3     2     u8[2]    Header (10 02)
4       1     u8       Sub-header (04)
5       1     u8       Sub-type (01 = channel group)
6-7     2     s16le    Gimbal axis 0 (range: ~-500 to +500)
8-9     2     s16le    Gimbal axis 1
10-11   2     s16le    Gimbal axis 2
12-13   2     s16le    Gimbal axis 3
14-17   4     u8[4]    Unknown (varies slightly)
18-19   2     u16le    Channel 0 output
20-21   2     u16le    Channel 1 output
...                    (continues for all channels)
82-83   2     u16le    Last channel pair
84      1     u8       Unknown
85      1     u8       Sequence counter (incrementing)
86      1     u8       Checksum (algorithm unknown)
```

**Gimbal values** (bytes 6-13): Signed 16-bit little-endian. Range approximately -500 to +500 at center rest, full range TBD. Four axes correspond to two physical sticks (2 axes each). Axis-to-stick mapping requires physical testing.

**Channel values** (bytes 18+): Unsigned 16-bit little-endian.
- Center: `0x8000` (32768)
- Switch high: `0xFE0C` (65036)
- Switch alt: `0xFF9C` (65436)
- Min: `0x0000`, Max: `0xFFFF`

**Example:**
```hex
a6 57 10 02 04 01 03 00 ff ff b8 fe 01 00 f8 ff
9c 00 00 80 00 80 00 80 00 80 00 80 00 80 07 00
7b fe 00 80 00 80 00 80 00 80 00 80 00 80 0c fe
0c fe 00 00 0c fe 00 00 f4 01 00 80 00 80 00 80
00 80 00 80 00 80 00 80 00 80 00 80 0c fe 00 00
00 00 01 00 91 01 44
```

#### 0x08 — Heartbeat (4 Hz)

Simple status frame. Content is always identical during normal operation.

**Size:** 7 bytes  
**Content (fixed):** `a6 08 10 02 04 03 00`

#### 0x15 — ELRS/RF Telemetry (5 Hz)

ELRS link statistics from the RF module, relayed through the MCU.

**Size:** 21 bytes  
**Header:** `c3 02` (different from standard `10 02` — routed from ELRS subsystem)

```
Offset  Size  Type     Description
------  ----  ----     -----------
0       1     u8       Sync (0xA6)
1       1     u8       Type (0x15)
2-3     2     u8[2]    Header (c3 02) — ELRS source
4-5     2     u8[2]    Constant (00 ea)
6-7     2     u8[2]    Varies slightly (RSSI? signal level?)
8-9     2     u8[2]    Constant (ea ee)
10-12   3     u8[3]    Constant (10 00 00)
13-14   2     u16le    0x4E20 = 20000 (link rate or timer?)
15-16   2     u8[2]    Link status (00 00 or ff ff)
17      1     u8       Sequence counter (incrementing)
18-20   3     u8[3]    CRC/checksum
```

**Example:**
```hex
a6 15 c3 02 00 ea 0d 3a ea ee 10 00 00 4e 20 00
00 2a e5 97 8e
```

#### 0x10 — Extended Telemetry (~3 Hz)

Extended status/config data, arrives in bursts of 3 (sub-indices 0, 1, 2) after each heartbeat cycle.

**Size:** 18 bytes  
**Header:** `02 04` (note: reversed from standard `10 02`)

```
Offset  Size  Type     Description
------  ----  ----     -----------
0       1     u8       Sync (0xA6)
1       1     u8       Type (0x10)
2-3     2     u8[2]    Header (02 04) — reversed
4       1     u8       Descriptor (06)
5       1     u8       Sub-index (0, 1, or 2)
6-7     2     u8[2]    Constant (00 00)
8-9     2     u16le    Value: 0x2000 = 8192
10-16   7     u8[7]    All zeros
17      1     u8       Checksum
```

**Examples:**
```hex
Sub 0: a6 10 02 04 06 00 00 00 20 00 00 00 00 00 00 00 00 86
Sub 1: a6 10 02 04 06 01 00 00 20 00 00 00 00 00 00 00 00 ee
Sub 2: a6 10 02 04 06 02 00 00 20 00 00 00 00 00 00 00 00 56
```

### App → MCU

The app writes at 2 Hz (every 500ms), batching multiple frames per write. Follows a strict 2-second repeating cycle:

```
T+0.000s: [0x0e]
T+0.500s: [0x08] + [0x0c] + [0x0e]
T+1.000s: [0x07] + [0x0e]
T+1.500s: [0x08] + [0x0c] + [0x0e]
```

#### 0x0E — Polling/Status Request (2 Hz)

Present in EVERY write batch. The most frequent App→MCU message.

**Size:** 14 bytes  
**Content (fixed during idle):** `a6 0e 10 04 02 02 06 83 df 00 00 00 00 2f`

#### 0x08 — Heartbeat Response (1 Hz)

App's acknowledgment of MCU heartbeat. Different payload from MCU's 0x08.

**Size:** 8 bytes  
**Content (fixed):** `a6 08 35 04 05 01 80 84`

Note: MCU heartbeat = `a6 08 10 02 04 03 00` (7B), App response = `a6 08 35 04 05 01 80 84` (8B). Same type byte, different content and size.

#### 0x0C — Config/State (1 Hz)

Always bundled with the heartbeat response.

**Size:** 12 bytes  
**Content (fixed during idle):** `a6 0c 10 04 02 81 01 01 00 00 00 7f`

#### 0x07 — Keep-alive Ping (0.5 Hz)

Lowest-frequency App→MCU message. Sent every 2 seconds.

**Size:** 7 bytes  
**Content (fixed):** `a6 07 2b 04 ff 01 f4`

## Timing Diagram (Idle State)

```
Time(ms)  MCU→App                              App→MCU
--------  -------                              -------
   0      0x57 channel data
  40      0x57 channel data
  80      0x57 channel data
 ...      (0x57 every 40ms)
 200      0x15 ELRS telemetry
 250      0x08 heartbeat                       0x0e poll
 ...
 400      0x15 ELRS telemetry
 500                                           0x08 + 0x0c + 0x0e
 600      0x15 ELRS telemetry
 750      0x08 heartbeat
 ...
 800      0x15 ELRS telemetry
1000      0x15 ELRS telemetry                  0x07 + 0x0e
 ...      0x10 extended (x3 burst)
1250      0x08 heartbeat
1500                                           0x08 + 0x0c + 0x0e
 ...
2000      (cycle repeats)                      0x0e (cycle repeats)
```

## Checksum

The last byte of each frame appears to be a checksum or CRC, but the algorithm has not been identified. Simple XOR, CRC-8 (multiple polynomials), and sum-based approaches all fail to match captured frames. This is an open research question.

## Frame Type Summary

| Type | Hex  | Size | Direction | Rate   | Description |
|------|------|------|-----------|--------|-------------|
| 0x57 | `a6 57` | 87B  | MCU→App | 25 Hz  | Channel/gimbal data |
| 0x08 | `a6 08` | 7B   | MCU→App | 4 Hz   | Heartbeat |
| 0x08 | `a6 08` | 8B   | App→MCU | 1 Hz   | Heartbeat response |
| 0x15 | `a6 15` | 21B  | MCU→App | 5 Hz   | ELRS RF telemetry |
| 0x10 | `a6 10` | 18B  | MCU→App | ~3 Hz  | Extended telemetry |
| 0x07 | `a6 07` | 7B   | App→MCU | 0.5 Hz | Keep-alive ping |
| 0x0C | `a6 0c` | 12B  | App→MCU | 1 Hz   | Config/state |
| 0x0E | `a6 0e` | 14B  | App→MCU | 2 Hz   | Poll/status request |

## CRSF Encapsulation

ELRS CRSF (Crossfire Serial) frames are transported within UMBUS. The AT32 MCU communicates directly with the ELRS RF module and wraps CRSF telemetry into UMBUS 0x15 frames. The app-side `CrsfSerial` class decodes these for display in the UI.

The MCU sends channel data to the app in 0x57 frames. The app processes mixing and sends the mixed output back to the MCU (likely via 0x0C or another App-to-MCU frame type). The MCU then re-encodes the final channel values as standard CRSF packed channels for the ELRS module.

## Tools

- `tools/umbus.py` — Python library for parsing/encoding UMBUS frames
- `tools/monitor.py` — Live channel visualization (requires root + exclusive ttyS0 access)
- `tools/strace-parser.py` — Parse UMBUS frames from strace output

## Open Questions

- [ ] Checksum algorithm (last byte of each frame; not XOR, CRC8, or sum — needs binary analysis)
- [ ] Gimbal axis-to-stick mapping (needs physical testing with one stick at a time)
- [ ] Full gimbal value range (approximate -500 to +500 observed, full range unknown)
- [ ] 0x15 field identification (which bytes are RSSI, LQ, SNR, TX power)
- [ ] 0x10 sub-index purpose (what do sub-channels 0, 1, 2 represent)
- [ ] 0x0E polling: does content change when requesting specific data?
- [ ] 0x0C config: does content change with model/settings changes?
- [ ] How CRSF frames are packed within UMBUS (exact encapsulation format)
- [ ] Channel data during active control: do additional bytes change?
- [ ] Maximum number of channels in 0x57 frame (32 theoretical, need to verify)
