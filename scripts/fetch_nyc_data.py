#!/usr/bin/env python3
"""
fetch_nyc_data.py — Pull live NYC building footprints near the High Line and
project them into the local metric coordinate system used by index.html.

Source: NYC Open Data (Socrata) "Building Footprints" dataset
        https://data.cityofnewyork.us/resource/5zhs-2jue.json

NOTE: the spec named dataset `qb5r-6dg9`, but that resource returns 404 — it
does not exist on the portal. `5zhs-2jue` is the live Building Footprints
dataset. Its height column is `height_roof` (in feet); there is no `name` or
`num_floors` column, so `bin` is used as both id and label.

Why this output shape:
  index.html's SiteParser.parseGeoJSON() already re-centers, rescales to a
  60-unit canvas, and applies a Mercator correction of cos(centerLat). By
  projecting to meters CENTERED AT (0,0) here, that correction collapses to
  cos(0) = 1, so the parser ingests this file verbatim with no edits. The
  written file is a standard GeoJSON FeatureCollection whose coordinates are
  already local meters ([x, z], +x east, +z north).

Run:
  python scripts/fetch_nyc_data.py
Output:
  data/highline_footprints.json
"""

import json
import math
import os
import sys
import urllib.parse
import urllib.request

# ── Bounding box: corridor extent + MAX_R (widened 2026-08-15) ───────────────
# The original box (40.740–40.755, -74.010 to -74.000) was short of the engines'
# MAX_R = 350 m culling radius on every side, and the deck overhung it by 33 m at
# each end — so rays that found no building inside 350 m had sometimes simply left
# the data. See IMPLEMENTATION_PLAN.md W2 "occluder coverage".
#
# These bounds are the access-point extent (40.7397–40.7553, -74.0083 to -74.0027)
# padded by 350 m on every side:  350/110574 = 0.003165 deg lat,
#                                 350/(111320*cos(40.7475)) = 0.004147 deg lon.
# Padding is deliberately ASYMMETRIC in longitude so the bbox centre — and hence the
# local projection origin — stays at exactly (40.7475, -74.005). Keeping the origin
# fixed means every coordinate in the re-fetched file is directly comparable with the
# previous one; a moved origin would have shifted all x by ~42 m for no reason.
LAT_MIN, LAT_MAX = 40.7365, 40.7585      # centre 40.7475, half-span 1216 m
LON_MIN, LON_MAX = -74.0125, -73.9975    # centre -74.005, half-span 633 m

# Projection origin = bbox center → guarantees output is centered at (0, 0)
LAT0 = (LAT_MIN + LAT_MAX) / 2.0
LON0 = (LON_MIN + LON_MAX) / 2.0

# Meters-per-degree (equirectangular approximation, accurate at this scale)
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(LAT0))

FEET_TO_M = 0.3048
DEFAULT_HEIGHT_M = 10.0       # fallback when height_roof is missing/zero

# ── High Line alignment (south -> north), approximate real geometry ──────────
# Access points are the real stair/elevator entrances; weight ~ relative
# entrance popularity (south terminus / Whitney and north terminus / Hudson
# Yards are the busiest). lat, lon, name, weight.
HIGH_LINE_ACCESS = [
    (40.7397, -74.0083, "Gansevoort St", 1.0),
    (40.7420, -74.0076, "14th St",       1.0),
    (40.7434, -74.0070, "16th St",       0.5),
    (40.7447, -74.0064, "18th St",       0.4),
    (40.7460, -74.0058, "20th St",       0.4),
    (40.7479, -74.0049, "23rd St",       0.7),
    (40.7495, -74.0040, "26th St",       0.4),
    (40.7508, -74.0033, "28th St",       0.4),
    (40.7522, -74.0027, "30th St",       0.7),
    (40.7553, -74.0050, "34th St-Hudson Yards", 1.0),
]

DATASET = "5zhs-2jue"
BASE_URL = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "highline_footprints.json",
)


def build_where() -> str:
    """SoQL spatial filter: within_box(NWlat, NWlon, SElat, SElon)."""
    return f"within_box(the_geom, {LAT_MAX}, {LON_MIN}, {LAT_MIN}, {LON_MAX})"


def build_query_url() -> str:
    params = {
        "$select": "the_geom, bin, height_roof, construction_year",
        "$where": build_where(),
        "$limit": "50000",
    }
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def expected_count() -> int:
    """Ask the API how many rows SHOULD match, as an independent second opinion.

    WHY THIS EXISTS. On 2026-06-28 this script ran, received a partial response of 176
    rows against a true 955, wrote them without complaint, and the project analysed
    18% of its own site for six weeks. Nothing in the output looked wrong: every row
    was a valid building with a real height and construction year. The only way to
    catch it was to ask a second time and compare — so that is now mandatory, and a
    mismatch aborts rather than warns.
    """
    url = BASE_URL + "?" + urllib.parse.urlencode(
        {"$select": "count(1)", "$where": build_where()})
    req = urllib.request.Request(url, headers={"User-Agent": "highline-abm/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    return int(rows[0][next(iter(rows[0]))])


def fetch(url: str) -> list:
    print(f"[fetch] GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "highline-abm/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    print(f"[fetch] {len(rows)} rows returned")
    return rows


def project(lon: float, lat: float):
    """lon/lat (degrees) → local meters centered at (0, 0)."""
    x = (lon - LON0) * M_PER_DEG_LON
    z = (lat - LAT0) * M_PER_DEG_LAT
    return [round(x, 2), round(z, 2)]


def height_meters(row: dict) -> float:
    roof = row.get("height_roof")  # feet
    if roof not in (None, ""):
        try:
            h = float(roof) * FEET_TO_M
            if h > 0:
                return round(h, 2)
        except (TypeError, ValueError):
            pass
    return DEFAULT_HEIGHT_M


def project_geometry(geom: dict):
    """Project a GeoJSON Polygon/MultiPolygon's coordinates into local meters."""
    if not geom or "type" not in geom:
        return None
    t = geom["type"]
    if t == "Polygon":
        return {
            "type": "Polygon",
            "coordinates": [[project(c[0], c[1]) for c in ring]
                            for ring in geom["coordinates"]],
        }
    if t == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [[[project(c[0], c[1]) for c in ring] for ring in poly]
                            for poly in geom["coordinates"]],
        }
    return None


def build_high_line() -> dict:
    """Project the High Line centerline + access points into local meters
    (same projection as the footprints) and measure real deck length."""
    access = []
    centerline = []
    prev = None
    length_m = 0.0
    for lat, lon, name, weight in HIGH_LINE_ACCESS:
        xz = project(lon, lat)
        centerline.append(xz)
        access.append({"name": name, "x": xz[0], "z": xz[1], "weight": weight})
        if prev is not None:
            length_m += math.hypot(xz[0] - prev[0], xz[1] - prev[1])
        prev = xz
    return {
        "length_m": round(length_m, 1),
        "centerline": centerline,
        "access_points": access,
    }


def main() -> int:
    try:
        rows = fetch(build_query_url())
    except Exception as exc:  # network / API failure
        print(f"[error] fetch failed: {exc}", file=sys.stderr)
        return 1

    features = []
    skipped = 0
    for i, row in enumerate(rows):
        geom = project_geometry(row.get("the_geom"))
        if geom is None:
            skipped += 1
            continue
        fid = row.get("bin") or f"bldg_{i}"
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "id": str(fid),
                "name": str(fid),  # dataset has no name column; bin is the label
                "height": height_meters(row),
                # Footprints carry no land-use; default keeps it in TYPE_EMIT.
                "type": "building",
                "construction_year": row.get("construction_year"),
            },
        })

    # ── completeness guard — see expected_count() for why ────────────────────────
    print(f"[parse] {len(rows)} rows returned · {len(features)} kept · "
          f"{skipped} skipped (geometry not Polygon/MultiPolygon)")
    try:
        n_expected = expected_count()
    except Exception as exc:
        print(f"[error] completeness count failed: {exc}\n"
              f"[abort] refusing to write an unverified footprint set.", file=sys.stderr)
        return 2
    if n_expected != len(rows):
        print(f"[abort] COMPLETENESS CHECK FAILED\n"
              f"          API count(1) for this $where : {n_expected}\n"
              f"          rows actually returned       : {len(rows)}\n"
              f"          shortfall                    : {n_expected - len(rows)}\n"
              f"        The response was partial. This is exactly the failure that cost "
              f"this project 779 buildings on 2026-06-28.\n"
              f"        NOTHING WAS WRITTEN. Re-run; if it persists, the spatial index "
              f"is degraded and you should wait rather than analyse a subset.",
              file=sys.stderr)
        return 3
    if skipped:
        print(f"[warn] {skipped} row(s) dropped on geometry type — these are silently "
              f"lost from the analysis. Investigate before trusting the output.")
    print(f"[ok] completeness verified: {n_expected} expected == {len(rows)} returned")

    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "source": BASE_URL,
            "bbox_latlon": [LAT_MIN, LON_MIN, LAT_MAX, LON_MAX],
            "origin_latlon": [LAT0, LON0],
            "units": "meters_local_centered",
            "count": len(features),
            "rows_returned": len(rows),
            "rows_skipped_geometry_type": skipped,
            "api_expected_count": n_expected,
            "completeness_verified": True,
            "bbox_note": "corridor extent + 350 m (MAX_R) on every side; centre pinned "
                         "to (40.7475, -74.005) so the local origin is unchanged from "
                         "the pre-2026-08-15 file",
        },
        "features": features,
        "high_line": build_high_line(),
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f)
    print(f"[done] wrote {len(features)} buildings "
          f"({skipped} skipped) -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
