"""build_counterfactual.py — does the measured field actually earn its canopy?

`build_envelope.py` generates a rib at every deck station from the measured
enclosure field: height ~ stolen-sky deficit, reach ~ sun-weighted surviving
aperture, heading = where light still arrives from. It reports 36.8% mean winter-sun
recapture at the reach tips of the enclosed stations.

That number is only an argument for computational design if a *dumb* canopy does
worse. This engine builds the dumb canopies and measures them with the identical
instrument.

What is reused, unchanged, by import
------------------------------------
  build_envelope._rib             the rib generator (geometry)
  build_envelope._recaptured_sun  the loop-closing recapture cast (measurement)
  build_envelope._tangent         deck tangent at a station
  build_rib_schedule._member3d    fabricated member length (segments of the 3-D rib)
  hl_core                         site, corridor, sun path, ray primitive

Nothing in those files is touched. **Only the driver changes.** Where the envelope
reads height/reach/heading out of the measured field, this script substitutes a
constant, and then runs the same generator and the same measurement.

How a constant driver is injected without editing `_rib`
--------------------------------------------------------
`_rib` computes  drive = clip(deficit,0,1) * (0.5 + 0.5*openness_gate),
                 openness_gate = clip((OPEN_SVF - svf_deck)/OPEN_SVF, 0, 1),
                 rib_h = RIB_BASE_H + (RIB_MAX_H - RIB_BASE_H)*drive,
                 reach = REACH_MAX * drive * (0.4 + 0.6*directionality).
Passing svf_deck = 0.0 sets openness_gate = 1, so drive == the `deficit` argument
verbatim. Feeding a constant there makes height and reach constant across all 232
stations — a uniform canopy — with the generator itself untouched.
(`ap_alt` is accepted by `_rib` but unused in its body; passed as 0.0.)

The two control variants (both reported)
----------------------------------------
  (a) equal max height   — 7.00 m rib everywhere, reach fixed, heading fixed north.
                           Spends ~2x the field-driven steel. The generous control.
  (b) equal member length — uniform drive solved by bisection so total fabricated
                           member length equals the field-driven 2,408.5 m. The
                           same steel, redistributed evenly. The fair control.

Both are also swept over 12 compass headings (a sensitivity beyond the brief): a
north-fixed control is the weakest possible naive canopy at 40.7 deg N, where winter
sun is southern, so the *best* naive heading is reported alongside. If the field
-driven form only beats a control aimed the wrong way, it has not proven anything.

Consumes:  data/envelope.json            (the field-driven baseline + station set)
           data/highline_viewshed.json   (deficit, for the enclosed-station mask)
           data/highline_footprints.json via hl_core.load_site  (the massing)
Produces:  data/counterfactual.json

Run:  python scripts/build_counterfactual.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import time

import numpy as np

import hl_core as hl
import build_envelope as be
from build_rib_schedule import _member3d

DATA = hl.DATA
ROOT = os.path.dirname(DATA)

SEED = 42                    # no stochastic step in this engine; recorded for convention
ENCLOSED_DEFICIT = 0.05      # same enclosed-station threshold build_envelope reports on
TARGET_HEIGHT_A = 7.0        # variant (a): "equal max height", metres
FIXED_DIRECTIONALITY = 1.0   # constant -> reach is fixed; 1.0 is the generator's maximum,
                             # i.e. the most generous reach the naive canopy can be given
HEADING_NORTH = 0.0          # hl_core convention: az = 0 -> +z (north)
N_HEADINGS = 12              # sensitivity sweep, 30 deg steps
KG_PER_M = 24.0              # matches build_rib_schedule (an ASSUMED linear density,
                             # not a structural sizing — see Projects/README.md §5)


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def _pearson(a, b):
    """Pearson r, or None when either series has no variance. A uniform canopy has
    constant rib height, so r against the deficit is UNDEFINED, not zero — and 0.0
    would read as 'measured no relationship' rather than 'no relationship possible'."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    if a.std() == 0.0 or b.std() == 0.0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _drive_for_height(h):
    """Invert _rib's height law: the constant `deficit` argument that yields rib_h = h
    when svf_deck = 0 (openness_gate = 1)."""
    return (h - be.RIB_BASE_H) / (be.RIB_MAX_H - be.RIB_BASE_H)


def _height_for_drive(d):
    return be.RIB_BASE_H + (be.RIB_MAX_H - be.RIB_BASE_H) * d


def _uniform_canopy(buildings, samples, drive, heading, sun_w, measure=True):
    """Generate the uniform canopy at every station with the UNCHANGED rib generator,
    and (optionally) measure it with the UNCHANGED recapture cast.

    Returns dict with per-station polylines, member lengths and recapture fractions."""
    ribs, apexes, mem_len, recap = [], [], [], []
    rib_h = reach = None
    for i, (xz, s) in enumerate(samples):
        px, pz = float(xz[0]), float(xz[1])
        tx, tz = be._tangent(samples, i)
        poly, apex, rib_h, reach = be._rib(
            px, pz, tx, tz,
            deficit=drive,               # svf_deck=0 below makes drive == this value
            ap_az=heading,
            ap_alt=0.0,                  # unused by _rib
            directionality=FIXED_DIRECTIONALITY,
            svf_deck=0.0,
        )
        rp = [[round(c, 2) for c in pt] for pt in poly]   # same rounding envelope.json stores,
        ribs.append(rp)                                   # so member length is comparable
        apexes.append(apex)
        mem_len.append(float(_member3d(rp)[0].sum()))
        if measure:
            # unrounded apex, exactly as build_envelope casts it
            recap.append(be._recaptured_sun(buildings, apex, *sun_w))
    return {
        "ribs": ribs, "apexes": apexes,
        "mem_len": np.array(mem_len),
        "recap": np.array(recap) if measure else None,
        "rib_height_m": rib_h, "reach_m": reach,
    }


def _solve_drive_for_length(buildings, samples, target_m, heading):
    """Bisect the uniform drive so total fabricated member length == target_m.
    Member length is monotone increasing in drive (both height and reach grow with it).
    Deterministic; no measurement cast during the solve."""
    def total(d):
        return float(_uniform_canopy(buildings, samples, d, heading, None,
                                     measure=False)["mem_len"].sum())
    lo, hi = 0.0, 1.0
    t_lo, t_hi = total(lo), total(hi)
    if target_m <= t_lo:
        return 0.0, t_lo, "clamped: target is below the minimum-rib canopy"
    if target_m >= t_hi:
        return 1.0, t_hi, "clamped: target exceeds the full-drive canopy"
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if total(mid) < target_m:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    d = 0.5 * (lo + hi)
    return d, total(d), None


def _summary(recap, enclosed, base_recap):
    """Per-variant recapture summary, always against the same station mask."""
    delta = recap - base_recap
    return {
        "mean_recaptured_winter_sun_frac_enclosed": round(float(recap[enclosed].mean()), 3)
        if enclosed.any() else None,
        "mean_recaptured_all": round(float(recap.mean()), 3),
        "median_recaptured_enclosed": round(float(np.median(recap[enclosed])), 3)
        if enclosed.any() else None,
        "min_recaptured_enclosed": round(float(recap[enclosed].min()), 3) if enclosed.any() else None,
        "max_recaptured_enclosed": round(float(recap[enclosed].max()), 3) if enclosed.any() else None,
        "mean_delta_vs_field_enclosed": round(float(delta[enclosed].mean()), 3)
        if enclosed.any() else None,
        "mean_delta_vs_field_all": round(float(delta.mean()), 3),
        "n_stations_naive_beats_field_enclosed": int((delta[enclosed] > 1e-9).sum())
        if enclosed.any() else None,
        "n_stations_naive_ties_field_enclosed": int((np.abs(delta[enclosed]) <= 1e-9).sum())
        if enclosed.any() else None,
        "n_stations_naive_loses_field_enclosed": int((delta[enclosed] < -1e-9).sum())
        if enclosed.any() else None,
    }


def build():
    site = hl.load_site()
    buildings, corr = site.buildings, site.corridor
    samples = corr.samples(be.SPACING)
    sun_w = hl.sun_path(be.WINTER)          # the winter set build_envelope closes the loop with

    # ---- the field-driven baseline, read (never recomputed) from envelope.json -----
    env = json.load(open(os.path.join(DATA, "envelope.json"), encoding="utf-8"))
    epts = env["points"]
    if len(epts) != len(samples):
        raise SystemExit(f"station mismatch: envelope.json has {len(epts)}, "
                         f"corridor resample gives {len(samples)} — regenerate envelope.json")
    base_recap = np.array([p["recaptured_winter_sun_frac"] for p in epts])
    base_defs = np.array([p["deficit_svf"] for p in epts])
    base_h = np.array([p["rib_height_m"] for p in epts])
    base_reach = np.array([p["reach_m"] for p in epts])
    base_mem = np.array([float(_member3d(p["rib"])[0].sum()) for p in epts])
    enclosed = base_defs > ENCLOSED_DEFICIT
    s_m = np.array([p["s_m"] for p in epts])

    base_summary = {
        "mean_recaptured_winter_sun_frac_enclosed": round(float(base_recap[enclosed].mean()), 3),
        "mean_recaptured_all": round(float(base_recap.mean()), 3),
        "deficit_vs_ribheight_r": round(_pearson(base_defs, base_h), 3),
        "total_member_length_m": round(float(base_mem.sum()), 1),
        "est_steel_tonnes": round(float(base_mem.sum()) * KG_PER_M / 1000.0, 2),
        "mean_rib_height_m": round(float(base_h.mean()), 2),
        "mean_reach_m": round(float(base_reach.mean()), 2),
    }

    print(f"field-driven baseline (from envelope.json, unchanged):")
    print(f"  enclosed-station mean winter-sun recapture = "
          f"{base_summary['mean_recaptured_winter_sun_frac_enclosed']*100:.1f}%   "
          f"(n = {int(enclosed.sum())} of {len(epts)})")
    print(f"  member {base_summary['total_member_length_m']:.1f} m  ·  "
          f"height vs deficit r = {base_summary['deficit_vs_ribheight_r']:+.3f}")

    variants = {}

    # ---- (a) equal max height: 7 m everywhere ------------------------------------
    drive_a = _drive_for_height(TARGET_HEIGHT_A)
    print(f"\n(a) uniform 7.00 m canopy, reach fixed, heading north ...")
    ca = _uniform_canopy(buildings, samples, drive_a, HEADING_NORTH, sun_w)
    variants["a_equal_max_height"] = {
        "label": "equal max height — 7.00 m rib at every station, reach fixed, heading fixed north",
        "driver": "uniform constant; no field input",
        "uniform_drive": round(drive_a, 6),
        "rib_height_m": round(ca["rib_height_m"], 3),
        "reach_m": round(ca["reach_m"], 3),
        "heading_deg": 0.0,
        "total_member_length_m": round(float(ca["mem_len"].sum()), 1),
        "est_steel_tonnes": round(float(ca["mem_len"].sum()) * KG_PER_M / 1000.0, 2),
        "member_length_vs_field_ratio": round(float(ca["mem_len"].sum() / base_mem.sum()), 3),
        "deficit_vs_ribheight_r": _pearson(base_defs, np.full(len(epts), ca["rib_height_m"])),
        "deficit_vs_ribheight_r_note":
            "null, not 0 — rib height is constant by construction, so the correlation is "
            "undefined (zero variance), not measured-and-found-absent. That undefinedness "
            "IS the counterfactual: a uniform canopy cannot track the field it ignores.",
        **_summary(ca["recap"], enclosed, base_recap),
    }

    # ---- (b) equal total member length --------------------------------------------
    target = float(base_mem.sum())
    print(f"(b) uniform canopy solved to {target:.1f} m member ...")
    drive_b, got_b, clamp = _solve_drive_for_length(buildings, samples, target, HEADING_NORTH)
    cb = _uniform_canopy(buildings, samples, drive_b, HEADING_NORTH, sun_w)
    variants["b_equal_member_length"] = {
        "label": f"equal total member length — {target:.1f} m redistributed uniformly, "
                 f"reach fixed, heading fixed north",
        "driver": "uniform constant; no field input",
        "uniform_drive": round(drive_b, 6),
        "rib_height_m": round(cb["rib_height_m"], 3),
        "reach_m": round(cb["reach_m"], 3),
        "heading_deg": 0.0,
        "total_member_length_m": round(float(cb["mem_len"].sum()), 1),
        "est_steel_tonnes": round(float(cb["mem_len"].sum()) * KG_PER_M / 1000.0, 2),
        "member_length_vs_field_ratio": round(float(cb["mem_len"].sum() / base_mem.sum()), 3),
        "length_match_residual_m": round(float(cb["mem_len"].sum()) - target, 3),
        "solver": "bisection on the uniform drive, 60 iterations, deterministic",
        "solver_clamp": clamp,
        "deficit_vs_ribheight_r": _pearson(base_defs, np.full(len(epts), cb["rib_height_m"])),
        "deficit_vs_ribheight_r_note":
            "null, not 0 — constant rib height, zero variance, correlation undefined.",
        **_summary(cb["recap"], enclosed, base_recap),
    }

    # ---- heading sensitivity (beyond the brief; guards against a rigged control) ---
    print(f"sweeping {N_HEADINGS} headings for both variants ...")
    sweep = {}
    for key, drive in (("a_equal_max_height", drive_a), ("b_equal_member_length", drive_b)):
        rows = []
        for k in range(N_HEADINGS):
            hd = 2 * math.pi * k / N_HEADINGS
            c = _uniform_canopy(buildings, samples, drive, hd, sun_w)
            rows.append({
                "heading_deg": round(math.degrees(hd), 1),
                "mean_recaptured_enclosed": round(float(c["recap"][enclosed].mean()), 3),
                "mean_recaptured_all": round(float(c["recap"].mean()), 3),
            })
        best = max(rows, key=lambda r: r["mean_recaptured_enclosed"])
        sweep[key] = {
            "rows": rows,
            "best_heading_deg": best["heading_deg"],
            "best_mean_recaptured_enclosed": best["mean_recaptured_enclosed"],
            "best_vs_field_delta_enclosed": round(
                best["mean_recaptured_enclosed"]
                - base_summary["mean_recaptured_winter_sun_frac_enclosed"], 3),
        }

    # ---- verdict -------------------------------------------------------------------
    fb = base_summary["mean_recaptured_winter_sun_frac_enclosed"]
    beat = [k for k, v in sweep.items() if v["best_mean_recaptured_enclosed"] > fb + 1e-9]
    tie = [k for k, v in sweep.items() if abs(v["best_mean_recaptured_enclosed"] - fb) <= 1e-9]
    verdict = {
        "field_driven_mean_recaptured_enclosed": fb,
        "best_naive_any_variant_any_heading": max(
            v["best_mean_recaptured_enclosed"] for v in sweep.values()),
        "field_driven_wins": not beat and not tie,
        "naive_variants_beating_field_at_best_heading": beat,
        "naive_variants_tying_field_at_best_heading": tie,
    }

    result = {
        "_meta": {
            "script": "build_counterfactual.py",
            "git_commit": _git_commit(),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": ["data/envelope.json", "data/highline_viewshed.json",
                       "data/highline_footprints.json"],
            "model": "naive-canopy counterfactual: build_envelope._rib and "
                     "build_envelope._recaptured_sun reused UNCHANGED by import; only the "
                     "height/reach/heading driver is replaced by a uniform constant. "
                     "Injected via svf_deck=0 (openness_gate=1), which makes _rib's internal "
                     "drive equal the passed `deficit` verbatim.",
            "reused_unchanged": ["build_envelope._rib", "build_envelope._recaptured_sun",
                                 "build_envelope._tangent", "build_rib_schedule._member3d",
                                 "hl_core.load_site", "hl_core.sun_path", "hl_core.ray_uv"],
            "params": {
                "seed": SEED,
                "seed_note": "no stochastic step in this engine; recorded for convention",
                "SPACING": be.SPACING, "MAX_R": be.MAX_R,
                "RIB_BASE_H": be.RIB_BASE_H, "RIB_MAX_H": be.RIB_MAX_H,
                "REACH_MAX": be.REACH_MAX, "OPEN_SVF": be.OPEN_SVF,
                "DECK_HALF_W": be.DECK_HALF_W,
                "winter_day": be.WINTER,
                "enclosed_deficit_threshold": ENCLOSED_DEFICIT,
                "target_height_a_m": TARGET_HEIGHT_A,
                "fixed_directionality": FIXED_DIRECTIONALITY,
                "fixed_directionality_note":
                    "constant across stations, so reach is fixed; 1.0 is the generator's "
                    "maximum, giving the naive canopy the longest reach it can have at its "
                    "drive — deliberately the generous choice",
                "n_headings_swept": N_HEADINGS,
                "kg_per_m": KG_PER_M,
                "kg_per_m_note": "assumed linear density, not a structural sizing",
            },
            "n_stations": len(epts),
            "n_enclosed_stations": int(enclosed.sum()),
            "limitations": [
                "Same-primitive validation. Every variant is measured by the ray-caster that "
                "generated the field-driven form, so this is an internal-consistency "
                "comparison, not an independent one (IMPLEMENTATION_PLAN.md W3.1).",
                "The recapture metric is winter-sun timesteps clear at the reach tip — a "
                "point measure at one height, not an irradiance integral over the deck.",
                "The uniform variants are aimed by a single global heading. A naive designer "
                "could do better with a per-station rule that is still not the measured field; "
                "that intermediate control is not tested here.",
            ],
        },
        "baseline_field_driven": base_summary,
        "variants": variants,
        "heading_sensitivity": sweep,
        "verdict": verdict,
        "points": [
            {
                "s_m": round(float(s_m[i]), 2),
                "deficit_svf": round(float(base_defs[i]), 4),
                "enclosed": bool(enclosed[i]),
                "field_rib_height_m": round(float(base_h[i]), 2),
                "field_reach_m": round(float(base_reach[i]), 2),
                "field_recaptured_winter_sun_frac": round(float(base_recap[i]), 3),
                "a_recaptured_winter_sun_frac": round(float(ca["recap"][i]), 3),
                "b_recaptured_winter_sun_frac": round(float(cb["recap"][i]), 3),
                "a_minus_field": round(float(ca["recap"][i] - base_recap[i]), 3),
                "b_minus_field": round(float(cb["recap"][i] - base_recap[i]), 3),
            }
            for i in range(len(epts))
        ],
    }

    outp = os.path.join(DATA, "counterfactual.json")
    json.dump(result, open(outp, "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {outp}  ({len(epts)} stations)")

    va = variants["a_equal_max_height"]; vb = variants["b_equal_member_length"]
    print(f"\n  field-driven          {fb*100:5.1f}%   "
          f"r = {base_summary['deficit_vs_ribheight_r']:+.3f}   "
          f"{base_summary['total_member_length_m']:.0f} m member")
    print(f"  (a) equal max height  {va['mean_recaptured_winter_sun_frac_enclosed']*100:5.1f}%   "
          f"r = null (constant height)   {va['total_member_length_m']:.0f} m member "
          f"({va['member_length_vs_field_ratio']:.2f}x)")
    print(f"  (b) equal member len  {vb['mean_recaptured_winter_sun_frac_enclosed']*100:5.1f}%   "
          f"r = null (constant height)   {vb['total_member_length_m']:.0f} m member "
          f"({vb['member_length_vs_field_ratio']:.2f}x)")
    print(f"\n  best naive over all headings: "
          f"{verdict['best_naive_any_variant_any_heading']*100:.1f}%")
    for k, v in sweep.items():
        print(f"    {k}: best {v['best_mean_recaptured_enclosed']*100:.1f}% at "
              f"{v['best_heading_deg']:.0f}deg  (field-driven {fb*100:.1f}%, "
              f"delta {v['best_vs_field_delta_enclosed']*100:+.1f} pts)")
    if verdict["field_driven_wins"]:
        print("\n  VERDICT: the field-driven canopy beats every naive control tested.")
    else:
        print(f"\n  VERDICT: a naive control MATCHES OR BEATS the field-driven canopy — "
              f"beat: {beat or 'none'}, tie: {tie or 'none'}. Report this as the finding.")
    return result


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
