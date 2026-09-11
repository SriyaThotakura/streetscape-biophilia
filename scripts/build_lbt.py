"""build_lbt.py — Radiance-lineage (Ladybug Tools) recompute of the deck's SVF and
sunlit hours, as a validation of the from-scratch hl_core engines.

Method = the same one behind Ladybug's "Direct Sun Hours" component: Ladybug
`Sunpath` gives real solar geometry at the site; `ladybug_geometry` casts rays
from each deck point and tests occlusion against the building context (walls +
roofs extruded from the footprints). No Grasshopper, no Radiance binaries — the
two requested metrics are geometric, and this IS the validated LB computation.

Outputs (same shape as my engines, written ALONGSIDE for A/B):
  data/highline_viewshed_lbt.json   per-point svf_deck / svf_prepark
  data/highline_solar_lbt.json      per-point sun_<date> (+ _prepark), same keys as highline_solar
  data/lbt_validation.json          correlation of hl_core vs Ladybug (r / R² / RMSE)

Buildings-only (matches the from-scratch model for a clean A/B; trees are a later layer).
Run from project root:  python scripts/build_lbt.py            # svf + 3 solstice/equinox dates
                        python scripts/build_lbt.py --quick     # fewer sky dirs / coarser sun (smoke)
"""
import json, math, os, sys, argparse
import numpy as np
import hl_core as hlc
from ladybug.location import Location
from ladybug.sunpath import Sunpath
from ladybug_geometry.geometry3d.pointvector import Point3D, Vector3D
from ladybug_geometry.geometry3d.ray import Ray3D
from ladybug_geometry.geometry3d.face import Face3D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
EYE_DECK = hlc.EYE_DECK
DECK_H = hlc.DECK_H
MAX_R = 350.0
SPACING = 8.0
# ── era thresholds: TWO CONSTANTS, TWO JOBS ─────────────────────────────────
# They answer different questions and are deliberately not the same number.
#
#   REZONING_YEAR = 2005  — CAUSAL. "Who caused the enclosure?" The 2005 West
#       Chelsea rezoning is the causal event: it moved the development rights and
#       made the tower boom legal. Used by build_attribution (the leaderboard and
#       its era bands) and by build_map_data's era colouring.
#
#   OPENING_YEAR = 2009   — BASELINE. "What did the deck lose AS A PARK?" The
#       pre-park counterfactual must be the city as it stood when the park opened.
#       A baseline predating the park would count loss no visitor ever experienced.
#       Used for svf_prepark, the solar prepark series, the deficit field, and
#       everything generated from the deficit.
#
# The split was decided on that reasoning. It is ALSO true that the 2009 baseline
# restores a statistical significance the 2005 baseline removed (the equal-material
# paired delta) — that was NOT the reason for the choice, and both results are
# recorded so a reader can check the claim rather than take it on trust.
#
# Boundary convention: "pre-park" is `yr <= OPENING_YEAR`, i.e. a building completed
# in 2009 counts as standing when the park opened. This matches the convention the
# engines used before 2026-08-16 and the secondary cut in build_attribution.
REZONING_YEAR = 2005          # causal
OPENING_YEAR = 2009           # baseline
PARK_YEAR = OPENING_YEAR      # this engine is a BASELINE engine
DATES = {"winter_solstice": (12, 21), "equinox": (3, 21), "summer_solstice": (6, 21)}
SUN_STEP_MIN = 10          # match hl_core's 10-min cadence
TZ = -5


def building_faces(b):
    """Walls + roof of a footprint extruded to height, in ladybug coords
    (x=east, y=north, z=up)."""
    p = b.poly; h = b.h; faces = []
    for i in range(len(p) - 1):
        x0, y0 = float(p[i][0]), float(p[i][1])
        x1, y1 = float(p[i + 1][0]), float(p[i + 1][1])
        faces.append(Face3D([Point3D(x0, y0, 0), Point3D(x1, y1, 0),
                             Point3D(x1, y1, h), Point3D(x0, y0, h)]))
    faces.append(Face3D([Point3D(float(x), float(y), h) for x, y in p[:-1]]))
    return faces


def blocked(faces_nearby, origin, vec):
    """True if a ray from origin along vec hits any nearby face (early-exit)."""
    ray = Ray3D(origin, vec)
    for f in faces_nearby:
        if f.intersect_line_ray(ray) is not None:
            return True
    return False


def nearby(blds, faces, px, py, r):
    out = []
    for bi, b in enumerate(blds):
        if math.hypot(b.c[0] - px, b.c[1] - py) - b.rad <= r:
            out.extend(faces[bi])
    return out


def sky_dirs(n_alt=7, n_az=24):
    """Hemisphere sample directions + cos(alt) weights (projected-solid-angle SVF)."""
    dirs, w = [], []
    for ia in range(n_alt):
        alt = (ia + 0.5) / n_alt * (math.pi / 2)
        ca, sa = math.cos(alt), math.sin(alt)
        for iz in range(n_az):
            az = (iz + 0.5) / n_az * 2 * math.pi
            dirs.append(Vector3D(ca * math.sin(az), ca * math.cos(az), sa))
            w.append(ca)           # cos(alt) weight = projected solid angle
    return dirs, np.array(w)


def svf_at(faces_nearby, origin, dirs, w):
    vis = np.array([0.0 if blocked(faces_nearby, origin, d) else 1.0 for d in dirs])
    return float((vis * w).sum() / w.sum())


def sun_vectors(sp, month, day, step_min):
    """(reverse) sun vectors for the daylight hours of a date, at step_min cadence."""
    vs = []
    for m in range(0, 24 * 60, step_min):
        sun = sp.calculate_sun(month, day, m / 60.0)
        if sun.is_during_day:
            vs.append(sun.sun_vector.reverse())     # point from deck toward the sun
    return vs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="coarse sampling (smoke test)")
    ap.add_argument("--epw", help="optional EPW for provenance/location (not required)")
    args = ap.parse_args()

    site = hlc.load_site()
    blds = site.buildings
    lat0, lon0 = site.meta.get("origin_latlon", [40.7475, -74.005])
    if args.epw:
        from ladybug.epw import EPW
        loc = EPW(args.epw).location; lat0, lon0 = loc.latitude, loc.longitude
    loc = Location("High Line", latitude=lat0, longitude=lon0, time_zone=TZ)
    sp = Sunpath.from_location(loc)

    faces = [building_faces(b) for b in blds]
    pre_idx = [bi for bi, b in enumerate(blds) if (b.yr is not None and b.yr <= OPENING_YEAR)]
    samples = site.corridor.samples(SPACING)
    dirs, w = sky_dirs(*( (4, 12) if args.quick else (7, 24) ))
    step = 30 if args.quick else SUN_STEP_MIN
    sun_by_date = {name: sun_vectors(sp, mo, dy, step) for name, (mo, dy) in DATES.items()}

    view_out, solar_out = [], []
    for (pt, s) in samples:
        px, py = float(pt[0]), float(pt[1])
        origin = Point3D(px, py, EYE_DECK)
        fn_all = nearby(blds, faces, px, py, MAX_R)
        fn_pre = nearby([blds[i] for i in pre_idx], [faces[i] for i in pre_idx], px, py, MAX_R)
        svf_d = svf_at(fn_all, origin, dirs, w)
        svf_p = svf_at(fn_pre, origin, dirs, w) if fn_pre else 1.0
        view_out.append({"s_m": round(s, 1), "svf_deck": round(svf_d, 4),
                         "svf_prepark": round(svf_p, 4)})
        srec = {"s_m": round(s, 1)}
        for name, vecs in sun_by_date.items():
            lit = sum(0 if blocked(fn_all, Point3D(px, py, DECK_H), v) else 1 for v in vecs)
            lit_p = sum(0 if blocked(fn_pre, Point3D(px, py, DECK_H), v) else 1 for v in vecs)
            srec[f"sun_{name}"] = round(lit * step / 60.0, 2)
            srec[f"sun_{name}_prepark"] = round(lit_p * step / 60.0, 2)
        solar_out.append(srec)

    meta = {"method": "Ladybug Sunpath + ladybug-geometry ray/Face3D intersection "
            "(the LB Direct Sun Hours method); buildings-only; no Radiance binaries",
            "site_latlon": [lat0, lon0], "tz": TZ, "sun_step_min": step,
            "sky_dirs": len(dirs), "max_radius_m": MAX_R, "n_points": len(view_out),
            "park_year": PARK_YEAR, "epw": args.epw or "not used (geometric sun hours)"}
    json.dump({"metadata": meta, "points": view_out}, open(os.path.join(D, "highline_viewshed_lbt.json"), "w"), indent=1)
    json.dump({"metadata": meta, "points": solar_out}, open(os.path.join(D, "highline_solar_lbt.json"), "w"), indent=1)

    # ── validation vs hl_core ──
    def corr(a, b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        m = ~(np.isnan(a) | np.isnan(b))
        if m.sum() < 3: return None
        r = float(np.corrcoef(a[m], b[m])[0, 1]); rmse = float(np.sqrt(np.mean((a[m] - b[m]) ** 2)))
        return {"r": round(r, 3), "r2": round(r * r, 3), "rmse": round(rmse, 4),
                "mean_mine": round(float(a[m].mean()), 3), "mean_lbt": round(float(b[m].mean()), 3), "n": int(m.sum())}
    mine_v = json.load(open(os.path.join(D, "highline_viewshed.json")))["points"]
    mine_s = json.load(open(os.path.join(D, "highline_solar.json")))["points"]
    val = {"svf_deck": corr([p["svf_deck"] for p in mine_v], [p["svf_deck"] for p in view_out]),
           "sun_winter": corr([p["sun_winter_solstice"] for p in mine_s], [p["sun_winter_solstice"] for p in solar_out]),
           "sun_summer": corr([p["sun_summer_solstice"] for p in mine_s], [p["sun_summer_solstice"] for p in solar_out])}
    json.dump({"comparison": "hl_core (from-scratch) vs Ladybug", "metrics": val},
              open(os.path.join(D, "lbt_validation.json"), "w"), indent=1)

    print("\n=== LADYBUG RECOMPUTE — validation of the from-scratch engine ===")
    print(f"site {lat0:.4f},{lon0:.4f}  |  {len(dirs)} sky dirs  |  sun step {step} min  |  {len(view_out)} pts")
    for k, v in val.items():
        if v:
            print(f"  {k:12s}  r={v['r']:+.2f}  R²={v['r2']:.2f}  RMSE={v['rmse']:.3f}   "
                  f"mean mine {v['mean_mine']} vs LB {v['mean_lbt']}")
    print("wrote highline_viewshed_lbt.json, highline_solar_lbt.json, lbt_validation.json")


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
