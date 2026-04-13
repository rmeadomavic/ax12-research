# OpenIPC FPV Ground Station Integration

Research on using the AX12 as an OpenIPC digital FPV ground station.

## Overview

OpenIPC uses commodity WiFi adapters in raw 802.11 broadcast mode (not standard WiFi networking) to transmit H.264/H.265 video from IP camera SoCs. The ground side receives raw packets via WFB-ng (WifiBroadcast Next Generation) with FEC for graceful degradation.

**Key insight:** This is NOT standard WiFi/RTSP. The AX12's built-in WiFi cannot receive these streams — a USB WiFi dongle with monitor mode support (RTL8812AU) is required.

## AX12 Integration Path

**PixelPilot** (Android app, GPL-3.0) can decode wfb-ng streams on Android devices using a USB RTL8812AU dongle with its bundled userspace "devourer" driver.

### Requirements

| Requirement | AX12 Status |
|---|---|
| Android arm64 | MT8788, Android 9 arm64 |
| USB OTG host mode | Confirmed via sysfs toggle (untested with physical adapter) |
| RTL8812AU USB dongle | Needs purchase (~$10-15) |
| PixelPilot APK | Available on GitHub releases |

### Setup Steps (theoretical — needs physical testing)

1. Enable USB OTG host mode: `python3 usb_otg.py enable`
2. Connect RTL8812AU via USB-C OTG adapter
3. Install PixelPilot APK
4. Launch PixelPilot — it should detect the dongle via userspace driver
5. Pair with OpenIPC air unit (channel/bandwidth must match)

## Latency Comparison

| System | Glass-to-Glass | Notes |
|---|---|---|
| Analog (legacy) | ~10-15ms | Lowest latency, lowest quality |
| HDZero | ~25-30ms | Purpose-built digital, analog-like latency |
| DJI O3/O4 | ~30-40ms | Proprietary, excellent image quality |
| Walksnail Avatar | ~25-35ms | Similar to DJI |
| **OpenIPC** | **60-100ms** | Depends on camera SoC and resolution |
| AX12 HDMI input | ~140ms | Current measurement, optimization possible |

OpenIPC at 60-100ms is competitive for cruising, long-range, and cinematic flying. Not ideal for racing where <40ms is expected.

## Cost Analysis

| Component | Cost |
|---|---|
| Camera board (GK7205V200 + IMX307) | $15-25 |
| AIO board (Mario, UltraSight) | $40-80 |
| RTL8812AU USB WiFi dongle (x2) | $8-15 each |
| USB-C OTG adapter | $5-8 |
| **Total for AX12 as GS** | **$10-23** (dongle + adapter only) |
| **Total complete system** | **$80-150** (air unit + GS dongle) |

Combined with the AX12 ($120), this enables a complete RC + digital FPV system for ~$200-270.

## Alternative Ground Station Hardware

| Platform | Notes |
|---|---|
| Radxa Zero 3W | Most popular dedicated GS, Rockchip HW decode, HDMI out |
| Orange Pi 5/5+ | RK3588, HW H.265, HDMI+VGA |
| NVR boards (HI3536DV100) | Cheapest option, HDMI+VGA |
| fpv4win (Windows) | WFB client for Windows PCs |
| Steam Deck | Community builds available |

## Supported Camera SoCs

| SoC | Sensor | Notes |
|---|---|---|
| GK7205V200 | IMX307 | Most common budget option |
| GK7205V300 | IMX307 | Slightly more capable |
| SSC338Q | IMX415 | Higher-end, NAND/NOR variants |
| Mario AIO | IMX335 | All-in-one, 30x32mm |

## Open Questions

- Does PixelPilot's userspace RTL8812AU driver work on Android 9 / kernel 4.4?
- Does the MT8788 USB OTG provide enough power for RTL8812AU (some need 500mA+)?
- Can PixelPilot and Flyshark run simultaneously without conflicts?
- Is there enough USB bandwidth for both RTL8812AU and potential GPS/ethernet dongles via hub?

## References

- PixelPilot: github.com/OpenIPC/PixelPilot (125+ stars)
- OpenIPC firmware: github.com/OpenIPC (127 repos)
- WFB-ng: github.com/svpcom/wifibroadcast
- fpv4win: github.com/OpenIPC/fpv4win
- Docs: docs.openipc.org
- Store: store.openipc.org
