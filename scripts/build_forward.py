"""build_forward.py — the counterfactual, run FORWARD.

build_viewshed measured what past development removed; this measures what zoning
still PERMITS: identify remaining soft sites along the corridor, extrude them to
the district's as-of-right envelope, and re-run the viewshed + solar engines
(hl_core). The delta is the sky and winter sun the deck loses if West Chelsea
builds out.

HONEST SCOPE — a MODEL, not a permit forecast. Soft sites and the envelope are
transparent knobs (top of file, echoed in the output metadata):
  soft site      = fronts the deck (< CORRIDOR_M), currently low (< SOFT_MAX_H),
                   and old (< SOFT_MAX_YEAR or unknown) — underbuilt, not yet redeveloped.
  as-of-right env = raise the footprint to ENVELOPE_H (the height the 2015–17
                   towers reached under the 2005 Special West Chelsea District).
Swap in NYC MapPLUTO per-lot FAR to make it permit-accurate; engine unchanged.

Writes data/forward_scenario.json. Run from project root:
    python scripts/build_forward.py
"""
import json, math, os, sys
import numpy as np
import hl_core as hlc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "forward_scenario.json")

EYE_DECK, DECK_H = hlc.EYE_DECK, hlc.DECK_H
N_AZ = 180
MAX_R = 400.0
SPACING = 8.0
DT_H = 1.0 / 6.0
WINTER_DOY = 355
# ── scenario knobs ──
CORRIDOR_M    = 55.0
SOFT_MAX_H    = 18.0
SOFT_MAX_YEAR = 2000
ENVELOPE_H    = 35.0


def svf_and_sun(blds, heights, px, pz, dirs, sun):
    """(sky-view-factor, winter sunlit hours) at one deck point for a height set."""
    e = hlc.edges_for(blds, px, pz, MAX_R, heights=heights)
    if e is None:
        return 1.0, len(sun[0]) * DT_H
    H = e[2]
    occ = 0.0
    for k in range(dirs.shape[0]):
        t, hit = hlc.ray_uv(e, px, pz, dirs[k, 0], dirs[k, 1], MAX_R)
        if hit.any():
            b = np.arctan2(H[hit] - EYE_DECK, t[hit]).max()
            if b > 0:
                occ += math.sin(b) ** 2
    svf = 1.0 - occ / dirs.shape[0]
    els, es, ns = sun; lit = 0
    for el, sdx, sdz in zip(els, es, ns):
        t, hit = hlc.ray_uv(e, px, pz, sdx, sdz, MAX_R)
        if hit.any() and np.arctan2(H[hit] - DECK_H, t[hit]).max() > el:
            continue
        lit += 1
    return svf, lit * DT_H


def main():
    site = hlc.load_site()
    blds = site.buildings
    h_now = np.array([b.h for b in blds])
    h_future = h_now.copy()
    soft = 0
    for bi, b in enumerate(blds):
        off = site.corridor.nearest_s(b.c[0], b.c[1])[1]
        old = (b.yr is None) or (b.yr < SOFT_MAX_YEAR)
        if off <= CORRIDOR_M and b.h < SOFT_MAX_H and old:
            h_future[bi] = max(b.h, ENVELOPE_H); soft += 1

    samples = site.corridor.samples(SPACING)
    ang = np.linspace(0, 2 * math.pi, N_AZ, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], 1)
    sun = hlc.sun_path(WINTER_DOY, dt_h=DT_H)

    pts = []
    for (pt, s) in samples:
        px, pz = float(pt[0]), float(pt[1])
        svf0, sun0 = svf_and_sun(blds, h_now, px, pz, dirs, sun)
        svf1, sun1 = svf_and_sun(blds, h_future, px, pz, dirs, sun)
        pts.append({"s": round(s, 1), "svf_now": round(svf0, 4), "svf_future": round(svf1, 4),
                    "sun_now": round(sun0, 2), "sun_future": round(sun1, 2)})

    svf0 = np.array([p["svf_now"] for p in pts]); svf1 = np.array([p["svf_future"] for p in pts])
    sun0 = np.array([p["sun_now"] for p in pts]); sun1 = np.array([p["sun_future"] for p in pts])
    dSvf = svf0 - svf1; dSun = sun0 - sun1
    i = int(dSvf.argmax())
    meta = {"scenario": "as-of-right buildout of corridor soft sites",
            "knobs": {"corridor_m": CORRIDOR_M, "soft_max_h": SOFT_MAX_H,
                      "soft_max_year": SOFT_MAX_YEAR, "envelope_h": ENVELOPE_H},
            "n_soft_sites": soft, "n_deck_points": len(pts), "length_m": site.length_m,
            "svf_now_mean": round(float(svf0.mean()), 3),
            "svf_future_mean": round(float(svf1.mean()), 3),
            "further_sky_lost_pct": round(float(100 * dSvf.mean()), 1),
            "further_winter_sun_stolen_h": round(float(dSun.mean()), 2),
            "worst_new_loss_s": pts[i]["s"], "disclaimer":
            "MODEL scenario, not a permit forecast — soft sites & envelope are heuristic knobs"}
    json.dump({"metadata": meta, "points": pts}, open(OUT, "w"), indent=1)

    print(f"\n=== FORWARD COUNTERFACTUAL — as-of-right buildout ===")
    print(f"soft sites (front deck, <{SOFT_MAX_H:.0f} m, pre-{SOFT_MAX_YEAR}) extruded to {ENVELOPE_H:.0f} m: {soft}")
    print(f"deck mean sky-view   now {svf0.mean():.3f}  →  after buildout {svf1.mean():.3f}")
    print(f"FURTHER sky lost       : {100*dSvf.mean():.1f}% avg, up to {100*dSvf.max():.1f}% (at s={pts[i]['s']:.0f} m)")
    print(f"FURTHER winter sun lost: {dSun.mean():.2f} h/day avg, up to {dSun.max():.2f} h (deck-wide)")
    print(f"→ if West Chelsea builds out its as-of-right envelope, the deck loses another")
    print(f"  {100*dSvf.mean():.0f}% of its sky and ~{dSun.mean()*60:.0f} min of winter sun per point, on top of what the towers already took.")
    print(f"\nwrote {os.path.relpath(OUT, ROOT)}  (MODEL scenario — knobs in metadata)")


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
