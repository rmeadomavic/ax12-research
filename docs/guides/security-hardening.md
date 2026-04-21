# AX12 Security Hardening Guide

## Risk Summary

The AX12 ships as a userdebug build with Android security patch 2019-12-05, SELinux in permissive mode, factory root, and ADB exposed over WiFi on port 5555. Any device on the same network can get an unauthenticated root shell. The MediaTek SoC is vulnerable to CVE-2020-0069 (mtk-su, local privilege escalation) and the Bluetooth stack to CVE-2020-0022 (BlueFrag, remote code execution). Treat the AX12 as a compromised device by default — harden it, isolate it, and never trust it with secrets.

## Immediate Mitigations (Applied)

These were applied on 2026-04-13 and persist across reboots where noted.

### ADB WiFi Disabled
```
su 0 setprop service.adb.tcp.port -1
su 0 stop adbd
```
> Does not persist across reboot. Add to `~/.termux/boot/` startup script.

### Baidu Location Services Disabled
```
su 0 pm disable-user com.baidu.map.location
```
> Prevents the Flyshark app's Baidu SDK from phoning home to `api.map.baidu.com` and `loc.map.baidu.com`. Does not break any transmitter functionality.

### Firewall Applied
Inbound traffic dropped except loopback, established connections, and SSH (8022). Baidu telemetry domains blocked on OUTPUT chain. See [`tools/firewall.sh`](../../tools/firewall.sh). Applied on boot via `~/.termux/boot/start-firewall.sh`.

## Additional Hardening

### Disable Unused GMS/System Services
These can be safely disabled without affecting transmitter or Termux operation:
```
su 0 pm disable-user com.google.android.gms.policy_sidecar_acs
su 0 pm disable-user com.google.android.printservice.recommendation
su 0 pm disable-user com.google.android.apps.docs
su 0 pm disable-user com.google.android.videos
su 0 pm disable-user com.google.android.music
su 0 pm disable-user com.google.android.apps.maps
su 0 pm disable-user com.android.chrome
su 0 pm disable-user com.android.email
```
> **Do NOT disable** `com.google.android.gms` entirely — Flyshark may depend on it for crash reporting or licensing checks.

### Network Isolation
- **Tailscale-only access** — SSH and remote tooling should only be reachable via Tailscale VPN. The firewall allows SSH on 8022 but Tailscale provides the authentication layer.
- **WiFi off when not needed** — toggle off from the pull-down when flying standalone. The transmitter functions fully without any network.
- **On shared/public networks** — assume hostile. The device cannot defend itself against network-level attacks targeting unpatched Android 9 services.

### Usage Discipline
- **Never sideload untrusted APKs** — CVE-2020-0069 means any app can escalate to root silently.
- **Do not use the browser** — Chrome on Android 9 is years behind on security patches. No browsing, no downloads.
- **Do not store credentials** — no SSH keys, API tokens, or passwords on-device. Use Tailscale's key management for remote access. Treat device storage as readable by any app.

## What Cannot Be Fixed

These require a firmware/OTA update from RadioMaster that will likely never ship:

| Issue | Why It's Unfixable |
|-------|-------------------|
| SELinux permissive | Policy is baked into the boot image |
| CVE-2020-0069 (mtk-su) | Kernel driver vulnerability, requires kernel patch |
| CVE-2020-0022 (BlueFrag) | Bluetooth stack fix requires system update |
| test-keys signed build | Boot image and system partition are test-signed |
| Factory root (`/system/xbin/su`) | Removal requires reflashing system partition |

## Safe Use Guidelines

| Scenario | Risk Level | Notes |
|----------|-----------|-------|
| Standalone TX, WiFi off | **Low** | No network attack surface. This is the intended use. |
| Home WiFi, Tailscale + firewall | **Medium** | Acceptable for development sessions. Keep sessions short. |
| Shared/public WiFi | **High** | Isolate on its own VLAN/SSID or avoid entirely. |
| Bluetooth enabled | **High** | BlueFrag is remotely exploitable. Disable BT when not pairing. |
