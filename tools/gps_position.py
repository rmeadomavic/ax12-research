#!/usr/bin/env python3
"""
GPS Position Display Tool for RadioMaster AX12
===============================================
Reads GPS position from the MT6631 GNSS chipset via Android location services
and NMEA data from the MediaTek GPS daemon.

Usage:
    python3 gps_position.py              # Single position snapshot
    python3 gps_position.py --monitor    # Continuous monitoring (1Hz)
    python3 gps_position.py --nmea       # Show raw NMEA sentences
    python3 gps_position.py --satellites # Show satellite constellation
    python3 gps_position.py --json       # Output as JSON
    python3 gps_position.py --start      # Start GPS test (activates GNSS radio)
    python3 gps_position.py --stop       # Stop GPS test

The AX12 is a drone transmitter - GPS on the transmitter enables
pilot position tracking for GCS integration.

GPS Hardware: MT6631 combo chip (WiFi/BT/GPS/FM)
Device nodes: /dev/stpgps, /dev/gps_emi
GPS daemon: mnld + mtk_agpsd
Test app: com.mediatek.ygps (MediaTek YGPS)

Note: GPS test must be started (--start or via YGPS app) before
NMEA data flows. Position from network provider (WiFi) is always
available even without GPS fix.
"""

import subprocess
import re
import sys
import time
import json
from datetime import datetime, timezone


def run_cmd(cmd, timeout=10):
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        return f"ERROR: {e}"


def get_location_dumpsys():
    """Get location from Android dumpsys location service."""
    output = run_cmd("su 0 dumpsys location")
    locations = {}

    # Parse Last Known Locations section
    in_last_known = False
    for line in output.split("\n"):
        if "Last Known Locations:" in line:
            in_last_known = True
            continue
        if in_last_known:
            if line.strip() == "" or (
                not line.startswith("    ") and line.strip()
            ):
                if "Last Known" not in line:
                    in_last_known = False
                    continue

            # Match: provider: Location[type lat,lon ...]
            m = re.search(
                r"(\w+): Location\[(\w+)\s+([-\d.]+),([-\d.]+)\s+hAcc=([\d.]+).*?alt=([-\d.]+)",
                line,
            )
            if m:
                provider = m.group(1)
                locations[provider] = {
                    "provider": provider,
                    "type": m.group(2),
                    "latitude": float(m.group(3)),
                    "longitude": float(m.group(4)),
                    "accuracy_m": float(m.group(5)),
                    "altitude_m": float(m.group(6)),
                }

    return locations


def get_nmea_from_logcat(lines=100):
    """Get recent NMEA sentences from logcat (requires YGPS app running)."""
    output = run_cmd(f"su 0 logcat -d -s YGPS/NmeaParser -t {lines}")
    nmea_sentences = []
    for line in output.split("\n"):
        # Extract NMEA sentence from logcat format
        m = re.search(r"parse:(\$[A-Z]{2,5}[^*]*\*[0-9A-Fa-f]{2})", line)
        if m:
            nmea_sentences.append(m.group(1))
    return nmea_sentences


def parse_nmea_position(sentences):
    """Parse position from NMEA GGA/RMC sentences."""
    position = {}

    for sent in reversed(sentences):  # Most recent first
        if "GGA" in sent:
            parts = sent.split(",")
            if len(parts) >= 10 and parts[2]:
                lat = nmea_to_decimal(parts[2], parts[3])
                lon = nmea_to_decimal(parts[4], parts[5])
                position["latitude"] = lat
                position["longitude"] = lon
                position["fix_quality"] = int(parts[6]) if parts[6] else 0
                position["satellites_used"] = (
                    int(parts[7]) if parts[7] else 0
                )
                position["altitude_m"] = (
                    float(parts[9]) if parts[9] else 0.0
                )
                position["time_utc"] = format_nmea_time(parts[1])
                position["source"] = "NMEA-GGA"
                break
        elif "RMC" in sent and "latitude" not in position:
            parts = sent.split(",")
            if len(parts) >= 7 and parts[3]:
                lat = nmea_to_decimal(parts[3], parts[4])
                lon = nmea_to_decimal(parts[5], parts[6])
                position["latitude"] = lat
                position["longitude"] = lon
                position["status"] = "Active" if parts[2] == "A" else "Void"
                position["time_utc"] = format_nmea_time(parts[1])
                position["source"] = "NMEA-RMC"

    return position


def parse_satellites(sentences):
    """Parse satellite information from GSV sentences."""
    constellations = {"GPS": [], "GLONASS": [], "BeiDou": [], "Galileo": []}

    for sent in sentences:
        if "GSV" not in sent:
            continue
        parts = sent.split(",")
        if len(parts) < 4:
            continue

        # Determine constellation
        prefix = sent[:3]
        if prefix == "$GP":
            constellation = "GPS"
        elif prefix == "$GL":
            constellation = "GLONASS"
        elif prefix == "$BD":
            constellation = "BeiDou"
        elif prefix == "$GA":
            constellation = "Galileo"
        else:
            continue

        # Parse satellite entries (4 per sentence, starting at index 4)
        i = 4
        while i + 3 < len(parts):
            prn = parts[i].strip()
            elev = parts[i + 1].strip()
            azim = parts[i + 2].strip()
            # SNR might have checksum appended
            snr_raw = parts[i + 3].split("*")[0].strip()

            if prn:
                sat = {
                    "prn": prn,
                    "elevation": int(elev) if elev else 0,
                    "azimuth": int(azim) if azim else 0,
                    "snr_db": int(snr_raw) if snr_raw else 0,
                }
                # Avoid duplicates
                if not any(
                    s["prn"] == prn for s in constellations[constellation]
                ):
                    constellations[constellation].append(sat)
            i += 4

    return constellations


def nmea_to_decimal(coord, direction):
    """Convert NMEA coordinate (DDMM.MMMM) to decimal degrees."""
    if not coord:
        return 0.0
    # Determine degrees digits (2 for lat, 3 for lon)
    if direction in ("N", "S"):
        deg = int(coord[:2])
        minutes = float(coord[2:])
    else:
        deg = int(coord[:3])
        minutes = float(coord[3:])

    decimal = deg + minutes / 60.0
    if direction in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def format_nmea_time(time_str):
    """Format NMEA time string (HHMMSS.sss) to readable format."""
    if not time_str or len(time_str) < 6:
        return "N/A"
    return f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:]}"


def ensure_gps_active():
    """Ensure GPS is actively receiving by starting YGPS if needed."""
    # Check if YGPS is running
    output = run_cmd("su 0 pidof com.mediatek.ygps")
    if not output.strip():
        print("[*] Starting MediaTek GPS test app...")
        run_cmd("su 0 am start -n com.mediatek.ygps/.YgpsActivity")
        time.sleep(2)
        return True
    return False


def start_gps_test():
    """Start GPS test via YGPS app UI automation.

    This activates the GNSS radio for satellite acquisition.
    The YGPS app must be in the GPS TEST tab with the START button visible.
    """
    print("[*] Starting GPS test...")

    # Launch YGPS
    run_cmd("su 0 am start -n com.mediatek.ygps/.YgpsActivity")
    time.sleep(2)

    # Tap "GPS TEST" tab (bounds [959,126][1072,210] in landscape)
    run_cmd("su 0 input tap 1015 168")
    time.sleep(1)

    # Tap "START" button (bounds [464,568][812,652])
    run_cmd("su 0 input tap 638 610")
    time.sleep(1)

    print("[+] GPS test started - GNSS radio acquiring satellites")
    print("[*] Wait 10-60s outdoors for first fix (TTFF)")
    print("[*] Run with no args or --satellites to check status")


def stop_gps_test():
    """Stop GPS test via YGPS app UI automation."""
    print("[*] Stopping GPS test...")

    # Bring YGPS to front
    run_cmd("su 0 am start -n com.mediatek.ygps/.YgpsActivity")
    time.sleep(1)

    # Tap "GPS TEST" tab
    run_cmd("su 0 input tap 1015 168")
    time.sleep(1)

    # Tap "STOP" button (bounds [812,568][1161,652])
    run_cmd("su 0 input tap 987 610")
    time.sleep(1)

    print("[+] GPS test stopped")


def display_position(as_json=False):
    """Display current GPS position."""
    # Get from Android location service
    locations = get_location_dumpsys()

    # Get from NMEA
    nmea = get_nmea_from_logcat(200)
    nmea_pos = parse_nmea_position(nmea)
    satellites = parse_satellites(nmea)

    # Best position: prefer network/fused (always available), show NMEA too
    best = locations.get("network") or locations.get("fused") or {}

    total_sats = sum(len(v) for v in satellites.values())

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "position": {
            "latitude": best.get("latitude") or nmea_pos.get("latitude", 0),
            "longitude": best.get("longitude") or nmea_pos.get("longitude", 0),
            "altitude_m": best.get("altitude_m")
            or nmea_pos.get("altitude_m", 0),
            "accuracy_m": best.get("accuracy_m", 0),
        },
        "gnss": {
            "fix_quality": nmea_pos.get("fix_quality", 0),
            "status": nmea_pos.get("status", "Unknown"),
            "time_utc": nmea_pos.get("time_utc", "N/A"),
            "satellites_visible": total_sats,
            "constellations": {
                k: len(v) for k, v in satellites.items() if v
            },
        },
        "providers": list(locations.keys()),
    }

    if as_json:
        print(json.dumps(result, indent=2))
        return result

    # Pretty display
    print("=" * 55)
    print("  AX12 GPS POSITION - Pilot Tracking")
    print("=" * 55)
    pos = result["position"]
    print(f"  Latitude:   {pos['latitude']:.6f}")
    print(f"  Longitude:  {pos['longitude']:.6f}")
    print(f"  Altitude:   {pos['altitude_m']:.1f} m")
    print(f"  Accuracy:   {pos['accuracy_m']:.1f} m")
    print("-" * 55)
    gnss = result["gnss"]
    fix_str = {0: "No Fix", 1: "GPS Fix", 2: "DGPS Fix"}.get(
        gnss["fix_quality"], f"Fix={gnss['fix_quality']}"
    )
    print(f"  Fix Status: {fix_str} ({gnss['status']})")
    print(f"  UTC Time:   {gnss['time_utc']}")
    print(f"  Satellites: {gnss['satellites_visible']} visible")
    for const, count in gnss["constellations"].items():
        print(f"    {const:10s}: {count} SVs")
    print(f"  Providers:  {', '.join(result['providers'])}")
    print("=" * 55)
    print(
        f"  Maps: https://maps.google.com/?q={pos['latitude']},{pos['longitude']}"
    )
    print()

    return result


def display_satellites():
    """Display detailed satellite constellation view."""
    nmea = get_nmea_from_logcat(200)
    satellites = parse_satellites(nmea)

    print("=" * 60)
    print("  AX12 GNSS SATELLITE CONSTELLATION")
    print("=" * 60)

    total = 0
    for constellation, sats in satellites.items():
        if not sats:
            continue
        total += len(sats)
        print(f"\n  [{constellation}] - {len(sats)} satellites")
        print(f"  {'PRN':>5} {'Elev':>5} {'Azim':>5} {'SNR':>5}  Signal")
        print(f"  {'-' * 5} {'-' * 5} {'-' * 5} {'-' * 5}  {'-' * 12}")
        for sat in sorted(sats, key=lambda s: -s["snr_db"]):
            # Signal bar
            snr = sat["snr_db"]
            if snr >= 30:
                bar = "####" + " Strong"
            elif snr >= 20:
                bar = "###" + "  Good"
            elif snr > 0:
                bar = "##" + "   Weak"
            else:
                bar = "-" + "    None"
            print(
                f"  {sat['prn']:>5} {sat['elevation']:>4}d"
                f" {sat['azimuth']:>4}d {snr:>4}  {bar}"
            )

    print(f"\n  Total SVs in view: {total}")
    print("=" * 60)


def display_nmea():
    """Display raw NMEA sentences."""
    nmea = get_nmea_from_logcat(50)
    print(f"--- Last {len(nmea)} NMEA sentences ---")
    for sent in nmea[-30:]:
        print(sent)
    print("---")


def monitor_mode():
    """Continuous position monitoring at ~1Hz."""
    print("[*] GPS Monitor Mode - Press Ctrl+C to stop")
    print()
    try:
        while True:
            # Clear screen
            print("\033[2J\033[H", end="")
            display_position()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Monitor stopped.")


def main():
    args = sys.argv[1:]

    # Ensure GPS is active
    ensure_gps_active()

    if "--start" in args:
        start_gps_test()
    elif "--stop" in args:
        stop_gps_test()
    elif "--monitor" in args:
        monitor_mode()
    elif "--nmea" in args:
        display_nmea()
    elif "--satellites" in args:
        display_satellites()
    elif "--json" in args:
        display_position(as_json=True)
    else:
        display_position()


if __name__ == "__main__":
    main()
