#!/usr/bin/env python3
"""
build_highline_exposure.py — Join the ComputerVision street-imagery audit onto
the High Line centerline segments used by index.html's pedestrian model.

Southern-corridor PILOT: the CV transect only carries imagery for points 8-47,
which lands on segment bins ~3-27 of 48. The south approach (bins 0-2) and the
entire northern stretch (bins 28-47, 26th St through Hudson Yards) have ZERO
CV data and are emitted as coverage:"none" with null metrics — never 0, never
interpolated across the gap. 0.0 is a legitimate measured value (P17's sky
view is genuinely 0), so null and 0 must stay distinct all the way through.

FRAMING (locked): the Mapillary photos are shot from streets beside and under
the viaduct (P17 is the underpass), so every metric here is STREET-LEVEL
CONTEXT EXPOSURE, not the on-deck pedestrian view.

Inputs (read-only):
  ComputerVision/SoftScan_Points.csv          50 pts, `id,lat,lng`, no header
  ComputerVision/highline_images_mapillary/   which points actually have imagery
  ComputerVision/highline_urban_audit.csv     39 pts — values are 255x the true
                                              fraction (0/255 masks were summed,
                                              not counted) -> divide by 255
  ComputerVision/HIGHLINE_MASTER_AUDIT.csv    12 pts — true percentages -> /100
  data/highline_footprints.json               high_line.centerline (local meters)

Output:
  data/highline_exposure.json

Run:
  python scripts/build_highline_exposure.py
"""

import csv
import hashlib
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CV_DIR = os.path.join(ROOT, "ComputerVision")
POINTS_CSV = os.path.join(CV_DIR, "SoftScan_Points.csv")
AUDIT_CSV = os.path.join(CV_DIR, "highline_urban_audit.csv")
MASTER_CSV = os.path.join(CV_DIR, "HIGHLINE_MASTER_AUDIT.csv")
IMAGE_DIR = os.path.join(CV_DIR, "highline_images_mapillary")
FOOTPRINTS = os.path.join(ROOT, "data", "highline_footprints.json")
OUT_PATH = os.path.join(ROOT, "data", "highline_exposure.json")

PED_SEGS = 48                 # must match PED_SEGS in index.html
INTERP_MAX_GAP = 2            # empty bin qualifies only if BOTH flanking
                              # measured bins are <= this many bins away
ENCLOSURE_CLAMP = 50.0        # notebook's own enclosure threshold

# Projection constants — MUST match scripts/fetch_nyc_data.py, which produced
# the centerline these points are joined against.
LAT_MIN, LAT_MAX = 40.740, 40.755
LON_MIN, LON_MAX = -74.010, -74.000
LAT0 = (LAT_MIN + LAT_MAX) / 2.0
LON0 = (LON_MIN + LON_MAX) / 2.0
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(LAT0))

NUMERIC_METRICS = ["gvi", "sky", "public_realm", "human_presence",
                   "hardness", "enclosure_clamped"]
TYPOLOGY_SLUGS = {"Canyon/Underpass": "canyon", "Open Plaza": "open_plaza"}


def project(lat: float, lon: float):
    """lat/lon degrees -> local meters, same space as high_line.centerline."""
    return ((lon - LON0) * M_PER_DEG_LON, (lat - LAT0) * M_PER_DEG_LAT)


def polyline_with_arclen(centerline):
    pts, s, prev = [], 0.0, None
    for x, z in centerline:
        if prev is not None:
            s += math.hypot(x - prev[0], z - prev[1])
        pts.append((x, z, s))
        prev = (x, z)
    return pts, s


def nearest_arc_length(pts, x, z):
    """Same math as nearestArcLength() in index.html: closest point on the
    polyline -> (arc length, perpendicular distance)."""
    best_d2, best_s = float("inf"), 0.0
    for k in range(len(pts) - 1):
        ax, az, as_ = pts[k]
        bx, bz, bs_ = pts[k + 1]
        dx, dz = bx - ax, bz - az
        seg2 = dx * dx + dz * dz or 1e-9
        t = ((x - ax) * dx + (z - az) * dz) / seg2
        t = 0.0 if t < 0 else 1.0 if t > 1 else t
        px, pz = ax + dx * t, az + dz * t
        d2 = (x - px) ** 2 + (z - pz) ** 2
        if d2 < best_d2:
            best_d2, best_s = d2, as_ + t * (bs_ - as_)
    return best_s, math.sqrt(best_d2)


def load_inputs():
    coords = {}
    with open(POINTS_CSV, newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 3:
                coords[int(row[0])] = (float(row[1]), float(row[2]))

    audit = {}
    with open(AUDIT_CSV, newline="") as f:
        for row in csv.DictReader(f):
            pid = int(row["id"])
            # 0/255 masks were summed, not counted -> values are 255x the
            # true fraction. Normalize and clip to [0, 1].
            audit[pid] = {
                "gvi": min(max(float(row["GVI"]) / 255.0, 0.0), 1.0),
                "sky": min(max(float(row["SkyFactor"]) / 255.0, 0.0), 1.0),
                "public_realm": min(max(float(row["PublicRealm"]) / 255.0, 0.0), 1.0),
                "human_presence": min(max(float(row["HumanPresence"]) / 255.0, 0.0), 1.0),
            }

    master = {}
    with open(MASTER_CSV, newline="") as f:
        for row in csv.DictReader(f):
            pid = int(row["Point"])
            raw_enc = float(row["Enclosure_Score"])
            master[pid] = {
                "gvi": float(row["Greenery_%"]) / 100.0,
                "sky": float(row["Sky_View_%"]) / 100.0,
                "hardness": float(row["Hardness_%"]) / 100.0,
                "enclosure_clamped": min(raw_enc, ENCLOSURE_CLAMP) / ENCLOSURE_CLAMP,
                "typology": TYPOLOGY_SLUGS.get(row["Typology"], None),
            }

    image_ids = sorted(
        int(f.split(".")[0]) for f in os.listdir(IMAGE_DIR) if f.endswith(".jpg")
    )

    with open(FOOTPRINTS) as f:
        hl = json.load(f)["high_line"]

    return coords, audit, master, image_ids, hl


def find_duplicate_pairs(image_ids):
    """Byte-identical photos (Mapillary returned the same nearest image for
    adjacent transect points). Returns {higher_id: lower_id}."""
    by_hash = {}
    for pid in image_ids:
        with open(os.path.join(IMAGE_DIR, f"{pid}.jpg"), "rb") as f:
            by_hash.setdefault(hashlib.md5(f.read()).hexdigest(), []).append(pid)
    twin_of = {}
    for ids in by_hash.values():
        ids.sort()
        for other in ids[1:]:
            twin_of[other] = ids[0]
    return twin_of


def point_metrics(pid, audit, master):
    """Merged per-point metrics. Master audit (correct units at source) wins
    for shared fields; hardness / enclosure_clamped / typology stay null for
    the points outside the 12-point master audit — never filled."""
    a = audit.get(pid)
    if a is None:
        return None
    m = master.get(pid, {})
    return {
        "gvi": m.get("gvi", a["gvi"]),
        "sky": m.get("sky", a["sky"]),
        "public_realm": a["public_realm"],
        "human_presence": a["human_presence"],
        "hardness": m.get("hardness"),
        "enclosure_clamped": m.get("enclosure_clamped"),
        "typology": m.get("typology"),
    }


def mean_or_none(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def main() -> int:
    coords, audit, master, image_ids, hl = load_inputs()
    pts, L = polyline_with_arclen(hl["centerline"])
    seg_len = L / PED_SEGS
    twin_of = find_duplicate_pairs(image_ids)
    kept_twin = {v: k for k, v in twin_of.items()}  # lower id -> its twin

    # ── Per-point join: every image-backed point contributes to its own bin ──
    contributions = {}   # bin -> list of metric dicts (includes twins)
    point_records = []   # emitted records: unique photos only
    for pid in image_ids:
        lat, lng = coords[pid]
        x, z = project(lat, lng)
        s, offset = nearest_arc_length(pts, x, z)
        b = min(int(s / L * PED_SEGS), PED_SEGS - 1)
        metrics = point_metrics(pid, audit, master)
        if metrics is None:
            print(f"[warn] point {pid} has an image but no audit row — skipped")
            continue
        contributions.setdefault(b, []).append(metrics)
        if pid in twin_of:
            continue  # byte-identical twin — represented by its kept partner
        point_records.append({
            "id": pid,
            "lat": lat,
            "lng": lng,
            "s_m": round(s, 2),
            "s_frac": round(s / L, 4),
            "bin": b,
            "offset_m": round(offset, 1),
            "image": f"{pid}.jpg",
            "mapillary_id": None,  # GAP: not recorded by the download notebook
            "duplicate_of": kept_twin.get(pid),  # twin point id sharing this photo
            "metrics": metrics,
        })

    # ── Segments: measured -> mean; short gaps -> interpolated; else none ──
    measured_bins = sorted(contributions.keys())
    segments = []
    for b in range(PED_SEGS):
        seg = {"bin": b, "s0_m": round(b * seg_len, 2), "s1_m": round((b + 1) * seg_len, 2)}
        if b in contributions:
            rows = contributions[b]
            seg["coverage"] = "measured"
            seg["n_points"] = len(rows)
            for k in NUMERIC_METRICS:
                seg[k] = mean_or_none([r[k] for r in rows])
            typs = {r["typology"] for r in rows if r["typology"]}
            seg["typology"] = typs.pop() if len(typs) == 1 else None
        else:
            lo = max((m for m in measured_bins if m < b), default=None)
            hi = min((m for m in measured_bins if m > b), default=None)
            if lo is not None and hi is not None and b - lo <= INTERP_MAX_GAP and hi - b <= INTERP_MAX_GAP:
                t = (b - lo) / (hi - lo)
                seg["coverage"] = "interpolated"
                seg["n_points"] = 0
                for k in NUMERIC_METRICS:
                    va = mean_or_none([r[k] for r in contributions[lo]])
                    vb = mean_or_none([r[k] for r in contributions[hi]])
                    # interpolate only when BOTH flanks carry the metric
                    seg[k] = round(va + (vb - va) * t, 4) if va is not None and vb is not None else None
                seg["typology"] = None
            else:
                seg["coverage"] = "none"
                seg["n_points"] = 0
                for k in NUMERIC_METRICS:
                    seg[k] = None
                seg["typology"] = None
        segments.append(seg)

    out = {
        "metadata": {
            "caveat": "street-level context exposure, not on-deck view",
            "sources": [
                "ComputerVision/SoftScan_Points.csv (50 survey points, straight synthetic transect)",
                "ComputerVision/highline_urban_audit.csv (values divided by 255: 0/255 masks were summed, not counted)",
                "ComputerVision/HIGHLINE_MASTER_AUDIT.csv (percentages divided by 100; wins over audit for shared fields)",
            ],
            "model": "nvidia/segformer-b5-finetuned-cityscapes-1024-1024",
            "imagery": "Mapillary street-level, capture metadata not retained",
            "centerline": "high_line.centerline from data/highline_footprints.json (local meters, fetch_nyc_data.py projection)",
            "ped_segs": PED_SEGS,
            "length_m": round(L, 1),
            "coverage_note": (
                "Southern-corridor pilot: imagery exists for transect points 8-47 only. "
                "Bins 0-2 and 28-47 have no CV data and are coverage:'none' with null metrics; "
                "null means unmeasured, 0.0 is a real measured value."
            ),
            "enclosure_note": f"enclosure_clamped = min(raw_enclosure, {ENCLOSURE_CLAMP:.0f}) / {ENCLOSURE_CLAMP:.0f}; raw score is unbounded when sky=0",
            "duplicates_note": (
                "Byte-identical Mapillary photos collapse to one point record (lower id kept, "
                "duplicate_of names the twin); both transect positions still contribute to their own bins."
            ),
            "interpolation_note": f"empty bins flanked by measured bins <= {INTERP_MAX_GAP} away are linearly interpolated along s and flagged",
            "typology_values": sorted(TYPOLOGY_SLUGS.values()),
        },
        "points": point_records,
        "segments": segments,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    # ── Verification report ──────────────────────────────────────────────────
    counts = {"measured": 0, "interpolated": 0, "none": 0}
    for s in segments:
        counts[s["coverage"]] += 1
    print(f"[done] wrote {OUT_PATH}")
    print(f"[coverage] measured={counts['measured']}  interpolated={counts['interpolated']}  none={counts['none']}  (of {PED_SEGS})")
    print(f"[points] {len(point_records)} unique records, {sum(len(v) for v in contributions.values())} bin contributions")
    print(f"[duplicates] {len(twin_of)} twins collapsed: " +
          ", ".join(f"{v}<-{k}" for k, v in sorted(twin_of.items())))

    edge_bins = list(range(0, 3)) + list(range(28, PED_SEGS))
    bad = [s["bin"] for s in segments if s["bin"] in edge_bins and
           (s["coverage"] != "none" or any(s[k] is not None for k in NUMERIC_METRICS + ["typology"]))]
    print(f"[check] bins 0-2 & 28-47 all none/null: {'PASS' if not bad else 'FAIL ' + str(bad)}")

    zero_fill = [s["bin"] for s in segments if s["coverage"] == "none" and
                 any(s[k] is not None for k in NUMERIC_METRICS)]
    print(f"[check] no values on uncovered segments: {'PASS' if not zero_fill else 'FAIL ' + str(zero_fill)}")

    measured_span = [s["bin"] for s in segments if s["coverage"] == "measured"]
    print(f"[span] measured bins {min(measured_span)}-{max(measured_span)}; "
          f"interpolated bins {[s['bin'] for s in segments if s['coverage'] == 'interpolated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
