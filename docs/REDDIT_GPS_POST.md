# Reddit Post Draft: AX12 GPS Discovery

**Subreddit:** r/Multicopter or r/fpv or r/RadioMaster
**Title:** Your RadioMaster AX12 has a hidden GPS receiver that nobody knew about

---

I've been reverse-engineering the RadioMaster AX12 and found something that no review, teardown, or spec sheet has mentioned: **the AX12 has a working GPS receiver.**

## The Discovery

The MediaTek MT8788 SoC in the AX12 uses an MT6631 combo chip that handles WiFi, Bluetooth, and FM radio. What RadioMaster apparently didn't realize (or chose not to expose) is that the MT6631 also includes a full multi-constellation GNSS receiver.

## What I Found

After rooting the device and digging through the kernel, I discovered:
- The GPS kernel module (`gps_drv`) is **loaded and running at boot**
- The GPS daemon (`mnld`) and assisted GPS service (`mtk_agpsd`) are **already active**
- Device nodes `/dev/stpgps` and `/dev/gps_emi` exist
- The MediaTek GPS test app (`com.mediatek.ygps`) is installed but hidden

When I started the GPS test app, the radio immediately saw **19 satellites** across GPS, GLONASS, and BeiDou constellations. WiFi-assisted positioning gave me a fix accurate to 13 meters within seconds. Full GNSS lock requires outdoor sky view but the hardware is 100% functional.

## Why This Matters

Your drone transmitter now knows where **you** are. This enables:
- **Pilot position tracking** - see yourself on a map
- **Return-to-pilot** calculations
- **Distance to drone** display from the radio itself
- **ATAK/TAK integration** - the transmitter becomes a node on the tactical map
- **GPS logging** - track your flying sessions geographically
- **Multi-pilot coordination** - everyone's position on a shared map

## How to Access It

You need root access (Magisk). Then:
```bash
# Start the GPS app
am start -n com.mediatek.ygps/.YgpsActivity

# Or use the command-line tool from the ax12-research project
python3 tools/gps_tool.py position
```

The GPS data is accessible through Android's standard Location APIs once the YGPS app or location service is activated.

## Other Discoveries from the Same Session

While I was in there, I also confirmed:
- **FM Radio** - the MT6631 has a fully functional FM receiver (chip ID 0x6631). Controllable via ioctl. Whether the antenna path is connected to the headphone jack needs more testing.
- **9-DOF IMU** - ICM-42607 with 400Hz gyroscope, 125Hz accelerometer, and 50Hz magnetometer. Head tracking anyone?
- **USB HID Gamepad** - kernel has CONFIG_USB_F_HID compiled in. The AX12 can present itself as a USB gamepad to any PC. Plug into your simulator, no drivers needed.
- **AI Accelerator** - MediaTek VPU/APU neural network hardware with NNAPI support
- **HDMI Output** - ITE IT66121 HDMI transmitter for screen mirroring to external displays

## Open Source

All tools are at **github.com/rmeadomavic/ax12-research** - the first (and currently only) open-source development toolkit for the AX12. Includes:
- GPS position tool with Google Maps links
- UMBUS protocol fully decoded (8 frame types, CRC-8/MAXIM)
- .rcm model format reverse-engineered with backup/restore
- ELRS telemetry decoder
- USB gamepad mode
- 13 Lua scripts (CCIP targeting, TAK OSD, compass, race timer, preflight checklist, etc.)
- 30+ Python tools total

The AX12 is way more capable than anyone realized. RadioMaster put a phone-grade SoC in a transmitter and we're just starting to unlock what it can do.

---

*Tested on AX12 firmware K908-V2.0, Android 9, rooted with Magisk, Termux + Claude Code for development.*

