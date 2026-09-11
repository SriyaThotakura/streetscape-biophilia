"""reconcile_exposure.py — cross-validate the geometric viewshed against the CV
audit, then FUSE them as orthogonal layers.

Original hypothesis: the geometric street-level Sky-View-Factor (Engine 1) could
be calibrated against the sparse CV-measured `sky` to act as a virtual sensor
that fills the coverage gap and lifts the metric to the deck.

Result: that hypothesis FAILS. Across every candidate pairing (sky, gvi,
sky+gvi, enclosure, hardness) the geometric field is uncorrelated with the CV
audit (|r| <= 0.34, R^2 ~ 0). This is not a bug — it is the finding:

  * The CV survey points sit ~30 m off the deck centerline, on the street.
  * SegFormer `sky` at street level is set by street trees, the elevated steel
    structure, scaffolding and awnings — none of which exist in a building-
    footprint isovist. Different vantage, different occluders.

So geometry and CV are not interchangeable sensors to be regressed onto one
another; they are ORTHOGONAL layers:

  * GEOMETRY  -> built enclosure: dense, whole-corridor, computable on the deck.
  * CV        -> what fills the opening: sparse, street-level surface mix
                 (sky vs vegetation vs hardscape).

This module (a) documents the null with the full pairing table, (b) does NOT
fabricate CV values for empty bins, and (c) fuses the two into a per-bin record
with an "opening character" composite where both layers exist. Deck values are
labelled geometric estimates pending co-located (on-deck) validation.

Pure numpy. Reads data/highline_viewshed.json + data/highline_exposure.json,
writes data/highline_reconciled.json. Run from project root:
    python scripts/reconcile_exposure.py
"""
import json, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWSHED = os.path.join(ROOT, "data", "highline_viewshed.json")
EXPOSURE = os.path.join(ROOT, "data", "highline_exposure.json")
OUT = os.path.join(ROOT, "data", "highline_reconciled.json")


def binmean(arr, s, seg):
    m = (s >= seg["s0_m"]) & (s < seg["s1_m"])
    return float(arr[m].mean()) if m.any() else float("nan")


def corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    return float(np.corrcoef(a[m], b[m])[0, 1]) if m.sum() > 2 else float("nan")


def main():
    vp = json.load(open(VIEWSHED))["points"]
    segs = json.load(open(EXPOSURE))["segments"]
    s = np.array([p["s_m"] for p in vp])
    svfs = np.array([p["svf_street"] for p in vp])
    svfd = np.array([p["svf_deck"] for p in vp])
    genc = np.array([p["enclosure_deg"] for p in vp])

    # --- cross-validation on the 25 measured bins ---
    G_svf, G_enc, cv = [], [], {k: [] for k in ("sky", "gvi", "enc", "hard")}
    for seg in segs:
        if seg.get("coverage") == "measured" and seg.get("sky") is not None:
            G_svf.append(binmean(svfs, s, seg))
            G_enc.append(binmean(genc, s, seg))
            cv["sky"].append(seg.get("sky") or 0.0)
            cv["gvi"].append(seg.get("gvi") or 0.0)
            cv["enc"].append(seg.get("enclosure_clamped"))
            cv["hard"].append(seg.get("hardness"))
    n = len(G_svf)
    skygvi = [a + b for a, b in zip(cv["sky"], cv["gvi"])]
    pairings = {
        "svf_geom~sky": corr(G_svf, cv["sky"]),
        "svf_geom~gvi": corr(G_svf, cv["gvi"]),
        "svf_geom~(sky+gvi)": corr(G_svf, skygvi),
        "svf_geom~enclosure_cv": corr(G_svf, cv["enc"]),
        "svf_geom~hardness": corr(G_svf, cv["hard"]),
        "enc_geom~sky": corr(G_enc, cv["sky"]),
        "enc_geom~enclosure_cv": corr(G_enc, cv["enc"]),
    }
    best = max(pairings.values(), key=abs)

    # --- fuse as orthogonal layers (NO fabricated CV in empty bins) ---
    def opening_character(gsvf, sky, gvi):
        if gsvf < 0.5:
            return "canyon"                      # geometry closes it regardless
        if sky is None:
            return "open_unsurveyed"             # geometry open, no CV to say what fills it
        if gvi >= sky and gvi >= 0.1:
            return "open_green"                  # opening filled by vegetation (biophilic relief)
        if sky >= 0.1:
            return "open_sky"                    # opening filled by bare sky (exposed)
        return "open_hard"                       # open geometry but hardscape/wall surfaces

    bins_out = []
    for seg in segs:
        measured = seg.get("coverage") == "measured" and seg.get("sky") is not None
        gsvf_s = binmean(svfs, s, seg)
        gsvf_d = binmean(svfd, s, seg)
        genc_b = binmean(genc, s, seg)
        sky = seg.get("sky") if measured else None
        gvi = seg.get("gvi") if measured else None
        bins_out.append({
            "bin": seg["bin"], "s0_m": seg["s0_m"], "s1_m": seg["s1_m"],
            # geometry layer — dense, whole corridor, MODEL estimate
            "geom_svf_street": round(gsvf_s, 4),
            "geom_svf_deck": round(gsvf_d, 4),
            "geom_enclosure_deg": round(genc_b, 2),
            # cv layer — sparse, street-level, MEASURED (null where uncovered)
            "cv_sky": round(sky, 4) if sky is not None else None,
            "cv_gvi": round(gvi, 4) if gvi is not None else None,
            "cv_coverage": seg.get("coverage"),
            # composite
            "opening_character": opening_character(gsvf_s, sky, gvi),
        })

    meta = {
        "method": "cross-validation (calibration hypothesis rejected) + orthogonal-layer fusion",
        "calibration_result": "REJECTED — geometry does not predict the CV audit",
        "n_measured_bins": n,
        "pairing_correlations": {k: round(v, 2) for k, v in pairings.items()},
        "strongest_|r|": round(best, 2),
        "why": "CV points sit ~30 m off-centerline; SegFormer sky is set by trees, "
               "the elevated structure, scaffolding & awnings absent from the footprint isovist.",
        "deck_values": "geometric model estimate, UNVALIDATED against co-located on-deck imagery",
        "n_bins": len(bins_out),
        "n_cv_covered": sum(1 for b in bins_out if b["cv_sky"] is not None),
    }
    json.dump({"metadata": meta, "bins": bins_out}, open(OUT, "w"), indent=1)

    # --- console report ---
    from collections import Counter
    ch = Counter(b["opening_character"] for b in bins_out)
    print("\n=== CROSS-VALIDATION: calibration hypothesis REJECTED ===")
    print(f"measured bins: {n}   (geometry vs CV, Pearson r)")
    for k, v in pairings.items():
        print(f"   {k:26s} r = {v:+.2f}")
    print(f"strongest |r| = {abs(best):.2f}  ->  geometry and CV measure different things.")
    print("\n=== FUSION: geometry (dense/deck) + CV (sparse/street) as orthogonal layers ===")
    print(f"opening character over all 48 bins:")
    for k, c in ch.most_common():
        print(f"   {k:18s} {c:2d} bins")
    print("\nNOTE: empty bins are NOT CV-filled (that would fabricate data). Deck SVF is a")
    print("model estimate; validating it needs on-deck imagery, not the 30 m-offset street points.")
    print(f"\nwrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
