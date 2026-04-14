#!/usr/bin/env python3
"""Rover/Boat Navigation Assistant for ArduRover Operations.

GPS math (haversine), route planning, geofencing, and speed conversion.
Python stdlib only -- runs on any platform including Termux/AX12.

Usage:
    python3 rover_nav.py waypoint LAT1 LON1 LAT2 LON2
    python3 rover_nav.py route LAT1,LON1 LAT2,LON2 LAT3,LON3 ...
    python3 rover_nav.py area LAT1,LON1 LAT2,LON2 LAT3,LON3 ...
    python3 rover_nav.py speed VALUE FROM_UNIT [TO_UNIT]
    python3 rover_nav.py geofence POINT_LAT,POINT_LON TYPE PARAMS...
    python3 rover_nav.py demo

Geofence types:
    geofence LAT,LON circle CENTER_LAT,CENTER_LON RADIUS_M
    geofence LAT,LON rect MIN_LAT,MIN_LON MAX_LAT,MAX_LON

Speed units: ms, kmh, knots, mph

Options:
    --json    Output JSON instead of formatted text
"""

import sys
import math
import json

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EARTH_RADIUS_M = 6371000.0

# Camp Mackall, NC demo waypoints (SORCC training area)
DEMO_WAYPOINTS = [
    (35.1400, -79.4800, "Start - Camp Mackall Gate"),
    (35.1420, -79.4750, "WP1 - Treeline East"),
    (35.1450, -79.4780, "WP2 - Creek Crossing"),
    (35.1470, -79.4820, "WP3 - Hilltop OP"),
    (35.1440, -79.4850, "WP4 - Rally Point"),
    (35.1400, -79.4800, "RTL - Camp Mackall Gate"),
]

# ---------------------------------------------------------------------------
# GPS Math (Haversine)
# ---------------------------------------------------------------------------

def to_rad(deg):
    return deg * math.pi / 180.0

def to_deg(rad):
    return rad * 180.0 / math.pi

def haversine(lat1, lon1, lat2, lon2):
    """Return distance in meters between two GPS coordinates."""
    dlat = to_rad(lat2 - lat1)
    dlon = to_rad(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c

def bearing(lat1, lon1, lat2, lon2):
    """Return initial bearing in degrees from point 1 to point 2."""
    dlon = to_rad(lon2 - lon1)
    rlat1 = to_rad(lat1)
    rlat2 = to_rad(lat2)
    x = math.sin(dlon) * math.cos(rlat2)
    y = (math.cos(rlat1) * math.sin(rlat2) -
         math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon))
    brng = to_deg(math.atan2(x, y))
    return (brng + 360) % 360

def compass_dir(deg):
    """Convert bearing degrees to 16-point compass direction."""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(deg / 22.5) % 16
    return dirs[idx]

def polygon_area(coords):
    """Calculate area of a GPS polygon using the shoelace formula on projected coords.

    Projects to approximate flat coordinates near the centroid for accuracy.
    Returns area in square meters.
    """
    if len(coords) < 3:
        return 0.0

    # Centroid for projection reference
    clat = sum(c[0] for c in coords) / len(coords)
    clon = sum(c[1] for c in coords) / len(coords)

    # Project to meters from centroid
    pts = []
    for lat, lon in coords:
        x = haversine(clat, clon, clat, lon)
        if lon < clon:
            x = -x
        y = haversine(clat, clon, lat, clon)
        if lat < clat:
            y = -y
        pts.append((x, y))

    # Shoelace formula
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0

# ---------------------------------------------------------------------------
# Speed Conversion
# ---------------------------------------------------------------------------

# All conversions go through m/s as canonical
TO_MS = {
    "ms":    1.0,
    "kmh":   1.0 / 3.6,
    "knots": 0.514444,
    "mph":   0.44704,
}

FROM_MS = {
    "ms":    1.0,
    "kmh":   3.6,
    "knots": 1.94384,
    "mph":   2.23694,
}

def convert_speed(value, from_unit, to_unit=None):
    """Convert speed between units. If to_unit is None, convert to all."""
    from_unit = from_unit.lower().replace("/", "")
    ms = value * TO_MS.get(from_unit, 1.0)
    if to_unit:
        to_unit = to_unit.lower().replace("/", "")
        return ms * FROM_MS.get(to_unit, 1.0)
    return {u: ms * f for u, f in FROM_MS.items()}

# ---------------------------------------------------------------------------
# Geofence
# ---------------------------------------------------------------------------

def point_in_circle(plat, plon, clat, clon, radius_m):
    """Check if point is inside a circular geofence."""
    dist = haversine(plat, plon, clat, clon)
    return dist <= radius_m, dist

def point_in_rect(plat, plon, min_lat, min_lon, max_lat, max_lon):
    """Check if point is inside a rectangular geofence."""
    inside = (min_lat <= plat <= max_lat) and (min_lon <= plon <= max_lon)
    return inside

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def fmt_dist(m):
    """Format distance for display."""
    if m >= 1000:
        return f"{m/1000:.3f} km"
    return f"{m:.1f} m"

def fmt_area(sq_m):
    """Format area for display."""
    if sq_m >= 1_000_000:
        return f"{sq_m/1_000_000:.4f} km2"
    elif sq_m >= 10_000:
        return f"{sq_m/10_000:.4f} ha"
    return f"{sq_m:.1f} m2"

def fmt_bearing(deg):
    return f"{deg:.1f} ({compass_dir(deg)})"

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_waypoint(args, as_json=False):
    """Calculate bearing and distance between two GPS coordinates."""
    if len(args) < 4:
        print("Usage: rover_nav.py waypoint LAT1 LON1 LAT2 LON2")
        return 1
    lat1, lon1, lat2, lon2 = float(args[0]), float(args[1]), float(args[2]), float(args[3])
    dist = haversine(lat1, lon1, lat2, lon2)
    brng = bearing(lat1, lon1, lat2, lon2)

    if as_json:
        print(json.dumps({
            "from": {"lat": lat1, "lon": lon1},
            "to": {"lat": lat2, "lon": lon2},
            "distance_m": round(dist, 2),
            "bearing_deg": round(brng, 2),
            "compass": compass_dir(brng),
        }, indent=2))
    else:
        print(f"=== WAYPOINT NAV ===")
        print(f"From:     {lat1:.6f}, {lon1:.6f}")
        print(f"To:       {lat2:.6f}, {lon2:.6f}")
        print(f"Distance: {fmt_dist(dist)}")
        print(f"Bearing:  {fmt_bearing(brng)}")
        # ETA at typical rover speeds
        for spd_name, spd_ms in [("Walk 1.5m/s", 1.5), ("Rover 3m/s", 3.0), ("Fast 5m/s", 5.0)]:
            if dist > 0:
                eta_s = dist / spd_ms
                mins = int(eta_s // 60)
                secs = int(eta_s % 60)
                print(f"ETA ({spd_name}): {mins}m {secs}s")
    return 0

def cmd_route(args, as_json=False):
    """Calculate total route distance for a series of waypoints."""
    if len(args) < 2:
        print("Usage: rover_nav.py route LAT1,LON1 LAT2,LON2 ...")
        return 1

    waypoints = []
    for arg in args:
        parts = arg.split(",")
        if len(parts) < 2:
            print(f"Bad waypoint format: {arg} (use LAT,LON)")
            return 1
        waypoints.append((float(parts[0]), float(parts[1])))

    legs = []
    total_dist = 0.0
    for i in range(len(waypoints) - 1):
        lat1, lon1 = waypoints[i]
        lat2, lon2 = waypoints[i + 1]
        dist = haversine(lat1, lon1, lat2, lon2)
        brng = bearing(lat1, lon1, lat2, lon2)
        total_dist += dist
        legs.append({
            "leg": i + 1,
            "from": {"lat": lat1, "lon": lon1},
            "to": {"lat": lat2, "lon": lon2},
            "distance_m": round(dist, 2),
            "bearing_deg": round(brng, 2),
            "compass": compass_dir(brng),
        })

    if as_json:
        print(json.dumps({
            "waypoints": len(waypoints),
            "legs": legs,
            "total_distance_m": round(total_dist, 2),
        }, indent=2))
    else:
        print(f"=== ROUTE PLAN ({len(waypoints)} waypoints, {len(legs)} legs) ===")
        cum = 0.0
        for leg in legs:
            cum += leg["distance_m"]
            print(f"Leg {leg['leg']}: {leg['from']['lat']:.6f},{leg['from']['lon']:.6f} -> "
                  f"{leg['to']['lat']:.6f},{leg['to']['lon']:.6f}")
            print(f"         {fmt_dist(leg['distance_m'])} @ {fmt_bearing(leg['bearing_deg'])}  "
                  f"(cumulative: {fmt_dist(cum)})")
        print(f"---")
        print(f"Total distance: {fmt_dist(total_dist)}")
        for spd_name, spd_ms in [("Walk 1.5m/s", 1.5), ("Rover 3m/s", 3.0), ("Fast 5m/s", 5.0)]:
            eta_s = total_dist / spd_ms
            mins = int(eta_s // 60)
            secs = int(eta_s % 60)
            print(f"ETA ({spd_name}): {mins}m {secs}s")
    return 0

def cmd_area(args, as_json=False):
    """Calculate area of a polygon defined by GPS coordinates."""
    if len(args) < 3:
        print("Usage: rover_nav.py area LAT1,LON1 LAT2,LON2 LAT3,LON3 ...")
        return 1

    coords = []
    for arg in args:
        parts = arg.split(",")
        if len(parts) < 2:
            print(f"Bad coordinate format: {arg} (use LAT,LON)")
            return 1
        coords.append((float(parts[0]), float(parts[1])))

    area = polygon_area(coords)
    # Also compute perimeter
    perimeter = 0.0
    for i in range(len(coords)):
        j = (i + 1) % len(coords)
        perimeter += haversine(coords[i][0], coords[i][1],
                               coords[j][0], coords[j][1])

    if as_json:
        print(json.dumps({
            "vertices": len(coords),
            "area_m2": round(area, 2),
            "area_hectares": round(area / 10000, 4),
            "perimeter_m": round(perimeter, 2),
        }, indent=2))
    else:
        print(f"=== SURVEY AREA ({len(coords)} vertices) ===")
        for i, (lat, lon) in enumerate(coords):
            print(f"  V{i+1}: {lat:.6f}, {lon:.6f}")
        print(f"Area:      {fmt_area(area)}")
        if area >= 10000:
            print(f"           ({area/10000:.4f} hectares)")
        print(f"Perimeter: {fmt_dist(perimeter)}")
    return 0

def cmd_speed(args, as_json=False):
    """Convert between speed units."""
    if len(args) < 2:
        print("Usage: rover_nav.py speed VALUE FROM_UNIT [TO_UNIT]")
        print("Units: ms, kmh, knots, mph")
        return 1

    value = float(args[0])
    from_unit = args[1].lower()
    to_unit = args[2].lower() if len(args) > 2 else None

    if from_unit not in TO_MS:
        print(f"Unknown unit: {from_unit}. Use: ms, kmh, knots, mph")
        return 1
    if to_unit and to_unit not in FROM_MS:
        print(f"Unknown unit: {to_unit}. Use: ms, kmh, knots, mph")
        return 1

    if to_unit:
        result = convert_speed(value, from_unit, to_unit)
        if as_json:
            print(json.dumps({"value": value, "from": from_unit, "to": to_unit, "result": round(result, 4)}))
        else:
            print(f"{value} {from_unit} = {result:.4f} {to_unit}")
    else:
        results = convert_speed(value, from_unit)
        if as_json:
            print(json.dumps({"value": value, "from": from_unit,
                              "conversions": {k: round(v, 4) for k, v in results.items()}}, indent=2))
        else:
            print(f"=== SPEED CONVERSION ===")
            print(f"{value} {from_unit} =")
            unit_labels = {"ms": "m/s", "kmh": "km/h", "knots": "knots", "mph": "mph"}
            for u, v in results.items():
                marker = " <--" if u == from_unit else ""
                print(f"  {v:10.4f} {unit_labels[u]}{marker}")
    return 0

def cmd_geofence(args, as_json=False):
    """Check if a point is inside a geofence."""
    if len(args) < 3:
        print("Usage:")
        print("  rover_nav.py geofence LAT,LON circle CENTER_LAT,CENTER_LON RADIUS_M")
        print("  rover_nav.py geofence LAT,LON rect MIN_LAT,MIN_LON MAX_LAT,MAX_LON")
        return 1

    pt = args[0].split(",")
    plat, plon = float(pt[0]), float(pt[1])
    fence_type = args[1].lower()

    if fence_type == "circle":
        if len(args) < 4:
            print("Circle geofence needs: CENTER_LAT,CENTER_LON RADIUS_M")
            return 1
        center = args[2].split(",")
        clat, clon = float(center[0]), float(center[1])
        radius = float(args[3])
        inside, dist = point_in_circle(plat, plon, clat, clon, radius)

        if as_json:
            print(json.dumps({
                "point": {"lat": plat, "lon": plon},
                "fence": {"type": "circle", "center": {"lat": clat, "lon": clon}, "radius_m": radius},
                "inside": inside,
                "distance_to_center_m": round(dist, 2),
                "margin_m": round(radius - dist, 2),
            }, indent=2))
        else:
            status = "INSIDE" if inside else "OUTSIDE"
            flag = "" if inside else "*** BREACH ***"
            print(f"=== GEOFENCE CHECK (CIRCLE) ===")
            print(f"Point:    {plat:.6f}, {plon:.6f}")
            print(f"Center:   {clat:.6f}, {clon:.6f}")
            print(f"Radius:   {fmt_dist(radius)}")
            print(f"Distance: {fmt_dist(dist)}")
            print(f"Margin:   {fmt_dist(radius - dist)}")
            print(f"Status:   {status} {flag}")

    elif fence_type == "rect":
        if len(args) < 4:
            print("Rect geofence needs: MIN_LAT,MIN_LON MAX_LAT,MAX_LON")
            return 1
        sw = args[2].split(",")
        ne = args[3].split(",")
        min_lat, min_lon = float(sw[0]), float(sw[1])
        max_lat, max_lon = float(ne[0]), float(ne[1])
        inside = point_in_rect(plat, plon, min_lat, min_lon, max_lat, max_lon)

        if as_json:
            print(json.dumps({
                "point": {"lat": plat, "lon": plon},
                "fence": {"type": "rect",
                           "sw": {"lat": min_lat, "lon": min_lon},
                           "ne": {"lat": max_lat, "lon": max_lon}},
                "inside": inside,
            }, indent=2))
        else:
            status = "INSIDE" if inside else "OUTSIDE"
            flag = "" if inside else "*** BREACH ***"
            print(f"=== GEOFENCE CHECK (RECT) ===")
            print(f"Point: {plat:.6f}, {plon:.6f}")
            print(f"SW:    {min_lat:.6f}, {min_lon:.6f}")
            print(f"NE:    {max_lat:.6f}, {max_lon:.6f}")
            print(f"Status: {status} {flag}")
    else:
        print(f"Unknown fence type: {fence_type}. Use: circle, rect")
        return 1
    return 0

def cmd_demo(as_json=False):
    """Run demo with Camp Mackall waypoints."""
    print("=== ROVER NAV DEMO - Camp Mackall, NC ===")
    print()

    # Waypoint calculation
    print("--- Waypoint (Gate to Treeline) ---")
    wp0 = DEMO_WAYPOINTS[0]
    wp1 = DEMO_WAYPOINTS[1]
    dist = haversine(wp0[0], wp0[1], wp1[0], wp1[1])
    brng = bearing(wp0[0], wp0[1], wp1[0], wp1[1])
    print(f"  {wp0[2]} -> {wp1[2]}")
    print(f"  Distance: {fmt_dist(dist)}")
    print(f"  Bearing:  {fmt_bearing(brng)}")
    print()

    # Route
    print("--- Full Route ---")
    total = 0.0
    for i in range(len(DEMO_WAYPOINTS) - 1):
        w1 = DEMO_WAYPOINTS[i]
        w2 = DEMO_WAYPOINTS[i + 1]
        d = haversine(w1[0], w1[1], w2[0], w2[1])
        b = bearing(w1[0], w1[1], w2[0], w2[1])
        total += d
        print(f"  Leg {i+1}: {w1[2][:20]:20s} -> {w2[2][:20]:20s}  "
              f"{fmt_dist(d):>12s}  {b:5.1f} {compass_dir(b)}")
    print(f"  Total: {fmt_dist(total)}")
    print()

    # Area (first 5 waypoints form a polygon, skip RTL duplicate)
    print("--- Survey Area (5 vertices) ---")
    poly = [(w[0], w[1]) for w in DEMO_WAYPOINTS[:5]]
    area = polygon_area(poly)
    print(f"  Area: {fmt_area(area)}")
    print()

    # Speed conversion
    print("--- Speed: 3 m/s rover ---")
    results = convert_speed(3.0, "ms")
    unit_labels = {"ms": "m/s", "kmh": "km/h", "knots": "knots", "mph": "mph"}
    for u, v in results.items():
        print(f"  {v:8.2f} {unit_labels[u]}")
    print()

    # Geofence
    print("--- Geofence: 500m circle around gate ---")
    gate = DEMO_WAYPOINTS[0]
    test_pt = DEMO_WAYPOINTS[3]  # Hilltop OP
    inside, dist_to = point_in_circle(test_pt[0], test_pt[1], gate[0], gate[1], 500.0)
    status = "INSIDE" if inside else "OUTSIDE"
    print(f"  Center: {gate[2]} ({gate[0]:.4f}, {gate[1]:.4f})")
    print(f"  Test:   {test_pt[2]} ({test_pt[0]:.4f}, {test_pt[1]:.4f})")
    print(f"  Radius: 500m  Distance: {fmt_dist(dist_to)}  Status: {status}")
    print()
    print("Demo complete.")
    return 0

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    if as_json:
        args.remove("--json")

    if not args:
        print(__doc__)
        return 1

    cmd = args[0].lower()
    cmd_args = args[1:]

    commands = {
        "waypoint": lambda: cmd_waypoint(cmd_args, as_json),
        "route":    lambda: cmd_route(cmd_args, as_json),
        "area":     lambda: cmd_area(cmd_args, as_json),
        "speed":    lambda: cmd_speed(cmd_args, as_json),
        "geofence": lambda: cmd_geofence(cmd_args, as_json),
        "demo":     lambda: cmd_demo(as_json),
    }

    if cmd in commands:
        return commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands.keys())}")
        return 1

if __name__ == "__main__":
    sys.exit(main() or 0)
