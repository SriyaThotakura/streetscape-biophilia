"""diagnose_coverage.py — how much measured sky is "no building" vs "no data"?

`data/highline_footprints.json` was fetched with a lat/lon bbox centred on the corridor.
The ray-cast engines cull occluders at MAX_R = 350 m. Those two numbers are independent,
and the bbox half-spans do not cover MAX_R around the whole deck — so some rays that
`build_viewshed` records as CLEAR (no hit within 350 m) are clear only because the fetch
stopped, not because the sky is open.

This engine separates the two. For every station it re-casts at the viewshed's own
azimuthal resolution using hl_core's own primitives, and for each ray that reaches MAX_R
without hitting anything it asks a second question: did that ray leave the fetched bbox
first?

  clear                  no edge hit within MAX_R                    (what the engine sees)
  clear AND covered      ... and the whole 350 m run is inside bbox  (genuinely open sky)
  clear AND truncated    ... but the run leaves the bbox before then (open sky OR no data)

DIAGNOSTIC ONLY. Reads the fetched footprints, writes one new file, and touches no engine,
no existing data/*.json, and nothing in hl_core.py. It deliberately does NOT estimate a
corrected SVF: that needs a re-fetch with a bbox sized to the corridor plus MAX_R, which
is a W0 decision and not this script's to make.

Consumes:  data/highline_footprints.json  (via hl_core.load_site)
Produces:  data/coverage_diagnostic.json

Run:  python scripts/diagnose_coverage.py
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import time

import numpy as np

import hl_core as hlc

DATA = hlc.DATA
ROOT = os.path.dirname(DATA)

# mirrored from build_viewshed.py — NOT redefined behaviour, just the same settings so the
# diagnostic describes the run that actually produced svf_deck
N_AZ = 360
MAX_R = 350.0
SPACING = 8.0
CMP_N_AZ = 180        # compare_corridors.py's own azimuthal resolution — the 0.808 vs
                      # 0.978 headline was computed at 180, not at build_viewshed's 360
EYE_DECK = hlc.EYE_DECK
PARK_YEAR = 2009


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def bbox_local(meta):
    """The fetched bbox, in the same local metres the geometry uses.

    fetch_nyc_data.py and hl_core share the projection: x = (lon-lon0)*111320*cos(lat0),
    z = (lat-lat0)*110574, with lat0/lon0 = origin_latlon = the bbox centre.
    """
    lat_min, lon_min, lat_max, lon_max = meta["bbox_latlon"]
    lat0, lon0 = meta["origin_latlon"]
    mlon = 111_320.0 * math.cos(math.radians(lat0))
    return {
        "x_min": (lon_min - lon0) * mlon,
        "x_max": (lon_max - lon0) * mlon,
        "z_min": (lat_min - lat0) * hlc.M_PER_DEG_LAT,
        "z_max": (lat_max - lat0) * hlc.M_PER_DEG_LAT,
    }


def covered_run(px, pz, dx, dz, bb, max_r):
    """Distance along the ray for which it is still inside the fetched bbox, capped at
    max_r. 0.0 if the station itself is outside the bbox — there is then no covered run at
    all from the origin outward, whatever the ray does later."""
    if not (bb["x_min"] <= px <= bb["x_max"] and bb["z_min"] <= pz <= bb["z_max"]):
        return 0.0
    t = max_r
    if abs(dx) > 1e-12:
        t = min(t, ((bb["x_max"] if dx > 0 else bb["x_min"]) - px) / dx)
    if abs(dz) > 1e-12:
        t = min(t, ((bb["z_max"] if dz > 0 else bb["z_min"]) - pz) / dz)
    return max(0.0, float(t))


def analyse_corridor(site, n_az, max_r=MAX_R, spacing=SPACING):
    """Per-station coverage rows for any site in the schema. Returns (rows, bbox, n_out)."""
    bld = site.buildings
    bb = bbox_local(site.meta)
    samples = site.corridor.samples(spacing)
    ang = np.linspace(0, 2 * math.pi, n_az, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], axis=1)   # build_viewshed's convention

    rows, n_outside = [], 0
    for (pt, s) in samples:
        px, pz = float(pt[0]), float(pt[1])
        inside = (bb["x_min"] <= px <= bb["x_max"] and bb["z_min"] <= pz <= bb["z_max"])
        if not inside:
            n_outside += 1

        edges = hlc.edges_for(bld, px, pz, max_r)
        n_clear = n_trunc = 0
        exit_d = []
        for k in range(n_az):
            dx, dz = float(dirs[k, 0]), float(dirs[k, 1])
            if edges is None:
                clear = True
            else:
                _, hit = hlc.ray_uv(edges, px, pz, dx, dz, max_r)
                clear = not bool(hit.any())
            if not clear:
                continue
            n_clear += 1
            run = covered_run(px, pz, dx, dz, bb, max_r)
            if run < max_r - 1e-9:
                n_trunc += 1
                exit_d.append(run)

        rows.append({
            "s_m": round(float(s), 1),
            "x": round(px, 2), "z": round(pz, 2),
            "station_inside_bbox": bool(inside),
            "n_azimuth": n_az,
            "n_clear": n_clear,
            "n_clear_bbox_truncated": n_trunc,
            "n_clear_fully_covered": n_clear - n_trunc,
            "frac_clear": round(n_clear / n_az, 4),
            "frac_truncated_of_clear": round(n_trunc / n_clear, 4) if n_clear else None,
            "frac_truncated_of_all_azimuths": round(n_trunc / n_az, 4),
            "mean_bbox_exit_m": round(float(np.mean(exit_d)), 1) if exit_d else None,
            "min_bbox_exit_m": round(float(np.min(exit_d)), 1) if exit_d else None,
        })
    return rows, bb, n_outside


def _summarise(rows, bb, n_out, label, footprints, n_bld):
    ft = np.array([r["frac_truncated_of_all_azimuths"] for r in rows])
    fc = np.array([r["frac_clear"] for r in rows])
    ftc = np.array([r["frac_truncated_of_clear"] or 0.0 for r in rows])
    half_x = 0.5 * (bb["x_max"] - bb["x_min"])
    half_z = 0.5 * (bb["z_max"] - bb["z_min"])
    xs = [r["x"] for r in rows]
    zs = [r["z"] for r in rows]
    return {
        "label": label,
        "footprints": footprints,
        "n_buildings": n_bld,
        "n_stations": len(rows),
        "n_azimuth": rows[0]["n_azimuth"],
        "n_stations_outside_bbox": n_out,
        "bbox_half_spans_m": {"east_west": round(half_x, 1),
                              "north_south": round(half_z, 1)},
        "corridor_margins_m": {
            "west": round(min(xs) - bb["x_min"], 1),
            "east": round(bb["x_max"] - max(xs), 1),
            "south": round(min(zs) - bb["z_min"], 1),
            "north": round(bb["z_max"] - max(zs), 1),
            "note": "clearance from the extreme station to each bbox wall. Any value "
                    "below MAX_R means rays in that direction are fetch-limited.",
        },
        "frac_truncated_of_all_azimuths": {
            "mean": round(float(ft.mean()), 4),
            "median": round(float(np.median(ft)), 4),
            "p10": round(float(np.percentile(ft, 10)), 4),
            "p25": round(float(np.percentile(ft, 25)), 4),
            "p75": round(float(np.percentile(ft, 75)), 4),
            "p90": round(float(np.percentile(ft, 90)), 4),
            "max": round(float(ft.max()), 4),
        },
        "mean_frac_clear": round(float(fc.mean()), 4),
        "mean_frac_truncated_of_clear": round(float(ftc.mean()), 4),
        "n_stations_zero_truncation": int((ft == 0).sum()),
        "n_stations_over_25pct_truncated": int((ft > 0.25).sum()),
    }


def main():
    t0 = time.time()
    site = hlc.load_site()
    meta = site.meta
    bb = bbox_local(meta)

    half_x = 0.5 * (bb["x_max"] - bb["x_min"])
    half_z = 0.5 * (bb["z_max"] - bb["z_min"])
    print(f"bbox local: x [{bb['x_min']:.1f}, {bb['x_max']:.1f}]  "
          f"z [{bb['z_min']:.1f}, {bb['z_max']:.1f}]")
    print(f"  half-spans  E-W {half_x:.1f} m   N-S {half_z:.1f} m   vs MAX_R {MAX_R:.0f} m")

    rows, _, n_outside = analyse_corridor(site, N_AZ)
    samples = site.corridor.samples(SPACING)

    # ---- joins for reporting: svf_deck / deficit come from the engine outputs ----------
    vs = json.load(open(os.path.join(DATA, "highline_viewshed.json"), encoding="utf-8"))
    vmap = {round(p["s_m"], 1): p for p in vs["points"]}
    vkeys = sorted(vmap)
    env = json.load(open(os.path.join(DATA, "envelope.json"), encoding="utf-8"))
    emap = {round(p["s_m"], 1): p for p in env["points"]}
    ekeys = sorted(emap)

    def nearest(keys, mapping, s):
        return mapping[min(keys, key=lambda k: abs(k - s))]

    for r in rows:
        v = nearest(vkeys, vmap, r["s_m"])
        e = nearest(ekeys, emap, r["s_m"])
        r["svf_deck"] = v.get("svf_deck")
        r["svf_prepark"] = v.get("svf_prepark")
        r["deficit_svf"] = e.get("deficit_svf")

    ft_all = np.array([r["frac_truncated_of_all_azimuths"] for r in rows])
    fc = np.array([r["frac_clear"] for r in rows])
    ft_clear = np.array([r["frac_truncated_of_clear"] or 0.0 for r in rows])
    svf = np.array([r["svf_deck"] for r in rows], dtype=float)

    worst = sorted(rows, key=lambda r: -r["frac_truncated_of_all_azimuths"])[:10]

    # ---- the ten stations whose svf is unmeasured, not measured ----------------------
    unmeasured = []
    for i, r in enumerate(rows):
        if r["station_inside_bbox"]:
            continue
        unmeasured.append({
            "station_index": i,
            "s_m": r["s_m"], "x": r["x"], "z": r["z"],
            "svf_deck_reported": r["svf_deck"],
            "svf_prepark_reported": r["svf_prepark"],
            "deficit_svf_reported": r["deficit_svf"],
            "frac_clear": r["frac_clear"],
            "frac_truncated_of_clear": r["frac_truncated_of_clear"],
            "bbox_exit_m": r["mean_bbox_exit_m"],
        })

    # ---- corridor comparison, at compare_corridors.py's OWN settings -----------------
    # The 0.808 vs 0.978 headline comes from compare_corridors.py at N_AZ = 180, not from
    # build_viewshed's 360. Coverage is therefore re-measured at 180 for BOTH corridors so
    # the comparison is like-for-like with the figure it is about.
    print(f"\ncomparing corridor coverage at compare_corridors' N_AZ = {CMP_N_AZ} ...")
    cmp_blocks = []
    for label, fname, svf_pub in (
            ("High Line (NYC)", "highline_footprints.json", 0.808),
            ("The 606 (Chicago)", "the606_footprints.json", 0.978)):
        s2 = hlc.load_site(os.path.join(DATA, fname))
        r2, bb2, no2 = analyse_corridor(s2, CMP_N_AZ)
        blk = _summarise(r2, bb2, no2, label, "data/" + fname, len(s2.buildings))
        blk["published_mean_svf"] = svf_pub
        cmp_blocks.append(blk)
        print("  %-20s trunc/all mean %.3f  median %.3f  max %.3f  outside-bbox %d/%d"
              % (label, blk["frac_truncated_of_all_azimuths"]["mean"],
                 blk["frac_truncated_of_all_azimuths"]["median"],
                 blk["frac_truncated_of_all_azimuths"]["max"],
                 blk["n_stations_outside_bbox"], blk["n_stations"]))

    hl_b, s6_b = cmp_blocks
    d_trunc = (s6_b["frac_truncated_of_all_azimuths"]["mean"]
               - hl_b["frac_truncated_of_all_azimuths"]["mean"])

    result = {
        "_meta": {
            "script": "scripts/diagnose_coverage.py",
            "git_commit": _git_commit(),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "purpose": "Separate 'no building within MAX_R' from 'no data beyond the "
                       "fetched bbox' in the measured sky. DIAGNOSTIC ONLY.",
            "source": ["data/highline_footprints.json", "data/highline_viewshed.json",
                       "data/envelope.json"],
            "writes": "data/coverage_diagnostic.json only. No engine, no existing "
                      "data/*.json and no hl_core primitive is modified or re-run.",
            "deterministic": True,
            "seed_note": "no stochastic step in this engine",
            "method": "For each station, cast N_AZ rays with hl_core.edges_for + "
                      "hl_core.ray_uv at the viewshed's own settings. A ray is CLEAR when "
                      "no edge is hit within MAX_R. A clear ray is BBOX-TRUNCATED when the "
                      "straight run from the station leaves the fetched bbox before "
                      "MAX_R — its clearance is bounded by the fetch, not by the site.",
            "params": {"N_AZ": N_AZ, "MAX_R": MAX_R, "SPACING": SPACING,
                       "eye_deck_m": EYE_DECK, "park_year": PARK_YEAR,
                       "mirrored_from": "scripts/build_viewshed.py"},
            "bbox_local_m": {k: round(v, 2) for k, v in bb.items()},
            "bbox_half_spans_m": {"east_west": round(half_x, 2),
                                  "north_south": round(half_z, 2)},
            "bbox_shortfall_vs_max_r_m": {
                "east_west": round(MAX_R - half_x, 2),
                "north_south": round(MAX_R - half_z, 2),
                "note": "positive means the bbox half-span is SMALLER than MAX_R, so a "
                        "station on the centreline cannot see a full 350 m in that axis "
                        "even before geometry is considered",
            },
            "corridor_overhang_m": {
                "z_min": round(bb["z_min"] - min(float(p[0][1]) for p in samples), 2),
                "z_max": round(max(float(p[0][1]) for p in samples) - bb["z_max"], 2),
                "note": "how far the deck runs beyond the fetched box at each end; "
                        "positive means stations sit outside the data entirely",
            },
            "n_stations": len(rows),
            "n_stations_outside_bbox": n_outside,
            "limitations": [
                "A truncated ray is NOT proven to be obstructed. It is unmeasured: there "
                "may or may not be a building out there. This file quantifies exposure to "
                "the question, not an answer to it.",
                "Buildings beyond the bbox are absent from BOTH svf_deck and svf_prepark, "
                "so the deficit's bias depends on the ERA of what is missing — see "
                "bias_direction.",
                "Coverage is tested against the fetch bbox only. NYC Open Data may also "
                "omit or mis-height individual structures inside the box; that is a "
                "different and unmeasured source of error.",
                "No corrected SVF is estimated here. That requires a re-fetch with a bbox "
                "of at least corridor extent + MAX_R, which is a W0 decision.",
            ],
        },
        "totals": {
            "mean_frac_clear": round(float(fc.mean()), 4),
            "mean_frac_truncated_of_all_azimuths": round(float(ft_all.mean()), 4),
            "max_frac_truncated_of_all_azimuths": round(float(ft_all.max()), 4),
            "mean_frac_truncated_of_clear": round(float(ft_clear.mean()), 4),
            "n_stations_with_any_truncation": int((ft_all > 0).sum()),
            "n_stations_over_10pct_truncated": int((ft_all > 0.10).sum()),
            "n_stations_over_25pct_truncated": int((ft_all > 0.25).sum()),
            "mean_svf_deck": round(float(svf.mean()), 4),
            "correlation_truncation_vs_svf_deck": round(
                float(np.corrcoef(ft_all, svf)[0, 1]), 4),
        },
        "worst_10_stations": [
            {k: w[k] for k in ("s_m", "x", "z", "station_inside_bbox", "frac_clear",
                               "frac_truncated_of_all_azimuths",
                               "frac_truncated_of_clear", "mean_bbox_exit_m",
                               "min_bbox_exit_m", "svf_deck", "svf_prepark",
                               "deficit_svf")}
            for w in worst
        ],
        "bias_direction": {
            "svf_deck": {
                "direction": "BIASED HIGH (reads more open than the site is)",
                "why": "svf = 1 - mean(sin^2(beta)) over azimuths. A bbox-truncated ray "
                       "contributes beta = 0, i.e. full sky, because no edge was found. "
                       "Any building that exists beyond the box but within MAX_R would "
                       "raise beta on that azimuth and lower svf. The error is therefore "
                       "one-signed: it can only have made the deck look MORE open.",
                "magnitude_bound": "The fraction of azimuths that are clear-and-truncated "
                                   "is the share of the SVF integral resting on unfetched "
                                   "space. It is an UPPER bound on the error, reached only "
                                   "if every truncated azimuth actually has an occluder "
                                   "beyond the box; the true bias is somewhere between 0 "
                                   "and that share times the mean sin^2(beta) such an "
                                   "occluder would subtend.",
            },
            "deficit_svf": {
                "direction": "MOSTLY CANCELS; residual sign depends on the ERA of what is "
                             "missing",
                "why": "deficit = svf_prepark - svf_deck, and both terms are computed from "
                       "the same fetched set. A missing PRE-2009 building is absent from "
                       "both and cancels almost exactly. A missing POST-2009 building is "
                       "absent from svf_deck only — it would have lowered svf_deck while "
                       "leaving svf_prepark untouched — so its omission biases the deficit "
                       "LOW, understating the stolen sky.",
                "which_is_more_likely": "The post-2009 towers in this dataset cluster along "
                                        "the corridor rather than at its periphery, and "
                                        "the truncated azimuths point outward (east-west "
                                        "and past the ends). So the missing set is more "
                                        "likely to be ordinary pre-2009 fabric, which "
                                        "cancels. Treat the deficit as the more robust of "
                                        "the two figures — but not as unaffected.",
            },
            "what_this_does_NOT_say": "No corrected SVF is offered. Establishing one means "
                                      "re-fetching with a bbox of corridor extent + MAX_R "
                                      "and re-running the engines, which would move every "
                                      "number keyed off svf_deck. That is a W0 decision.",
        },
        "unmeasured_stations_presented_as_measured": {
            "what": "These stations lie OUTSIDE the fetched bbox entirely. No footprint "
                    "data exists at their own location, so every ray leaves covered space "
                    "at distance 0. build_viewshed's `edges_for` returns None there and "
                    "the engine writes svf_deck = 1.0.",
            "why_it_matters": "1.0 here is the ABSENCE OF DATA reported as a measurement "
                              "of perfectly open sky. It is the project's own `null never "
                              "0` rule inverted: a value that could not be measured is "
                              "being presented as a measured maximum. The correct value is "
                              "null with a reason.",
            "not_fixed_here": "data/highline_viewshed.json is NOT rewritten. Correcting it "
                              "means a re-fetch and a full engine re-run, which is a W0 "
                              "decision. This block records the exposure; "
                              "IMPLEMENTATION_PLAN.md W2 carries the disclosure.",
            "n_stations": len(unmeasured),
            "stations": unmeasured,
        },
        "corridor_comparison": {
            "question": "Is the 0.808 vs 0.978 headline comparing two corridors that are "
                        "comparably covered, or is one of them better fetched than the "
                        "other?",
            "measured_at": f"N_AZ = {CMP_N_AZ}, MAX_R = {MAX_R}, SPACING = {SPACING} — "
                           "compare_corridors.py's own settings, not build_viewshed's, so "
                           "this describes the run that produced the published figures.",
            "corridors": cmp_blocks,
            "delta_mean_truncation_606_minus_highline": round(d_trunc, 4),
            "verdict_note": "A corridor with MORE truncation has its SVF biased further "
                            "HIGH (more of its 'open sky' is unfetched space). If the two "
                            "differ materially, the 0.170 SVF gap between them is partly "
                            "an artefact of unequal fetch coverage, and the direction of "
                            "that artefact is set by which corridor is worse covered.",
        },
        "stations": rows,
    }

    outp = os.path.join(DATA, "coverage_diagnostic.json")
    json.dump(result, open(outp, "w", encoding="utf-8"), indent=1)
    t = result["totals"]
    print(f"\nwrote {outp}  ({len(rows)} stations, {time.time()-t0:.1f} s)")
    print(f"  stations outside the fetched bbox      : {n_outside} of {len(rows)}")
    print(f"  mean clear-ray fraction                : {t['mean_frac_clear']:.3f}")
    print(f"  mean bbox-truncated / all azimuths     : {t['mean_frac_truncated_of_all_azimuths']:.3f}")
    print(f"  mean bbox-truncated / clear rays       : {t['mean_frac_truncated_of_clear']:.3f}")
    print(f"  stations >10% / >25% truncated         : "
          f"{t['n_stations_over_10pct_truncated']} / {t['n_stations_over_25pct_truncated']}")
    print(f"  corr(truncation, svf_deck)             : "
          f"{t['correlation_truncation_vs_svf_deck']:+.3f}")
    print("\n  worst 10 stations by truncated share of all azimuths:")
    print("    %8s %7s %8s %9s %9s %8s %9s" %
          ("s_m", "inside", "clear", "trunc/all", "trunc/clr", "exit_m", "svf_deck"))
    for w in result["worst_10_stations"]:
        print("    %8.1f %7s %8.3f %9.3f %9.3f %8s %9s" %
              (w["s_m"], "yes" if w["station_inside_bbox"] else "NO",
               w["frac_clear"], w["frac_truncated_of_all_azimuths"],
               w["frac_truncated_of_clear"],
               "-" if w["mean_bbox_exit_m"] is None else "%.0f" % w["mean_bbox_exit_m"],
               w["svf_deck"]))
    return result


if __name__ == "__main__":
    main()
