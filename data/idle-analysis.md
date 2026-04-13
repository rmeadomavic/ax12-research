# UMBUS Idle Serial Capture Analysis

**Date:** 2026-04-12
**Device:** RadioMaster AX12 (Android 9, MT8788)
**App:** com.Flyshark.RadioMasterAX (Qt6 + libQt6SerialPort)
**Serial port:** /dev/ttyS0 @ 921600 baud
**Capture duration:** 10 seconds strace + 10 seconds raw binary

## Serial Port Details

- App PID: 14356
- ttyS0 FD: 94 (also holds lock file LCK..ttyS0 on FD 105)
- Serial thread: PID 14372 (dedicated reader/writer thread)
- Read buffer size: 32768 bytes

## MCU -> App (Read) Frame Types

### 0x57 - Channel Data (25 Hz, every 40ms)
- **Size:** 87 bytes fixed
- **Rate:** 248 frames / 10s = 24.8 Hz (25 Hz nominal)
- **Example (complete frame):**
```
a6 57 10 02 04 01 03 00 ff ff b8 fe 01 00 f8 ff
9c 00 00 80 00 80 00 80 00 80 00 80 00 80 07 00
7b fe 00 80 00 80 00 80 00 80 00 80 00 80 0c fe
0c fe 00 00 0c fe 00 00 f4 01 00 80 00 80 00 80
00 80 00 80 00 80 00 80 00 80 00 80 0c fe 00 00
00 00 01 00 91 01 44
```
- **Structure observations:**
  - Bytes 0-1: `a6 57` sync + type
  - Bytes 2-3: `10 02` (common sub-header, possibly protocol version/address)
  - Byte 4: `04` (possibly payload length indicator)
  - Byte 5: `01` (possibly sub-type: channel group)
  - Bytes 6-7: vary slightly (03 00 / 02 00) - possibly stick position for CH1/2
  - Bytes 8-9: `ff ff` / `fe ff` - CH data (near center, little-endian signed)
  - Bytes 10-11: `b8 fe` / `b9 fe` - CH data
  - Remaining bytes: channel values, mostly `00 80` (center = 0x8000?) and `0c fe`
  - Last 3 bytes: appear to be a sequence counter + checksum (e.g., `91 01 44`, `92 01 dc`)
  - Byte 85 (second-to-last pair): incrementing counter (90, 91, 92, 93...)

### 0x08 - Heartbeat (4 Hz, every 250ms)
- **Size:** 7 bytes fixed
- **Rate:** 40 frames / 10s = 4 Hz
- **Frame is always identical:**
```
a6 08 10 02 04 03 00
```
- **Structure:**
  - Bytes 0-1: `a6 08` sync + type
  - Bytes 2-3: `10 02` sub-header
  - Bytes 4-6: `04 03 00` - fixed payload

### 0x15 - ELRS/RF Telemetry (5 Hz, every 200ms)
- **Size:** 21 bytes fixed
- **Rate:** 50 frames / 10s = 5 Hz
- **Example:**
```
a6 15 c3 02 00 ea 0d 3a ea ee 10 00 00 4e 20 00
00 2a e5 97 8e
```
- **Structure observations:**
  - Bytes 0-1: `a6 15` sync + type
  - Bytes 2-3: `c3 02` (differs from `10 02` used by 0x57/0x08 -- different source?)
  - Bytes 4-5: `00 ea` constant
  - Bytes 6-7: `0d 3a` / `0a 3a` - varies slightly (RSSI?)
  - Bytes 8-9: `ea ee` constant
  - Bytes 10-12: `10 00 00` constant
  - Bytes 13-14: `4e 20` = 20000 decimal (possibly link rate or timer value)
  - Bytes 15-16: `00 00` or `ff ff` (link status?)
  - Byte 17: incrementing counter (2a, 2b, 2c, 2d...)
  - Bytes 18-20: vary (checksum/CRC)

### 0x10 - Extended Telemetry/Config (grouped with heartbeat)
- **Size:** 18 bytes fixed
- **Rate:** ~30 frames / 10s, arrive in bursts of 3 after each heartbeat cycle
- **Variants (differ at byte 5 = sub-index):**
```
Sub 0: a6 10 02 04 06 00 00 00 20 00 00 00 00 00 00 00 00 86
Sub 1: a6 10 02 04 06 01 00 00 20 00 00 00 00 00 00 00 00 ee
Sub 2: a6 10 02 04 06 02 00 00 20 00 00 00 00 00 00 00 00 56
```
- **Structure observations:**
  - Bytes 0-1: `a6 10` sync + type
  - Bytes 2-3: `02 04` (note: reversed from the `10 02` in 0x57/0x08)
  - Byte 4: `06` (payload descriptor)
  - Byte 5: sub-index (0, 1, 2)
  - Bytes 6-7: `00 00` constant
  - Bytes 8-9: `20 00` = 8192 decimal (some config value?)
  - Bytes 10-16: all zeros
  - Byte 17: checksum (86, ee, 56)

## App -> MCU (Write) Frame Types

The app writes at 2 Hz (every 500ms), batching multiple frames per write.
Total: 20 writes in 10 seconds.

**Repeating 2-second cycle:**

| Time offset | Write size | Frames contained |
|---|---|---|
| T+0.000s | 14 bytes | 0x0e |
| T+0.500s | 34 bytes | 0x08 + 0x0c + 0x0e |
| T+1.000s | 21 bytes | 0x07 + 0x0e |
| T+1.500s | 34 bytes | 0x08 + 0x0c + 0x0e |

### 0x0e - Polling/Status Request (2 Hz, every 500ms)
- **Size:** 14 bytes
- **Always identical:**
```
a6 0e 10 04 02 02 06 83 df 00 00 00 00 2f
```
- Present in EVERY write (the only frame that appears in all 4 write slots)

### 0x08 - Heartbeat Response (1 Hz, every 1000ms)
- **Size:** 8 bytes
- **Always identical:**
```
a6 08 35 04 05 01 80 84
```
- Note: MCU sends `a6 08 10 02 04 03 00` (7B), app responds `a6 08 35 04 05 01 80 84` (8B)
- Different payloads = different roles (MCU heartbeat vs app heartbeat ack)

### 0x0c - Config/State (1 Hz, every 1000ms)
- **Size:** 12 bytes
- **Always identical during idle:**
```
a6 0c 10 04 02 81 01 01 00 00 00 7f
```
- Always bundled with 0x08 heartbeat response

### 0x07 - Keep-alive/Ping (0.5 Hz, every 2000ms)
- **Size:** 7 bytes
- **Always identical:**
```
a6 07 2b 04 ff 01 f4
```
- Lowest-frequency app->MCU message

## Traffic Summary

| Direction | Frame Type | Size | Rate | Notes |
|---|---|---|---|---|
| MCU->App | 0x57 (Channel) | 87B | 25 Hz | Stick/switch positions |
| MCU->App | 0x08 (Heartbeat) | 7B | 4 Hz | Fixed content |
| MCU->App | 0x15 (ELRS Telem) | 21B | 5 Hz | RF link telemetry |
| MCU->App | 0x10 (Extended) | 18B | ~3 Hz | 3 sub-channels, config |
| App->MCU | 0x0e (Poll/Status) | 14B | 2 Hz | Fixed content |
| App->MCU | 0x08 (HB Response) | 8B | 1 Hz | Heartbeat ack |
| App->MCU | 0x0c (Config) | 12B | 1 Hz | Fixed during idle |
| App->MCU | 0x07 (Keep-alive) | 7B | 0.5 Hz | Lowest frequency |

## Bandwidth

- **MCU->App:** ~87*25 + 7*4 + 21*5 + 18*3 = 2175 + 28 + 105 + 54 = **~2362 bytes/sec** (~18.9 kbps)
- **App->MCU:** (14 + 34 + 21 + 34) / 2 = **~51.5 bytes/sec** (~0.4 kbps)
- **Total:** ~2414 bytes/sec (~19.3 kbps), well within 921600 baud capacity
- **MCU dominates:** ~97.9% of traffic is MCU->App

## Common Frame Header

Most frames share a pattern after the sync+type bytes:
- 0x57: `a6 57 10 02 04 ...`
- 0x08 (MCU): `a6 08 10 02 04 ...`
- 0x0e (App): `a6 0e 10 04 02 ...`
- 0x0c (App): `a6 0c 10 04 02 ...`
- 0x08 (App): `a6 08 35 04 05 ...`
- 0x10: `a6 10 02 04 06 ...`

Bytes 2-3 after sync+type appear to encode source/destination or protocol version.
MCU frames tend to use `10 02`, app frames use `10 04`. This may indicate:
- Byte 2: protocol version or routing (0x10 = standard, 0x35 = response, 0xc3 = ELRS)
- Byte 3: source address (0x02 = MCU, 0x04 = App)

## Non-Serial Activity (from full strace)

During idle, the app's non-serial activity consists of:
- **Mali GPU ioctls** (FD 51) -- continuous UI rendering
- **GED driver ioctls** (FD 48) -- GPU enhanced driver
- **Binder transactions** (FD 11) -- Android IPC for window management
- **eventfd signaling** (FDs 52, 65) -- inter-thread wake-up for Qt event loop
- **No network I/O** during idle
- **No file I/O** during idle
- **No database operations** during idle

## Capture Files

- `idle-strace.txt` - 10s strace of read/write on FD 94 (ttyS0), 8039 lines
- `idle-strace-full.txt` - 5s full strace of all syscalls, 33770 lines
- `idle-raw-10s.bin` - 10s raw binary capture from ttyS0, 23531 bytes
