#!/usr/bin/env python3
"""
Airspace Awareness Tool for RadioMaster AX12
=============================================
Offline airspace restriction checker using the AX12's GPS position.
Python stdlib only - no external dependencies.

Provides pre-flight airspace briefing with:
- Known restricted/prohibited areas (MOAs, R-areas)
- Nearby airports with Class B/C/D/E airspace
- Distance and bearing calculations
- Sunrise/sunset estimation for flight window planning

Built-in database covers NC Fort Liberty / Camp Mackall operating area.

Usage:
    python3 airspace_check.py brief                    # Pre-flight brief from GPS
    python3 airspace_check.py brief <lat> <lon>        # Brief for specific position
    python3 airspace_check.py check <lat> <lon>        # Check position restrictions
    python3 airspace_check.py radius <lat> <lon> <nm>  # What's within N nm
    python3 airspace_check.py distance <lat> <lon> <id> # Distance to airport

Author: Kyle Adomavicius / SORCC
"""

import sys
import math
import json
import subprocess
import re
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NM_PER_DEG_LAT = 60.0  # 1 degree latitude ~= 60 nm
EARTH_RADIUS_NM = 3440.065  # Earth radius in nautical miles
FEET_PER_METER = 3.28084
SM_PER_NM = 1.15078  # statute miles per nautical mile

# ---------------------------------------------------------------------------
# Airspace Database - NC Fort Liberty / Camp Mackall Area
# ---------------------------------------------------------------------------

AIRPORTS = [
    {"id": "KFAY", "name": "Fayetteville Regional (Grannis Field)", "lat": 34.9912, "lon": -78.8803, "class": "D", "tower": True, "elev_ft": 189},
    {"id": "KPOB", "name": "Pope Army Airfield", "lat": 35.1709, "lon": -79.0145, "class": "D", "tower": True, "elev_ft": 218},
    {"id": "KFBG", "name": "Simmons Army Airfield (Fort Liberty)", "lat": 35.1318, "lon": -78.9367, "class": "D", "tower": True, "elev_ft": 244},
    {"id": "KSOP", "name": "Moore County Airport", "lat": 35.2374, "lon": -79.3912, "class": "E", "tower": False, "elev_ft": 455},
    {"id": "KHFF", "name": "Mackall Army Airfield", "lat": 35.0364, "lon": -79.4975, "class": "D", "tower": True, "elev_ft": 376},
    {"id": "KRDU", "name": "Raleigh-Durham International", "lat": 35.8776, "lon": -78.7875, "class": "C", "tower": True, "elev_ft": 435},
    {"id": "KCLT", "name": "Charlotte Douglas International", "lat": 35.2140, "lon": -80.9431, "class": "B", "tower": True, "elev_ft": 748},
    {"id": "KGSO", "name": "Piedmont Triad International", "lat": 36.0978, "lon": -79.9373, "class": "C", "tower": True, "elev_ft": 925},
    {"id": "KLBT", "name": "Lumberton Regional", "lat": 34.6100, "lon": -79.0595, "class": "E", "tower": False, "elev_ft": 126},
    {"id": "KEXX", "name": "Davidson County Airport", "lat": 35.7812, "lon": -80.3039, "class": "E", "tower": False, "elev_ft": 733},
    {"id": "KSUT", "name": "Cape Fear Regional Jetport", "lat": 34.7873, "lon": -78.0730, "class": "E", "tower": False, "elev_ft": 27},
    {"id": "KAFP", "name": "Anson County Airport", "lat": 35.0183, "lon": -80.0774, "class": "G", "tower": False, "elev_ft": 406},
    {"id": "5W4", "name": "Scotland County Airport", "lat": 34.7851, "lon": -79.5048, "class": "G", "tower": False, "elev_ft": 236},
    {"id": "N96", "name": "Carthage Airport", "lat": 35.3461, "lon": -79.4149, "class": "G", "tower": False, "elev_ft": 455},
]

# Restricted / Prohibited / MOA areas
RESTRICTED_AREAS = [
    {
        "id": "R-5311A",
        "name": "Fort Liberty Restricted Area A",
        "type": "Restricted",
        "center_lat": 35.14,
        "center_lon": -79.01,
        "radius_nm": 6.0,
        "floor_ft": 0,
        "ceiling_ft": 17999,
        "status": "Active - contact Pope Approach",
        "schedule": "Intermittent by NOTAM",
        "authority": "Fort Liberty Range Control",
    },
    {
        "id": "R-5311B",
        "name": "Fort Liberty Restricted Area B",
        "type": "Restricted",
        "center_lat": 35.08,
        "center_lon": -79.05,
        "radius_nm": 4.0,
        "floor_ft": 0,
        "ceiling_ft": 17999,
        "status": "Active - contact Pope Approach",
        "schedule": "Intermittent by NOTAM",
        "authority": "Fort Liberty Range Control",
    },
    {
        "id": "R-5311C",
        "name": "Fort Liberty Restricted Area C (Camp Mackall)",
        "type": "Restricted",
        "center_lat": 35.04,
        "center_lon": -79.50,
        "radius_nm": 5.0,
        "floor_ft": 0,
        "ceiling_ft": 17999,
        "status": "Active - contact Pope Approach",
        "schedule": "Intermittent by NOTAM",
        "authority": "Fort Liberty Range Control",
    },
    {
        "id": "R-5311D",
        "name": "Fort Liberty Impact Area",
        "type": "Restricted",
        "center_lat": 35.17,
        "center_lon": -79.10,
        "radius_nm": 3.0,
        "floor_ft": 0,
        "ceiling_ft": 50000,
        "status": "Continuous when active",
        "schedule": "Published by NOTAM",
        "authority": "Fort Liberty Range Control",
    },
    {
        "id": "MOA-SEYMOUR",
        "name": "Seymour Johnson MOA",
        "type": "MOA",
        "center_lat": 35.34,
        "center_lon": -77.96,
        "radius_nm": 20.0,
        "floor_ft": 500,
        "ceiling_ft": 17999,
        "status": "Active intermittent",
        "schedule": "Published by NOTAM",
        "authority": "Seymour Johnson AFB",
    },
    {
        "id": "MOA-PAMLICO",
        "name": "Pamlico MOA",
        "type": "MOA",
        "center_lat": 35.25,
        "center_lon": -76.70,
        "radius_nm": 25.0,
        "floor_ft": 8000,
        "ceiling_ft": 17999,
        "status": "Active intermittent",
        "schedule": "Published by NOTAM",
        "authority": "Cherry Point MCAS",
    },
]

NATIONAL_PARKS = [
    {
        "id": "NP-MOORES-CREEK",
        "name": "Moores Creek National Battlefield",
        "lat": 34.4581,
        "lon": -78.1103,
        "radius_nm": 1.0,
        "note": "No drone ops without NPS permit (36 CFR 1.5)",
    },
    {
        "id": "NP-GUILFORD",
        "name": "Guilford Courthouse NMP",
        "lat": 36.1323,
        "lon": -79.8440,
        "radius_nm": 0.5,
        "note": "No drone ops without NPS permit (36 CFR 1.5)",
    },
    {
        "id": "NP-CARL-SANDBURG",
        "name": "Carl Sandburg Home NHS",
        "lat": 35.2679,
        "lon": -82.4535,
        "radius_nm": 0.5,
        "note": "No drone ops without NPS permit (36 CFR 1.5)",
    },
]

# Default airspace radii (nm) for airport classes
CLASS_RADIUS_NM = {
    "B": 5.0,
    "C": 5.0,
    "D": 4.0,
    "E": 4.0,
    "G": 0.0,
}


# ---------------------------------------------------------------------------
# Geometry Helpers
# ---------------------------------------------------------------------------

def haversine_nm(lat1, lon1, lat2, lon2):
    """Great-circle distance in nautical miles between two points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_NM * c


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing (true) from point 1 to point 2, in degrees."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    brg = math.degrees(math.atan2(x, y))
    return (brg + 360) % 360


def compass_dir(bearing):
    """Convert bearing to 8-point compass direction."""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((bearing + 22.5) / 45) % 8
    return dirs[idx]


# ---------------------------------------------------------------------------
# Sunrise / Sunset (simplified solar calculation)
# ---------------------------------------------------------------------------

def sun_times(lat, lon, date=None):
    """
    Compute approximate sunrise and sunset times (UTC) for a given position and date.
    Uses the NOAA simplified algorithm. Accuracy ~1-2 minutes.
    Returns (sunrise_utc, sunset_utc) as datetime objects, or (None, None) for polar.
    """
    if date is None:
        date = datetime.now(timezone.utc).date()

    # Day of year
    n = date.timetuple().tm_yday

    # Solar noon approximation
    lng_hour = lon / 15.0

    # Sunrise
    t_rise = n + (6 - lng_hour) / 24
    t_set = n + (18 - lng_hour) / 24

    results = {}
    for label, t in [("sunrise", t_rise), ("sunset", t_set)]:
        # Sun's mean anomaly
        M = (0.9856 * t) - 3.289

        # Sun's true longitude
        L = M + (1.916 * math.sin(math.radians(M))) + (0.020 * math.sin(math.radians(2 * M))) + 282.634
        L = L % 360

        # Sun's right ascension
        RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L))))
        RA = RA % 360

        # RA in same quadrant as L
        L_quad = (math.floor(L / 90)) * 90
        RA_quad = (math.floor(RA / 90)) * 90
        RA = RA + (L_quad - RA_quad)
        RA = RA / 15  # convert to hours

        # Sun's declination
        sin_dec = 0.39782 * math.sin(math.radians(L))
        cos_dec = math.cos(math.asin(sin_dec))

        # Sun's local hour angle
        zenith = 90.833  # official zenith for sunrise/sunset
        cos_H = (math.cos(math.radians(zenith)) - (sin_dec * math.sin(math.radians(lat)))) / (cos_dec * math.cos(math.radians(lat)))

        if cos_H > 1 or cos_H < -1:
            return None, None  # No sunrise/sunset (polar)

        if label == "sunrise":
            H = 360 - math.degrees(math.acos(cos_H))
        else:
            H = math.degrees(math.acos(cos_H))
        H = H / 15  # hours

        # Local mean time
        T = H + RA - (0.06571 * t) - 6.622

        # UTC
        UT = T - lng_hour
        UT = UT % 24

        hours = int(UT)
        minutes = int((UT - hours) * 60)
        seconds = int(((UT - hours) * 60 - minutes) * 60)

        dt = datetime(date.year, date.month, date.day, hours, minutes, seconds, tzinfo=timezone.utc)
        results[label] = dt

    return results.get("sunrise"), results.get("sunset")


def format_local_time(dt_utc, utc_offset_hours=-4):
    """Format UTC datetime to local time string. Default offset is EDT (-4)."""
    if dt_utc is None:
        return "N/A"
    local = dt_utc + timedelta(hours=utc_offset_hours)
    tz_name = "EDT" if utc_offset_hours == -4 else "EST" if utc_offset_hours == -5 else f"UTC{utc_offset_hours:+d}"
    return f"{local.strftime('%H:%M')} {tz_name} ({dt_utc.strftime('%H:%M')}Z)"


# ---------------------------------------------------------------------------
# GPS Integration (uses gps_position.py patterns)
# ---------------------------------------------------------------------------

def get_gps_position():
    """Get current position from Android location services."""
    try:
        result = subprocess.run(
            ["su", "0", "dumpsys", "location"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout + result.stderr
    except Exception:
        return None, None

    for line in output.split("\n"):
        m = re.search(
            r"(\w+): Location\[(\w+)\s+([-\d.]+),([-\d.]+)\s+hAcc=([\d.]+)",
            line,
        )
        if m:
            return float(m.group(3)), float(m.group(4))

    return None, None


# ---------------------------------------------------------------------------
# Check Functions
# ---------------------------------------------------------------------------

def check_position(lat, lon):
    """Check a position against all known restricted areas and airports."""
    results = {
        "position": {"lat": lat, "lon": lon},
        "inside_restricted": [],
        "nearby_restricted": [],
        "inside_airport_airspace": [],
        "nearby_airports": [],
        "inside_national_park": [],
        "warnings": [],
    }

    # Check restricted areas
    for area in RESTRICTED_AREAS:
        dist = haversine_nm(lat, lon, area["center_lat"], area["center_lon"])
        brg = bearing_deg(lat, lon, area["center_lat"], area["center_lon"])
        entry = {
            "id": area["id"],
            "name": area["name"],
            "type": area["type"],
            "distance_nm": round(dist, 1),
            "bearing": round(brg),
            "compass": compass_dir(brg),
            "floor_ft": area["floor_ft"],
            "ceiling_ft": area["ceiling_ft"],
            "status": area["status"],
            "authority": area["authority"],
        }
        if dist <= area["radius_nm"]:
            results["inside_restricted"].append(entry)
            results["warnings"].append(
                f"INSIDE {area['type'].upper()} AREA {area['id']} ({area['name']})"
            )
        elif dist <= area["radius_nm"] + 5:
            results["nearby_restricted"].append(entry)

    # Check airports
    for ap in AIRPORTS:
        dist = haversine_nm(lat, lon, ap["lat"], ap["lon"])
        brg = bearing_deg(lat, lon, ap["lat"], ap["lon"])
        radius = CLASS_RADIUS_NM.get(ap["class"], 0)
        entry = {
            "id": ap["id"],
            "name": ap["name"],
            "class": ap["class"],
            "distance_nm": round(dist, 1),
            "distance_sm": round(dist * SM_PER_NM, 1),
            "bearing": round(brg),
            "compass": compass_dir(brg),
            "tower": ap["tower"],
            "elev_ft": ap["elev_ft"],
        }
        if radius > 0 and dist <= radius:
            results["inside_airport_airspace"].append(entry)
            results["warnings"].append(
                f"INSIDE Class {ap['class']} airspace for {ap['id']} ({ap['name']})"
            )
        elif dist <= 10:
            results["nearby_airports"].append(entry)

    # Check national parks
    for park in NATIONAL_PARKS:
        dist = haversine_nm(lat, lon, park["lat"], park["lon"])
        if dist <= park["radius_nm"]:
            results["inside_national_park"].append({
                "id": park["id"],
                "name": park["name"],
                "distance_nm": round(dist, 1),
                "note": park["note"],
            })
            results["warnings"].append(f"INSIDE NPS AREA: {park['name']}")

    # Sort nearby by distance
    results["nearby_restricted"].sort(key=lambda x: x["distance_nm"])
    results["nearby_airports"].sort(key=lambda x: x["distance_nm"])

    return results


def find_within_radius(lat, lon, radius_nm):
    """Find all known features within a given radius."""
    features = []

    for ap in AIRPORTS:
        dist = haversine_nm(lat, lon, ap["lat"], ap["lon"])
        if dist <= radius_nm:
            brg = bearing_deg(lat, lon, ap["lat"], ap["lon"])
            features.append({
                "type": "Airport",
                "id": ap["id"],
                "name": ap["name"],
                "class": ap["class"],
                "distance_nm": round(dist, 1),
                "bearing": round(brg),
                "compass": compass_dir(brg),
            })

    for area in RESTRICTED_AREAS:
        dist = haversine_nm(lat, lon, area["center_lat"], area["center_lon"])
        if dist <= radius_nm + area["radius_nm"]:
            brg = bearing_deg(lat, lon, area["center_lat"], area["center_lon"])
            features.append({
                "type": area["type"],
                "id": area["id"],
                "name": area["name"],
                "distance_nm": round(dist, 1),
                "bearing": round(brg),
                "compass": compass_dir(brg),
            })

    for park in NATIONAL_PARKS:
        dist = haversine_nm(lat, lon, park["lat"], park["lon"])
        if dist <= radius_nm:
            brg = bearing_deg(lat, lon, park["lat"], park["lon"])
            features.append({
                "type": "National Park",
                "id": park["id"],
                "name": park["name"],
                "distance_nm": round(dist, 1),
                "bearing": round(brg),
                "compass": compass_dir(brg),
            })

    features.sort(key=lambda x: x["distance_nm"])
    return features


def distance_to_airport(lat, lon, airport_id):
    """Get distance and bearing to a specific airport."""
    airport_id = airport_id.upper()
    for ap in AIRPORTS:
        if ap["id"].upper() == airport_id:
            dist = haversine_nm(lat, lon, ap["lat"], ap["lon"])
            brg = bearing_deg(lat, lon, ap["lat"], ap["lon"])
            return {
                "id": ap["id"],
                "name": ap["name"],
                "class": ap["class"],
                "distance_nm": round(dist, 1),
                "distance_sm": round(dist * SM_PER_NM, 1),
                "bearing_true": round(brg),
                "compass": compass_dir(brg),
                "tower": ap["tower"],
                "elev_ft": ap["elev_ft"],
                "airspace_radius_nm": CLASS_RADIUS_NM.get(ap["class"], 0),
            }
    return None


def recommend_max_alt(check_result):
    """Recommend max altitude based on nearby airspace."""
    max_alt = 400  # Default Part 107

    if check_result["inside_restricted"]:
        max_alt = 0

    if check_result["inside_airport_airspace"]:
        max_alt = 0

    for ap in check_result["nearby_airports"]:
        if ap["distance_nm"] < 2:
            max_alt = min(max_alt, 200)
        elif ap["distance_nm"] < 3:
            max_alt = min(max_alt, 300)

    return max_alt


# ---------------------------------------------------------------------------
# Display Functions
# ---------------------------------------------------------------------------

def display_check(lat, lon):
    """Display airspace check results."""
    result = check_position(lat, lon)

    print("=" * 62)
    print("  AIRSPACE CHECK")
    print(f"  Position: {lat:.4f}, {lon:.4f}")
    print("=" * 62)

    if result["warnings"]:
        print()
        print("  *** WARNINGS ***")
        for w in result["warnings"]:
            print(f"  [!] {w}")

    if result["inside_restricted"]:
        print()
        print("  INSIDE RESTRICTED AIRSPACE:")
        for r in result["inside_restricted"]:
            print(f"    {r['id']} - {r['name']}")
            print(f"      Type: {r['type']}  Floor: {r['floor_ft']}ft  Ceiling: {r['ceiling_ft']}ft")
            print(f"      Status: {r['status']}")
            print(f"      Authority: {r['authority']}")

    if result["inside_airport_airspace"]:
        print()
        print("  INSIDE AIRPORT AIRSPACE:")
        for a in result["inside_airport_airspace"]:
            print(f"    {a['id']} - {a['name']} (Class {a['class']})")
            print(f"      Distance: {a['distance_nm']} nm ({a['distance_sm']} sm)  Bearing: {a['bearing']}d {a['compass']}")

    if not result["warnings"]:
        print()
        print("  [OK] No restricted airspace conflicts detected")

    if result["nearby_restricted"]:
        print()
        print("  NEARBY RESTRICTED AREAS (within 5 nm of boundary):")
        for r in result["nearby_restricted"][:5]:
            print(f"    {r['id']} ({r['type']}) - {r['distance_nm']} nm {r['compass']}")
            print(f"      {r['name']}")

    if result["nearby_airports"]:
        print()
        print("  NEARBY AIRPORTS (within 10 nm):")
        for a in result["nearby_airports"][:8]:
            twr = "TWR" if a["tower"] else "CTAF"
            print(f"    {a['id']:6s} Class {a['class']}  {a['distance_nm']:5.1f} nm  {a['bearing']:03d}d {a['compass']:2s}  {twr}  {a['name']}")

    max_alt = recommend_max_alt(result)
    print()
    if max_alt == 0:
        print("  RECOMMENDED MAX ALT: DO NOT FLY - Authorization required")
    else:
        print(f"  RECOMMENDED MAX ALT: {max_alt} ft AGL (Part 107)")
    print("=" * 62)

    return result


def display_radius(lat, lon, radius_nm):
    """Display all features within a radius."""
    features = find_within_radius(lat, lon, radius_nm)

    print("=" * 62)
    print(f"  FEATURES WITHIN {radius_nm} NM")
    print(f"  Center: {lat:.4f}, {lon:.4f}")
    print("=" * 62)

    if not features:
        print("  No known features within radius.")
    else:
        print(f"  {'Type':12s} {'ID':16s} {'Dist':>6s} {'Brg':>5s} Name")
        print(f"  {'-'*12} {'-'*16} {'-'*6} {'-'*5} {'-'*20}")
        for f in features:
            cls = f" ({f['class']})" if "class" in f else ""
            print(f"  {f['type']:12s} {f['id']:16s} {f['distance_nm']:5.1f}nm {f['bearing']:03d}d{f['compass']:>3s} {f['name']}{cls}")

    print(f"\n  Total: {len(features)} features")
    print("=" * 62)


def display_distance(lat, lon, airport_id):
    """Display distance to a specific airport."""
    info = distance_to_airport(lat, lon, airport_id)
    if info is None:
        print(f"  Airport '{airport_id}' not found in database.")
        print("  Known airports:")
        for ap in AIRPORTS:
            print(f"    {ap['id']:6s} - {ap['name']}")
        return

    print("=" * 62)
    print(f"  DISTANCE TO {info['id']}")
    print("=" * 62)
    print(f"  Airport:    {info['id']} - {info['name']}")
    print(f"  Class:      {info['class']}  {'(Towered)' if info['tower'] else '(Uncontrolled)'}")
    print(f"  Elevation:  {info['elev_ft']} ft MSL")
    print(f"  Distance:   {info['distance_nm']} nm ({info['distance_sm']} sm)")
    print(f"  Bearing:    {info['bearing_true']}d True ({info['compass']})")
    if info["airspace_radius_nm"] > 0:
        print(f"  Airspace:   {info['airspace_radius_nm']} nm radius (Class {info['class']})")
        inside = info["distance_nm"] <= info["airspace_radius_nm"]
        print(f"  Status:     {'INSIDE controlled airspace' if inside else 'Outside controlled airspace'}")
    print("=" * 62)


def display_brief(lat, lon):
    """Generate a comprehensive pre-flight airspace brief."""
    now = datetime.now(timezone.utc)
    check = check_position(lat, lon)
    sunrise, sunset = sun_times(lat, lon, now.date())

    # Determine if DST (rough: March-November for Eastern US)
    month = now.month
    utc_offset = -4 if 3 <= month <= 10 else -5

    print("=" * 62)
    print("  PRE-FLIGHT AIRSPACE BRIEF")
    print("=" * 62)
    print(f"  Date:       {now.strftime('%Y-%m-%d')} (UTC: {now.strftime('%H:%M')}Z)")
    print(f"  Position:   {lat:.4f}N, {abs(lon):.4f}W")
    print(f"  Maps:       https://maps.google.com/?q={lat},{lon}")

    # Sun times
    print()
    print("  SOLAR")
    print(f"  Sunrise:    {format_local_time(sunrise, utc_offset)}")
    print(f"  Sunset:     {format_local_time(sunset, utc_offset)}")
    if sunrise and sunset:
        civ_begin = sunrise + timedelta(minutes=-30)
        civ_end = sunset + timedelta(minutes=30)
        print(f"  Civ Twi:    {format_local_time(civ_begin, utc_offset)} - {format_local_time(civ_end, utc_offset)}")
        daylight = sunset - sunrise
        dl_hours = daylight.total_seconds() / 3600
        print(f"  Daylight:   {dl_hours:.1f} hours")

    # Airspace status
    print()
    print("  AIRSPACE STATUS")
    if check["warnings"]:
        for w in check["warnings"]:
            print(f"  [!] {w}")
    else:
        print("  [OK] No restricted airspace conflicts at this position")

    if check["inside_restricted"]:
        for r in check["inside_restricted"]:
            print(f"    {r['id']}: {r['floor_ft']}-{r['ceiling_ft']}ft  Contact: {r['authority']}")

    if check["inside_airport_airspace"]:
        for a in check["inside_airport_airspace"]:
            print(f"    {a['id']} Class {a['class']}: {a['distance_nm']} nm {a['compass']}  LAANC/ATC auth required")

    # Recommended altitude
    max_alt = recommend_max_alt(check)
    print()
    if max_alt == 0:
        print("  MAX ALTITUDE: DO NOT FLY without authorization")
    else:
        print(f"  MAX ALTITUDE: {max_alt} ft AGL (Part 107)")

    # Nearest airports
    print()
    print("  NEAREST AIRPORTS")
    all_airports = []
    for ap in AIRPORTS:
        dist = haversine_nm(lat, lon, ap["lat"], ap["lon"])
        brg = bearing_deg(lat, lon, ap["lat"], ap["lon"])
        all_airports.append({
            "id": ap["id"],
            "name": ap["name"],
            "class": ap["class"],
            "distance_nm": round(dist, 1),
            "bearing": round(brg),
            "compass": compass_dir(brg),
            "tower": ap["tower"],
        })
    all_airports.sort(key=lambda x: x["distance_nm"])

    for a in all_airports[:6]:
        twr = "TWR" if a["tower"] else "CTAF"
        cls = f"Class {a['class']}" if a["class"] != "G" else "      "
        print(f"    {a['id']:6s} {cls}  {a['distance_nm']:5.1f} nm  {a['bearing']:03d}d {a['compass']:2s}  {twr}  {a['name']}")

    # Nearby restricted
    if check["nearby_restricted"]:
        print()
        print("  NEARBY RESTRICTED/MOA (< 5 nm from boundary)")
        for r in check["nearby_restricted"][:4]:
            print(f"    {r['id']:16s} {r['distance_nm']:5.1f} nm {r['compass']:2s}  {r['name']}")

    # Regulatory reminders
    print()
    print("  REGULATORY NOTES")
    print("  - Part 107: 400ft AGL max, VLOS, daylight + civil twilight w/ anti-collision light")
    print("  - Controlled airspace: LAANC authorization or ATC waiver required")
    print("  - Restricted areas: Active status via NOTAM, contact authority listed")
    print("  - TFRs: Check tfr.faa.gov before flight (not available offline)")
    print("  - NOTAMS: Check notams.faa.gov before flight (not available offline)")

    print()
    print("  DISCLAIMER: Offline tool - verify with current FAA sources before flight")
    print("=" * 62)


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def print_usage():
    print("""
Airspace Awareness Tool - AX12
================================
Usage:
  airspace_check.py brief [<lat> <lon>]        Pre-flight airspace brief
  airspace_check.py check <lat> <lon>           Check position restrictions
  airspace_check.py radius <lat> <lon> <nm>     Features within N nautical miles
  airspace_check.py distance <lat> <lon> <id>   Distance to specific airport
  airspace_check.py list                        List all known airports/areas

Examples:
  airspace_check.py brief                       Brief from GPS position
  airspace_check.py brief 35.147 -79.476        Brief for Camp Mackall area
  airspace_check.py check 35.147 -79.476        Check a position
  airspace_check.py radius 35.147 -79.476 10    What's within 10 nm
  airspace_check.py distance 35.147 -79.476 KFAY  Distance to Fayetteville
""")


def list_database():
    """List all entries in the database."""
    print("=" * 62)
    print("  AIRSPACE DATABASE")
    print("=" * 62)
    print()
    print("  AIRPORTS:")
    print(f"  {'ID':6s} {'Class':5s} {'Twr':3s}  {'Lat':>9s} {'Lon':>10s}  Name")
    print(f"  {'-'*6} {'-'*5} {'-'*3}  {'-'*9} {'-'*10}  {'-'*30}")
    for ap in AIRPORTS:
        twr = "Y" if ap["tower"] else "N"
        print(f"  {ap['id']:6s} {ap['class']:^5s} {twr:^3s}  {ap['lat']:9.4f} {ap['lon']:10.4f}  {ap['name']}")

    print()
    print("  RESTRICTED AREAS / MOAs:")
    print(f"  {'ID':16s} {'Type':10s} {'Radius':>6s}  {'Floor':>7s} {'Ceil':>7s}  Name")
    print(f"  {'-'*16} {'-'*10} {'-'*6}  {'-'*7} {'-'*7}  {'-'*30}")
    for area in RESTRICTED_AREAS:
        print(f"  {area['id']:16s} {area['type']:10s} {area['radius_nm']:5.1f}nm  {area['floor_ft']:6d}ft {area['ceiling_ft']:6d}ft  {area['name']}")

    print()
    print("  NATIONAL PARKS:")
    for park in NATIONAL_PARKS:
        print(f"  {park['id']:20s} {park['name']}")

    print()
    print(f"  Total: {len(AIRPORTS)} airports, {len(RESTRICTED_AREAS)} restricted/MOA, {len(NATIONAL_PARKS)} NPS areas")
    print("=" * 62)


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print_usage()
        return

    cmd = args[0].lower()

    if cmd == "list":
        list_database()
        return

    if cmd == "brief":
        if len(args) >= 3:
            lat, lon = float(args[1]), float(args[2])
        else:
            lat, lon = get_gps_position()
            if lat is None:
                print("[!] Could not get GPS position. Provide lat/lon manually.")
                print("    Usage: airspace_check.py brief <lat> <lon>")
                return
            print(f"[*] GPS position: {lat:.4f}, {lon:.4f}")
            print()
        display_brief(lat, lon)

    elif cmd == "check":
        if len(args) < 3:
            print("Usage: airspace_check.py check <lat> <lon>")
            return
        lat, lon = float(args[1]), float(args[2])
        display_check(lat, lon)

    elif cmd == "radius":
        if len(args) < 4:
            print("Usage: airspace_check.py radius <lat> <lon> <nm>")
            return
        lat, lon, radius = float(args[1]), float(args[2]), float(args[3])
        display_radius(lat, lon, radius)

    elif cmd == "distance":
        if len(args) < 4:
            print("Usage: airspace_check.py distance <lat> <lon> <airport_id>")
            return
        lat, lon = float(args[1]), float(args[2])
        airport_id = args[3]
        display_distance(lat, lon, airport_id)

    else:
        print(f"Unknown command: {cmd}")
        print_usage()


if __name__ == "__main__":
    main()
