"""build_removals.py — per-scenario deck SVF profiles + winter-sun deltas for the
Board 1 counterfactual matrix. One entry per matrix cell.

Scenarios (15 + a KEY cell rendered from the shared scales):
  baseline · pre-2009 (all post-park removed) · forward (as-of-right buildout) ·
  r1..r12 (remove each of the top-12 attribution culprits, one at a time).

baseline & forward are pulled from forward_scenario.json (identical hl_core params
N_AZ=180, MAX_R=400), so every cell is strictly comparable. pre-2009 + the 12
single removals are computed here with the same primitives.

Writes data/removals.json. Run from project root:  python scripts/build_removals.py
"""
import json, math, os, sys
import numpy as np
import hl_core as hlc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
N_AZ = 180
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
WINTER_DOY = 355
SUN_STEP_MIN = 10       # match build_forward's 10-min baseline so Δsun is consistent


def svf_profile(blds, samples, dirs, sun):
    """Per-point (svf_deck, winter_sunlit_hours) for a building set."""
    svf, wsun = [], []
    els, es, ns = sun
    for (pt, s) in samples:
        px, pz = float(pt[0]), float(pt[1])
        e = hlc.edges_for(blds, px, pz, MAX_R)
        if e is None:
            svf.append(1.0); wsun.append(len(els) * SUN_STEP_MIN / 60.0); continue
        H = e[2]
        betas = np.zeros(N_AZ)
        for k in range(N_AZ):
            t, hit = hlc.ray_uv(e, px, pz, dirs[k, 0], dirs[k, 1], MAX_R)
            if hit.any():
                betas[k] = max(0.0, float(np.arctan2(H[hit] - hlc.EYE_DECK, t[hit]).max()))
        svf.append(1.0 - float(np.mean(np.sin(betas) ** 2)))
        lit = 0
        for el, sdx, sdz in zip(els, es, ns):
            tt, hh = hlc.ray_uv(e, px, pz, sdx, sdz, MAX_R)
            if hh.any() and np.arctan2(H[hh] - hlc.DECK_H, tt[hh]).max() > el:
                continue
            lit += 1
        wsun.append(lit * SUN_STEP_MIN / 60.0)
    return np.array(svf), np.array(wsun)


def main():
    site = hlc.load_site()
    blds = site.buildings
    samples = site.corridor.samples(SPACING)
    ang = np.linspace(0, 2 * math.pi, N_AZ, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], 1)
    sun = hlc.sun_path(WINTER_DOY, dt_h=SUN_STEP_MIN / 60.0)

    fwd = json.load(open(os.path.join(D, "forward_scenario.json")))["points"]
    s_axis = [p["s"] for p in fwd]
    base_svf = np.array([p["svf_now"] for p in fwd])
    base_sun = np.array([p["sun_now"] for p in fwd])
    fwd_svf = np.array([p["svf_future"] for p in fwd])
    fwd_sun = np.array([p["sun_future"] for p in fwd])

    att = json.load(open(os.path.join(D, "attribution.json")))
    top = att["leaderboard"][:12]
    cal = json.load(open(os.path.join(D, "svf_calibration.json")))["svf"]
    A, B = cal["a"], cal["b"]
    base_mean_svf, base_mean_sun = float(np.mean(base_svf)), float(np.mean(base_sun))

    scen = []
    def add(key, label, meta, direction, svf, wsun, tone):
        m_svf, m_sun = float(np.mean(svf)), float(np.mean(wsun))
        scen.append({"key": key, "label": label, "meta": meta, "dir": direction, "tone": tone,
                     "svf": [round(float(v), 4) for v in svf],
                     "mean_svf": round(m_svf, 4),
                     "mean_svf_cal": round(max(0.0, min(1.0, A * m_svf + B)), 3),
                     "mean_winter_sun_h": round(m_sun, 2),
                     "d_svf_pct": round(100 * (m_svf - base_mean_svf), 2),
                     "d_svf_pct_cal": round(100 * A * (m_svf - base_mean_svf), 2),
                     "d_winter_sun_h": round(m_sun - base_mean_sun, 4)})   # full precision for <0.01 display

    # ── the scenario labels are DERIVED, and this is not a style preference ──────────
    # Until 2026-09-05 all three were typed, and all three were wrong: the file shipped
    # "176 buildings" (the pre-re-fetch count), "6 post-2009 towers removed" and
    # "9 soft sites built out" against a site that actually carries 2,083 footprints, 93
    # post-2009 buildings and 59 soft sites. The NUMBERS in the file were correct
    # throughout — its own pre-2009 row restores +23.06 SVF points, which matches the
    # independently computed mean stolen sky of 0.2305 — so nothing was ever miscomputed.
    # Only the captions lied, which is the harder failure to catch: a reader has no reason
    # to doubt a label sitting next to a number that is right.
    #
    # Every count below is now read from the same objects the scenario is built from, so a
    # label cannot survive the data moving underneath it.
    pre = [b for b in blds if (b.yr is not None and b.yr <= OPENING_YEAR)]
    n_removed = len(blds) - len(pre)
    # The removed set is NOT simply "post-2009". The membership test is `yr <= OPENING_YEAR`
    # with a not-None guard, so a building with NO recorded year fails it and is removed
    # from the baseline as well — "year unknown" is treated as "not proven pre-park". On the
    # current data that is 93 dated post-2009 buildings plus 23 undated ones, 116 in all.
    # The label has to say so: calling it "93 post-2009 buildings" would describe a
    # different scenario from the one this file computes.
    n_dated = sum(1 for b in blds if b.yr is not None and b.yr > OPENING_YEAR)
    n_undated = sum(1 for b in blds if b.yr is None)
    n_soft = json.load(open(os.path.join(D, "forward_scenario.json")))["metadata"].get(
        "n_soft_sites")

    add("baseline", "BASELINE", f"{len(blds):,} footprints", "reference state",
        base_svf, base_sun, "neutral")
    ps, pw = svf_profile(pre, samples, dirs, sun)
    add("pre2009", "PRE-2009",
        f"{n_removed} removed: {n_dated} completed after {OPENING_YEAR}, "
        f"{n_undated} with no recorded year",
        "sky regained (aggregate)", ps, pw, "restore")
    add("forward", "FORWARD",
        (f"{n_soft} soft sites built out" if n_soft is not None
         else "soft sites built out — count not carried by forward_scenario.json"),
        "extra loss if built out", fwd_svf, fwd_sun, "loss")
    print(f"[labels] derived: {len(blds)} footprints · {n_removed} removed "
          f"({n_dated} dated post-{OPENING_YEAR} + {n_undated} undated) · "
          f"{n_soft} soft sites")
    for i, r in enumerate(top, 1):
        subset = [b for b in blds if b.id != r["id"]]
        s_, w_ = svf_profile(subset, samples, dirs, sun)
        add(f"r{i}", f"−#{r['id']}", f"{r['year']} · {r['height_m']:.0f} m", "sky regained if removed",
            s_, w_, "restore")
        scen[-1]["id"] = r["id"]; scen[-1]["year"] = r["year"]; scen[-1]["height_m"] = r["height_m"]
        print(f"  removed rank {i} (#{r['id']}): dSVF {scen[-1]['d_svf_pct']:+.2f}%  dSun {scen[-1]['d_winter_sun_h']:+.3f}h")

    all_svf = np.concatenate([np.array(s["svf"]) for s in scen])
    d_svf = [s["d_svf_pct"] for s in scen]
    # difference-strip clip provenance (render uses p99; footer documents the true peak)
    base_arr = np.array(base_svf)
    rem = [s for s in scen if s["key"].startswith("r")]
    all_diff = np.concatenate([np.array(s["svf"]) - base_arr for s in rem])
    peak = 0.0; peak_s = 0.0; peak_id = None
    for s in rem:
        d = np.array(s["svf"]) - base_arr; j = int(d.argmax())
        if d[j] > peak: peak, peak_s, peak_id = float(d[j]), s_axis[j], s["id"]
    cal = json.load(open(os.path.join(D, "svf_calibration.json")))["svf"]
    meta = {"n_scenarios": len(scen), "n_points": len(s_axis), "n_azimuth": N_AZ,
            "max_radius_m": MAX_R, "winter_doy": WINTER_DOY, "sun_step_min": SUN_STEP_MIN,
            "svf_scale": [round(float(all_svf.min()), 3), round(float(all_svf.max()), 3)],
            "d_svf_scale": [round(min(d_svf), 2), round(max(d_svf), 2)],
            "diff_p99": round(float(np.percentile(all_diff, 99)), 3),
            "diff_peak": round(peak, 3), "diff_peak_s": round(float(peak_s), 1), "diff_peak_id": peak_id,
            "calibration_a": cal["a"], "calibration_b": cal["b"],
            "note": "d_svf_pct/d_winter_sun_h are vs baseline; removals restore (+), forward loses (−). "
                    "Multiply d_svf by calibration_a for Ladybug-absolute. Difference strips clipped at diff_p99."}
    json.dump({"metadata": meta, "s_axis": s_axis, "scenarios": scen},
              open(os.path.join(D, "removals.json"), "w"))
    print(f"\nwrote data/removals.json: {len(scen)} scenarios, svf scale {meta['svf_scale']}, "
          f"dSVF scale {meta['d_svf_scale']}%")


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
