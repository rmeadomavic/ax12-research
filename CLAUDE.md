# AX12 Research

Hardware reverse engineering project for the RadioMaster AX12 transmitter.

## Device

- Android 9, MediaTek MT8788 SoC, AT32 coprocessor MCU
- Root access via `su 0` (factory userdebug build, no exploit required)
- UMBUS protocol over /dev/ttyS0 at 921600 baud, 8 frame types

## Repo

- Published at github.com/rmeadomavic/ax12-research, branch `main`
- Structure: `docs/` (protocol/, hardware/, software/, guides/), `tools/`, `captures/`, `data/`, `device-tree/`, `dashboard/`, `scripts/`
- Native `.so` and `.apk` files are gitignored -- do not commit them

## Development Rules

- All Python scripts require root: `su 0 python3 script.py`
- Python tools use stdlib only -- no external dependencies
- Preserve existing dataclass/enum patterns when editing tools
- Never read /dev/ttyS0 directly -- use strace to monitor serial traffic
  (direct reads steal bytes from the app and corrupt its state)

## Serial Monitoring

```
su 0 strace -e read,write -p <pid> -x -s 512 2>&1 | grep ttyS0
```

Attach to the process that owns the serial port. Do not open the port
from a second process.

## Ground Truth Reference

Before stating any capability as "confirmed" or "working," check this list.
The GPS error (WiFi coordinates labeled as satellite fix) survived multiple
doc iterations because each pass trusted the previous one instead of
checking evidence.

### Confirmed (captured, measured, or tested on device)

- UMBUS protocol: 8 frame types captured in idle-raw-10s.bin with frame
  counts. CRC-8/MAXIM with per-type init values validated at 99.4%+.
- Gimbal/switch/pot mapping: Verified via calibrator.py live input testing.
- MCU autonomous operation: Confirmed from umbus-mcu-standalone.bin capture
  (all frame types broadcast without Flyshark running).
- Factory root: SUID su binary at /system/xbin/su, userdebug build,
  SELinux permissive. No exploit, no Magisk.
- I2C device map: 28 devices enumerated via sysfs. Active/phantom status
  confirmed per bus scan (2026-04-13).
- GPS/NFC/camera NOT populated: Confirmed via I2C bus scan, AGC at noise
  floor, zero satellite acquisitions, thermal sensors at -127C.
- Lua dead stubs: serialRead/Write confirmed as bare ret instructions
  via disassembly.

### Inferred (from symbols, specs, or external docs — not tested on AX12)

- ELRS backpack capabilities (WiFi AP, MAVLink forwarding, VTX sync, OTA):
  Entirely from ExpressLRS documentation. ttyS1 is silent — no traffic
  captured. Backpack may not even be powered/functional.
- Three UMBUS transports (TCP, USB-HID): Symbol names exist in native lib.
  Only UART is confirmed from captures. TCP/USB-HID may be dead code.
- ELRS telemetry field mapping (bytes 11-16 = RSSI/LQ/SNR): Inferred from
  CRSF spec. All values are zero in idle captures. Needs bound receiver.
- FM radio audio: ioctl commands accepted, mixer controls writable. No
  confirmation that audio actually plays through speakers or headphones.
- MAVLink setup guide: Written from ELRS 3.5 specs and QGC docs. Never
  tested end-to-end on AX12.
- IMU data: Drivers loaded, SensorService running. Actual sensor output
  never verified against physical motion. Sensor HAL has known issues.
- Native library architecture: All from strings/readelf, no decompilation.
  Class relationships and transport claims are structural inference.
- 140ms HDMI latency: Pipeline analysis estimate, not clean end-to-end
  measurement.

### Common False Patterns to Watch For

- "Driver loaded" ≠ "hardware works" (GPS, IMU)
- "sysfs write succeeded" ≠ "hardware switched modes" (USB OTG, gamepad)
- "Tool printed success" ≠ "feature works end-to-end" (FM, CoT, MAVLink)
- "Symbol exists in .so" ≠ "code path is active" (TCP/USB-HID transports)
- "dumpsys returns coordinates" ≠ "GPS satellite fix" (WiFi location)
- "Satellites in view" ≠ "satellites acquired" (YGPS app)
