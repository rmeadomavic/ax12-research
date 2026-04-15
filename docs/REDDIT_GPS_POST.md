# Reddit Post Draft: AX12 GPS Discovery

**Subreddit:** r/Multicopter or r/fpv or r/RadioMaster
**Title:** Your RadioMaster AX12 has a hidden GPS receiver that nobody knew about

**STATUS: DRAFT — GPS antenna situation unconfirmed. See notes below.**

---

I've been reverse-engineering the RadioMaster AX12 and found something that no review, teardown, or spec sheet has mentioned: **the AX12 has a GNSS receiver built into the MT6631 combo chip.**

## The Discovery

The MediaTek MT8788 SoC in the AX12 uses an MT6631 combo chip that handles WiFi, Bluetooth, and FM radio. What RadioMaster apparently didn't expose is that the MT6631 also includes a full multi-constellation GNSS receiver.

## What I Found

After rooting the device (factory `su` — userdebug build, no exploit needed) and digging through the kernel:
- The GPS kernel module (`gps_drv`) is **loaded and running at boot**
- The GPS daemon (`mnld`) and assisted GPS service (`mtk_agpsd`) are **already active**
- Device nodes `/dev/stpgps` and `/dev/gps_emi` exist
- The MediaTek GPS test app (`com.mediatek.ygps`) is installed but hidden
- GNSS mode 1 (GPS + GLONASS), also scans BeiDou

## What Works and What Doesn't

**Works:** The GNSS software stack is fully operational. Android's WiFi-based network location provider returns coordinates (typically ~13m accuracy from WiFi AP databases). The YGPS app launches and shows satellites being scanned.

**Doesn't work yet:** No actual GPS satellite fix has been achieved. AGC values read at the thermal noise floor, zero satellites acquired across hours of testing, and the GNSS RTC is stuck at 2000-01-01 (never obtained a time fix). This suggests the GNSS antenna may not be populated on the PCB, or has poor/no RF coupling. **Physical PCB inspection pending** — the board hasn't been opened yet to confirm antenna presence.

## Why This Matters (If the Antenna Issue Is Solved)

If an external antenna mod or antenna connection fix gets the GNSS receiver working:
- **Pilot position tracking** — see yourself on a map
- **Return-to-pilot** calculations
- **Distance to drone** display from the radio itself
- **ATAK/TAK integration** — the transmitter becomes a node on the tactical map
- **GPS logging** — track your flying sessions geographically

## How to Check on Your Device

You need root access (factory `su 0` — no Magisk required):
```bash
# Start the GPS test app
su 0 am start -n com.mediatek.ygps/.YgpsActivity

# Or use the command-line tool from the ax12-research project
su 0 python3 tools/gps_tool.py position
```

Note: `gps_tool.py` returns WiFi-based network location by default. This gives you coordinates but is NOT a GPS satellite fix. Check the `provider` field to distinguish.

## Other Discoveries

While investigating, I also confirmed:
- **FM Radio** — MT6631 FM tuner responds to ioctl commands. Antenna path (headphone jack) needs testing.
- **IMU** — ICM-42607 6-axis (driver broken in current firmware, needs RadioMaster fix)
- **HDMI Output** — IT66121 HDMI transmitter for screen mirroring
- **USB OTG** — Sysfs controls respond, needs physical testing with USB-C OTG adapter

## Open Source

All tools at **github.com/rmeadomavic/ax12-research** — the first open-source research toolkit for the AX12.

---

*Tested on AX12 firmware K908-V2.0, Android 9, factory root (userdebug build).*
