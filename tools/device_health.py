#!/data/data/com.termux/files/usr/bin/python3
"""
AX12 Device Health Check — comprehensive one-shot diagnostic.

Run with no args for a full color report, or --json for machine-readable output.

Usage:
    python3 tools/device_health.py
    python3 tools/device_health.py --json
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ── ANSI colors ──────────────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    HEADER = "\033[1;96m"

def ok(text):    return f"{C.GREEN}OK{C.RESET}   {text}"
def warn(text):  return f"{C.YELLOW}WARN{C.RESET} {text}"
def fail(text):  return f"{C.RED}FAIL{C.RESET} {text}"
def info(text):  return f"{C.DIM}INFO{C.RESET} {text}"

def section(title):
    bar = "─" * (60 - len(title) - 2)
    return f"\n{C.HEADER}── {title} {bar}{C.RESET}"

# ── Shell helpers ────────────────────────────────────────────────────────────

def run(cmd, timeout=10):
    """Run a shell command, return stdout stripped. Empty string on failure."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip()
    except Exception:
        return ""

def run_su(cmd, timeout=10):
    """Run via su 0 (root)."""
    return run(f"su 0 {cmd}", timeout=timeout)

def read_file(path):
    """Read a sysfs/procfs file, return stripped content or empty string."""
    try:
        return Path(path).read_text().strip()
    except Exception:
        return ""

def getprop(key):
    return run(f"getprop {key}")

# ── Section collectors ───────────────────────────────────────────────────────
# Each returns (lines: list[str], data: dict) for display and JSON.

def check_system():
    lines, data = [], {}

    android_ver = getprop("ro.build.version.release")
    build_id    = getprop("ro.build.display.id")
    build_type  = getprop("ro.build.type")
    kernel      = run("uname -r")
    selinux     = run("getenforce") or getprop("ro.boot.selinux") or "unknown"

    uptime_raw = read_file("/proc/uptime")
    up_secs = 0
    if uptime_raw:
        up_secs = int(float(uptime_raw.split()[0]))
    days, rem = divmod(up_secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    uptime_str = ""
    if days: uptime_str += f"{days}d "
    uptime_str += f"{hours}h {mins}m"

    data = {
        "android": android_ver,
        "build_id": build_id,
        "build_type": build_type,
        "kernel": kernel,
        "selinux": selinux,
        "uptime_seconds": up_secs,
        "uptime_human": uptime_str.strip(),
    }

    lines.append(ok(f"Android {android_ver}  |  Kernel {kernel}"))
    lines.append(info(f"Build: {build_id}"))
    lines.append(info(f"Type: {build_type}  |  SELinux: {selinux}"))

    if up_secs > 86400 * 7:
        lines.append(warn(f"Uptime {uptime_str} (>7 days — consider reboot)"))
    else:
        lines.append(ok(f"Uptime {uptime_str}"))

    return lines, data

def check_cpu():
    lines, data = [], {}

    governor = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    if not governor:
        # Needs root on some MTK devices
        governor = run_su("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null")
    cur_freq = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    max_freq = read_file("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    ncpu     = run("nproc") or "?"

    # CPU temperature — mtktscpu thermal zone
    cpu_temp_c = None
    for tz in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        tz_type = read_file(tz / "type")
        if tz_type == "mtktscpu":
            raw = read_file(tz / "temp")
            if raw:
                cpu_temp_c = int(raw) / 1000.0
            break

    cur_mhz = int(cur_freq) // 1000 if cur_freq else 0
    max_mhz = int(max_freq) // 1000 if max_freq else 0

    data = {
        "cores": int(ncpu) if ncpu.isdigit() else ncpu,
        "governor": governor,
        "current_mhz": cur_mhz,
        "max_mhz": max_mhz,
        "temperature_c": cpu_temp_c,
    }

    lines.append(ok(f"{ncpu} cores  |  Governor: {governor}"))
    lines.append(info(f"Freq: {cur_mhz}/{max_mhz} MHz"))

    if cpu_temp_c is not None:
        if cpu_temp_c >= 80:
            lines.append(fail(f"CPU temp {cpu_temp_c:.1f} C — THROTTLING LIKELY"))
        elif cpu_temp_c >= 65:
            lines.append(warn(f"CPU temp {cpu_temp_c:.1f} C — warm"))
        else:
            lines.append(ok(f"CPU temp {cpu_temp_c:.1f} C"))
    else:
        lines.append(warn("CPU temp unavailable"))

    return lines, data

def check_memory():
    lines, data = [], {}

    meminfo = read_file("/proc/meminfo")
    mi = {}
    for line in meminfo.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            mi[parts[0].rstrip(":")] = int(parts[1])  # kB

    total_mb = mi.get("MemTotal", 0) / 1024
    avail_mb = mi.get("MemAvailable", 0) / 1024
    used_mb  = total_mb - avail_mb

    # ZRAM
    zram_disksize = read_file("/sys/block/zram0/disksize")
    zram_used     = read_file("/sys/block/zram0/mem_used_total")
    zram_disk_mb  = int(zram_disksize) / 1024 / 1024 if zram_disksize else 0
    zram_used_mb  = int(zram_used) / 1024 / 1024 if zram_used else 0

    pct = (used_mb / total_mb * 100) if total_mb else 0

    data = {
        "total_mb": round(total_mb),
        "used_mb": round(used_mb),
        "available_mb": round(avail_mb),
        "used_pct": round(pct, 1),
        "zram_disk_mb": round(zram_disk_mb),
        "zram_used_mb": round(zram_used_mb),
    }

    if pct > 90:
        lines.append(fail(f"RAM {used_mb:.0f}/{total_mb:.0f} MB ({pct:.0f}% used)"))
    elif pct > 75:
        lines.append(warn(f"RAM {used_mb:.0f}/{total_mb:.0f} MB ({pct:.0f}% used)"))
    else:
        lines.append(ok(f"RAM {used_mb:.0f}/{total_mb:.0f} MB ({pct:.0f}% used)"))

    lines.append(info(f"Available: {avail_mb:.0f} MB  |  ZRAM: {zram_used_mb:.0f}/{zram_disk_mb:.0f} MB"))

    return lines, data

def check_storage():
    lines, data = [], {}

    # /data partition
    df_data = run("df -h /data 2>/dev/null")
    data_info = _parse_df(df_data)

    # SD card — check common mount points
    sd_info = None
    for path in ["/storage/sdcard1", "/mnt/media_rw/sdcard1", "/mnt/expand"]:
        if os.path.ismount(path):
            sd_raw = run(f"df -h {path} 2>/dev/null")
            sd_info = _parse_df(sd_raw)
            if sd_info.get("total"):
                break
            sd_info = None

    data["data"] = data_info
    data["sdcard"] = sd_info

    if data_info:
        pct = data_info.get("used_pct", 0)
        if pct > 90:
            lines.append(fail(f"/data {data_info['used']}/{data_info['total']} ({pct}% used)"))
        elif pct > 75:
            lines.append(warn(f"/data {data_info['used']}/{data_info['total']} ({pct}% used)"))
        else:
            lines.append(ok(f"/data {data_info['used']}/{data_info['total']} ({pct}% used)"))
        lines.append(info(f"Free: {data_info.get('avail', '?')}"))
    else:
        lines.append(warn("/data: could not read"))

    if sd_info and sd_info.get("total"):
        lines.append(ok(f"SD card: {sd_info['used']}/{sd_info['total']} ({sd_info.get('used_pct', '?')}% used)"))
    else:
        lines.append(info("No SD card detected"))

    return lines, data

def _parse_df(raw):
    """Parse df output (2nd line) into dict."""
    if not raw:
        return {}
    dfl = raw.strip().splitlines()
    if len(dfl) < 2:
        return {}
    parts = dfl[1].split()
    if len(parts) < 5:
        return {}
    return {
        "total": parts[1],
        "used": parts[2],
        "avail": parts[3],
        "used_pct": int(parts[4].rstrip("%")) if parts[4].rstrip("%").isdigit() else 0,
    }

def check_battery():
    lines, data = [], {}

    uevent = read_file("/sys/class/power_supply/battery/uevent")
    props = {}
    for line in uevent.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v

    status   = props.get("POWER_SUPPLY_STATUS", "Unknown")
    health   = props.get("POWER_SUPPLY_HEALTH", "Unknown")
    capacity = props.get("POWER_SUPPLY_CAPACITY", "?")
    voltage  = props.get("POWER_SUPPLY_VOLTAGE_NOW", "0")
    temp_raw = props.get("POWER_SUPPLY_TEMP", "0")
    tech     = props.get("POWER_SUPPLY_TECHNOLOGY", "?")
    cycles   = props.get("POWER_SUPPLY_CYCLE_COUNT", "?")

    voltage_v = int(voltage) / 1_000_000 if voltage.isdigit() else 0
    temp_c    = int(temp_raw) / 10 if temp_raw.lstrip("-").isdigit() else 0

    data = {
        "status": status,
        "health": health,
        "capacity_pct": int(capacity) if capacity.isdigit() else capacity,
        "voltage_v": round(voltage_v, 3),
        "temperature_c": round(temp_c, 1),
        "technology": tech,
        "cycle_count": int(cycles) if cycles.isdigit() else cycles,
    }

    cap_int = int(capacity) if capacity.isdigit() else -1
    if cap_int < 15:
        lines.append(fail(f"Battery {capacity}% — CRITICAL"))
    elif cap_int < 30:
        lines.append(warn(f"Battery {capacity}%"))
    else:
        lines.append(ok(f"Battery {capacity}%  |  {status}"))

    lines.append(info(f"Voltage: {voltage_v:.3f}V  |  Temp: {temp_c:.1f} C  |  Health: {health}"))
    lines.append(info(f"Tech: {tech}  |  Cycles: {cycles}"))

    if temp_c > 45:
        lines.append(warn(f"Battery temp {temp_c:.1f} C — high"))

    return lines, data

def check_network():
    lines, data = [], {}

    # WiFi info via su 0 dumpsys
    wifi_raw = run_su("dumpsys wifi 2>/dev/null | grep 'mWifiInfo' | head -1", timeout=5)

    ssid = freq = rssi = link_speed = None
    if wifi_raw:
        m = re.search(r'SSID:\s*([^,]+)', wifi_raw)
        if m: ssid = m.group(1).strip()
        m = re.search(r'RSSI:\s*(-?\d+)', wifi_raw)
        if m: rssi = int(m.group(1))
        m = re.search(r'Frequency:\s*(\d+)', wifi_raw)
        if m: freq = int(m.group(1))
        m = re.search(r'Link speed:\s*(\d+)', wifi_raw)
        if m: link_speed = int(m.group(1))

    # Fallback RSSI from /proc/net/wireless
    if rssi is None:
        wl = read_file("/proc/net/wireless")
        for wline in wl.splitlines():
            if "wlan0" in wline:
                parts = wline.split()
                if len(parts) >= 4:
                    try:
                        rssi = int(float(parts[3].rstrip(".")))
                    except ValueError:
                        pass

    # IP address
    wlan_ip = None
    ifcfg = run("ifconfig wlan0 2>/dev/null")
    m = re.search(r'inet\s+([\d.]+)', ifcfg)
    if m:
        wlan_ip = m.group(1)

    # Tailscale
    ts_ip = None
    ts_raw = run("ip addr show tun0 2>/dev/null") or run("ip addr show tailscale0 2>/dev/null")
    m = re.search(r'inet\s+([\d.]+)', ts_raw or "")
    if m:
        ts_ip = m.group(1)
    if not ts_ip:
        ts_ip = run("tailscale ip -4 2>/dev/null") or None

    # Gateway / ping
    gw = None
    route = run("ip route 2>/dev/null")
    m = re.search(r'default\s+via\s+([\d.]+)', route)
    if m:
        gw = m.group(1)
    if not gw:
        # Try getprop fallback
        gw = getprop("dhcp.wlan0.gateway") or None
    if not gw:
        # Try su for root routing table
        route_su = run_su("ip route 2>/dev/null")
        m = re.search(r'default\s+via\s+([\d.]+)', route_su or "")
        if m:
            gw = m.group(1)

    gw_ping_ms = None
    if gw:
        ping_out = run(f"ping -c 1 -W 2 {gw} 2>/dev/null", timeout=5)
        m = re.search(r'time[=]([\d.]+)', ping_out)
        if m:
            gw_ping_ms = float(m.group(1))

    data = {
        "wifi_ssid": ssid,
        "wifi_rssi_dbm": rssi,
        "wifi_freq_mhz": freq,
        "wifi_link_mbps": link_speed,
        "wlan_ip": wlan_ip,
        "tailscale_ip": ts_ip,
        "gateway": gw,
        "gateway_ping_ms": gw_ping_ms,
    }

    if ssid:
        band = ""
        if freq:
            band = "5 GHz" if freq > 4000 else "2.4 GHz"
        rssi_str = f"{rssi} dBm" if rssi is not None else "?"
        if rssi is not None and rssi > -50:
            lines.append(ok(f"WiFi: {ssid}  |  {rssi_str}  |  {band}"))
        elif rssi is not None and rssi > -70:
            lines.append(ok(f"WiFi: {ssid}  |  {rssi_str}  |  {band}"))
        else:
            lines.append(warn(f"WiFi: {ssid}  |  {rssi_str} (weak)  |  {band}"))
        if link_speed:
            lines.append(info(f"Link speed: {link_speed} Mbps  |  IP: {wlan_ip or '?'}"))
    else:
        lines.append(fail("WiFi: not connected"))

    if ts_ip:
        lines.append(ok(f"Tailscale: {ts_ip}"))
    else:
        lines.append(warn("Tailscale: no IP detected"))

    if gw_ping_ms is not None:
        if gw_ping_ms > 100:
            lines.append(warn(f"Gateway ping: {gw_ping_ms:.1f} ms (slow)"))
        else:
            lines.append(ok(f"Gateway ping: {gw_ping_ms:.1f} ms"))
    elif gw:
        lines.append(fail(f"Gateway {gw}: ping failed"))
    else:
        lines.append(warn("No default gateway"))

    return lines, data

def check_serial():
    lines, data = [], {}

    tty_exists = os.path.exists("/dev/ttyS0")

    # Check who's using ttyS0
    tty_owner = None
    fuser_out = run("fuser /dev/ttyS0 2>/dev/null")
    if fuser_out:
        tty_owner = fuser_out.strip()

    # Flyshark running?
    flyshark_running = False
    ps_out = run("su 0 ps -A 2>/dev/null | grep -i flyshark | grep -v grep")
    if ps_out:
        flyshark_running = True

    # ttyS0 permissions
    tty_perms = run("ls -la /dev/ttyS0 2>/dev/null")

    data = {
        "ttyS0_exists": tty_exists,
        "ttyS0_owner_pids": tty_owner,
        "ttyS0_permissions": tty_perms,
        "flyshark_running": flyshark_running,
    }

    if tty_exists:
        lines.append(ok("/dev/ttyS0 present"))
        if tty_perms:
            lines.append(info(f"Perms: {tty_perms}"))
    else:
        lines.append(fail("/dev/ttyS0 missing"))

    if tty_owner:
        lines.append(warn(f"ttyS0 in use by PID: {tty_owner}"))
    else:
        lines.append(ok("ttyS0 not locked by any process"))

    if flyshark_running:
        lines.append(info("Flyshark app is running (may claim serial)"))
    else:
        lines.append(info("Flyshark app not running"))

    return lines, data

def check_services():
    lines, data = [], {}

    # Check key Android services via ps
    services = {
        "GPS (mnld)":       "mnld",
        "GPS (agpsd)":      "mtk_agpsd",
        "Sensors HAL":      "sensors@",
        "Bluetooth":        "bluetooth",
        "Camera HAL":       "camerahalserver",
        "Camera Server":    "cameraserver",
    }

    ps_out = run("su 0 ps -A 2>/dev/null")
    for label, pattern in services.items():
        found = any(pattern.lower() in line.lower() for line in ps_out.splitlines())
        data[label] = found
        if found:
            lines.append(ok(label))
        else:
            lines.append(warn(f"{label} — not running"))

    return lines, data

def check_packages():
    lines, data = [], {}

    packages = {
        "Meshtastic":  "com.geeksville.mesh",
        "RetroArch":   "com.retroarch.aarch64",
        "Termux":      "com.termux",
        "Tailscale":   "com.tailscale.ipn",
        "Flyshark":    "com.Flyshark.RadioMasterAX",
        "Claude":      "com.anthropic.claude",
    }

    installed = run("pm list packages -3 2>/dev/null")

    for label, pkg in packages.items():
        if f"package:{pkg}" in installed:
            # Get version
            ver_raw = run_su(f"dumpsys package {pkg} 2>/dev/null | grep versionName | head -1", timeout=5)
            ver = "?"
            if ver_raw:
                m = re.search(r'versionName=(.+)', ver_raw)
                if m:
                    ver = m.group(1).strip()
            data[label] = {"installed": True, "version": ver, "package": pkg}
            lines.append(ok(f"{label}: {ver}"))
        else:
            data[label] = {"installed": False, "package": pkg}
            lines.append(info(f"{label}: not installed"))

    return lines, data

def check_ax12_research():
    lines, data = [], {}

    repo = Path.home() / "ax12-research"
    if not repo.is_dir():
        lines.append(fail("ax12-research repo not found"))
        data["found"] = False
        return lines, data

    data["found"] = True

    # Git branch
    branch = run(f"cd {repo} && git branch --show-current 2>/dev/null")
    data["branch"] = branch or "unknown"

    # Last commit
    last_commit = run(f"cd {repo} && git log --oneline -1 2>/dev/null")
    data["last_commit"] = last_commit or "unknown"

    # Dirty?
    dirty = run(f"cd {repo} && git status --porcelain 2>/dev/null")
    data["dirty"] = bool(dirty)

    # Tool count
    tools_dir = repo / "tools"
    py_count = len(list(tools_dir.glob("*.py"))) if tools_dir.is_dir() else 0
    data["python_tools"] = py_count

    # Lua scripts
    lua_count = 0
    for _ in repo.rglob("*.lua"):
        lua_count += 1
    data["lua_scripts"] = lua_count

    lines.append(ok(f"Branch: {branch}") if branch else warn("Branch: detached/unknown"))

    if last_commit:
        lines.append(info(f"Last commit: {last_commit}"))

    if dirty:
        n_dirty = len(dirty.strip().splitlines())
        lines.append(warn(f"Working tree dirty ({n_dirty} file{'s' if n_dirty != 1 else ''})"))
    else:
        lines.append(ok("Working tree clean"))

    lines.append(info(f"Python tools: {py_count}  |  Lua scripts: {lua_count}"))

    return lines, data

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    json_mode = "--json" in sys.argv

    checks = [
        ("System",          check_system),
        ("CPU",             check_cpu),
        ("Memory",          check_memory),
        ("Storage",         check_storage),
        ("Battery",         check_battery),
        ("Network",         check_network),
        ("Serial",          check_serial),
        ("Services",        check_services),
        ("Packages",        check_packages),
        ("AX12 Research",   check_ax12_research),
    ]

    all_data = {}
    all_lines = []

    t0 = time.time()

    for name, fn in checks:
        try:
            clines, cdata = fn()
        except Exception as e:
            clines = [fail(f"Check crashed: {e}")]
            cdata = {"error": str(e)}
        all_data[name.lower().replace(" ", "_")] = cdata
        all_lines.append((name, clines))

    elapsed = time.time() - t0
    all_data["_meta"] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_seconds": round(elapsed, 2),
        "tool": "device_health.py",
    }

    if json_mode:
        print(json.dumps(all_data, indent=2))
        return

    # Color report
    print()
    print(f"{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════╗{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║          AX12 Device Health Report                          ║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║          {time.strftime('%Y-%m-%d %H:%M:%S'):50s}║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════════════════════════════╝{C.RESET}")

    for name, clines in all_lines:
        print(section(name))
        for line in clines:
            print(f"  {line}")

    # Summary
    print(section("Summary"))
    total_ok = total_warn = total_fail = 0
    for _, clines in all_lines:
        for line in clines:
            # Count by looking at the raw escape sequences
            if C.GREEN + "OK" in line:
                total_ok += 1
            elif C.YELLOW + "WARN" in line:
                total_warn += 1
            elif C.RED + "FAIL" in line:
                total_fail += 1

    summary = f"  {C.GREEN}{total_ok} OK{C.RESET}  |  {C.YELLOW}{total_warn} WARN{C.RESET}  |  {C.RED}{total_fail} FAIL{C.RESET}"
    print(summary)
    print(f"  {C.DIM}Completed in {elapsed:.1f}s{C.RESET}")
    print()


if __name__ == "__main__":
    main()
