# USB OTG Host Mode Testing Guide

The AX12's top USB-C port supports OTG host mode via sysfs. This lets you
connect USB peripherals (keyboards, GPS receivers, flash drives) directly
to the transmitter. The `usb_otg.py` tool toggles three MT8788 controls:
host GPIO (VBUS power), MUSB cmode, and dual_role mode.

## Prerequisites

- USB-C OTG adapter (USB-C male to USB-A female)
- SSH access via WiFi or Tailscale (ADB drops when host mode is enabled)

## Enable Host Mode

```bash
su 0 /data/data/com.termux/files/usr/bin/python3 ~/ax12-research/tools/usb_otg.py enable
# Shortcut (if shell alias configured):
usb-host
```

## Revert to Device Mode

```bash
su 0 /data/data/com.termux/files/usr/bin/python3 ~/ax12-research/tools/usb_otg.py disable
# Shortcut:
usb-device
```

## Verify

```bash
su 0 python3 ~/ax12-research/tools/usb_otg.py status    # role, VBUS, cmode
su 0 python3 ~/ax12-research/tools/usb_otg.py devices    # connected USB devices
su 0 dmesg | tail -30                                     # kernel enumeration logs
```

## Device Test Matrix

### USB Flash Drive
- **Expect:** `/dev/block/sdX` appears, kernel logs show `sd 0:0:0:0`
- **Test:** `su 0 mkdir -p /mnt/usb && su 0 mount /dev/block/sda1 /mnt/usb && ls /mnt/usb`
- **Cleanup:** `su 0 umount /mnt/usb`

### USB Keyboard
- **Expect:** new `/dev/input/eventX`, kernel logs show `input: ... as /devices/...`
- **Test:** `su 0 getevent -l /dev/input/eventX` then press keys
- **Use case:** text input without on-screen keyboard

### USB GPS (u-blox)
- **Expect:** `/dev/ttyACM0` appears (CDC-ACM driver)
- **Test:** `su 0 cat /dev/ttyACM0` — should print NMEA sentences (`$GNGGA,...`)
- **Use case:** precise GPS for GCS position or antenna tracker reference

### USB Ethernet (RTL8152 / AX88179)
- **Expect:** `eth0` or similar interface appears in `ip link`
- **Test:** `su 0 dhcpcd eth0 && ping -c 3 1.1.1.1`
- **Use case:** wired network when WiFi is unreliable

### USB Serial Adapter (FTDI / CH340 / CP2102)
- **Expect:** `/dev/ttyUSB0` — only if kernel has the driver compiled in
- **Check:** `su 0 python3 ~/ax12-research/tools/usb_otg.py status` reports loaded modules
- **Test:** `su 0 cat /dev/ttyUSB0` or use a Python serial reader
- **Use case:** direct MAVLink or UMBUS bridge without strace

### USB Gamepad / Joystick
- **Expect:** `/dev/input/eventX` with `EV_ABS` axes
- **Test:** `su 0 getevent -l /dev/input/eventX` then move sticks/press buttons
- **Use case:** prototype switch panel input for trainer port or sim

## Known Limitations

1. **Top USB-C only** — the bottom port is power-only, no data lines.
2. **ADB disconnects** — host mode flips the data role. Use SSH over WiFi
   or Tailscale (`ssh ax12`) for shell access while testing.
3. **VBUS power** — the AX12 must source 5V to the connected device. Some
   OTG adapters include power pass-through from an external source; use one
   if the device draws more than ~100mA.
4. **USB 3.0 devices** — the xHCI driver may not bind. Stick to USB 2.0
   devices or hubs; the MUSB controller handles USB 2.0 reliably.
5. **Driver availability** — kernel modules for FTDI/CH340/CP2102 may not
   be compiled in. Check `dmesg` for "no driver" errors after plugging in.

## Quick Reference

| Action         | Command                                      |
|----------------|----------------------------------------------|
| Enable host    | `usb_otg.py enable` (or `usb-host`)         |
| Disable host   | `usb_otg.py disable` (or `usb-device`)      |
| Check state    | `usb_otg.py status`                          |
| List devices   | `usb_otg.py devices`                         |
| Kernel logs    | `su 0 dmesg \| tail -30`                     |
