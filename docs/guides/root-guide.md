# AX12 Root & Developer Setup Guide

How to turn your RadioMaster AX12 into a full development platform with remote SSH access and root.

## What You Need

- RadioMaster AX12 (running stock RadioMasterOS / Android 9)
- WiFi network (AX12 and your computer on the same network)
- A computer (Windows/Mac/Linux) for initial setup
- ~30 minutes

## Step 1: Enable Developer Options

1. Open **Settings** on the AX12 (swipe down from top, tap the gear icon)
2. Scroll to **About phone** (or **About tablet**)
3. Tap **Build number** 7 times — you'll see "You are now a developer!"
4. Go back to Settings → **Developer options**
5. Enable **USB debugging**
6. Enable **ADB over network** (also called "ADB over WiFi" or "Wireless debugging")
7. Note the IP address shown (e.g., `192.168.1.xxx:5555`)

## Step 2: Install Termux

Termux is a terminal emulator and Linux environment for Android. **Do NOT install from Google Play** — that version is outdated and broken.

### Option A: Via F-Droid (Recommended)
1. On the AX12, open the browser
2. Go to `f-droid.org`
3. Download and install the F-Droid app
4. Open F-Droid, search for "Termux"
5. Install Termux and Termux:API

### Option B: Via ADB from your computer
1. Download the Termux APK from the [F-Droid Termux page](https://f-droid.org/en/packages/com.termux/) or [GitHub releases](https://github.com/termux/termux-app/releases)
2. Connect to the AX12 via ADB:
   ```
   adb connect <AX12_IP>:5555
   adb install termux.apk
   ```

## Step 3: Set Up Termux

Open Termux on the AX12 and run:

```bash
# Update package repos
pkg update && pkg upgrade -y

# Install essentials
pkg install -y openssh python nodejs git curl wget

# Optional but recommended
pkg install -y binutils dtc strace
```

### Set up SSH for remote access

```bash
# Set a password for SSH login
passwd

# Start the SSH server
sshd

# Find the AX12's IP
ifconfig wlan0 | grep inet
```

SSH runs on port **8022** (not 22). Connect from your computer:
```bash
ssh -p 8022 <AX12_IP>
```

### Make SSH start automatically

Termux doesn't have a traditional init system. You can use Termux:Boot to auto-start sshd, or just run `sshd` each time you open Termux.

To install Termux:Boot:
1. Install from F-Droid
2. Open it once (to register the boot receiver)
3. Create the boot script:
   ```bash
   mkdir -p ~/.termux/boot
   echo '#!/data/data/com.termux/files/usr/bin/bash
   sshd' > ~/.termux/boot/start-sshd.sh
   chmod +x ~/.termux/boot/start-sshd.sh
   ```

## Step 4: Install Tailscale (Persistent Remote Access)

Tailscale gives you a stable, encrypted connection to the AX12 from anywhere — no port forwarding needed.

1. Download the Tailscale APK on the AX12:
   - Open the browser → `tailscale.com/download/android`
   - Or install via ADB: download the APK on your computer and `adb install tailscale.apk`
2. Open Tailscale, sign in with your account
3. The AX12 will appear in your Tailscale network with a stable IP (e.g., `100.x.x.x`)
4. SSH from anywhere: `ssh -p 8022 100.x.x.x`

**Note:** You may need to manually start Tailscale after each reboot. Open the Tailscale app and toggle the connection on.

## Step 5: Install Claude Code CLI

Claude Code provides an AI-powered terminal assistant that runs directly on the AX12.

```bash
# Install via npm (Node.js must be installed first — see Step 3)
npm install -g @anthropic-ai/claude-code

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Add to your .bashrc so it persists
echo 'export ANTHROPIC_API_KEY="sk-ant-YOUR_KEY_HERE"' >> ~/.bashrc

# Launch Claude Code
claude
```

## Step 6: Root Access

### The Good News: Factory Root

The AX12 ships with a root binary pre-installed. This isn't a hack — RadioMaster included it in the firmware (it's a `userdebug` build).

```bash
# From Termux, get a root shell:
su 0 id
# Output: uid=0(root) gid=0(root) groups=0(root)

# Run any command as root:
su 0 cat /proc/partitions
su 0 ls -la /dev/ttyS0
```

**Important:** `su 0 <command>` runs a single command as root. For a full root shell: `su 0 sh`.

The Termux `su` binary is NOT in root's PATH, so always use full paths when running Termux tools as root:
```bash
# This fails:
su 0 python3 myscript.py

# This works:
su 0 /data/data/com.termux/files/usr/bin/python3 myscript.py
```

### ADB Root

If connected via ADB (USB or WiFi):
```
adb root
adb shell
# You're now root
```

### What About mtk-su?

The AX12 uses a MediaTek MT8788 SoC. You might find references to `mtk-su` (CVE-2020-0069), a well-known MediaTek kernel exploit. **It does NOT work on MT8788** — the exploit's payload database doesn't include this chipset. You'll get:

```
Failed critical init step 4 - This firmware cannot be supported
```

This doesn't matter since factory `su` is available.

### Persistent Root with Magisk (Advanced)

**Status: Work in Progress**

The AX12's boot chain makes Magisk installation challenging:

1. **dm-verity is enforcing** — the kernel verifies the boot partition on every boot. If the boot image is modified (e.g., patched by Magisk), dm-verity detects the change and reverts it.

2. **eMMC write protection** — the boot partition device (`/dev/block/mmcblk0p28`) is hardware write-protected. Direct `dd` writes appear to succeed but don't persist.

3. **Whole-disk bypass** — writing to the raw eMMC device (`/dev/block/mmcblk0`) at the boot partition's sector offset (964608) DOES bypass the partition-level write protection. The write persists through a reboot.

4. **But dm-verity wins** — even though the patched boot image is physically on disk, dm-verity detects the modification during boot and restores the original.

**Current approach under investigation:**
- Disabling dm-verity via `adb disable-verity` (requires unlocked bootloader)
- Bootloader unlock via `fastboot flashing unlock` (untested, could brick)
- Custom kernel with dm-verity disabled

**For most development purposes, `su 0` provides everything you need.** Magisk is only necessary if you need root access from apps (not Termux) or want Magisk modules.

## Step 7: Verify Everything Works

```bash
# Test SSH (from your computer)
ssh -p 8022 <AX12_IP_or_Tailscale_IP>

# Test root
su 0 id

# Read serial data (the MCU communication bus)
su 0 cat /dev/ttyS0 | xxd | head -20

# Check device tree
su 0 ls /proc/device-tree/

# List all hardware
su 0 ls /dev/

# Check running processes
su 0 ps -A | grep -i shark
```

## Troubleshooting

### SSH connection refused
- Make sure `sshd` is running in Termux: just type `sshd`
- Check the port: Termux SSH is on **8022**, not 22
- Check firewall: the AX12's Android firewall might block connections

### Can't find AX12 on network
- Make sure WiFi is connected on the AX12
- Try `adb connect <IP>:5555` from a computer on the same network
- Use Tailscale for a reliable connection

### `su 0` gives "permission denied"
- This shouldn't happen on stock RadioMasterOS — the `su` binary is pre-installed
- Check: `ls -la /system/xbin/su` should show `-rwsr-sr-x` (SUID bit set)
- Try: `adb root` then `adb shell` as an alternative

### Termux apps not found as root
- Root shell doesn't have Termux's PATH. Always use full paths:
  ```bash
  su 0 /data/data/com.termux/files/usr/bin/python3 script.py
  ```

### Serial port busy
- The RadioMaster app holds `/dev/ttyS0` exclusively when running
- Don't try to read ttyS0 directly — use `strace` on the app process instead:
  ```bash
  su 0 strace -e trace=read,write -p $(su 0 pidof com.Flyshark.RadioMasterAX)
  ```
- Two processes reading ttyS0 simultaneously will corrupt the data stream

### Tailscale disconnects after sleep
- Open Tailscale and re-enable the connection
- Consider disabling battery optimization for Tailscale in Android settings

## System Information

| Property | Value |
|----------|-------|
| SoC | MediaTek MT8788 (device tree: mt6771) |
| CPU | Octa-core ARM64 |
| RAM | 4GB |
| Storage | 64GB eMMC |
| Kernel | Linux 4.4.146 |
| Android | 9 (Pie) |
| Build | userdebug (RadioMasterOS) |
| SELinux | Permissive |
| Security Patch | 2019-12-05 |
| Root | Factory su at /system/xbin/su |
| Display | 5.5" 1280x720 touchscreen |
| Battery | 10,000mAh |
