"""build_attribution.py — per-building attribution of the deck's enclosure.

Every blocked ray (hl_core) is tagged with the building that blocked it, turning
the aggregate counterfactual into a leaderboard of enclosure culprits:
  • sky occlusion — per azimuth, the dominant building owns that azimuth's
    sin²(β) loss of Sky-View-Factor, summed over the deck.
  • winter sun stolen — per timestep, the building that blocks the sun owns that
    deck-point-hour of shadow.

Writes data/attribution.json. Run from project root:
    python scripts/build_attribution.py
"""
import json, math, os, sys
import numpy as np
import hl_core as hlc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "attribution.json")

EYE_DECK = hlc.EYE_DECK
DECK_H = hlc.DECK_H
N_AZ = 180
MAX_R = 400.0
SPACING = 8.0
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
DT_H = 1.0 / 6.0
SOLAR_DATES = {"winter_solstice": 355, "equinox": 81}


def main():
    site = hlc.load_site()
    blds = site.buildings
    samples = site.corridor.samples(SPACING)
    ang = np.linspace(0, 2 * math.pi, N_AZ, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], axis=1)
    nB = len(blds)

    sky_occ = np.zeros(nB)
    sun_steal = {k: np.zeros(nB) for k in SOLAR_DATES}
    s_lo = np.full(nB, np.inf); s_hi = np.full(nB, -np.inf)
    paths = {k: hlc.sun_path(day, dt_h=DT_H) for k, day in SOLAR_DATES.items()}

    for (pt, s) in samples:
        px, pz = float(pt[0]), float(pt[1])
        e = hlc.edges_for(blds, px, pz, MAX_R)
        if e is None:
            continue
        H, BID = e[2], e[3]
        for k in range(N_AZ):
            t, hit = hlc.ray_uv(e, px, pz, dirs[k, 0], dirs[k, 1], MAX_R)
            if not hit.any():
                continue
            beta = np.arctan2(H[hit] - EYE_DECK, t[hit])
            j = int(np.argmax(beta))
            if beta[j] <= 0:
                continue
            b = int(BID[hit][j])
            sky_occ[b] += math.sin(beta[j]) ** 2
            if s < s_lo[b]: s_lo[b] = s
            if s > s_hi[b]: s_hi[b] = s
        for name, (els, es, ns) in paths.items():
            for el, sdx, sdz in zip(els, es, ns):
                t, hit = hlc.ray_uv(e, px, pz, sdx, sdz, MAX_R)
                if not hit.any():
                    continue
                beta = np.arctan2(H[hit] - DECK_H, t[hit])
                j = int(np.argmax(beta))
                if beta[j] > el:
                    sun_steal[name][int(BID[hit][j])] += DT_H

    total_occ = sky_occ.sum() or 1.0
    n_pts = len(samples)
    rows = []
    for bi, b in enumerate(blds):
        if sky_occ[bi] <= 0 and all(sun_steal[k][bi] <= 0 for k in SOLAR_DATES):
            continue
        yr = b.yr
        if yr is None:
            band = "unknown"
        elif yr < REZONING_YEAR:
            band = "pre-rezoning"
        elif yr <= OPENING_YEAR - 1:
            band = "rezoning-era"          # 2005-2008: permitted under the new envelope
        else:
            band = "post-opening"          # 2009+
        rows.append({
            "id": b.id, "year": b.yr, "height_m": round(b.h, 1),
            # PRIMARY cut. NOT b.era(PARK_YEAR): hl_core.era uses strict `yr > park_year`,
            # which puts buildings completed IN 2005 on the pre side. The rezoning was
            # adopted in 2005, so 2005 completions belong to the cohort it created.
            "era": "post" if band in ("rezoning-era", "post-opening") else
                   ("pre" if band == "pre-rezoning" else None),
            "era_band": band,                        # three-way, for the finer cut
            "era_2009_secondary": b.era(OPENING_YEAR),   # the retired opening-date cut
            "sky_share_pct": round(100 * sky_occ[bi] / total_occ, 2),
            "svf_removed_pts": round(100 * sky_occ[bi] / (n_pts * N_AZ), 2),
            "winter_deckhours_stolen": round(float(sun_steal["winter_solstice"][bi]), 1),
            "equinox_deckhours_stolen": round(float(sun_steal["equinox"][bi]), 1),
            "affects_s": [round(float(s_lo[bi]), 0), round(float(s_hi[bi]), 0)]
                         if np.isfinite(s_lo[bi]) else None,
        })
    rows.sort(key=lambda r: r["sky_share_pct"], reverse=True)
    for r in rows:
        r["rank"] = rows.index(r) + 1

    def agg(pred):
        g = [r for r in rows if pred(r)]
        sh = sum(r["sky_share_pct"] for r in g)
        n_pct = 100.0 * len(g) / len(rows) if rows else 0.0
        return {"n": len(g), "pct_of_ranked": round(n_pct, 1),
                "sky_share_pct": round(sh, 1),
                "over_representation": round(sh / n_pct, 2) if n_pct else None,
                "winter_deckhours_stolen":
                    round(sum(r["winter_deckhours_stolen"] for r in g), 1)}

    post_share = sum(r["sky_share_pct"] for r in rows if r["era"] == "post")
    post_sun = sum(r["winter_deckhours_stolen"] for r in rows if r["era"] == "post")
    assert (meta_n := len([r for r in rows if r["era"] == "post"])) ==         len([r for r in rows if r["era_band"] in ("rezoning-era", "post-opening")]),         "primary cut and era_band disagree"
    meta = {"model": "per-building attribution of viewshed + solar ray-casts",
            "n_buildings_ranked": len(rows), "n_deck_points": n_pts, "n_azimuth": N_AZ,
            "park_year": PARK_YEAR, "length_m": site.length_m,
            "era_threshold_primary": REZONING_YEAR,
            "era_threshold_secondary": OPENING_YEAR,
            "era_threshold_rationale":
                "PRIMARY is the 2005 West Chelsea rezoning, not the 2009 opening. The "
                "rezoning moved the development rights and made the tower boom legal; the "
                "opening is when the gates opened. The 2009 cut splits the cohort the "
                "rezoning created — ranks 1, 2 and 3 are 2008, 2006 and 2006 — and assigns "
                "them to the 'pre' side, understating the self-enclosure. Both cuts are "
                "reported; the 2005 one is the headline.",
            "post_rezoning_2005_sky_share_pct": round(post_share, 1),
            "post_rezoning_2005_winter_deckhours": round(post_sun, 1),
            "bands": {
                "pre_rezoning_lt2005": agg(lambda r: r["era_band"] == "pre-rezoning"),
                "rezoning_era_2005_2008": agg(lambda r: r["era_band"] == "rezoning-era"),
                "post_opening_2009plus": agg(lambda r: r["era_band"] == "post-opening"),
                "year_unknown": agg(lambda r: r["era_band"] == "unknown"),
            },
            "cuts": {
                "primary_2005_rezoning": agg(lambda r: r["era"] == "post"),
                "secondary_2009_opening": agg(lambda r: r["era_2009_secondary"] == "post"),
            }}
    json.dump({"metadata": meta, "leaderboard": rows}, open(OUT, "w"), indent=1)

    print(f"\n=== ENCLOSURE CULPRITS — leaderboard ({len(rows)} buildings) ===")
    print(f"{'#':>2} {'id':>10} {'yr':>5} {'ht':>5} {'sky%':>6} {'winterSun':>10}  where")
    for r in rows[:12]:
        aff = f"{r['affects_s'][0]:.0f}–{r['affects_s'][1]:.0f} m" if r["affects_s"] else "—"
        flag = {"rezoning-era": " *2005-08 REZONING*",
                "post-opening": " *POST-2009*"}.get(r["era_band"], "")
        print(f"{r['rank']:>2} {r['id']:>10} {str(r['year']):>5} {r['height_m']:>5.0f} "
              f"{r['sky_share_pct']:>6.1f} {r['winter_deckhours_stolen']:>10.1f}  {aff}{flag}")
    bd = meta["bands"]; ct = meta["cuts"]
    print(f"\n{'band':<24}{'n':>5}{'%ranked':>9}{'sky share':>11}{'over-rep':>10}")
    for k, lbl in (("pre_rezoning_lt2005", "pre-2005"),
                   ("rezoning_era_2005_2008", "2005-2008 rezoning"),
                   ("post_opening_2009plus", "2009+ opening"),
                   ("year_unknown", "year unknown")):
        v = bd[k]
        if v["n"]:
            print(f"{lbl:<24}{v['n']:>5}{v['pct_of_ranked']:>8.1f}%{v['sky_share_pct']:>10.1f}%"
                  f"{v['over_representation']:>9.2f}x")
    p_, s_ = ct["primary_2005_rezoning"], ct["secondary_2009_opening"]
    print(f"\nPRIMARY  post-2005 rezoning : {p_['n']:>3} of {len(rows)} ranked "
          f"({p_['pct_of_ranked']:.1f}%) own {p_['sky_share_pct']:.1f}% "
          f"({p_['over_representation']:.2f}x), {p_['winter_deckhours_stolen']:.0f} winter deck-hours")
    print(f"secondary post-2009 opening : {s_['n']:>3} of {len(rows)} ranked "
          f"({s_['pct_of_ranked']:.1f}%) own {s_['sky_share_pct']:.1f}% "
          f"({s_['over_representation']:.2f}x)")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
