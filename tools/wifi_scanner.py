#!/usr/bin/env python3
"""WiFi network scanner and monitor for RadioMaster AX12.

Uses `iw wlan0 scan` (requires root) to discover nearby networks.
Displays SSID, BSSID, signal strength, channel, frequency, security,
and band. Supports one-shot scan, continuous monitor, and JSON export.

Usage:
    su 0 python3 wifi_scanner.py scan
    su 0 python3 wifi_scanner.py scan --sort channel
    su 0 python3 wifi_scanner.py monitor --interval 15
    su 0 python3 wifi_scanner.py export --output scan_results.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict


# -- constants ---------------------------------------------------------------

FREQ_CHANNEL_MAP = {
    2412: 1, 2417: 2, 2422: 3, 2427: 4, 2432: 5, 2437: 6, 2442: 7,
    2447: 8, 2452: 9, 2457: 10, 2462: 11, 2467: 12, 2472: 13, 2484: 14,
    5180: 36, 5200: 40, 5220: 44, 5240: 48, 5260: 52, 5280: 56,
    5300: 60, 5320: 64, 5500: 100, 5520: 104, 5540: 108, 5560: 112,
    5580: 116, 5600: 120, 5620: 124, 5640: 128, 5660: 132, 5680: 136,
    5700: 140, 5720: 144, 5745: 149, 5765: 153, 5785: 157, 5805: 161,
    5825: 165, 5845: 169, 5865: 173, 5885: 177,
}

IW_CMD = ["su", "0", "iw", "wlan0", "scan"]


class SecurityType(Enum):
    OPEN = "OPEN"
    WEP = "WEP"
    WPA = "WPA"
    WPA2 = "WPA2"
    WPA_WPA2 = "WPA/WPA2"
    WPA3 = "WPA3"
    WPA2_WPA3 = "WPA2/WPA3"


# -- ANSI colors -------------------------------------------------------------

class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_RED = "\033[41m"


def signal_color(rssi: int) -> str:
    """Color code based on signal strength."""
    if rssi >= -50:
        return Color.GREEN
    elif rssi >= -60:
        return Color.CYAN
    elif rssi >= -70:
        return Color.YELLOW
    elif rssi >= -80:
        return Color.RED
    else:
        return Color.DIM + Color.RED


def signal_bar(rssi: int, width: int = 10) -> str:
    """Visual bar for signal strength."""
    # Map -100..-30 to 0..width
    level = max(0, min(width, int((rssi + 100) / 70 * width)))
    filled = "\u2588" * level
    empty = "\u2591" * (width - level)
    color = signal_color(rssi)
    return f"{color}{filled}{Color.DIM}{empty}{Color.RESET}"


def band_label(freq: int) -> str:
    """Return band label from frequency."""
    if 2400 <= freq <= 2500:
        return "2.4G"
    elif 5000 <= freq <= 5900:
        return " 5G "
    elif 5925 <= freq <= 7125:
        return " 6G "
    return " ?? "


def band_color(freq: int) -> str:
    """Color for band indicator."""
    if 2400 <= freq <= 2500:
        return Color.YELLOW
    elif 5000 <= freq <= 5900:
        return Color.CYAN
    return Color.MAGENTA


# -- data model --------------------------------------------------------------

@dataclass
class Network:
    bssid: str = ""
    ssid: str = ""
    frequency: int = 0
    channel: int = 0
    signal: int = -100
    security: str = "OPEN"
    band: str = ""
    hidden: bool = False
    associated: bool = False
    capability: str = ""
    channel_width: str = ""
    last_seen: str = ""
    wps: bool = False
    station_count: Optional[int] = None
    channel_utilisation: Optional[str] = None


# -- parser ------------------------------------------------------------------

def parse_iw_scan(output: str) -> List[Network]:
    """Parse output of `iw wlan0 scan` into Network objects."""
    networks = []
    current = None

    for line in output.splitlines():
        # New BSS entry
        m = re.match(r'^BSS ([0-9a-f:]{17})\(on (\w+)\)(.*)', line)
        if m:
            if current is not None:
                _finalize(current)
                networks.append(current)
            current = Network(bssid=m.group(1).upper())
            if "associated" in m.group(3):
                current.associated = True
            continue

        if current is None:
            continue

        stripped = line.strip()

        # Frequency
        m = re.match(r'freq:\s+(\d+)', stripped)
        if m:
            current.frequency = int(m.group(1))
            current.channel = FREQ_CHANNEL_MAP.get(current.frequency, 0)
            current.band = band_label(current.frequency).strip()
            continue

        # Signal
        m = re.match(r'signal:\s+(-?[\d.]+)\s+dBm', stripped)
        if m:
            current.signal = int(float(m.group(1)))
            continue

        # SSID
        m = re.match(r'SSID:\s*(.*)', stripped)
        if m:
            ssid = m.group(1).strip()
            if not ssid:
                current.hidden = True
                current.ssid = "<hidden>"
            else:
                current.ssid = ssid
            continue

        # DS Parameter set (channel)
        m = re.match(r'DS Parameter set:\s*channel\s+(\d+)', stripped)
        if m:
            current.channel = int(m.group(1))
            continue

        # Capability
        m = re.match(r'capability:\s+(.*)', stripped)
        if m:
            current.capability = m.group(1).strip()
            continue

        # WPA
        if stripped.startswith("WPA:"):
            if current.security == "OPEN":
                current.security = "WPA"
            continue

        # RSN (WPA2+)
        if stripped.startswith("RSN:"):
            _parse_rsn_security(current, stripped)
            continue

        # Authentication suites detail
        m = re.match(r'\* Authentication suites:\s+(.*)', stripped)
        if m:
            auth = m.group(1)
            if "SAE" in auth or "00-0f-ac:8" in auth:
                if current.security in ("WPA2", "WPA/WPA2"):
                    current.security = "WPA2/WPA3"
                else:
                    current.security = "WPA3"
            continue

        # Channel width from VHT/HT operation
        m = re.match(r'\* channel width:\s+\d+\s+\((.+?)\)', stripped)
        if m:
            current.channel_width = m.group(1)
            continue

        # Last seen
        m = re.match(r'last seen:\s+(.*)', stripped)
        if m:
            current.last_seen = m.group(1).strip()
            continue

        # WPS
        if stripped.startswith("WPS:"):
            current.wps = True
            continue

        # Station count
        m = re.match(r'\* station count:\s+(\d+)', stripped)
        if m:
            current.station_count = int(m.group(1))
            continue

        # Channel utilisation
        m = re.match(r'\* channel utilisation:\s+(.*)', stripped)
        if m:
            current.channel_utilisation = m.group(1).strip()
            continue

    # Don't forget the last entry
    if current is not None:
        _finalize(current)
        networks.append(current)

    return networks


def _parse_rsn_security(net: Network, line: str):
    """Update security field based on RSN presence."""
    if net.security == "WPA":
        net.security = "WPA/WPA2"
    elif net.security == "OPEN":
        net.security = "WPA2"


def _finalize(net: Network):
    """Fill in derived fields."""
    if not net.band and net.frequency:
        net.band = band_label(net.frequency).strip()
    if not net.channel and net.frequency:
        net.channel = FREQ_CHANNEL_MAP.get(net.frequency, 0)
    # Check WEP from capability
    if net.security == "OPEN" and "Privacy" in net.capability:
        net.security = "WEP"


# -- scanning ----------------------------------------------------------------

def run_scan() -> List[Network]:
    """Execute iw scan and return parsed networks."""
    try:
        result = subprocess.run(
            IW_CMD, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            # iw scan can fail if a scan is already in progress; retry once
            if "busy" in result.stderr.lower() or result.returncode == 240:
                print(f"{Color.YELLOW}Scan busy, retrying in 2s...{Color.RESET}",
                      file=sys.stderr)
                time.sleep(2)
                result = subprocess.run(
                    IW_CMD, capture_output=True, text=True, timeout=30
                )
            if result.returncode != 0:
                print(f"{Color.RED}iw scan failed (rc={result.returncode}):{Color.RESET}",
                      file=sys.stderr)
                print(result.stderr, file=sys.stderr)
                return []
        return parse_iw_scan(result.stdout)
    except FileNotFoundError:
        print(f"{Color.RED}Error: 'iw' not found. Need root: su 0 python3 ...{Color.RESET}",
              file=sys.stderr)
        return []
    except subprocess.TimeoutExpired:
        print(f"{Color.RED}Scan timed out after 30s.{Color.RESET}", file=sys.stderr)
        return []


# -- display -----------------------------------------------------------------

def sort_networks(networks: List[Network], key: str = "signal") -> List[Network]:
    """Sort networks by the given key."""
    if key == "signal":
        return sorted(networks, key=lambda n: n.signal, reverse=True)
    elif key == "channel":
        return sorted(networks, key=lambda n: (n.frequency, n.signal * -1))
    elif key == "ssid":
        return sorted(networks, key=lambda n: n.ssid.lower())
    elif key == "security":
        return sorted(networks, key=lambda n: (n.security, -n.signal))
    return networks


def display_table(networks: List[Network], show_header: bool = True):
    """Print networks as a formatted table."""
    if not networks:
        print(f"{Color.YELLOW}No networks found.{Color.RESET}")
        return

    # Header
    if show_header:
        print()
        print(f"{Color.BOLD}{'':>2} {'SSID':<30} {'BSSID':<19} {'RSSI':>5} "
              f"{'Signal':<12} {'Ch':>3} {'Freq':>5} {'Band':<5} "
              f"{'Width':<10} {'Security':<12} {'Flags':<6}{Color.RESET}")
        print(f"{Color.DIM}{'-' * 120}{Color.RESET}")

    for i, n in enumerate(networks, 1):
        # Build flags
        flags = []
        if n.associated:
            flags.append("*")
        if n.hidden:
            flags.append("H")
        if n.wps:
            flags.append("W")
        flag_str = "".join(flags)

        # SSID display
        ssid_display = n.ssid
        if n.associated:
            ssid_display = f"{Color.GREEN}{Color.BOLD}{n.ssid}{Color.RESET}"
        elif n.hidden:
            ssid_display = f"{Color.DIM}{n.ssid}{Color.RESET}"
        else:
            ssid_display = f"{Color.WHITE}{n.ssid}{Color.RESET}"

        # Pad SSID (account for ANSI codes in length)
        ssid_pad = 30 - len(n.ssid)
        if ssid_pad < 0:
            ssid_pad = 0

        bc = band_color(n.frequency)
        sc = signal_color(n.signal)

        width_str = n.channel_width if n.channel_width else "20 MHz"

        sec_color = Color.GREEN if "WPA3" in n.security else (
            Color.YELLOW if "WPA2" in n.security else (
                Color.RED if n.security in ("OPEN", "WEP") else Color.WHITE
            ))

        print(f"{Color.DIM}{i:>2}{Color.RESET} "
              f"{ssid_display}{' ' * ssid_pad} "
              f"{Color.DIM}{n.bssid:<19}{Color.RESET}"
              f"{sc}{n.signal:>4}{Color.RESET} "
              f"{signal_bar(n.signal)} "
              f"{bc}{n.channel:>3}{Color.RESET} "
              f"{n.frequency:>5} "
              f"{bc}{n.band:<5}{Color.RESET}"
              f"{width_str:<10} "
              f"{sec_color}{n.security:<12}{Color.RESET}"
              f"{Color.MAGENTA}{flag_str:<6}{Color.RESET}")


def display_channel_utilization(networks: List[Network]):
    """Show how many networks are on each channel."""
    channel_counts: Dict[int, List[Network]] = {}
    for n in networks:
        ch = n.channel
        if ch not in channel_counts:
            channel_counts[ch] = []
        channel_counts[ch].append(n)

    print(f"\n{Color.BOLD}Channel Utilization{Color.RESET}")
    print(f"{Color.DIM}{'-' * 60}{Color.RESET}")

    # 2.4 GHz channels
    print(f"\n  {Color.YELLOW}{Color.BOLD}2.4 GHz{Color.RESET}")
    for ch in range(1, 15):
        nets = channel_counts.get(ch, [])
        count = len(nets)
        if count == 0:
            bar = f"{Color.DIM}  --{Color.RESET}"
        else:
            bar_color = Color.GREEN if count <= 2 else (
                Color.YELLOW if count <= 4 else Color.RED)
            blocks = "\u2588" * count
            bar = f"{bar_color}{blocks}{Color.RESET} {count}"
        print(f"  Ch {ch:>2}: {bar}")

    # 5 GHz channels
    channels_5g = sorted(set(
        n.channel for n in networks if n.band == "5G"
    ))
    if channels_5g:
        # Show all common 5GHz channels, not just ones with networks
        all_5g = sorted(set(channels_5g) | {36, 40, 44, 48, 52, 56, 60, 64,
                                              100, 104, 108, 112, 116, 120,
                                              124, 128, 132, 136, 140, 144,
                                              149, 153, 157, 161, 165})
        print(f"\n  {Color.CYAN}{Color.BOLD}5 GHz{Color.RESET}")
        for ch in all_5g:
            nets = channel_counts.get(ch, [])
            count = len(nets)
            if count == 0:
                continue  # Only show populated 5GHz channels
            bar_color = Color.GREEN if count <= 2 else (
                Color.YELLOW if count <= 4 else Color.RED)
            blocks = "\u2588" * count
            bar = f"{bar_color}{blocks}{Color.RESET} {count}"
            print(f"  Ch {ch:>3}: {bar}")


def display_summary(networks: List[Network]):
    """Print summary statistics."""
    total = len(networks)
    hidden = sum(1 for n in networks if n.hidden)
    band_24 = sum(1 for n in networks if n.band == "2.4G")
    band_5 = sum(1 for n in networks if n.band == "5G")
    associated = [n for n in networks if n.associated]

    open_nets = sum(1 for n in networks if n.security in ("OPEN", "WEP"))
    wpa3_nets = sum(1 for n in networks if "WPA3" in n.security)
    wps_nets = sum(1 for n in networks if n.wps)

    strongest = max(networks, key=lambda n: n.signal) if networks else None
    weakest = min(networks, key=lambda n: n.signal) if networks else None

    print(f"\n{Color.BOLD}Summary{Color.RESET}")
    print(f"{Color.DIM}{'-' * 40}{Color.RESET}")
    print(f"  Total networks:  {Color.WHITE}{total}{Color.RESET}")
    print(f"  Hidden:          {Color.DIM}{hidden}{Color.RESET}")
    print(f"  2.4 GHz:         {Color.YELLOW}{band_24}{Color.RESET}")
    print(f"  5 GHz:           {Color.CYAN}{band_5}{Color.RESET}")
    print(f"  Open/WEP:        {Color.RED}{open_nets}{Color.RESET}")
    print(f"  WPA3:            {Color.GREEN}{wpa3_nets}{Color.RESET}")
    print(f"  WPS enabled:     {Color.MAGENTA}{wps_nets}{Color.RESET}")

    if associated:
        a = associated[0]
        print(f"\n  {Color.GREEN}Connected:{Color.RESET} {a.ssid} "
              f"({a.bssid}) {a.signal} dBm ch{a.channel}")

    if strongest:
        print(f"  {Color.GREEN}Strongest:{Color.RESET}  {strongest.ssid} "
              f"({strongest.signal} dBm)")
    if weakest:
        print(f"  {Color.RED}Weakest:{Color.RESET}    {weakest.ssid} "
              f"({weakest.signal} dBm)")
    print()


# -- commands ----------------------------------------------------------------

def cmd_scan(args):
    """One-shot scan and display."""
    print(f"{Color.BOLD}Scanning WiFi networks...{Color.RESET}", file=sys.stderr)
    networks = run_scan()
    if not networks:
        return 1
    networks = sort_networks(networks, args.sort)
    display_table(networks)
    display_channel_utilization(networks)
    display_summary(networks)
    return 0


def cmd_monitor(args):
    """Continuous scanning with updates."""
    scan_num = 0
    try:
        while True:
            scan_num += 1
            ts = time.strftime("%H:%M:%S")
            # Clear screen
            print("\033[2J\033[H", end="")
            print(f"{Color.BOLD}WiFi Monitor{Color.RESET} "
                  f"{Color.DIM}scan #{scan_num} @ {ts} "
                  f"(Ctrl+C to stop){Color.RESET}")

            networks = run_scan()
            if networks:
                networks = sort_networks(networks, args.sort)
                display_table(networks)
                display_channel_utilization(networks)
                display_summary(networks)
            else:
                print(f"{Color.YELLOW}Scan returned no results.{Color.RESET}")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n{Color.DIM}Monitor stopped.{Color.RESET}")
        return 0


def cmd_export(args):
    """Export scan results to JSON."""
    print(f"{Color.BOLD}Scanning for export...{Color.RESET}", file=sys.stderr)
    networks = run_scan()
    if not networks:
        return 1
    networks = sort_networks(networks, args.sort)

    export_data = {
        "scan_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "device": "RadioMaster AX12",
        "interface": "wlan0",
        "network_count": len(networks),
        "networks": [asdict(n) for n in networks],
        "channel_summary": _channel_summary(networks),
    }

    output_path = args.output
    with open(output_path, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"{Color.GREEN}Exported {len(networks)} networks to {output_path}{Color.RESET}")

    # Also print table to stderr for visibility
    display_table(networks)
    display_summary(networks)
    return 0


def _channel_summary(networks: List[Network]) -> Dict:
    """Build channel summary for export."""
    summary = {}
    for n in networks:
        ch_key = str(n.channel)
        if ch_key not in summary:
            summary[ch_key] = {"count": 0, "band": n.band, "networks": []}
        summary[ch_key]["count"] += 1
        summary[ch_key]["networks"].append(n.ssid)
    return summary


# -- main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AX12 WiFi Scanner - scan, monitor, and export WiFi networks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Requires root: su 0 python3 wifi_scanner.py scan"
    )
    sub = parser.add_subparsers(dest="command")

    # scan
    p_scan = sub.add_parser("scan", help="One-shot scan and display")
    p_scan.add_argument("--sort", choices=["signal", "channel", "ssid", "security"],
                        default="signal", help="Sort order (default: signal)")

    # monitor
    p_mon = sub.add_parser("monitor", help="Continuous scanning")
    p_mon.add_argument("--interval", type=int, default=15,
                       help="Seconds between scans (default: 15)")
    p_mon.add_argument("--sort", choices=["signal", "channel", "ssid", "security"],
                       default="signal", help="Sort order (default: signal)")

    # export
    p_exp = sub.add_parser("export", help="Export results to JSON")
    p_exp.add_argument("--output", "-o", default="wifi_scan.json",
                       help="Output file (default: wifi_scan.json)")
    p_exp.add_argument("--sort", choices=["signal", "channel", "ssid", "security"],
                        default="signal", help="Sort order (default: signal)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "scan":
        return cmd_scan(args)
    elif args.command == "monitor":
        return cmd_monitor(args)
    elif args.command == "export":
        return cmd_export(args)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
