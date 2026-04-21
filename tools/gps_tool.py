#!/usr/bin/env python3
"""GPS Location Display and Logging Tool for RadioMaster AX12.

Reads GPS position from Android's location service (dumpsys location)
and provides display, monitoring, logging, NMEA reading, and satellite info.

Usage:
    python3 gps_tool.py position      - Show current position once
    python3 gps_tool.py monitor       - Continuously update (2s polling)
    python3 gps_tool.py log [file]    - Log positions to JSONL file
    python3 gps_tool.py nmea          - Read NMEA from /dev/stpgps (root)
    python3 gps_tool.py satellites    - Show satellite info if available
"""

import subprocess
import sys
import re
import json
import time
import math
import os
from datetime import datetime


def run_cmd(cmd):
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return ''
    except Exception as e:
        return ''


def parse_location_line(line):
    """Parse a Location[] line from dumpsys location output.

    Format: Location[provider lat,lon hAcc=X et=... alt=X vAcc=X sAcc=X bAcc=X ...]
    """
    info = {}

    # Extract provider
    m = re.search(r'Location\[(\w+)', line)
    if m:
        info['provider'] = m.group(1)

    # Extract lat,lon
    m = re.search(r'Location\[\w+\s+([-\d.]+),([-\d.]+)', line)
    if m:
        info['latitude'] = float(m.group(1))
        info['longitude'] = float(m.group(2))

    # Extract horizontal accuracy
    m = re.search(r'hAcc=([\d.]+)', line)
    if m:
        info['accuracy_m'] = float(m.group(1))

    # Extract altitude
    m = re.search(r'alt=([-\d.]+)', line)
    if m:
        info['altitude_m'] = float(m.group(1))

    # Extract vertical accuracy
    m = re.search(r'vAcc=([\d.]+)', line)
    if m:
        info['vertical_accuracy_m'] = float(m.group(1))

    # Extract speed accuracy (may be ???)
    m = re.search(r'sAcc=([\d.]+)', line)
    if m:
        info['speed_accuracy'] = float(m.group(1))

    # Extract bearing accuracy (may be ???)
    m = re.search(r'bAcc=([\d.]+)', line)
    if m:
        info['bearing_accuracy'] = float(m.group(1))

    # Extract speed if present
    m = re.search(r'speed=([\d.]+)', line)
    if m:
        info['speed_mps'] = float(m.group(1))

    # Extract bearing if present
    m = re.search(r'bearing=([\d.]+)', line)
    if m:
        info['bearing_deg'] = float(m.group(1))

    # Extract elapsed time
    m = re.search(r'et=\+?([\w.]+)', line)
    if m:
        info['elapsed_time'] = m.group(1)

    return info


def get_locations():
    """Get all last known locations from dumpsys location."""
    output = run_cmd('su 0 dumpsys location')
    locations = {}

    # Find the Last Known Locations section
    in_section = False
    for line in output.split('\n'):
        if 'Last Known Locations:' in line and 'Coarse' not in line:
            in_section = True
            continue
        elif in_section:
            if line.strip().startswith('Last Known') or (line.strip() and not line.startswith(' ')):
                break
            # Parse provider: Location[...] lines
            m = re.match(r'\s+(\w+):\s+Location\[', line)
            if m:
                provider_name = m.group(1)
                loc = parse_location_line(line)
                if loc and 'latitude' in loc:
                    locations[provider_name] = loc

    return locations


def get_best_location():
    """Get the best available location (prefer fused, then gps, then network)."""
    locations = get_locations()

    for provider in ['fused', 'gps', 'network', 'passive']:
        if provider in locations:
            return locations[provider]

    return None


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two GPS points in meters."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def format_position(loc, prev_loc=None):
    """Format a location dict for display."""
    if not loc or 'latitude' not in loc:
        return 'No position available'

    lines = []
    lines.append('=' * 50)
    lines.append('  GPS POSITION')
    lines.append('=' * 50)
    lines.append('  Latitude:   {:.6f}'.format(loc['latitude']))
    lines.append('  Longitude:  {:.6f}'.format(loc['longitude']))

    if 'altitude_m' in loc:
        lines.append('  Altitude:   {:.1f} m'.format(loc['altitude_m']))

    if 'accuracy_m' in loc:
        lines.append('  Accuracy:   {:.0f} m'.format(loc['accuracy_m']))

    if 'vertical_accuracy_m' in loc:
        lines.append('  V.Accuracy: {:.0f} m'.format(loc['vertical_accuracy_m']))

    if 'speed_mps' in loc:
        speed_kmh = loc['speed_mps'] * 3.6
        lines.append('  Speed:      {:.1f} m/s ({:.1f} km/h)'.format(loc['speed_mps'], speed_kmh))

    if 'bearing_deg' in loc:
        lines.append('  Bearing:    {:.1f} deg'.format(loc['bearing_deg']))

    if 'provider' in loc:
        lines.append('  Provider:   {}'.format(loc['provider']))

    if 'elapsed_time' in loc:
        lines.append('  Fix Age:    {}'.format(loc['elapsed_time']))

    lines.append('  Timestamp:  {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    # Distance from previous
    if prev_loc and 'latitude' in prev_loc:
        dist = haversine_distance(
            prev_loc['latitude'], prev_loc['longitude'],
            loc['latitude'], loc['longitude']
        )
        lines.append('  Distance:   {:.1f} m from previous'.format(dist))

    lines.append('')
    lines.append('  Maps: https://maps.google.com/?q={},{}'.format(loc['latitude'], loc['longitude']))
    lines.append('=' * 50)

    return '\n'.join(lines)


def cmd_position():
    """Show current position once."""
    loc = get_best_location()
    if loc:
        print(format_position(loc))
    else:
        print('ERROR: No GPS position available.')
        print('Ensure location services are enabled and YGPS or another GPS app is running.')
        sys.exit(1)


def cmd_monitor():
    """Continuously monitor position with 2-second polling."""
    print('GPS Monitor (Ctrl+C to stop)')
    print('Polling every 2 seconds...')
    print()

    prev_loc = None
    try:
        while True:
            loc = get_best_location()
            if loc:
                # Clear screen (ANSI)
                print('\033[2J\033[H', end='')
                print('GPS Monitor (Ctrl+C to stop)')
                print(format_position(loc, prev_loc))
                prev_loc = loc
            else:
                print('Waiting for GPS fix...')
            time.sleep(2)
    except KeyboardInterrupt:
        print('\nMonitor stopped.')


def cmd_log(filename=None):
    """Log positions to a JSONL file."""
    if filename is None:
        filename = os.path.expanduser(
            '~/ax12-research/data/gps_log_{}.jsonl'.format(
                datetime.now().strftime('%Y%m%d_%H%M%S')
            )
        )

    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    print('Logging GPS to: {}'.format(filename))
    print('Polling every 2 seconds... (Ctrl+C to stop)')
    print()

    prev_loc = None
    count = 0

    try:
        with open(filename, 'a') as f:
            while True:
                loc = get_best_location()
                if loc:
                    entry = {
                        'timestamp': datetime.now().isoformat(),
                    }
                    entry.update(loc)
                    if prev_loc and 'latitude' in prev_loc:
                        entry['distance_from_prev_m'] = haversine_distance(
                            prev_loc['latitude'], prev_loc['longitude'],
                            loc['latitude'], loc['longitude']
                        )

                    f.write(json.dumps(entry) + '\n')
                    f.flush()
                    count += 1

                    print('  [{}] {:.6f}, {:.6f}  acc={}m  alt={}m'.format(
                        count,
                        loc['latitude'], loc['longitude'],
                        loc.get('accuracy_m', '?'),
                        loc.get('altitude_m', '?')
                    ))

                    prev_loc = loc
                else:
                    print('  Waiting for fix...')

                time.sleep(2)
    except KeyboardInterrupt:
        print('\nLogging stopped. {} entries written to {}'.format(count, filename))


def cmd_nmea():
    """Try to read NMEA sentences from /dev/stpgps (requires root)."""
    device = '/dev/stpgps'

    if not os.path.exists(device):
        print('ERROR: {} not found. GPS driver may not be loaded.'.format(device))
        sys.exit(1)

    print('Reading NMEA from {} (Ctrl+C to stop)'.format(device))
    print('Note: Requires root access and mnld may hold the device.')
    print()

    try:
        with open(device, 'r', errors='replace') as f:
            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line.startswith('$'):
                        # Parse common NMEA sentences
                        if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                            print('[FIX] {}'.format(line))
                        elif line.startswith('$GPRMC') or line.startswith('$GNRMC'):
                            print('[NAV] {}'.format(line))
                        elif line.startswith('$GPGSV') or line.startswith('$GLGSV') or line.startswith('$GAGSV'):
                            print('[SAT] {}'.format(line))
                        else:
                            print('      {}'.format(line))
                    elif line:
                        print('[RAW] {}'.format(line))
                else:
                    time.sleep(0.1)
    except PermissionError:
        print('ERROR: Permission denied reading {}. Run as root.'.format(device))
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nNMEA reading stopped.')


def cmd_satellites():
    """Show satellite information if available from dumpsys."""
    output = run_cmd('su 0 dumpsys location')

    print('=' * 50)
    print('  GNSS / SATELLITE INFO')
    print('=' * 50)

    # Extract GNSS KPI section
    in_gnss = False
    gnss_lines = []
    for line in output.split('\n'):
        if 'GNSS_KPI_START' in line:
            in_gnss = True
            continue
        elif 'GNSS_KPI_END' in line:
            in_gnss = False
            continue
        elif in_gnss:
            gnss_lines.append(line.strip())

    if gnss_lines:
        print('\n  GNSS KPI:')
        for line in gnss_lines:
            if line:
                print('    {}'.format(line))

    # Extract GPS internal state
    in_gps = False
    gps_lines = []
    for line in output.split('\n'):
        if 'gps Internal State:' in line:
            in_gps = True
            continue
        elif in_gps:
            if 'Internal State' in line and 'gps' not in line:
                break
            if line.startswith('  ') and not line.startswith('    '):
                break
            gps_lines.append(line.strip())

    if gps_lines:
        print('\n  GPS Engine State:')
        for line in gps_lines:
            if line:
                print('    {}'.format(line))

    # Check enabled providers
    in_providers = False
    for line in output.split('\n'):
        if 'Enabled Providers:' in line:
            in_providers = True
            print('\n  Enabled Providers:')
            continue
        elif in_providers:
            if line.strip() and line.startswith('    '):
                print('    {}'.format(line.strip()))
            else:
                if not line.startswith('  ') or (line.strip() and not line.startswith('    ')):
                    break

    # Try to get satellite count from YGPS logs
    sat_output = run_cmd('logcat -d -t 20 -s YGPS MNL_TAG 2>/dev/null')
    if sat_output.strip():
        print('\n  Recent GNSS Log Entries:')
        for line in sat_output.strip().split('\n')[-10:]:
            print('    {}'.format(line))

    # Show current fix info
    loc = get_best_location()
    if loc:
        print('\n  Current Fix:')
        print('    Position: {}, {}'.format(loc.get('latitude', '?'), loc.get('longitude', '?')))
        print('    Accuracy: {} m'.format(loc.get('accuracy_m', '?')))
        print('    Provider: {}'.format(loc.get('provider', '?')))

    print('=' * 50)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    mode = sys.argv[1].lower()

    if mode == 'position':
        cmd_position()
    elif mode == 'monitor':
        cmd_monitor()
    elif mode == 'log':
        filename = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_log(filename)
    elif mode == 'nmea':
        cmd_nmea()
    elif mode in ('satellites', 'sats', 'sat'):
        cmd_satellites()
    else:
        print('Unknown mode: {}'.format(mode))
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
