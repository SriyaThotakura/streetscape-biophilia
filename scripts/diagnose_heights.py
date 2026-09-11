"""diagnose_heights.py — does the corridor comparison survive The 606's defaulted heights?

`data/the606_footprints.json` carries its own warning: *"1614/3621 from OSM tags; rest =
2 levels x 3.2 m default"*. In practice **2,998 of 3,621 buildings (82.8%) sit at exactly
6.40 m**. Under-heighting The 606's context inflates its SVF, which WIDENS the published
gap — so unlike the bbox-coverage bias (which runs the conservative way), this one runs
AGAINST the claim.

This engine quantifies it. It re-runs The 606's SVF with the defaulted buildings raised to
a stated set of hypothetical heights, using `compare_corridors.point_metrics` and
`hl_core.edges_for` **unchanged** — `edges_for` already accepts a per-building `heights`
override, so nothing needs editing to substitute a scenario.

DIAGNOSTIC ONLY. Every scenario below is a HYPOTHETICAL, labelled as such. None of them is
a corrected figure, and `data/comparison.json` is not rewritten. Establishing a corrected
606 SVF would need real heights — an OSM re-fetch with `building:levels` resolved, or a
Chicago open-data building-height join — which is a separate decision.

Consumes:  data/the606_footprints.json, data/highline_footprints.json, data/comparison.json
Produces:  data/height_sensitivity.json

Run:  python scripts/diagnose_heights.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import subprocess
import time

import numpy as np

import hl_core as hlc
import compare_corridors as cc          # reused UNCHANGED: point_metrics, N_AZ, MAX_R, SPACING

DATA = hlc.DATA
ROOT = os.path.dirname(DATA)

DEFAULT_H = 6.40           # the value 82.8% of The 606's buildings carry
LEVEL_H = 3.2              # the OSM level height the default is built from
# hypothetical replacements, stated not derived. 10.6 is included because it is
# hl_core.EYE_DECK — the deck eye height, below which a building cannot occlude any sky at
# all — and 12.8 / 16.0 because they are 4 and 5 OSM levels, values the corridor's own
# tagged stock actually contains.
SCENARIOS = [7.5, 9.0, 10.6, 12.0, 12.8, 15.0, 16.0, 20.0]

# supplementary: raise only a FRACTION of the defaulted stock to a plausible walk-up
# height, which is a more realistic failure mode than a uniform lift of all 2,998
FRACTION_SCENARIOS = [(0.10, 12.8), (0.25, 12.8), (0.50, 12.8), (0.25, 16.0)]
HL_LAT, S6_LAT = 40.7409, 41.9138


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def height_profile(path, label):
    d = json.load(open(path, encoding="utf-8"))
    raw = [f["properties"].get("height") for f in d["features"]]
    missing = sum(1 for h in raw if h is None)
    hs = np.array([float(h) for h in raw if h is not None])
    c = collections.Counter(hs.tolist())
    mode_v, mode_n = c.most_common(1)[0]
    # a "default cluster" = one value carrying an implausible share of a real building stock
    lvl_multiples = sum(n for v, n in c.items()
                        if abs(v / LEVEL_H - round(v / LEVEL_H)) < 1e-9)
    return {
        "label": label,
        "source_file": "data/" + os.path.basename(path),
        "n_buildings": int(len(raw)),
        "n_missing_height": int(missing),
        "n_unique_heights": int(len(c)),
        "modal_height_m": round(float(mode_v), 2),
        "modal_count": int(mode_n),
        "modal_share_pct": round(100.0 * mode_n / len(hs), 1),
        "mean_m": round(float(hs.mean()), 2),
        "median_m": round(float(np.median(hs)), 2),
        "p90_m": round(float(np.percentile(hs, 90)), 2),
        "max_m": round(float(hs.max()), 2),
        "share_above_20m_pct": round(100.0 * float((hs > 20).mean()), 1),
        "n_at_level_multiples": int(lvl_multiples),
        "share_at_level_multiples_pct": round(100.0 * lvl_multiples / len(hs), 1),
        "top5": [[round(float(v), 2), int(n)] for v, n in c.most_common(5)],
        "has_default_cluster": bool(100.0 * mode_n / len(hs) > 20.0),
    }


def svf_with_heights(site, dirs, sun, override=None, heights=None):
    """Mean SVF over the corridor, via compare_corridors.point_metrics UNCHANGED.

    `override` maps a building's stored height to a replacement, or pass an explicit
    per-building `heights` list. hl_core.edges_for takes the resulting array directly, so no
    engine is edited to run a scenario.
    """
    if heights is None:
        heights = (None if override is None
                   else [override.get(round(b.h, 4), b.h) for b in site.buildings])
    svf = []
    for (pt, s) in site.corridor.samples(cc.SPACING):
        px, pz = float(pt[0]), float(pt[1])
        e = hlc.edges_for(site.buildings, px, pz, cc.MAX_R, heights=heights)
        svf.append(cc.point_metrics(e, px, pz, dirs, sun)[0])
    return float(np.mean(svf))


def main():
    t0 = time.time()
    ang = np.linspace(0, 2 * math.pi, cc.N_AZ, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], 1)

    hl_site = hlc.load_site(os.path.join(DATA, "highline_footprints.json"))
    s6_site = hlc.load_site(os.path.join(DATA, "the606_footprints.json"))
    hl_sun = hlc.sun_path(355, lat=HL_LAT)
    s6_sun = hlc.sun_path(355, lat=S6_LAT)

    prof_hl = height_profile(os.path.join(DATA, "highline_footprints.json"), "High Line (NYC)")
    prof_s6 = height_profile(os.path.join(DATA, "the606_footprints.json"), "The 606 (Chicago)")

    pub = {c["name"]: c for c in json.load(
        open(os.path.join(DATA, "comparison.json"), encoding="utf-8"))["corridors"]}
    pub_hl = pub["High Line (NYC)"]["mean_svf"]
    pub_s6 = pub["The 606 (Chicago)"]["mean_svf"]

    print("reproducing the published baseline with the same machinery ...")
    base_hl = svf_with_heights(hl_site, dirs, hl_sun)
    base_s6 = svf_with_heights(s6_site, dirs, s6_sun)
    print("  High Line  computed %.4f  published %.3f" % (base_hl, pub_hl))
    print("  The 606    computed %.4f  published %.3f" % (base_s6, pub_s6))

    n_default = sum(1 for b in s6_site.buildings if abs(b.h - DEFAULT_H) < 1e-9)

    rows = []
    print("\nhypothetical scenarios — raising the %d buildings at %.2f m:" % (n_default, DEFAULT_H))
    for h in SCENARIOS:
        s = svf_with_heights(s6_site, dirs, s6_sun, {DEFAULT_H: h})
        rows.append({
            "hypothetical_default_height_m": h,
            "storeys_implied_at_3p2m": round(h / LEVEL_H, 1),
            "n_buildings_raised": n_default,
            "the606_mean_svf": round(s, 4),
            "delta_vs_baseline_svf": round(s - base_s6, 4),
            "gap_vs_highline_svf": round(s - base_hl, 4),
            "gap_direction": "606 still more open" if s > base_hl else "GAP CLOSED OR REVERSED",
        })
        print("  %5.1f m (%.1f storeys) -> 606 SVF %.4f   gap vs High Line %+.4f  %s"
              % (h, h / LEVEL_H, s, s - base_hl,
                 "" if s > base_hl else "<-- CLOSED"))

    # ---- supplementary: raise only a fraction, deterministically ---------------------
    # A uniform lift of all 2,998 is unrealistic. Raising a share of them to a plausible
    # walk-up height is closer to how an OSM height gap actually looks. Selection is by
    # sorted building index — deterministic, no RNG.
    idx_default = [i for i, b in enumerate(s6_site.buildings)
                   if abs(b.h - DEFAULT_H) < 1e-9]
    # Order once by a stable hash of the building id, then take the first k. This makes the
    # subsets NESTED (10% is inside 25% is inside 50%) and spatially uniform. A stride like
    # idx[::n] is neither: different fractions land on different spatial subsets, which
    # produced a non-monotone result — 50% reading MORE open than 25%.
    order = sorted(idx_default,
                   key=lambda i: hashlib.md5(str(s6_site.buildings[i].id).encode()).hexdigest())
    frac_rows = []
    print("\nsupplementary — raising only a FRACTION of the defaulted stock:")
    for frac, h in FRACTION_SCENARIOS:
        k = int(round(frac * len(idx_default)))
        chosen = set(order[:k])
        hh = [(h if i in chosen else b.h) for i, b in enumerate(s6_site.buildings)]
        s = svf_with_heights(s6_site, dirs, s6_sun, heights=hh)
        frac_rows.append({
            "fraction_raised": frac,
            "n_raised": len(chosen),
            "hypothetical_height_m": h,
            "storeys_implied_at_3p2m": round(h / LEVEL_H, 1),
            "the606_mean_svf": round(s, 4),
            "gap_vs_highline_svf": round(s - base_hl, 4),
            "selection": "first k of the defaulted set ordered by md5(building id) — nested across fractions, spatially uniform, deterministic, no RNG",
        })
        print("  %3.0f%% at %4.1f m -> 606 SVF %.4f   gap %+.4f"
              % (100 * frac, h, s, s - base_hl))

    # ---- break-even: uniform height at which the gap reaches zero --------------------
    print("\nsolving break-even (606 SVF == High Line SVF) ...")
    lo, hi = DEFAULT_H, 200.0
    s_hi = svf_with_heights(s6_site, dirs, s6_sun, {DEFAULT_H: hi})
    if s_hi > base_hl:
        break_even = None
        be_note = ("no break-even below %.0f m: even raising every defaulted building to "
                   "%.0f m leaves The 606 more open than the High Line (SVF %.4f vs %.4f)"
                   % (hi, hi, s_hi, base_hl))
        n_iter = 0
    else:
        for n_iter in range(1, 25):
            mid = 0.5 * (lo + hi)
            if svf_with_heights(s6_site, dirs, s6_sun, {DEFAULT_H: mid}) > base_hl:
                lo = mid
            else:
                hi = mid
            if hi - lo < 0.05:
                break
        break_even = 0.5 * (lo + hi)
        be_note = None
        print("  break-even at %.2f m (%.1f storeys), %d iterations"
              % (break_even, break_even / LEVEL_H, n_iter))

    # plausibility evidence, from The 606's own data
    s6_h = np.array([b.h for b in s6_site.buildings])
    tagged = s6_h[np.abs(s6_h / LEVEL_H - np.round(s6_h / LEVEL_H)) > 1e-9]   # true height tags
    nondefault = s6_h[np.abs(s6_h - DEFAULT_H) > 1e-9]

    plaus = {
        "the606_max_building_m": round(float(s6_h.max()), 2),
        "the606_share_above_20m_pct": round(100.0 * float((s6_h > 20).mean()), 1),
        "the606_non_default_subset": {
            "n": int(len(nondefault)),
            "mean_m": round(float(nondefault.mean()), 2),
            "median_m": round(float(np.median(nondefault)), 2),
            "max_m": round(float(nondefault.max()), 2),
        },
        "the606_true_height_tag_subset": {
            "note": "buildings whose height is NOT a multiple of the 3.2 m level height — "
                    "these carry a real OSM `height` tag rather than a levels estimate",
            "n": int(len(tagged)),
            "values_m": sorted(round(float(v), 2) for v in set(tagged.tolist())),
            "mean_m": round(float(tagged.mean()), 2) if len(tagged) else None,
            "max_m": round(float(tagged.max()), 2) if len(tagged) else None,
        },
        "highline_comparison": {
            "mean_m": prof_hl["mean_m"],
            "share_above_20m_pct": prof_hl["share_above_20m_pct"],
            "max_m": prof_hl["max_m"],
        },
    }

    result = {
        "_meta": {
            "script": "scripts/diagnose_heights.py",
            "git_commit": _git_commit(),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "purpose": "Quantify the effect of The 606's defaulted building heights on the "
                       "published corridor comparison. DIAGNOSTIC ONLY — every scenario is "
                       "a hypothetical, not a correction.",
            "source": ["data/the606_footprints.json", "data/highline_footprints.json",
                       "data/comparison.json"],
            "writes": "data/height_sensitivity.json only. compare_corridors.py, hl_core.py "
                      "and data/comparison.json are NOT modified.",
            "reused_unchanged": ["compare_corridors.point_metrics", "compare_corridors.N_AZ",
                                 "compare_corridors.MAX_R", "compare_corridors.SPACING",
                                 "hl_core.edges_for (its existing `heights` override)",
                                 "hl_core.ray_uv", "hl_core.sun_path", "hl_core.load_site"],
            "deterministic": True,
            "seed_note": "no stochastic step; the break-even is a bisection to 0.05 m",
            "params": {"N_AZ": cc.N_AZ, "MAX_R": cc.MAX_R, "SPACING": cc.SPACING,
                       "default_height_m": DEFAULT_H, "osm_level_height_m": LEVEL_H,
                       "scenario_heights_m": SCENARIOS},
            "scenario_set_definition":
                "A scenario raises EVERY building stored at exactly %.2f m. That is %d "
                "buildings. The file's own height_note implies only ~%d are true fallbacks "
                "(3621 - 1614 tagged), so ~%d of them may be genuine two-storey buildings "
                "already correctly at %.2f m. Raising all of them therefore OVERSTATES the "
                "correction — which is the conservative direction for a survival test: if "
                "the gap holds here, it holds."
                % (DEFAULT_H, n_default, 3621 - 1614, n_default - (3621 - 1614), DEFAULT_H),
            "limitations": [
                "These are hypotheticals. None is a corrected 606 SVF, and none may be "
                "quoted as one.",
                "A uniform replacement height is itself unrealistic — real building stock "
                "varies. The scenarios bracket the effect; they do not model the fabric.",
                "The bbox-coverage bias measured in data/coverage_diagnostic.json runs the "
                "OPPOSITE way (it understates the gap). The two are not netted here; each "
                "is reported on its own terms.",
                "Only heights are varied. Footprint completeness, which differs between an "
                "OSM extract and NYC Open Data, is not tested.",
            ],
        },
        "height_distribution": {"high_line": prof_hl, "the606": prof_s6},
        "baseline": {
            "note": "the same machinery, re-run, to confirm this harness reproduces the "
                    "published figures before any scenario is trusted",
            "highline_computed_svf": round(base_hl, 4),
            "highline_published_svf": pub_hl,
            "the606_computed_svf": round(base_s6, 4),
            "the606_published_svf": pub_s6,
            "published_gap": round(pub_s6 - pub_hl, 4),
            "computed_gap": round(base_s6 - base_hl, 4),
            "reproduces": bool(abs(base_hl - pub_hl) < 0.002 and abs(base_s6 - pub_s6) < 0.002),
        },
        "scenarios_hypothetical": rows,
        "break_even": {
            "question": "At what uniform height for the defaulted buildings does The 606's "
                        "mean SVF fall to the High Line's, closing the gap entirely?",
            "break_even_height_m": round(break_even, 2) if break_even else None,
            "storeys_implied_at_3p2m": round(break_even / LEVEL_H, 1) if break_even else None,
            "no_break_even_note": be_note,
            "plausibility_evidence": plaus,
        },
        "verdict": None,          # filled below
    }

    # ---- verdict ---------------------------------------------------------------------
    # The plausibility test is NOT "is the break-even below the tallest building" — one
    # 35 m outlier says nothing about 2,998 of them. The test is whether the break-even is
    # credible as a height for the WHOLE defaulted stock, judged against the stock in the
    # same corridor that actually carries height information.
    informative_mean = float(nondefault.mean())
    ratio = break_even / informative_mean if break_even else None
    closed = [r for r in rows if r["the606_mean_svf"] <= base_hl]
    first_closed = min((r["hypothetical_default_height_m"] for r in closed), default=None)
    eye = hlc.EYE_DECK

    if break_even is None:
        verdict = ("SURVIVES OUTRIGHT — no uniform height closes the gap.")
        robust = "robust"
    elif ratio >= 2.0:
        verdict = (
            "SURVIVES, but NOT robustly. The gap closes at a uniform %.2f m (%.1f storeys) "
            "for all %d defaulted buildings. That is %.1fx the mean height of the %d "
            "buildings in the SAME corridor that do carry height information (%.2f m), and "
            "OSM tagging bias runs the other way — taller buildings are more likely to be "
            "tagged, not less. A uniform %.1f-storey defaulted stock through Logan Square, "
            "Humboldt Park and Wicker Park is not credible, so the gap stands. But the "
            "margin is thinner than the coverage analysis implied: the comparison is "
            "insensitive to the defaults only while they stay below the %.1f m deck eye, "
            "and it degrades quickly above it."
            % (break_even, break_even / LEVEL_H, n_default, ratio, len(nondefault),
               informative_mean, break_even / LEVEL_H, eye))
        robust = "survives, not robust"
    else:
        verdict = (
            "AT RISK. The gap closes at a uniform %.2f m (%.1f storeys), only %.1fx the "
            "mean of the corridor's height-tagged stock (%.2f m). That is within the range "
            "a real building stock could take, so the comparison CANNOT be defended on "
            "these data. Do not board it without real heights."
            % (break_even, break_even / LEVEL_H, ratio, informative_mean))
        robust = "at risk"

    result["scenarios_fractional_hypothetical"] = frac_rows
    result["mechanism"] = {
        "deck_eye_height_m": eye,
        "why_low_scenarios_change_nothing":
            "compare_corridors computes beta = arctan2(H - EYE_DECK, t) and clamps it at 0, "
            "so a building shorter than the %.1f m deck eye occludes NO sky and cannot move "
            "the SVF at all. Raising the defaults from %.2f m to 7.5 or 9.0 m changes the "
            "result by exactly zero. The comparison is completely insensitive to the default "
            "height until it crosses %.1f m — which is the real question this diagnostic "
            "answers: not 'are the defaults low', but 'how many buildings above %.1f m are "
            "recorded at %.2f m'."
            % (eye, DEFAULT_H, eye, eye, DEFAULT_H),
        "first_scenario_that_closes_the_gap_m": first_closed,
    }
    result["verdict"] = {
        "gap_holds_at_every_scenario": bool(not closed),
        "robustness": robust,
        "statement": verdict,
        "break_even_vs_informative_stock": {
            "break_even_m": round(break_even, 2) if break_even else None,
            "mean_of_height_bearing_buildings_m": round(informative_mean, 2),
            "ratio": round(ratio, 2) if ratio else None,
            "n_height_bearing": int(len(nondefault)),
        },
        "direction_reminder": "Defaulted heights inflate The 606's SVF and therefore WIDEN "
                              "the published gap. This bias runs AGAINST the claim, unlike "
                              "the bbox-coverage bias, which runs for it.",
    }

    outp = os.path.join(DATA, "height_sensitivity.json")
    json.dump(result, open(outp, "w", encoding="utf-8"), indent=1)
    print("\nwrote %s  (%.1f s)" % (outp, time.time() - t0))
    print("\nVERDICT: " + verdict)
    return result


if __name__ == "__main__":
    main()
