#!/usr/bin/env python3
"""Payload Drop Point Calculator for RadioMaster AX12.

Training tool for drone operators. Calculates optimal
release points for aerial payload drops accounting for altitude,
groundspeed, wind, and aerodynamic drag.

Usage:
    python3 payload_drop.py calc --alt 50 --speed 10 --target-lat 35.148 --target-lon -79.476
    python3 payload_drop.py table --target-lat 35.148 --target-lon -79.476
    python3 payload_drop.py interactive

Modes:
    calc        - One-shot calculation with provided parameters
    table       - Generate drop table for multiple altitudes/speeds
    interactive - Prompt for inputs with defaults
"""

import sys
import math
import argparse
import subprocess
import re
from datetime import datetime

# Constants
G = 9.80665        # gravitational acceleration (m/s^2)
RHO = 1.225        # air density at sea level (kg/m^3)
EARTH_RADIUS = 6371000.0  # Earth radius in meters


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two GPS coordinates in meters."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS * c


def bearing_between(lat1, lon1, lat2, lon2):
    """Calculate initial bearing from point 1 to point 2 in degrees."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.atan2(x, y)
    return (math.degrees(bearing) + 360) % 360


def destination_point(lat, lon, bearing_deg, distance_m):
    """Calculate destination point given start, bearing, and distance."""
    lat = math.radians(lat)
    lon = math.radians(lon)
    bearing = math.radians(bearing_deg)
    d = distance_m / EARTH_RADIUS

    lat2 = math.asin(math.sin(lat) * math.cos(d) +
                     math.cos(lat) * math.sin(d) * math.cos(bearing))
    lon2 = lon + math.atan2(math.sin(bearing) * math.sin(d) * math.cos(lat),
                            math.cos(d) - math.sin(lat) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)


def fall_time_simple(altitude):
    """Simple free-fall time without drag: t = sqrt(2h/g)."""
    if altitude <= 0:
        return 0.0
    return math.sqrt(2.0 * altitude / G)


def fall_time_with_drag(altitude, mass, cd, area, dt=0.01):
    """Iterative fall calculation with aerodynamic drag.

    Returns: (fall_time, impact_speed)
    """
    if altitude <= 0 or mass <= 0:
        return 0.0, 0.0

    v = 0.0  # vertical velocity (downward positive)
    h = altitude
    t = 0.0

    while h > 0:
        # Drag force: F_d = 0.5 * rho * v^2 * Cd * A
        drag_accel = 0.5 * RHO * v * v * cd * area / mass
        # Net acceleration (gravity minus drag)
        accel = G - drag_accel
        v += accel * dt
        h -= v * dt
        t += dt

        # Safety: cap at 5 min
        if t > 300:
            break

    return t, v


def estimate_cross_section(mass):
    """Estimate payload cross-sectional area from mass.

    Rough approximation: assume sphere-like payload.
    Volume ~ mass/density, then A = pi*r^2
    """
    # Assume payload density ~500 kg/m^3 (loose package)
    density = 500.0
    volume = mass / density
    radius = (3.0 * volume / (4.0 * math.pi)) ** (1.0/3.0)
    return math.pi * radius * radius


def calculate_drop(altitude, speed, heading, target_lat, target_lon,
                   wind_speed=0.0, wind_dir=0.0, mass=1.0, cd=0.5,
                   pilot_lat=None, pilot_lon=None):
    """Calculate release point for payload drop.

    Args:
        altitude: drone altitude AGL (meters)
        speed: drone groundspeed (m/s)
        heading: drone heading/track (degrees, 0=North)
        target_lat, target_lon: target coordinates
        wind_speed: wind speed (m/s)
        wind_dir: wind FROM direction (degrees, meteorological convention)
        mass: payload mass (kg)
        cd: drag coefficient
        pilot_lat, pilot_lon: pilot position (optional)

    Returns: dict with all drop parameters
    """
    result = {}

    # Calculate fall time
    area = estimate_cross_section(mass)

    if cd > 0 and mass > 0:
        fall_t, impact_v = fall_time_with_drag(altitude, mass, cd, area)
        result["method"] = "drag_model"
    else:
        fall_t = fall_time_simple(altitude)
        impact_v = G * fall_t
        result["method"] = "free_fall"

    result["fall_time_s"] = round(fall_t, 2)
    result["impact_speed_ms"] = round(impact_v, 1)
    result["impact_speed_mph"] = round(impact_v * 2.237, 1)

    # Horizontal drift from drone speed
    # Payload maintains drone horizontal velocity at release
    drone_drift = speed * fall_t
    result["drone_drift_m"] = round(drone_drift, 1)

    # Wind drift during fall
    # wind_dir is FROM, so drift direction = wind_dir + 180
    wind_drift = wind_speed * fall_t
    wind_drift_dir = (wind_dir + 180) % 360  # direction wind pushes TO
    result["wind_drift_m"] = round(wind_drift, 1)
    result["wind_drift_dir"] = round(wind_drift_dir, 1)

    # Total drift vector (combine drone movement and wind)
    drone_dx = drone_drift * math.sin(math.radians(heading))  # East component
    drone_dy = drone_drift * math.cos(math.radians(heading))  # North component

    wind_dx = wind_drift * math.sin(math.radians(wind_drift_dir))
    wind_dy = wind_drift * math.cos(math.radians(wind_drift_dir))

    total_dx = drone_dx + wind_dx
    total_dy = drone_dy + wind_dy
    total_drift = math.sqrt(total_dx**2 + total_dy**2)
    drift_bearing = (math.degrees(math.atan2(total_dx, total_dy)) + 360) % 360

    result["total_drift_m"] = round(total_drift, 1)
    result["drift_bearing"] = round(drift_bearing, 1)

    # Release point = target - drift vector
    # Release BEFORE the target (upwind/uptrack)
    release_bearing = (drift_bearing + 180) % 360
    release_lat, release_lon = destination_point(
        target_lat, target_lon, release_bearing, total_drift
    )

    result["release_lat"] = round(release_lat, 7)
    result["release_lon"] = round(release_lon, 7)
    result["target_lat"] = target_lat
    result["target_lon"] = target_lon

    # Distance and bearing from pilot to release point
    if pilot_lat is not None and pilot_lon is not None:
        dist_to_release = haversine_distance(pilot_lat, pilot_lon,
                                             release_lat, release_lon)
        bear_to_release = bearing_between(pilot_lat, pilot_lon,
                                          release_lat, release_lon)
        result["pilot_to_release_m"] = round(dist_to_release, 1)
        result["pilot_to_release_bearing"] = round(bear_to_release, 1)
        result["pilot_lat"] = pilot_lat
        result["pilot_lon"] = pilot_lon

    # Google Maps link
    result["maps_link"] = (
        "https://maps.google.com/maps?q={:.7f},{:.7f}".format(
            release_lat, release_lon)
    )

    return result


def get_current_position():
    """Try to get current GPS position from gps_tool."""
    try:
        out = subprocess.run(
            ["python3",
             "/data/data/com.termux/files/home/ax12-research/tools/gps_tool.py",
             "position"],
            capture_output=True, text=True, timeout=10
        ).stdout
        lat_m = re.search(r"Lat:\s*([-\d.]+)", out)
        lon_m = re.search(r"Lon:\s*([-\d.]+)", out)
        if lat_m and lon_m:
            return float(lat_m.group(1)), float(lon_m.group(1))
    except Exception:
        pass
    return None, None


def compass_direction(bearing):
    """Convert bearing to compass direction string."""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = int((bearing + 11.25) / 22.5) % 16
    return dirs[idx]


def print_result(result):
    """Pretty-print drop calculation results."""
    print("")
    print("=" * 60)
    print("  PAYLOAD DROP POINT CALCULATION")
    print("=" * 60)

    print("")
    print("  Method: {}".format(result["method"].replace("_", " ").title()))
    print("  Fall time: {:.2f} s".format(result["fall_time_s"]))
    print("  Impact speed: {:.1f} m/s ({:.1f} mph)".format(
        result["impact_speed_ms"], result["impact_speed_mph"]))

    print("")
    print("  --- Drift ---")
    print("  Drone forward drift: {:.1f} m".format(result["drone_drift_m"]))
    print("  Wind drift: {:.1f} m toward {}".format(
        result["wind_drift_m"], compass_direction(result["wind_drift_dir"])))
    print("  Total drift: {:.1f} m bearing {:.0f} ({})".format(
        result["total_drift_m"], result["drift_bearing"],
        compass_direction(result["drift_bearing"])))

    print("")
    print("  --- Release Point ---")
    print("  Lat: {:.7f}".format(result["release_lat"]))
    print("  Lon: {:.7f}".format(result["release_lon"]))

    if "pilot_to_release_m" in result:
        bear = result["pilot_to_release_bearing"]
        print("")
        print("  --- From Pilot ---")
        print("  Distance: {:.0f} m".format(result["pilot_to_release_m"]))
        print("  Bearing: {:.0f} ({})".format(bear, compass_direction(bear)))

    print("")
    print("  Maps: {}".format(result["maps_link"]))

    # ASCII diagram
    print_diagram(result)
    print("")


def print_diagram(result):
    """Print ASCII diagram of drop geometry."""
    drift = result["total_drift_m"]
    fall_t = result["fall_time_s"]

    print("")
    print("  --- Drop Geometry (not to scale) ---")
    print("")
    print("       RELEASE            TARGET")
    print("         |                  |")
    print("         V  ----drone---->  |")
    print("        . .                 |")
    print("       .   .  (fall)        |")
    print("      .     .               |")
    print("     .       .              |")
    print("    *         * <-- impact  X")
    print("    |<-- {:.1f}m drift -->|".format(drift))
    print("    |   fall: {:.2f}s        |".format(fall_t))
    print("")
    if "pilot_to_release_m" in result:
        d = result["pilot_to_release_m"]
        b = result["pilot_to_release_bearing"]
        print("    Pilot -> Release: {:.0f}m @ {:.0f} {}".format(
            d, b, compass_direction(b)))


def mode_calc(args):
    """One-shot calculation mode."""
    heading = args.heading
    if heading is None and args.target_lat is not None:
        pilot_lat, pilot_lon = args.pilot_lat, args.pilot_lon
        if pilot_lat is None or pilot_lon is None:
            pilot_lat, pilot_lon = get_current_position()
        if pilot_lat is not None and args.target_lat is not None:
            heading = bearing_between(pilot_lat, pilot_lon,
                                      args.target_lat, args.target_lon)
        else:
            heading = 0.0
    elif heading is None:
        heading = 0.0

    pilot_lat = args.pilot_lat
    pilot_lon = args.pilot_lon
    if pilot_lat is None or pilot_lon is None:
        pilot_lat, pilot_lon = get_current_position()

    result = calculate_drop(
        altitude=args.alt,
        speed=args.speed,
        heading=heading,
        target_lat=args.target_lat,
        target_lon=args.target_lon,
        wind_speed=args.wind_speed or 0.0,
        wind_dir=args.wind_dir or 0.0,
        mass=args.mass or 1.0,
        cd=args.cd or 0.5,
        pilot_lat=pilot_lat,
        pilot_lon=pilot_lon,
    )

    print_result(result)
    return result


def mode_table(args):
    """Generate drop table for multiple altitudes and speeds."""
    altitudes = [20, 30, 40, 50, 75, 100, 150]
    speeds = [5, 8, 10, 12, 15, 20]

    mass = args.mass or 1.0
    cd = args.cd or 0.5
    wind_speed = args.wind_speed or 0.0
    wind_dir = args.wind_dir or 0.0

    print("")
    print("=" * 70)
    print("  DROP TABLE - Release Distance (meters before target)")
    print("  Mass: {:.1f}kg | Cd: {} | Wind: {:.1f}m/s from {:.0f}".format(
        mass, cd, wind_speed, wind_dir))
    print("=" * 70)
    print("")

    # Header
    hdr = "{:<8}".format("Alt(m)")
    for s in speeds:
        hdr += "{:>8}".format(s)
    print("  {}".format(hdr))
    print("  {:>8}{:>48}".format("Speed(m/s) ->", ""))
    print("  {}".format("-" * 58))

    for alt in altitudes:
        row = "{:<8}".format(alt)
        for spd in speeds:
            result = calculate_drop(
                altitude=alt, speed=spd, heading=0.0,
                target_lat=args.target_lat or 0.0,
                target_lon=args.target_lon or 0.0,
                wind_speed=wind_speed, wind_dir=wind_dir,
                mass=mass, cd=cd
            )
            row += "{:>8.1f}".format(result["total_drift_m"])
        print("  {}".format(row))

    # Fall time column
    print("")
    print("  {:<8}{:<15}{:<15}{:<12}".format(
        "Alt(m)", "Fall Time(s)", "Impact(m/s)", "Impact(mph)"))
    print("  {}".format("-" * 50))
    for alt in altitudes:
        result = calculate_drop(
            altitude=alt, speed=0, heading=0,
            target_lat=0, target_lon=0,
            mass=mass, cd=cd
        )
        print("  {:<8}{:<15.2f}{:<15.1f}{:<12.1f}".format(
            alt, result["fall_time_s"], result["impact_speed_ms"],
            result["impact_speed_mph"]))

    print("")


def mode_interactive(args):
    """Interactive mode with prompts."""
    print("")
    print("  PAYLOAD DROP CALCULATOR - Interactive Mode")
    print("  " + "-" * 40)

    def ask(prompt, default=None, type_fn=float):
        s = "  {}".format(prompt)
        if default is not None:
            s += " [{}]".format(default)
        s += ": "
        try:
            val = input(s).strip()
            if not val and default is not None:
                return type_fn(default)
            return type_fn(val)
        except (ValueError, EOFError):
            if default is not None:
                return type_fn(default)
            return None

    alt = ask("Drone altitude AGL (m)", 50)
    speed = ask("Drone groundspeed (m/s)", 10)
    heading = ask("Drone heading (deg, 0=N)", 0)
    target_lat = ask("Target latitude", 35.148)
    target_lon = ask("Target longitude", -79.476)
    wind_speed = ask("Wind speed (m/s)", 0)
    wind_dir = ask("Wind FROM direction (deg)", 0)
    mass = ask("Payload mass (kg)", 1.0)
    cd = ask("Drag coefficient", 0.5)

    pilot_lat, pilot_lon = get_current_position()
    if pilot_lat is None:
        pilot_lat = ask("Pilot latitude (or 0 to skip)", 0)
        pilot_lon = ask("Pilot longitude (or 0 to skip)", 0)
        if pilot_lat == 0 and pilot_lon == 0:
            pilot_lat, pilot_lon = None, None

    result = calculate_drop(
        altitude=alt, speed=speed, heading=heading,
        target_lat=target_lat, target_lon=target_lon,
        wind_speed=wind_speed, wind_dir=wind_dir,
        mass=mass, cd=cd,
        pilot_lat=pilot_lat, pilot_lon=pilot_lon,
    )

    print_result(result)


def main():
    parser = argparse.ArgumentParser(
        description="Payload Drop Point Calculator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest="mode")

    # Calc mode
    calc_p = subparsers.add_parser("calc", help="One-shot calculation")
    calc_p.add_argument("--alt", type=float, required=True,
                        help="Altitude AGL (meters)")
    calc_p.add_argument("--speed", type=float, required=True,
                        help="Groundspeed (m/s)")
    calc_p.add_argument("--heading", type=float, default=None,
                        help="Drone heading (deg, 0=N)")
    calc_p.add_argument("--target-lat", type=float, required=True,
                        help="Target latitude")
    calc_p.add_argument("--target-lon", type=float, required=True,
                        help="Target longitude")
    calc_p.add_argument("--wind-speed", type=float, default=0,
                        help="Wind speed (m/s)")
    calc_p.add_argument("--wind-dir", type=float, default=0,
                        help="Wind FROM direction (deg)")
    calc_p.add_argument("--mass", type=float, default=1.0,
                        help="Payload mass (kg)")
    calc_p.add_argument("--cd", type=float, default=0.5,
                        help="Drag coefficient")
    calc_p.add_argument("--pilot-lat", type=float, default=None,
                        help="Pilot latitude")
    calc_p.add_argument("--pilot-lon", type=float, default=None,
                        help="Pilot longitude")

    # Table mode
    table_p = subparsers.add_parser("table", help="Generate drop table")
    table_p.add_argument("--target-lat", type=float, default=0,
                         help="Target latitude")
    table_p.add_argument("--target-lon", type=float, default=0,
                         help="Target longitude")
    table_p.add_argument("--wind-speed", type=float, default=0,
                         help="Wind speed (m/s)")
    table_p.add_argument("--wind-dir", type=float, default=0,
                         help="Wind FROM direction (deg)")
    table_p.add_argument("--mass", type=float, default=1.0,
                         help="Payload mass (kg)")
    table_p.add_argument("--cd", type=float, default=0.5,
                         help="Drag coefficient")

    # Interactive mode
    subparsers.add_parser("interactive", help="Interactive prompts")

    args = parser.parse_args()

    if args.mode == "calc":
        mode_calc(args)
    elif args.mode == "table":
        mode_table(args)
    elif args.mode == "interactive":
        mode_interactive(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
