"""build_solar.py — Engine 2: solar accretion on the elevated deck.

For deck sample points, computes daily SUNLIT HOURS by stepping the sun across
the sky (hl_core.sun_path) and ray-casting toward it against the building prisms:
the deck point is in sun iff no roofline subtends an elevation above the sun's.
Runs three representative dates with ALL buildings vs PRE-park buildings only —
the difference is sunlight stolen by post-2009 development.

Writes data/highline_solar.json. Run from project root:
    python scripts/build_solar.py
"""
import json, os
import numpy as np
import hl_core as hlc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "highline_solar.json")

DECK_SURFACE = hlc.DECK_H     # sunlight lands on the deck surface (~9 m)
MAX_R = 400.0
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
DT_H = 1.0 / 6.0
DATES = {"summer_solstice": 172, "equinox": 81, "winter_solstice": 355}


def sunlit_hours(edges, px, pz, els, es, ns):
    """Hours the point is in sun over the given sun path."""
    if edges is None:
        return float(len(els) * DT_H)
    H = edges[2]
    lit = 0
    for el, dx, dz in zip(els, es, ns):
        t, hit = hlc.ray_uv(edges, px, pz, dx, dz, MAX_R)
        if hit.any() and np.arctan2(H[hit] - DECK_SURFACE, t[hit]).max() > el:
            continue
        lit += 1
    return lit * DT_H


def main():
    site = hlc.load_site()
    bld = site.buildings
    samples = site.corridor.samples(SPACING)
    bld_pre = [b for b in bld if (b.yr is not None and b.yr <= OPENING_YEAR)]
    paths = {name: hlc.sun_path(day, dt_h=DT_H) for name, day in DATES.items()}
    daylen = {name: len(p[0]) * DT_H for name, p in paths.items()}

    pts_out = []
    for (pt, s) in samples:
        px, pz = float(pt[0]), float(pt[1])
        e_all = hlc.edges_for(bld, px, pz, MAX_R)
        e_pre = hlc.edges_for(bld_pre, px, pz, MAX_R)
        rec = {"s_m": round(s, 1), "x": round(px, 2) + 0.0, "z": round(pz, 2) + 0.0}
        for name, (els, es, ns) in paths.items():
            rec[f"sun_{name}"] = round(sunlit_hours(e_all, px, pz, els, es, ns), 2)
            rec[f"sun_{name}_prepark"] = round(sunlit_hours(e_pre, px, pz, els, es, ns), 2)
        pts_out.append(rec)

    meta = {"model": "solar-geometry sun path + ray-cast occlusion on deck surface",
            "lat": hlc.LAT, "deck_surface_m": DECK_SURFACE, "timestep_min": DT_H * 60,
            "max_radius_m": MAX_R, "park_year": PARK_YEAR, "dates_day_of_year": DATES,
            "daylight_hours": {k: round(v, 2) for k, v in daylen.items()},
            "n_points": len(pts_out), "length_m": site.length_m}
    json.dump({"metadata": meta, "points": pts_out}, open(OUT, "w"), indent=1)

    print("\n=== ENGINE 2 — SOLAR ACCRETION on the deck ({} points, {} m) ===".format(len(pts_out), site.length_m))
    for name in DATES:
        allh = np.array([p[f"sun_{name}"] for p in pts_out])
        preh = np.array([p[f"sun_{name}_prepark"] for p in pts_out])
        stolen = preh - allh
        i = int(stolen.argmax())
        print(f"\n{name.replace('_',' ')}  (daylight {daylen[name]:.1f} h)")
        print(f"   mean sunlit hours  all towers : {allh.mean():.2f} h   "
              f"pre-park : {preh.mean():.2f} h")
        print(f"   sunlight STOLEN by post-{PARK_YEAR} dev: {stolen.mean():.2f} h avg, "
              f"up to {stolen.max():.2f} h (at s={pts_out[i]['s_m']} m)")
        print(f"   deck in shadow >half the day  : "
              f"{100*np.mean(allh < daylen[name]/2):.0f}% of points")
    print(f"\nwrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
