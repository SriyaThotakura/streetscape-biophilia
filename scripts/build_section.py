"""build_section.py — long-section profile: nearest street-wall height on each
side of the deck, sampled along the walk.

For each centerline sample it takes the local tangent, casts a ray perpendicular
to each side (hl_core), and records the nearest building's distance, height and
construction year. Sides are labelled west (Hudson, -x) / east (city, +x).
Feeds the mirrored long-section band in index_strip.html.

Writes data/highline_section.json. Run from project root:
    python scripts/build_section.py
"""
import json, math, os
import numpy as np
import hl_core as hlc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "highline_section.json")

SPACING = 8.0
MAX_SIDE = 140.0
# ── era threshold ────────────────────────────────────────────────────────────
# PRIMARY is the 2005 West Chelsea rezoning, not the 2009 park opening. The
# rezoning is the causal event: it is what moved the development rights and made
# the tower boom legal. The opening is when the gates opened. Cutting at 2009
# splits the cohort the rezoning created — the three largest single culprits are
# 2008, 2006 and 2006 — and hands them to the "pre" side, which understates the
# self-enclosure the project is about. Measured: the 2005 cut puts 27.1% of ranked
# buildings on 67.9% of the stolen sky (2.50x); the 2009 cut, 19.4% on 43.0%
# (2.22x), and the 2005-2008 band alone runs at 3.23x.
REZONING_YEAR = 2005          # primary
OPENING_YEAR = 2009           # secondary, retained for reporting
PARK_YEAR = REZONING_YEAR


def cast(edges, buildings, px, pz, dx, dz):
    """Nearest hit along one ray: (dist, height, year) or (None, 0, None)."""
    if edges is None:
        return None, 0.0, None
    t, hit = hlc.ray_uv(edges, px, pz, dx, dz, MAX_SIDE)
    if not hit.any():
        return None, 0.0, None
    th = t[hit]; H = edges[2][hit]; BID = edges[3][hit]
    j = int(np.argmin(th))
    yy = buildings[int(BID[j])].yr
    return float(th[j]), float(H[j]), (yy if yy else None)


def main():
    site = hlc.load_site()
    bld = site.buildings
    samples = site.corridor.samples(SPACING)
    pts = np.array([s[0] for s in samples])
    out = []
    for i in range(len(pts)):
        px, pz = float(pts[i, 0]), float(pts[i, 1])
        a = pts[max(0, i - 1)]; b = pts[min(len(pts) - 1, i + 1)]
        tx, tz = b[0] - a[0], b[1] - a[1]
        tl = math.hypot(tx, tz) or 1.0
        tx, tz = tx / tl, tz / tl
        n1 = (-tz, tx); n2 = (tz, -tx)
        west, east = (n1, n2) if n1[0] < n2[0] else (n2, n1)
        e = hlc.edges_for(bld, px, pz, MAX_SIDE)
        wd, wh, wy = cast(e, bld, px, pz, *west)
        ed, eh, ey = cast(e, bld, px, pz, *east)
        out.append({"s": round(float(samples[i][1]), 1),
                    "west_d": round(wd, 1) if wd else None, "west_h": round(wh, 1), "west_yr": wy,
                    "east_d": round(ed, 1) if ed else None, "east_h": round(eh, 1), "east_yr": ey})

    meta = {"model": "perpendicular ray-cast, nearest street wall each side",
            "max_side_m": MAX_SIDE, "park_year": PARK_YEAR,
            "sides": "west = Hudson (-x), east = city (+x)",
            "n_points": len(out), "length_m": site.length_m}
    json.dump({"metadata": meta, "points": out}, open(OUT, "w"), indent=1)

    wh = np.array([p["west_h"] for p in out]); eh = np.array([p["east_h"] for p in out])
    river = np.mean(wh < 4)
    print(f"\n=== LONG-SECTION ({len(out)} points, {site.length_m} m) ===")
    print(f"mean wall height  west(Hudson): {wh.mean():.1f} m   east(city): {eh.mean():.1f} m")
    print(f"west side open (<4 m wall)     : {100*river:.0f}% of the walk  (the river frontage)")
    print(f"tallest west wall {wh.max():.0f} m  |  tallest east wall {eh.max():.0f} m")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
