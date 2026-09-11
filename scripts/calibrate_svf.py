"""calibrate_svf.py — ⚠️ SUPERSEDED 2026-08-16. DIAGNOSTIC ONLY.

THE CALIBRATED SVF IS NO LONGER PUBLISHED. The project publishes the RAW isovist
(0.424) and reports Ladybug (0.269) beside it as an independent instrument. Neither
figure is adjusted toward the other. This script still runs, and its output
`data/svf_calibration.json` is kept — as EVIDENCE FOR THE RETIREMENT, not as a
correction to apply.

WHY IT WAS RETIRED. It was fitted when the footprint set was 81.6% incomplete, where
it looked defensible: r 0.956, RMSE 0.132 -> 0.094. Against the complete 2,083-building
site the same fit is `a = 0.9364, b = -0.1288`, r 0.871, RMSE 0.201 -> 0.127, and it
fails on residual STRUCTURE, not merely on r:

  1. U-shaped bias across isovist quintiles: +0.037, +0.000, -0.044, -0.029, +0.034.
     That swing is a third of the calibrated RMSE — biased in the middle of its range.
  2. Heteroscedasticity: residual sd runs 0.033 -> 0.092 -> 0.138 -> 0.176 -> 0.125.
     A 5x spread; least reliable exactly where the deck is half-open.
  3. 38 of 232 predictions (16%) fall outside [0, 1] and are clamped. One station in
     six gets a physically impossible sky-view factor.
  4. A quadratic barely helps: RMSE 0.121 vs 0.127, a 4.7% gain.

  (4) is the decisive one. The divergence is NOT a function of the isovist value, so no
  univariate recalibration can absorb it. Measured, the residual tracks occluder
  DENSITY (r +0.384 with building count within MAX_R) and runs the OTHER way against
  height — r -0.332 with the tallest occluder, -0.373 with the count above 150 m. It is
  a MODEL-ORDER limit: svf = 1 - mean(sin^2(beta)) collapses each azimuth to one horizon
  angle and assumes open sky above it. Against a single tall wall that is nearly exact;
  against many mid-rise roofs at different distances the real hemisphere is punctured in
  ways one beta per azimuth cannot represent. Fitting a line to that hides a structural
  limitation behind two parameters.

The original rationale, kept for the record: the 2.5-D isovist tracks Ladybug's 3-D
hemispherical SVF but reads systematically more open (it cannot see upper-hemisphere
occlusion). The fit `svf_lbt = a·svf_mine + b` was meant to give the fast dense engine
Ladybug-absolute scale while keeping its spatial pattern. Solar needs no calibration
(r ~0.93 post-re-fetch); its fit is reported for completeness.

Cheap (reads JSON, no ray-casting) — re-run whenever build_lbt.py refreshes the
`*_lbt.json`. Writes data/svf_calibration.json + data/highline_viewshed_cal.json.
Run from project root:  python scripts/calibrate_svf.py
"""
import json, os, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")


def load(name):
    return json.load(open(os.path.join(D, name)))["points"]


def fit(mine, lbt):
    """Linear fit lbt = a·mine + b, with raw/calibrated RMSE."""
    a_, b_ = np.polyfit(mine, lbt, 1)
    pred = a_ * np.asarray(mine) + b_
    r = float(np.corrcoef(mine, lbt)[0, 1])
    rmse_raw = float(np.sqrt(np.mean((np.asarray(mine) - np.asarray(lbt)) ** 2)))
    rmse_cal = float(np.sqrt(np.mean((pred - np.asarray(lbt)) ** 2)))
    return {"a": round(float(a_), 4), "b": round(float(b_), 4), "r": round(r, 3),
            "r2": round(r * r, 3), "rmse_raw": round(rmse_raw, 4), "rmse_cal": round(rmse_cal, 4),
            "mean_mine": round(float(np.mean(mine)), 3), "mean_lbt": round(float(np.mean(lbt)), 3)}


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    for f in ("highline_viewshed_lbt.json", "highline_solar_lbt.json"):
        if not os.path.exists(os.path.join(D, f)):
            print(f"missing {f} — run build_lbt.py first."); return

    mv, lv = load("highline_viewshed.json"), load("highline_viewshed_lbt.json")
    ms, ls = load("highline_solar.json"), load("highline_solar_lbt.json")
    assert len(mv) == len(lv) == len(ms) == len(ls), "point-count mismatch"

    svf_mine = [p["svf_deck"] for p in mv]; svf_lbt = [p["svf_deck"] for p in lv]
    svf_f = fit(svf_mine, svf_lbt)
    a, b = svf_f["a"], svf_f["b"]

    metrics = {"svf_deck": svf_f,
               "sun_winter": fit([p["sun_winter_solstice"] for p in ms], [p["sun_winter_solstice"] for p in ls]),
               "sun_summer": fit([p["sun_summer_solstice"] for p in ms], [p["sun_summer_solstice"] for p in ls]),
               "sun_equinox": fit([p["sun_equinox"] for p in ms], [p["sun_equinox"] for p in ls])}

    # apply calibration to the dense from-scratch SVF (deck + counterfactual)
    clamp = lambda v: round(max(0.0, min(1.0, a * v + b)), 4)   # SVF stays in [0,1]
    cal_pts = []
    for p in mv:
        cal_pts.append({"s_m": p["s_m"],
                        "svf_deck": p["svf_deck"], "svf_deck_cal": clamp(p["svf_deck"]),
                        "svf_prepark": p["svf_prepark"], "svf_prepark_cal": clamp(p["svf_prepark"])})
    for p, lp in zip(cal_pts, lv):
        p["svf_deck_lbt"] = lp["svf_deck"]

    lbt_meta = json.load(open(os.path.join(D, "highline_viewshed_lbt.json")))["metadata"]
    json.dump({"fit": "svf_lbt = a·svf_mine + b", "source": "Ladybug recompute",
               "lbt_resolution": {"sky_dirs": lbt_meta.get("sky_dirs"), "sun_step_min": lbt_meta.get("sun_step_min")},
               "svf": svf_f, "self_enclosure_delta_scaled_by_a": a,
               "metrics": metrics}, open(os.path.join(D, "svf_calibration.json"), "w"), indent=1)
    json.dump({"metadata": {"calibration": f"svf_deck_cal = {a}*svf_deck + {b}", "vs": "Ladybug"},
               "points": cal_pts}, open(os.path.join(D, "highline_viewshed_cal.json"), "w"), indent=1)

    res = f"{lbt_meta.get('sky_dirs')} sky dirs, {lbt_meta.get('sun_step_min')} min sun"
    print(f"\n=== hl_core → LADYBUG VALIDATION  ({len(mv)} pts · {res}) ===")
    print(f"{'metric':12s} {'r':>6} {'R²':>6} {'RMSE':>7}  {'mean mine':>10} {'mean LB':>9}   fit  a·x+b")
    for k, v in metrics.items():
        print(f"{k:12s} {v['r']:>+6.2f} {v['r2']:>6.2f} {v['rmse_raw']:>7.3f}  "
              f"{v['mean_mine']:>10.3f} {v['mean_lbt']:>9.3f}   a={v['a']:+.3f} b={v['b']:+.3f}")
    print(f"\nSVF calibration:  svf_cal = {a:+.4f}·svf_mine {b:+.4f}   "
          f"(R²={svf_f['r2']}, RMSE {svf_f['rmse_raw']:.3f} → {svf_f['rmse_cal']:.3f} after fit)")
    print(f"self-enclosure delta scales by a={a} under calibration "
          f"(mean deck {np.mean(svf_mine):.3f} → {a*np.mean(svf_mine)+b:.3f}, matches LB {svf_f['mean_lbt']}).")
    print(f"wrote data/svf_calibration.json, data/highline_viewshed_cal.json")


if __name__ == "__main__":
    main()
