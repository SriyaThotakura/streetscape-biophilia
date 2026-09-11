"""build_viewshed.py — Engine 1: 2.5-D isovist / viewshed for the elevated deck.

For sample points along the deck centerline, ray-casts against the building
prisms (hl_core) to derive the on-deck visual field: Sky-View-Factor (deck &
street), the pre-park counterfactual SVF, enclosure angle, view-corridor
openings, Hudson sightlines, nearest wall and dominant-occluder year.

The delta svf_prepark − svf_deck isolates sky lost to post-park development —
the self-enclosure the High Line's own success induced.

Writes data/highline_viewshed.json. Run from project root:
    python scripts/build_viewshed.py
"""
import json, math, os
import numpy as np
import hl_core as hlc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "highline_viewshed.json")

EYE_DECK   = hlc.EYE_DECK       # ~10.6 m
EYE_STREET = hlc.EYE            # ~1.6 m
N_AZ     = 360
MAX_R    = 350.0
OPEN_DEG = 5.0
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
SPACING  = 8.0


def horizon(edges, buildings, px, pz, eye, dirs):
    """Per-azimuth (elevation β, nearest hit dist, dominant occluder height & year)."""
    H, BID = edges[2], edges[3]
    nAz = dirs.shape[0]
    beta = np.zeros(nAz); dist = np.full(nAz, np.inf)
    occH = np.zeros(nAz); occY = np.full(nAz, -1)
    for k in range(nAz):
        t, hit = hlc.ray_uv(edges, px, pz, dirs[k, 0], dirs[k, 1], MAX_R)
        if not hit.any():
            continue
        th = t[hit]; hh = H[hit]; bb = BID[hit]
        ang = np.arctan2(hh - eye, th)
        j = int(np.argmax(ang))
        beta[k] = max(0.0, ang[j]); dist[k] = th.min()
        occH[k] = hh[j]
        yy = buildings[int(bb[j])].yr
        occY[k] = yy if yy else -1
    return beta, dist, occH, occY


def svf_from_beta(beta):
    return float(1.0 - np.mean(np.sin(np.clip(beta, 0, math.pi / 2)) ** 2))


def openings(beta, dirs_ang):
    open_mask = beta < math.radians(OPEN_DEG)
    n = len(open_mask); runs = 0
    start = 0
    while start < n and open_mask[start]:
        start += 1
    if start == n:
        return 1, True
    idx = [(start + j) % n for j in range(n)]
    prev = False; west = False
    for k in idx:
        if open_mask[k] and not prev:
            runs += 1
        if open_mask[k]:
            a = dirs_ang[k] % (2 * math.pi)
            if math.radians(135) <= a <= math.radians(225):
                west = True
        prev = open_mask[k]
    return runs, west


def main():
    site = hlc.load_site()
    bld = site.buildings
    samples = site.corridor.samples(SPACING)
    ang = np.linspace(0, 2 * math.pi, N_AZ, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], axis=1)
    # strictly BEFORE the rezoning year: a building completed in 2005 belongs to the
    # cohort the rezoning created, not to the baseline it replaced
    bld_pre = [b for b in bld if (b.yr is not None and b.yr <= OPENING_YEAR)]

    out = []
    for (pt, s) in samples:
        px, pz = float(pt[0]), float(pt[1])
        e_all = hlc.edges_for(bld, px, pz, MAX_R)
        if e_all is None:
            out.append({"s_m": round(s, 1), "x": round(px, 2) + 0.0, "z": round(pz, 2) + 0.0,
                        "svf_deck": 1.0, "svf_street": 1.0, "svf_prepark": 1.0,
                        "enclosure_deg": 0.0, "openings": 1, "river_view": True,
                        "nearest_wall_m": None, "dom_occ_year": None})
            continue
        beta_d, dist_d, occH, occY = horizon(e_all, bld, px, pz, EYE_DECK, dirs)
        beta_s, _, _, _ = horizon(e_all, bld, px, pz, EYE_STREET, dirs)
        e_pre = hlc.edges_for(bld_pre, px, pz, MAX_R)
        beta_p = horizon(e_pre, bld_pre, px, pz, EYE_DECK, dirs)[0] if e_pre else np.zeros(N_AZ)
        nopen, west = openings(beta_d, ang)
        dom = int(np.argmax(beta_d))
        nearest = float(np.min(dist_d)) if np.isfinite(dist_d).any() else None
        out.append({
            "s_m": round(s, 1), "x": round(px, 2) + 0.0, "z": round(pz, 2) + 0.0,
            "svf_deck": round(svf_from_beta(beta_d), 4),
            "svf_street": round(svf_from_beta(beta_s), 4),
            "svf_prepark": round(svf_from_beta(beta_p), 4),
            "enclosure_deg": round(float(np.degrees(beta_d.mean())), 2),
            "openings": int(nopen), "river_view": bool(west),
            "nearest_wall_m": round(nearest, 1) if nearest else None,
            "dom_occ_year": int(occY[dom]) if occY[dom] > 0 else None,
        })

    meta = {
        "model": "2.5D isovist ray-cast, Oke uniform-sky SVF",
        "eye_deck_m": EYE_DECK, "eye_street_m": EYE_STREET,
        "n_azimuth": N_AZ, "max_radius_m": MAX_R, "park_year": PARK_YEAR,
        "n_buildings": len(bld), "n_prepark": len(bld_pre),
        "spacing_m": SPACING, "length_m": site.length_m, "n_points": len(out),
        "era_thresholds": {
            "baseline_used_here": OPENING_YEAR,
            "causal_used_by_attribution": REZONING_YEAR,
            "why_they_differ":
                "Two constants, two jobs. OPENING_YEAR = 2009 is the BASELINE: the "
                "deficit means 'sky the deck lost AS A PARK', so the counterfactual is "
                "the city as it stood when the park opened. A baseline predating the "
                "park would count loss no visitor ever experienced. REZONING_YEAR = 2005 "
                "is CAUSAL and belongs to build_attribution: 'who caused the enclosure' "
                "is answered by the rezoning that moved the development rights, not by "
                "the date the gates opened.",
            "boundary": "pre-park is `yr <= 2009`; a 2009 completion counts as standing "
                        "when the park opened.",
            "decided_on": "the reasoning above, not on the result.",
            "checkable_side_effect":
                "The 2009 baseline ALSO restores a statistical significance that the 2005 "
                "baseline removed: the equal-material paired delta is significant at this "
                "baseline and is not at the 2005 one. That was NOT the reason for the "
                "choice. Both runs exist so the claim can be checked rather than trusted "
                "— see data/_pre2005_snapshot/ for the 2009-baseline run that preceded "
                "the 2005 experiment, and the 2005-baseline figures recorded in "
                "IMPLEMENTATION_PLAN.md W2.",
            "measured_both_ways": {
                "deficit_mean_2009_baseline": 0.2305,
                "deficit_mean_2005_baseline": 0.3596,
                "note": "svf_deck is identical either way (0.4244); only the pre-park "
                        "baseline moves.",
            },
        },
    }
    json.dump({"metadata": meta, "points": out}, open(OUT, "w"), indent=1)

    svf_d = np.array([p["svf_deck"] for p in out])
    svf_s = np.array([p["svf_street"] for p in out])
    svf_p = np.array([p["svf_prepark"] for p in out])
    enc = np.array([p["enclosure_deg"] for p in out])
    river = np.array([p["river_view"] for p in out])
    post_dom = [p for p in out if p["dom_occ_year"] and p["dom_occ_year"] >= REZONING_YEAR]
    lost = svf_p - svf_d
    print(f"\n=== THE SELF-ENCLOSING LINE — viewshed reveal ({len(out)} deck points, {site.length_m} m) ===")
    print(f"mean Sky-View-Factor  deck: {svf_d.mean():.3f}   street: {svf_s.mean():.3f}   "
          f"(deck sees {100*(svf_d.mean()-svf_s.mean()):+.1f} SVF pts more sky)")
    print(f"mean enclosure angle       : {enc.mean():.1f} deg   (max {enc.max():.1f} at s={out[int(enc.argmax())]['s_m']} m)")
    print(f"points with a Hudson sightline: {int(river.sum())}/{len(out)} ({100*river.mean():.0f}%)")
    print(f"\n--- self-enclosure (all vs pre-{PARK_YEAR} buildings) ---")
    print(f"mean deck SVF w/ ONLY pre-park buildings : {svf_p.mean():.3f}")
    print(f"mean deck SVF w/ all buildings           : {svf_d.mean():.3f}")
    print(f"sky lost to post-{PARK_YEAR} development     : {100*lost.mean():.2f} SVF pts avg, "
          f"up to {100*lost.max():.1f} pts (at s={out[int(lost.argmax())]['s_m']} m)")
    print(f"deck points whose DOMINANT wall is a post-park tower: {len(post_dom)}/{len(out)} "
          f"({100*len(post_dom)/len(out):.0f}%)")
    print(f"\nwrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
