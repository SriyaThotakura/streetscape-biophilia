"""validate_envelope.py — the independent recheck of the Answering Line's winter-sun
recapture (IMPLEMENTATION_PLAN.md W3.1).

`build_envelope.py` generates the canopy from the measured enclosure field and then
validates it with `_recaptured_sun`, **the same hl_core ray primitive that generated
the form**. `build_counterfactual.py` measured the equal-material uniform control (b)
with that same primitive and found the field-driven form ahead by 3.2 points
(36.8% vs 33.6%). A 3.2-point margin taken inside one instrument's own error is not
yet a finding. This script re-measures BOTH configurations with a second instrument.

What is independent, and what is deliberately identical
-------------------------------------------------------
INDEPENDENT — the measurement:
  ladybug `Sunpath` for solar position (real date/timezone/longitude, equation of
  time), and `ladybug_geometry` Ray3D/Face3D intersection for occlusion. Same
  lineage as `build_lbt.py`, which is how the diagnosis half of this project was
  validated (SVF r 0.956, winter sun r 0.993).

IDENTICAL — everything else, mirrored from build_envelope._recaptured_sun:
  sensor    the rib apex: deck centreline station displaced by the FULL reach along
            the aperture heading, at absolute height DECK_H + rib_height. No lateral
            offset, no eye-height lift. (build_envelope.py:164, :235)
  occluders the building footprint prisms ONLY — no canopy geometry, so ribs cannot
            occlude one another or themselves; no deck, parapet, planting or terrain.
            Culled by the same disc test at MAX_R = 350 m, and intersections beyond
            350 m horizontal are rejected to mirror ray_uv's `t <= max_r`.
  blocking  a timestep is recovered iff every occluder top is STRICTLY below the sun
            ray at that occluder's distance. LB's Face3D spans z in [0, h], so a hit
            means h >= ray_z — the exact complement of hl_core's `top < ray_y`.
  reduction unweighted mean of per-station fractions (not pooled timesteps).
  mask      the same enclosed stations, deficit_svf > 0.05, strict. n is DERIVED from
            the data, not fixed: it was 56 before the 2026-08-15 re-fetch recovered
            the missing footprints, and is 159 after.

Two sun models, reported side by side and NEVER blended
--------------------------------------------------------
  lb_sunpath        ladybug Sunpath, Dec 21, 10-min cadence, tz -5, is_during_day.
                    56 timesteps. THE HEADLINE — a genuinely independent instrument.
  hl_core_vectors   hl_core.sun_path(355)'s own 53 vectors cast through
                    ladybug_geometry. Isolates the ray/occlusion engine with the sun
                    model held shared, so any movement can be attributed.

The two configurations
----------------------
  1. field_driven           rebuilt exactly from build_envelope's generator (unrounded
                            apex, as the engine casts it), verified against envelope.json
  2. uniform_equal_member   control (b) from build_counterfactual: the uniform drive
                            re-solved by the same bisection to the same 2,408.5 m of
                            member, verified against counterfactual.json

Consumes:  data/envelope.json, data/counterfactual.json,
           data/highline_footprints.json via hl_core.load_site
Produces:  data/envelope_validation.json

Nothing in build_envelope.py, build_counterfactual.py, build_lbt.py or hl_core.py is
modified; every generator and the hand-rolled measurement are reused by import.

Run:  python scripts/validate_envelope.py
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time

import numpy as np

import hl_core as hl
import build_envelope as be
import build_counterfactual as bc
from build_rib_schedule import _member3d

from ladybug.location import Location
from ladybug.sunpath import Sunpath
from ladybug_geometry.geometry3d.pointvector import Point3D, Vector3D
from ladybug_geometry.geometry3d.ray import Ray3D
from ladybug_geometry.geometry3d.face import Face3D

DATA = hl.DATA
ROOT = os.path.dirname(DATA)

MAX_R = be.MAX_R                 # 350.0 — the same search radius the engine uses
ENCLOSED_DEFICIT = bc.ENCLOSED_DEFICIT   # 0.05, strict >
WINTER_MONTH_DAY = (12, 21)      # the calendar date hl_core's day-of-year 355 stands for
SUN_STEP_MIN = 10                # matches hl_core's dt_h = 1/6 and build_lbt's cadence
TZ = -5                          # matches build_lbt.py
LON = -74.005                    # origin_latlon longitude; hl_core has no longitude at all
LAT_ORIGIN = 40.7475             # data/highline_footprints.json metadata.origin_latlon
LAT_HLCORE = hl.LAT              # 40.7409, hard-coded in hl_core
EPS = 1e-9

BOOTSTRAP_N = 20_000             # paired-resample count for the delta's interval
BOOTSTRAP_SEED = 42              # portfolio convention; each instrument gets a fresh
                                 # default_rng(42), so a block is reproducible on its own
                                 # and does not depend on the order the blocks are computed


# ─────────────────────────────────────────────────────────────────────────────
# PRE-REGISTERED PREDICTION for configuration (a) — written before (a) was ever
# measured under Ladybug, and deliberately falsifiable.
#
# The first run (field-driven + control b only) found the hand-rolled caster
# SHAPE-DEPENDENTLY biased: it deflated by -3.99 pts on the field-driven canopy but
# only -2.69 pts on the flat equal-material control, i.e. it is more generous to
# taller, further-reaching geometry. If that bias model is right and monotone in
# height/reach, then (a) — 7.00 m tall with 5.52 m of reach at EVERY station, the
# tallest and furthest-reaching configuration in the study — must deflate MORE than
# the field-driven form, whose ribs average 1.99 m / 0.47 m.
#
# This is recorded here so the outcome cannot be reverse-fitted. A failure is a
# finding ABOUT THE BIAS MODEL, not a nuisance: it would mean the deflation is not
# monotone in reach and that the field/control gap had some other cause.
# ─────────────────────────────────────────────────────────────────────────────
PREDICTION_A = {
    "registered": "before configuration (a) was measured under either Ladybug sun model",
    "basis": "the shape-dependent instrument bias measured in the previous run: the "
             "hand-rolled caster deflated -3.99 pts on the field-driven canopy vs -2.69 "
             "pts on the flat equal-material control (b), and its per-station error was "
             "RMSE 0.130 on the field-driven form vs 0.091 on the control.",
    "reasoning": "if that bias is monotone in rib height and reach, then (a) — uniform "
                 "7.00 m height and 5.524 m reach at every station, the tallest and "
                 "furthest-reaching configuration in the study, against the field-driven "
                 "canopy's 1.99 m / 0.47 m means — must lose MORE to the independent "
                 "instrument than the field-driven form does.",
    "predicted_ordering": "deflation_a < deflation_field_driven < deflation_control_b "
                          "(signed points, all expected negative) — i.e. |deflation| "
                          "largest for (a), smallest for the flat control.",
    "predicted_deflation_a_pts": "more negative than -3.99",
    "falsifies_bias_model_if": "(a) deflates LESS than the field-driven form. That would "
                               "mean the deflation is not monotone in height/reach and "
                               "that the field-vs-control gap measured last run had some "
                               "other cause — a finding about the bias model, to be "
                               "reported as such and not explained away.",
    "outcome": None,             # filled in below, after measurement
}


# ─────────────────────────────────────────────────────────────────────────────
# provenance
# ─────────────────────────────────────────────────────────────────────────────
def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def _rnd(x, n=4):
    """Round, but keep None as None. A value that could not be computed stays null —
    0.0 would claim a measurement that was never made."""
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, n)


def _pearson(a, b):
    """(r, reason_if_undefined). Undefined -> None, never 0.0."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 3:
        return None, f"fewer than 3 paired stations (n={int(m.sum())})"
    if a[m].std() == 0.0 or b[m].std() == 0.0:
        return None, "zero variance in one series — correlation undefined, not zero"
    return float(np.corrcoef(a[m], b[m])[0, 1]), None


def _bootstrap_paired(d, n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED):
    """Non-parametric bootstrap over the PAIRED per-station differences (field minus
    control), which is what carries the claim — resampling stations, not timesteps.
    Returns points (x100), null with a reason when it cannot be computed."""
    d = np.asarray(d, float)
    d = d[~np.isnan(d)]
    if len(d) < 3:
        return {"point_estimate_pts": None, "ci95_low_pts": None, "ci95_high_pts": None,
                "frac_resamples_le_zero": None, "excludes_zero": None,
                "null_reason": f"fewer than 3 paired stations (n={len(d)})"}
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, len(d), size=(n, len(d)))].mean(axis=1) * 100.0
    lo, hi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    return {
        "n_resamples": n, "seed": seed, "n_stations": int(len(d)),
        "point_estimate_pts": _rnd(float(d.mean()) * 100.0, 3),
        "ci95_low_pts": _rnd(lo, 2), "ci95_high_pts": _rnd(hi, 2),
        "frac_resamples_le_zero": _rnd(float((means <= 0.0).mean()), 4),
        "excludes_zero": bool(lo > 0.0),
        "null_reason": None,
    }


def _win_tie_loss(field, control):
    """Per-station outcome of (field vs control), and the distinction the mean hides:
    a tie at 0.0 is both canopies failing, a tie above 0.0 is genuine parity."""
    a, b = np.asarray(field, float), np.asarray(control, float)
    d = a - b
    tie = np.abs(d) <= EPS
    return {
        "n_stations": int(len(d)),
        "n_field_ahead": int((d > EPS).sum()),
        "n_tied": int(tie.sum()),
        "n_control_ahead": int((d < -EPS).sum()),
        "n_tied_at_zero": int((tie & (a <= EPS) & (b <= EPS)).sum()),
        "n_tied_above_zero": int((tie & (a > EPS)).sum()),
        "n_tied_at_full_recovery": int((tie & (a >= 1.0 - EPS)).sum()),
        "n_both_zero_recapture": int(((a <= EPS) & (b <= EPS)).sum()),
        "note": "tolerance 1e-9. n_tied_at_zero is both canopies recovering nothing — the "
                "deep-canyon cores a 7 m canopy cannot reach; those stations enter the mean "
                "but cannot separate the two configurations. n_tied_above_zero is real "
                "parity (n_tied_at_full_recovery is its fully-recovered subset).",
    }


def _serviceable_mask(field, control, eps=EPS):
    """The SECONDARY population: enclosed stations where at least one canopy recovers a
    non-zero fraction UNDER THE INSTRUMENT IN QUESTION.

    Defined once, by that rule, and not tuned. The mask is instrument-specific by
    construction — Ladybug and the hand-rolled caster disagree about which stations are
    inert, and forcing one instrument's mask onto another would import its errors.
    """
    a, b = np.asarray(field, float), np.asarray(control, float)
    return (a > eps) | (b > eps)


def _serviceable_block(field_full, control_full):
    """Recompute the paired delta and the bootstrap over the serviceable cut.

    `field_full` / `control_full` are already restricted to the enclosed stations, so
    this is a cut WITHIN the primary population, never a different one. The full-
    population figures are embedded in the returned block: the reporting rule is that
    the serviceable numbers are never quoted without the full-population numbers beside them,
    and the file enforces it by carrying both in the same object.
    """
    a, b = np.asarray(field_full, float), np.asarray(control_full, float)
    m = _serviceable_mask(a, b)
    fs, cs = a[m], b[m]
    d_full, d_cut = a - b, fs - cs
    return {
        "population": "serviceable (SECONDARY — never report without the full-population "
                      "figures carried alongside in this same block)",
        "definition": "enclosed stations (deficit_svf > 0.05, the primary mask) where at "
                      "least one of the two canopies recovers a non-zero fraction under "
                      "THIS instrument. Stations where both recover exactly nothing are "
                      "excluded: they enter the full-population mean but cannot separate "
                      "the two configurations.",
        "eps": EPS,
        "n_serviceable": int(m.sum()),
        "n_excluded_both_zero": int((~m).sum()),
        "n_full_population": int(len(a)),
        "field_driven": {
            "mean_recaptured_serviceable": _rnd(float(fs.mean()), 4) if m.any() else None,
            "mean_recaptured_full_population": _rnd(float(a.mean()), 4),
        },
        "uniform_equal_member_b": {
            "mean_recaptured_serviceable": _rnd(float(cs.mean()), 4) if m.any() else None,
            "mean_recaptured_full_population": _rnd(float(b.mean()), 4),
        },
        "paired_delta": {
            "serviceable_pts": _rnd(float(d_cut.mean()) * 100, 3) if m.any() else None,
            "full_population_pts": _rnd(float(d_full.mean()) * 100, 3),
            "ratio_serviceable_over_full": _rnd(
                float(d_cut.mean()) / float(d_full.mean()), 3)
            if m.any() and abs(float(d_full.mean())) > 1e-12 else None,
            "note": "the two deltas differ only by the denominator — the excluded "
                    "stations contribute exactly 0 to the full-population sum, so the "
                    "serviceable delta is the same total spread over fewer stations.",
        },
        "win_tie_loss": _win_tie_loss(fs, cs) if m.any() else None,
        "bootstrap": _bootstrap_paired(d_cut),
        "bootstrap_full_population": _bootstrap_paired(d_full),
    }


def _rmse(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() == 0:
        return None
    return float(np.sqrt(np.mean((a[m] - b[m]) ** 2)))


# ─────────────────────────────────────────────────────────────────────────────
# the Ladybug measurement — build_lbt.py's lineage, build_envelope's model
# ─────────────────────────────────────────────────────────────────────────────
class Context:
    """Building prisms as ladybug_geometry faces, plus the arrays needed for the
    exact culls. Ladybug coords are (x=east, y=north, z=up); hl_core's ground plane
    is (x=east, z=north), so a world point (x, y_up, z_north) maps to Point3D(x, z, y)."""

    def __init__(self, buildings):
        self.b = buildings
        self.faces = [self._prism(b) for b in buildings]
        self.cx = np.array([b.c[0] for b in buildings])
        self.cz = np.array([b.c[1] for b in buildings])
        self.rad = np.array([b.rad for b in buildings])
        self.h = np.array([b.h for b in buildings])
        self.n_faces = sum(len(f) for f in self.faces)

    @staticmethod
    def _prism(b):
        """Walls + roof, identical to build_lbt.building_faces."""
        p, h, out = b.poly, b.h, []
        for i in range(len(p) - 1):
            x0, y0 = float(p[i][0]), float(p[i][1])
            x1, y1 = float(p[i + 1][0]), float(p[i + 1][1])
            out.append(Face3D([Point3D(x0, y0, 0), Point3D(x1, y1, 0),
                               Point3D(x1, y1, h), Point3D(x0, y0, h)]))
        out.append(Face3D([Point3D(float(x), float(y), h) for x, y in p[:-1]]))
        return out


def lb_recapture(ctx, apex, sun_vecs):
    """Ladybug re-measurement of build_envelope._recaptured_sun at one rib apex.

    Returns (fraction, n_clear, n_total, no_occluders). `no_occluders` mirrors the
    engine's `edges is None` early return — no building disc within MAX_R at all, so
    the 1.0 comes back without a single ray being cast.
    """
    ax, ay, az = apex[0], apex[1], apex[2]          # world x(east), y(up), z(north)

    # the engine's occluder set, exactly: hl_core.edges_for's disc test, no height filter
    disc = (np.hypot(ctx.cx - ax, ctx.cz - az) - ctx.rad) <= MAX_R
    if not disc.any():
        return 1.0, len(sun_vecs), len(sun_vecs), True

    # exact cull: the ray only ascends from ay, so a prism no taller than ay can be
    # intersected by neither its walls (z in [0,h]) nor its roof (z = h).
    cand = np.where(disc & (ctx.h > ay))[0]
    if len(cand) == 0:
        return 1.0, len(sun_vecs), len(sun_vecs), False

    wx = ctx.cx[cand] - ax
    wz = ctx.cz[cand] - az
    crad = ctx.rad[cand]
    origin = Point3D(ax, az, ay)

    clear = 0
    for v in sun_vecs:
        hx, hz = v.x, v.y                           # horizontal (east, north) of the sun vector
        L = math.hypot(hx, hz)
        if L <= EPS:                                # sun at the zenith; cannot happen in winter
            clear += 1
            continue
        hx /= L; hz /= L
        # exact half-line/disc cull — a prism can only block if the ray line passes
        # within its bounding radius and it is not entirely behind the apex
        along = wx * hx + wz * hz
        perp = np.abs(wx * hz - wz * hx)
        sub = cand[(perp <= crad) & (along >= -crad)]
        if len(sub) == 0:
            clear += 1
            continue
        ray = Ray3D(origin, v)
        blocked = False
        for bi in sub:
            for f in ctx.faces[bi]:
                ip = f.intersect_line_ray(ray)
                if ip is None:
                    continue
                # mirror ray_uv's window: forward hits only, horizontal t <= MAX_R
                t = math.hypot(ip.x - ax, ip.y - az)
                if 1e-6 < t <= MAX_R + EPS:
                    blocked = True
                    break
            if blocked:
                break
        if not blocked:
            clear += 1
    return clear / len(sun_vecs), clear, len(sun_vecs), False


# ─────────────────────────────────────────────────────────────────────────────
# the two sun models
# ─────────────────────────────────────────────────────────────────────────────
def sun_lb(lat, lon=LON, tz=TZ, step_min=SUN_STEP_MIN):
    """Option 1 — ladybug Sunpath's own solar geometry. build_lbt.py's method."""
    loc = Location("High Line", latitude=lat, longitude=lon, time_zone=tz)
    sp = Sunpath.from_location(loc)
    mo, dy = WINTER_MONTH_DAY
    vecs, alts = [], []
    for m in range(0, 24 * 60, step_min):
        s = sp.calculate_sun(mo, dy, m / 60.0)
        if s.is_during_day:
            vecs.append(s.sun_vector.reverse())     # from the point toward the sun
            alts.append(s.altitude)
    return vecs, alts


def sun_hlcore():
    """Option 2 — hl_core.sun_path(355)'s own 53 vectors, cast through
    ladybug_geometry. The sun model is held shared with the engine on purpose, so any
    movement isolates the ray/occlusion engine."""
    el, e, n = hl.sun_path(be.WINTER)
    vecs = [Vector3D(float(ei) * math.cos(float(li)),
                     float(ni) * math.cos(float(li)),
                     math.sin(float(li)))
            for li, ei, ni in zip(el, e, n)]
    return vecs, [math.degrees(float(x)) for x in el]


# ─────────────────────────────────────────────────────────────────────────────
# rebuilding the two configurations exactly
# ─────────────────────────────────────────────────────────────────────────────
def rebuild_field_driven(site, samples):
    """Re-run build_envelope's generator to recover the UNROUNDED apexes it cast from
    (envelope.json stores them at 2 dp). Every step is build_envelope's own function."""
    buildings = site.buildings
    sun_el, sun_e, sun_n = be._sun_dirs()
    vs = json.load(open(os.path.join(DATA, "highline_viewshed.json"), encoding="utf-8"))
    vpts = {round(p["s_m"], 1): p for p in vs["points"]}
    vkeys = np.array(sorted(vpts))

    apexes, heights, reaches, defs, ribs = [], [], [], [], []
    for i, (xz, s) in enumerate(samples):
        px, pz = float(xz[0]), float(xz[1])
        v = vpts[vkeys[int(np.argmin(np.abs(vkeys - s)))]]
        deficit = max(0.0, v["svf_prepark"] - v["svf_deck"])
        az, alt = be._horizon(buildings, px, pz)
        ap_az, ap_alt, directionality = be._aperture(az, alt, sun_el, sun_e, sun_n)
        tx, tz = be._tangent(samples, i)
        poly, apex, rib_h, reach = be._rib(px, pz, tx, tz, deficit / 0.35,
                                           ap_az, ap_alt, directionality, v["svf_deck"])
        apexes.append(apex); heights.append(rib_h); reaches.append(reach)
        defs.append(round(deficit, 4))
        ribs.append([[round(c, 2) for c in pt] for pt in poly])
    return (np.array(apexes), np.array(heights), np.array(reaches),
            np.array(defs), ribs)


def rebuild_uniform_a(site, samples, va):
    """Control (a): the 'equal max height' canopy — 7.00 m rib at every station, reach
    fixed, heading fixed north. counterfactual.json records (a)'s MEASUREMENT but not its
    rib polylines, so the geometry is regenerated from the stored `uniform_drive` and
    `heading_deg` with build_counterfactual._uniform_canopy, imported unchanged and run
    with measure=False (no recapture cast during the rebuild).

    This is byte-for-byte the same regeneration path build_structure.py's
    `--source counterfactual_a` uses, including the same rebuild gate, so the geometry
    measured here and the geometry sized to 188.6 t there are the same geometry.
    Aborts if the rebuild does not reproduce the stored height / reach / member length.
    """
    drive = float(va["uniform_drive"])
    heading = math.radians(float(va["heading_deg"]))
    c = bc._uniform_canopy(site.buildings, samples, drive, heading, None, measure=False)
    got_len = float(c["mem_len"].sum())
    dev = {
        "rib_height_m": abs(float(c["rib_height_m"]) - float(va["rib_height_m"])),
        "reach_m": abs(float(c["reach_m"]) - float(va["reach_m"])),
        "total_member_length_m": abs(got_len - float(va["total_member_length_m"])),
    }
    if (dev["rib_height_m"] > 5e-4 or dev["reach_m"] > 5e-4
            or dev["total_member_length_m"] > 0.05):
        raise SystemExit(f"CONFIGURATION (a) REBUILD MISMATCH vs counterfactual.json: {dev}")
    return (np.array(c["apexes"]), float(c["rib_height_m"]), float(c["reach_m"]),
            drive, got_len, dev)


def rebuild_uniform_b(site, samples, target_member_m):
    """Control (b): re-solve the uniform drive with build_counterfactual's own
    bisection so total member length matches the field-driven canopy, then generate
    with the unchanged rib generator. No measurement cast here."""
    drive, got, clamp = bc._solve_drive_for_length(
        site.buildings, samples, target_member_m, bc.HEADING_NORTH)
    c = bc._uniform_canopy(site.buildings, samples, drive, bc.HEADING_NORTH,
                           None, measure=False)
    return (np.array(c["apexes"]), float(c["rib_height_m"]), float(c["reach_m"]),
            drive, float(c["mem_len"].sum()), clamp)


# ─────────────────────────────────────────────────────────────────────────────
def main():
    t_start = time.time()
    site = hl.load_site()
    samples = site.corridor.samples(be.SPACING)
    ctx = Context(site.buildings)
    print(f"site: {len(site.buildings)} buildings, {ctx.n_faces} faces, "
          f"{len(samples)} stations")

    env = json.load(open(os.path.join(DATA, "envelope.json"), encoding="utf-8"))
    cf = json.load(open(os.path.join(DATA, "counterfactual.json"), encoding="utf-8"))
    epts = env["points"]
    if len(epts) != len(samples):
        raise SystemExit(f"station mismatch: envelope.json {len(epts)} vs "
                         f"corridor resample {len(samples)}")

    # ---- configuration 1: the field-driven canopy --------------------------------
    print("rebuilding configuration 1 (field-driven) from build_envelope's generator ...")
    apex_f, h_f, reach_f, defs, ribs_f = rebuild_field_driven(site, samples)
    stored_apex = np.array([p["apex"] for p in epts])
    apex_dev = float(np.max(np.abs(apex_f - stored_apex)))
    s_m = np.array([p["s_m"] for p in epts])
    enclosed = defs > ENCLOSED_DEFICIT
    n_enc = int(enclosed.sum())
    print(f"  apex rebuild max deviation vs envelope.json (stored at 2 dp): {apex_dev:.4f} m")
    print(f"  enclosed stations (deficit > {ENCLOSED_DEFICIT}): {n_enc} of {len(epts)}")

    # ---- configuration 2: control (b), equal member length ------------------------
    target = float(np.sum([_member3d(p["rib"])[0].sum() for p in epts]))
    print(f"rebuilding configuration 2 (uniform, equal member length {target:.1f} m) ...")
    apex_b, h_b, reach_b, drive_b, got_b, clamp_b = rebuild_uniform_b(site, samples, target)
    cfb = cf["variants"]["b_equal_member_length"]
    print(f"  solved drive {drive_b:.6f} (counterfactual.json {cfb['uniform_drive']:.6f})  "
          f"height {h_b:.3f} m  reach {reach_b:.3f} m")

    # ---- configuration 3: control (a), equal MAX HEIGHT (7.00 m everywhere) --------
    cfa = cf["variants"]["a_equal_max_height"]
    print("rebuilding configuration 3 (uniform, equal max height 7.00 m) ...")
    apex_a, h_a, reach_a, drive_a, got_a, dev_a = rebuild_uniform_a(site, samples, cfa)
    print(f"  drive {drive_a:.6f}  height {h_a:.3f} m  reach {reach_a:.3f} m  "
          f"member {got_a:.1f} m  — rebuild gate PASS (max dev "
          f"{max(dev_a.values()):.2e})")

    # ---- check 3: the hand-rolled baseline, recomputed UNROUNDED on both sides -----
    print("recomputing the hand-rolled readback unrounded on both configurations ...")
    hl_sun = hl.sun_path(be.WINTER)
    hr_f = np.array([be._recaptured_sun(site.buildings, a, *hl_sun) for a in apex_f])
    hr_b = np.array([be._recaptured_sun(site.buildings, a, *hl_sun) for a in apex_b])
    hr_a = np.array([be._recaptured_sun(site.buildings, a, *hl_sun) for a in apex_a])
    stored_f = np.array([p["recaptured_winter_sun_frac"] for p in epts])
    stored_b = np.array([p["b_recaptured_winter_sun_frac"] for p in cf["points"]])
    stored_a = np.array([p["a_recaptured_winter_sun_frac"] for p in cf["points"]])
    hr_dev_f = float(np.max(np.abs(hr_f - stored_f)))
    hr_dev_b = float(np.max(np.abs(hr_b - stored_b)))
    hr_dev_a = float(np.max(np.abs(hr_a - stored_a)))

    hr_mean_f = float(hr_f[enclosed].mean())
    hr_mean_b = float(hr_b[enclosed].mean())
    hr_mean_a = float(hr_a[enclosed].mean())
    hr_delta_unrounded = hr_mean_f - hr_mean_b
    pub_delta = (cf["baseline_field_driven"]["mean_recaptured_winter_sun_frac_enclosed"]
                 - cfb["mean_recaptured_winter_sun_frac_enclosed"])

    # ---- check 1: the no-occluder early return -----------------------------------
    def no_occ_stations(apexes):
        idx = []
        for i, a in enumerate(apexes):
            if not ((np.hypot(ctx.cx - a[0], ctx.cz - a[2]) - ctx.rad) <= MAX_R).any():
                idx.append(i)
        return idx

    no_occ_f, no_occ_b = no_occ_stations(apex_f), no_occ_stations(apex_b)
    no_occ_a = no_occ_stations(apex_a)

    # ---- check 2: latitude sensitivity of the Ladybug sun model -------------------
    print("check 2: Ladybug sun at both latitudes ...")
    lat_runs = {}
    for tag, lat in (("origin_latlon_40.7475", LAT_ORIGIN), ("hl_core_40.7409", LAT_HLCORE)):
        vecs, alts = sun_lb(lat)
        rf = np.array([lb_recapture(ctx, a, vecs)[0] for a in apex_f])
        rb = np.array([lb_recapture(ctx, a, vecs)[0] for a in apex_b])
        ra = np.array([lb_recapture(ctx, a, vecs)[0] for a in apex_a])
        lat_runs[tag] = {"lat": lat, "n_timesteps": len(vecs),
                         "alt_deg_min": _rnd(min(alts), 3), "alt_deg_max": _rnd(max(alts), 3),
                         "mean_field": float(rf[enclosed].mean()),
                         "mean_uniform_b": float(rb[enclosed].mean()),
                         "paired_delta": float(rf[enclosed].mean() - rb[enclosed].mean()),
                         "mean_uniform_a": float(ra[enclosed].mean()),
                         "paired_delta_field_vs_a": float(rf[enclosed].mean()
                                                          - ra[enclosed].mean()),
                         "_rf": rf, "_rb": rb, "_ra": ra}
    dlat_f = abs(lat_runs["origin_latlon_40.7475"]["mean_field"]
                 - lat_runs["hl_core_40.7409"]["mean_field"]) * 100
    dlat_b = abs(lat_runs["origin_latlon_40.7475"]["mean_uniform_b"]
                 - lat_runs["hl_core_40.7409"]["mean_uniform_b"]) * 100
    print(f"  latitude shift: field {dlat_f:.4f} pts, uniform(b) {dlat_b:.4f} pts")

    # ---- the two sun models, side by side ----------------------------------------
    models = {}
    vecs_a, alts_a = sun_lb(LAT_ORIGIN)
    models["lb_sunpath"] = {
        "label": "ladybug Sunpath — independent solar geometry (HEADLINE)",
        "vecs": vecs_a, "alts": alts_a, "lat": LAT_ORIGIN,
        "rf": lat_runs["origin_latlon_40.7475"]["_rf"],
        "rb": lat_runs["origin_latlon_40.7475"]["_rb"],
        "ra": lat_runs["origin_latlon_40.7475"]["_ra"],
    }
    print("running sun model 2 (hl_core's 53 vectors through ladybug_geometry) ...")
    vecs_b_, alts_b_ = sun_hlcore()
    models["hl_core_vectors"] = {
        "label": "hl_core.sun_path(355) vectors cast through ladybug_geometry — "
                 "isolates the ray engine with the sun model held shared",
        "vecs": vecs_b_, "alts": alts_b_, "lat": LAT_HLCORE,
        "rf": np.array([lb_recapture(ctx, a, vecs_b_)[0] for a in apex_f]),
        "rb": np.array([lb_recapture(ctx, a, vecs_b_)[0] for a in apex_b]),
        "ra": np.array([lb_recapture(ctx, a, vecs_b_)[0] for a in apex_a]),
    }

    results = {}
    for key, M in models.items():
        rf, rb = M["rf"], M["rb"]
        r_f, why_f = _pearson(hr_f[enclosed], rf[enclosed])
        r_b, why_b = _pearson(hr_b[enclosed], rb[enclosed])
        d_lb = rf[enclosed] - rb[enclosed]
        d_hr = hr_f[enclosed] - hr_b[enclosed]
        sgn_lb = np.sign(np.where(np.abs(d_lb) <= EPS, 0.0, d_lb))
        sgn_hr = np.sign(np.where(np.abs(d_hr) <= EPS, 0.0, d_hr))
        results[key] = {
            "label": M["label"],
            "sun_model": {
                "n_timesteps": len(M["vecs"]),
                "latitude": M["lat"],
                "alt_deg_min": _rnd(min(M["alts"]), 3),
                "alt_deg_max": _rnd(max(M["alts"]), 3),
            },
            "field_driven": {
                "mean_recaptured_enclosed": _rnd(float(rf[enclosed].mean()), 4),
                "mean_recaptured_all": _rnd(float(rf.mean()), 4),
                "vs_handrolled_r": _rnd(r_f, 4),
                "vs_handrolled_r_null_reason": why_f,
                "vs_handrolled_rmse": _rnd(_rmse(hr_f[enclosed], rf[enclosed]), 4),
                "handrolled_mean_enclosed": _rnd(hr_mean_f, 4),
                "mean_shift_pts": _rnd((float(rf[enclosed].mean()) - hr_mean_f) * 100, 2),
            },
            "uniform_equal_member_b": {
                "mean_recaptured_enclosed": _rnd(float(rb[enclosed].mean()), 4),
                "mean_recaptured_all": _rnd(float(rb.mean()), 4),
                "vs_handrolled_r": _rnd(r_b, 4),
                "vs_handrolled_r_null_reason": why_b,
                "vs_handrolled_rmse": _rnd(_rmse(hr_b[enclosed], rb[enclosed]), 4),
                "handrolled_mean_enclosed": _rnd(hr_mean_b, 4),
                "mean_shift_pts": _rnd((float(rb[enclosed].mean()) - hr_mean_b) * 100, 2),
            },
            "paired_delta": {
                "ladybug_pts": _rnd(float(d_lb.mean()) * 100, 3),
                "handrolled_pts": _rnd(float(d_hr.mean()) * 100, 3),
                "handrolled_pts_published_rounded": _rnd(pub_delta * 100, 3),
                "delta_of_deltas_pts": _rnd((float(d_lb.mean()) - float(d_hr.mean())) * 100, 3),
                "n_stations": n_enc,
                "note": "field_driven minus uniform_equal_member_b over the same "
                        f"{n_enc} enclosed stations; a shared open-bias cancels here, "
                        "which is why both configurations were re-measured rather than "
                        "only the field-driven one.",
            },
            "sign_disagreement": {
                "n_sign_differs": int((sgn_lb != sgn_hr).sum()),
                "n_strict_flip": int(((sgn_lb * sgn_hr) < 0).sum()),
                "n_tie_mismatch": int(((sgn_lb != sgn_hr) & ((sgn_lb == 0) | (sgn_hr == 0))).sum()),
                "n_ties_ladybug": int((sgn_lb == 0).sum()),
                "n_ties_handrolled": int((sgn_hr == 0).sum()),
                "n_field_wins_ladybug": int((sgn_lb > 0).sum()),
                "n_field_wins_handrolled": int((sgn_hr > 0).sum()),
                "note": "per-station sign of (field - uniform b), tolerance 1e-9. "
                        "n_sign_differs counts every mismatch including ties; "
                        "n_strict_flip counts only stations where one instrument has "
                        "the field-driven form ahead and the other has it behind.",
            },
            "win_tie_loss": _win_tie_loss(rf[enclosed], rb[enclosed]),
            "bootstrap": _bootstrap_paired(d_lb),
        }
        # appended last: the full-population keys above are the primary result and keep their
        # order and their values untouched
        results[key]["secondary_serviceable_population"] = _serviceable_block(
            rf[enclosed], rb[enclosed])

        # ---- configuration 3, appended after everything above ---------------------
        ra = M["ra"]
        r_a, why_a = _pearson(hr_a[enclosed], ra[enclosed])
        d_fa = rf[enclosed] - ra[enclosed]
        results[key]["uniform_equal_max_height_a"] = {
            "label": "control (a) — uniform 7.00 m rib, 5.524 m reach, heading north. "
                     "The tallest and furthest-reaching configuration in the study, and "
                     "the one the published 39.8% belongs to.",
            "mean_recaptured_enclosed": _rnd(float(ra[enclosed].mean()), 4),
            "mean_recaptured_all": _rnd(float(ra.mean()), 4),
            "vs_handrolled_r": _rnd(r_a, 4),
            "vs_handrolled_r_null_reason": why_a,
            "vs_handrolled_rmse": _rnd(_rmse(hr_a[enclosed], ra[enclosed]), 4),
            "handrolled_mean_enclosed": _rnd(hr_mean_a, 4),
            "mean_shift_pts": _rnd((float(ra[enclosed].mean()) - hr_mean_a) * 100, 2),
        }
        results[key]["paired_delta_field_vs_a"] = {
            "ladybug_pts": _rnd(float(d_fa.mean()) * 100, 3),
            "handrolled_pts": _rnd((hr_mean_f - hr_mean_a) * 100, 3),
            "handrolled_pts_published_rounded": _rnd(
                (cf["baseline_field_driven"]["mean_recaptured_winter_sun_frac_enclosed"]
                 - cfa["mean_recaptured_winter_sun_frac_enclosed"]) * 100, 3),
            "delta_of_deltas_pts": _rnd(
                (float(d_fa.mean()) - (hr_mean_f - hr_mean_a)) * 100, 3),
            "n_stations": n_enc,
            "sign_note": "NEGATIVE means (a) recovers more than the field-driven canopy. "
                         "(a) spends 2.96x the sized steel to do it (63.8 t vs 188.6 t, "
                         "data/structure.json + data/structure_counterfactual.json), so "
                         "this delta is not an equal-cost comparison and must never be "
                         "quoted as one.",
        }
        results[key]["win_tie_loss_field_vs_a"] = _win_tie_loss(rf[enclosed], ra[enclosed])
        results[key]["bootstrap_field_vs_a"] = _bootstrap_paired(d_fa)

    # ---- the pre-registered prediction, scored --------------------------------------
    pred = json.loads(json.dumps(PREDICTION_A))     # copy; PREDICTION_A stays pristine
    per_instrument = {}
    for key, R in results.items():
        df = R["field_driven"]["mean_shift_pts"]
        db = R["uniform_equal_member_b"]["mean_shift_pts"]
        da = R["uniform_equal_max_height_a"]["mean_shift_pts"]
        held = (da is not None and df is not None and db is not None
                and da < df < db)
        per_instrument[key] = {
            "deflation_a_pts": da,
            "deflation_field_driven_pts": df,
            "deflation_control_b_pts": db,
            "observed_ordering": f"a {da:+.2f} · field {df:+.2f} · b {db:+.2f}",
            "predicted_ordering_held": bool(held),
            "a_deflated_more_than_field": bool(da is not None and df is not None and da < df),
            "margin_a_vs_field_pts": _rnd((da - df), 2) if (da is not None and df is not None)
            else None,
        }
    all_held = all(v["predicted_ordering_held"] for v in per_instrument.values())
    any_a_more = all(v["a_deflated_more_than_field"] for v in per_instrument.values())
    pred["outcome"] = {
        "per_instrument": per_instrument,
        "held_under_all_instruments": bool(all_held),
        "a_deflated_more_than_field_under_all_instruments": bool(any_a_more),
        "verdict": (
            "HELD — (a) deflated more than the field-driven form, which deflated more than "
            "the flat control, under every instrument. The shape-dependent bias model "
            "predicted a configuration it had never seen, and was right."
            if all_held else
            "FAILED — the predicted ordering did not hold under every instrument. The "
            "deflation is NOT simply monotone in rib height and reach, so the "
            "field-vs-control gap measured in the previous run cannot be attributed to "
            "height/reach alone. This is a finding about the bias model and is reported "
            "as one; it is not explained away."),
        "reading": "Deflation is reported as the signed shift from each configuration's own "
                   "hand-rolled mean to its Ladybug mean, in points. More negative = the "
                   "independent instrument took more away.",
    }

    # ---- per-station rows ---------------------------------------------------------
    lbA, lbB = models["lb_sunpath"], models["hl_core_vectors"]
    points = []
    for i in range(len(epts)):
        row = {
            "s_m": round(float(s_m[i]), 2),
            "deficit_svf": round(float(defs[i]), 4),
            "enclosed": bool(enclosed[i]),
            "field_rib_height_m": round(float(h_f[i]), 3),
            "field_reach_m": round(float(reach_f[i]), 3),
            "field_apex_xyz": [round(float(c), 3) for c in apex_f[i]],
            "b_apex_xyz": [round(float(c), 3) for c in apex_b[i]],
            "handrolled_field": round(float(hr_f[i]), 6),
            "handrolled_b": round(float(hr_b[i]), 6),
            "lb_sunpath_field": round(float(lbA["rf"][i]), 6),
            "lb_sunpath_b": round(float(lbA["rb"][i]), 6),
            "hl_core_vectors_field": round(float(lbB["rf"][i]), 6),
            "hl_core_vectors_b": round(float(lbB["rb"][i]), 6),
            "handrolled_field_minus_b": round(float(hr_f[i] - hr_b[i]), 6),
            "lb_sunpath_field_minus_b": round(float(lbA["rf"][i] - lbA["rb"][i]), 6),
            "no_occluders_within_350m_field": i in no_occ_f,
            "no_occluders_within_350m_b": i in no_occ_b,
            # ---- configuration (a), appended after the existing columns ----------
            "a_apex_xyz": [round(float(c), 3) for c in apex_a[i]],
            "handrolled_a": round(float(hr_a[i]), 6),
            "lb_sunpath_a": round(float(lbA["ra"][i]), 6),
            "hl_core_vectors_a": round(float(lbB["ra"][i]), 6),
            "handrolled_field_minus_a": round(float(hr_f[i] - hr_a[i]), 6),
            "lb_sunpath_field_minus_a": round(float(lbA["rf"][i] - lbA["ra"][i]), 6),
            "no_occluders_within_350m_a": i in no_occ_a,
        }
        if i in no_occ_f or i in no_occ_b or i in no_occ_a:
            row["unearned_score_flag"] = (
                "no building disc within MAX_R of this apex — the engine's "
                "`edges is None` branch returns 1.0 without casting a ray, and the "
                "Ladybug path mirrors it. Not a measurement.")
        points.append(row)

    # ---- assemble -----------------------------------------------------------------
    out = {
        "_meta": {
            "script": "validate_envelope.py",
            "git_commit": _git_commit(),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "purpose": "IMPLEMENTATION_PLAN.md W3.1 — independent Ladybug recheck of the "
                       "winter-sun recapture for BOTH the field-driven canopy and the "
                       "equal-material uniform control (b). Decides whether the 3.2-point "
                       "equal-material margin can be quoted at all.",
            "source": ["data/envelope.json", "data/counterfactual.json",
                       "data/highline_viewshed.json", "data/highline_footprints.json"],
            "independent_of": "hl_core.sun_path and hl_core.ray_uv (the primitive that "
                              "generated the form and produced the published readback)",
            "measurement": "ladybug.Sunpath for solar position + ladybug_geometry "
                           "Ray3D/Face3D intersection for occlusion — the same lineage as "
                           "build_lbt.py, which validated this project's diagnosis half "
                           "(SVF r 0.956, winter sun r 0.993). No Radiance binaries.",
            "mirrored_from_build_envelope": {
                "sensor": "rib apex — station displaced by the full reach along the "
                          "aperture heading, absolute height DECK_H + rib_height "
                          "(build_envelope.py:164). No lateral offset, no eye-height lift.",
                "occluders": "building footprint prisms ONLY (walls 0..h + roof). No canopy "
                             "geometry: ribs cannot occlude one another or themselves. No "
                             "deck, parapet, planting or terrain.",
                "cull": f"hl_core.edges_for's disc test at MAX_R = {MAX_R} m; intersections "
                        f"beyond {MAX_R} m horizontal rejected to mirror ray_uv's t <= max_r.",
                "blocking": "recovered iff every occluder top is strictly below the sun ray "
                            "at its distance; LB Face3D spans z in [0, h], so a hit means "
                            "h >= ray_z — the exact complement of hl_core's `top < ray_y`.",
                "reduction": "unweighted mean of per-station fractions, not pooled timesteps",
                "mask": f"deficit_svf > {ENCLOSED_DEFICIT} (strict), n = {n_enc} of {len(epts)}",
            },
            "bootstrap_method": f"Non-parametric bootstrap over the {n_enc} PAIRED "
                                "per-station differences (field minus uniform control), "
                                f"{BOOTSTRAP_N} resamples with replacement, "
                                f"numpy default_rng(seed={BOOTSTRAP_SEED}). Stations are "
                                "resampled, not timesteps: the claim is a mean over "
                                "stations, so station-to-station spread is the relevant "
                                "sampling variation. Each instrument's block draws from a "
                                "FRESH default_rng(42), so a block reproduces on its own "
                                "and does not depend on the order the blocks are computed. "
                                "Percentile interval (2.5/97.5). Reported in points; "
                                "`excludes_zero` is whether the whole interval is above 0.",
            "secondary_serviceable_population": {
                "status": "SECONDARY. The full enclosed population (deficit_svf > 0.05, "
                          f"n = {n_enc}) remains the primary result and the headline "
                          "denominator for every claim. The serviceable cut is a "
                          "sensitivity, not a replacement.",
                "reporting_rule": "Never quote a serviceable figure without the "
                                  "full-population figure beside it. Every "
                                  "`secondary_serviceable_population` block in this file "
                                  "carries both, so the pair cannot be separated by "
                                  "reading one key.",
                "definition": "enclosed stations where at least one of the two canopies "
                              "recovers a non-zero fraction under the instrument in "
                              "question (tolerance 1e-9). Defined once, by that rule, "
                              "and not tuned.",
                "why_instrument_specific": "the mask is recomputed per instrument rather "
                                           "than fixed from one of them. Ladybug and the "
                                           "hand-rolled caster disagree about which "
                                           "stations are inert; imposing one instrument's "
                                           "mask on another would import its errors into "
                                           "the other's population.",
                "motivation": "under Ladybug a large minority of the enclosed stations have BOTH "
                              "canopies at exactly zero recapture. Those stations enter "
                              "the mean and the bootstrap but carry no information about "
                              "which canopy is better, so nearly half the comparison "
                              "population is inert and the paired delta is in fact "
                              "decided by the remainder. deficit_svf > 0.05 is a "
                              "DIAGNOSIS threshold — it selects stations that lost sky — "
                              "and it is being used here as a design-EVALUATION "
                              "population, which is not what it was chosen for.",
                "justification_is_pre_existing": {
                    "claim": "the deepest cores are a massing problem a canopy cannot "
                             "fix — so their inertness is a predicted property of the "
                             "design, not a discovery made in this dataset.",
                    "source": "THE_ANSWERING_LINE.md, 'Honest results', lines 49-51",
                    "quote": "The deepest cores recover ~0% — a 7 m canopy cannot reach "
                             "winter sun at the bottom of a 24 m+ canyon (see the "
                             "field-plot scatter). Stated plainly rather than hidden: the "
                             "canopy answers the mid-range enclosure; the worst cores are "
                             "a massing problem a canopy can't fix.",
                    "note": "this claim predates the counterfactual and this validation "
                            "run. It is why the cut is defensible as a stated design "
                            "boundary rather than as a filter invented to rescue a "
                            "result.",
                },
                "defined_after_the_full_population_result_was_known": True,
                "post_hoc_disclosure": "This cut was defined AFTER the full-population result was "
                                       "known — after the Ladybug paired delta came back "
                                       "at +1.98 pts with a 95% CI spanning zero. That "
                                       "ordering is recorded here deliberately. A "
                                       "population chosen once the result is visible "
                                       "cannot carry the same evidential weight as a "
                                       "pre-registered one, however sound its rationale, "
                                       "and no reading of this block should treat the "
                                       "serviceable interval as confirmatory. It is a "
                                       "sensitivity that shows where the signal lives, "
                                       "not a second test that the design claim passed.",
                "not_tuned": "the rule has one free parameter (the non-zero tolerance, "
                             "1e-9 = the file's existing EPS) and it was not swept. No "
                             "alternative serviceable definition was tried and "
                             "discarded.",
            },
            "third_configuration_added": {
                "configuration": "control (a) — equal max height, uniform 7.00 m rib and "
                                 "5.524 m reach at every station, heading fixed north.",
                "why": "(a)'s 39.8% was hand-rolled-only and had no independent "
                       "counterpart, so the three recapture figures could not be placed "
                       "under one instrument. It is also the configuration most exposed "
                       "to the shape-dependent bias found in the previous run, which "
                       "makes it the sharpest available test of that bias model.",
                "geometry_origin": "counterfactual.json stores (a)'s measurement, not its "
                                   "rib polylines. Regenerated from the stored "
                                   "uniform_drive and heading_deg by "
                                   "build_counterfactual._uniform_canopy, imported "
                                   "unchanged with measure=False — the identical path "
                                   "build_structure.py --source counterfactual_a uses, "
                                   "with the identical rebuild gate, so the geometry "
                                   "measured here is the geometry sized to 188.6 t there.",
                "identical_to_the_other_configurations": "same sensor definition (rib "
                                                         "apex, full reach, DECK_H + "
                                                         "rib_height), same buildings-only "
                                                         "occluder set, same MAX_R cull, "
                                                         "same blocking test, same "
                                                         "timestep sets, same 56-station "
                                                         "enclosed mask, same reduction.",
                "prediction": PREDICTION_A["predicted_ordering"],
                "prediction_registered_before_measurement": True,
            },
            "prediction_configuration_a": pred,
            "win_tie_loss_note": "Per-station outcome of field vs uniform control, with the "
                                 "tied stations split into tied-at-zero (both canopies "
                                 "recover nothing) and tied above zero (genuine parity). "
                                 "The two are not the same evidence and the mean hides "
                                 "which is which.",
            "exact_culls_note":"Two culls narrow the face set without changing the result: "
                                "(1) a prism with h <= apex height cannot be intersected by a "
                                "strictly ascending ray; (2) a prism whose bounding disc does "
                                "not meet the ray half-line cannot block it. Both are "
                                "conservative and remove no possible occluder.",
            "reused_unchanged": ["build_envelope._rib", "build_envelope._horizon",
                                 "build_envelope._aperture", "build_envelope._tangent",
                                 "build_envelope._sun_dirs", "build_envelope._recaptured_sun",
                                 "build_counterfactual._uniform_canopy",
                                 "build_counterfactual._solve_drive_for_length",
                                 "build_rib_schedule._member3d", "hl_core.load_site",
                                 "hl_core.sun_path", "hl_core.ray_uv"],
            "params": {
                "MAX_R": MAX_R, "SPACING": be.SPACING,
                "winter_date": f"{WINTER_MONTH_DAY[0]:02d}-{WINTER_MONTH_DAY[1]:02d}",
                "hl_core_day_of_year": be.WINTER,
                "sun_step_min": SUN_STEP_MIN, "tz": TZ, "longitude": LON,
                "enclosed_deficit_threshold": ENCLOSED_DEFICIT,
                "n_buildings": len(site.buildings), "n_faces": ctx.n_faces,
                "deterministic": True,
                "seed_note": "no stochastic step in this engine",
            },
            "n_stations": len(epts),
            "n_enclosed_stations": n_enc,
            "runtime_s": None,
            "limitations": [
                "Geometric sun hours, both instruments — timesteps with an unobstructed "
                "line to the apex. Not an irradiance integral, and no sky diffuse component.",
                "Buildings-only context in both instruments, matching build_lbt.py. Trees, "
                "the deck structure and the canopy's own ribs are absent from the occluder "
                "set, so inter-rib self-shading is unmeasured by BOTH.",
                "The sensor is a single point at the rib apex, not the deck surface under "
                "the canopy. It measures whether the form reaches light, not what a visitor "
                "standing on the deck receives.",
                "The two sun models are reported side by side and are never averaged or "
                "calibrated into a single figure.",
            ],
        },
        "checks": {
            "rebuild_fidelity": {
                "apex_max_deviation_m_vs_envelope_json": _rnd(apex_dev, 6),
                "apex_deviation_note": "envelope.json stores the apex at 2 dp; the engine "
                                       "casts from the unrounded value, which is what is "
                                       "rebuilt here. A deviation <= 0.005 m is the rounding.",
                "handrolled_max_deviation_field_vs_envelope_json": _rnd(hr_dev_f, 6),
                "handrolled_max_deviation_b_vs_counterfactual_json": _rnd(hr_dev_b, 6),
                "handrolled_deviation_note": "both stored series are rounded to 3 dp; a "
                                             "deviation <= 0.0005 is that rounding.",
                "uniform_b_drive_solved": _rnd(drive_b, 9),
                "uniform_b_drive_stored": cfb["uniform_drive"],
                "uniform_b_height_m": _rnd(h_b, 4),
                "uniform_b_height_stored": cfb["rib_height_m"],
                "uniform_b_reach_m": _rnd(reach_b, 4),
                "uniform_b_reach_stored": cfb["reach_m"],
                "uniform_b_member_length_m": _rnd(got_b, 2),
                "uniform_b_member_target_m": _rnd(target, 2),
                "uniform_b_solver_clamp": clamp_b,
                "handrolled_max_deviation_a_vs_counterfactual_json": _rnd(hr_dev_a, 6),
                "uniform_a_drive": _rnd(drive_a, 9),
                "uniform_a_drive_stored": cfa["uniform_drive"],
                "uniform_a_height_m": _rnd(h_a, 4),
                "uniform_a_height_stored": cfa["rib_height_m"],
                "uniform_a_reach_m": _rnd(reach_a, 4),
                "uniform_a_reach_stored": cfa["reach_m"],
                "uniform_a_member_length_m": _rnd(got_a, 2),
                "uniform_a_member_length_stored": cfa["total_member_length_m"],
                "uniform_a_rebuild_gate": {
                    "max_deviation": {k: _rnd(v, 6) for k, v in dev_a.items()},
                    "thresholds": {"rib_height_m": 5e-4, "reach_m": 5e-4,
                                   "total_member_length_m": 0.05},
                    "verdict": "PASS — the geometry measured here is the same geometry "
                               "build_structure.py --source counterfactual_a sized to "
                               "188.6 t, regenerated by the identical path.",
                },
            },
            "check1_no_occluder_early_return": {
                "condition": "hl_core.edges_for returns None — no building disc within "
                             f"{MAX_R} m of the apex. build_envelope._recaptured_sun then "
                             "returns 1.0 without casting a single ray.",
                "n_stations_field_driven": len(no_occ_f),
                "n_stations_uniform_b": len(no_occ_b),
                "n_enclosed_stations_field_driven": int(sum(1 for i in no_occ_f if enclosed[i])),
                "n_enclosed_stations_uniform_b": int(sum(1 for i in no_occ_b if enclosed[i])),
                "enclosed_s_m_field_driven": [round(float(s_m[i]), 2) for i in no_occ_f if enclosed[i]],
                "enclosed_s_m_uniform_b": [round(float(s_m[i]), 2) for i in no_occ_b if enclosed[i]],
                "all_s_m_field_driven": [round(float(s_m[i]), 2) for i in no_occ_f],
                "all_s_m_uniform_b": [round(float(s_m[i]), 2) for i in no_occ_b],
                "n_stations_uniform_a": len(no_occ_a),
                "n_enclosed_stations_uniform_a": int(sum(1 for i in no_occ_a if enclosed[i])),
                "enclosed_s_m_uniform_a": [round(float(s_m[i]), 2) for i in no_occ_a if enclosed[i]],
                "all_s_m_uniform_a": [round(float(s_m[i]), 2) for i in no_occ_a],
                "verdict": ("no enclosed station takes the early return — every value in "
                            "the 56-station means is a cast measurement")
                           if not any(enclosed[i] for i in no_occ_f + no_occ_b + no_occ_a) else
                           ("AT LEAST ONE ENCLOSED STATION SCORES 1.0 WITHOUT A RAY BEING "
                            "CAST — unearned, see the s_m lists above"),
            },
            "check2_latitude_sensitivity": {
                "question": "does the Ladybug sun model's latitude (40.7475 from "
                            "origin_latlon vs 40.7409 hard-coded in hl_core) move the result?",
                "runs": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                         for k, v in lat_runs.items()},
                "mean_shift_field_pts": _rnd(dlat_f, 4),
                "mean_shift_uniform_b_pts": _rnd(dlat_b, 4),
                "paired_delta_shift_pts": _rnd(
                    abs(lat_runs["origin_latlon_40.7475"]["paired_delta"]
                        - lat_runs["hl_core_40.7409"]["paired_delta"]) * 100, 4),
                "below_0p1_pts": bool(max(dlat_f, dlat_b) < 0.1),
                "latitude_used_for_headline": LAT_ORIGIN,
            },
            "check3_handrolled_unrounded": {
                "question": "is the published 3.2-point margin carrying the 3 dp readback "
                            "asymmetry? build_counterfactual reads the field-driven baseline "
                            "back from envelope.json at 3 dp while computing the variants "
                            "unrounded.",
                "mean_field_unrounded": _rnd(hr_mean_f, 6),
                "mean_uniform_b_unrounded": _rnd(hr_mean_b, 6),
                "delta_pts_unrounded": _rnd(hr_delta_unrounded * 100, 4),
                "delta_pts_as_published": _rnd(pub_delta * 100, 4),
                "rounding_carried_pts": _rnd((hr_delta_unrounded - pub_delta) * 100, 4),
            },
        },
        "handrolled": {
            "label": "hl_core ray primitive — the instrument under test, the one that "
                     "generated the form. Recomputed here UNROUNDED on both configurations.",
            "sun_model": {"n_timesteps": len(hl_sun[0]), "latitude": LAT_HLCORE,
                          "source": "hl_core.sun_path(355)"},
            "field_driven": {"mean_recaptured_enclosed": _rnd(hr_mean_f, 6),
                             "mean_recaptured_all": _rnd(float(hr_f.mean()), 6)},
            "uniform_equal_member_b": {"mean_recaptured_enclosed": _rnd(hr_mean_b, 6),
                                       "mean_recaptured_all": _rnd(float(hr_b.mean()), 6)},
            "paired_delta": {
                "pts": _rnd(hr_delta_unrounded * 100, 3),
                "pts_published_rounded": _rnd(pub_delta * 100, 3),
                "n_stations": n_enc,
            },
            "win_tie_loss": _win_tie_loss(hr_f[enclosed], hr_b[enclosed]),
            "bootstrap": _bootstrap_paired(hr_f[enclosed] - hr_b[enclosed]),
            "secondary_serviceable_population": _serviceable_block(
                hr_f[enclosed], hr_b[enclosed]),
            "uniform_equal_max_height_a": {
                "label": "control (a) — uniform 7.00 m rib, 5.524 m reach, heading north, "
                         "recomputed here UNROUNDED by the instrument under test.",
                "mean_recaptured_enclosed": _rnd(hr_mean_a, 6),
                "mean_recaptured_all": _rnd(float(hr_a.mean()), 6),
            },
            "paired_delta_field_vs_a": {
                "pts": _rnd((hr_mean_f - hr_mean_a) * 100, 3),
                "pts_published_rounded": _rnd(
                    (cf["baseline_field_driven"]["mean_recaptured_winter_sun_frac_enclosed"]
                     - cfa["mean_recaptured_winter_sun_frac_enclosed"]) * 100, 3),
                "n_stations": n_enc,
            },
            "win_tie_loss_field_vs_a": _win_tie_loss(hr_f[enclosed], hr_a[enclosed]),
            "bootstrap_field_vs_a": _bootstrap_paired(hr_f[enclosed] - hr_a[enclosed]),
        },
        "results": {k: v for k, v in results.items()},
        "points": points,
    }
    out["_meta"]["runtime_s"] = round(time.time() - t_start, 1)

    outp = os.path.join(DATA, "envelope_validation.json")
    json.dump(out, open(outp, "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {outp}  ({len(points)} stations, {out['_meta']['runtime_s']} s)")

    # ---- console report -----------------------------------------------------------
    print("\n" + "=" * 78)
    print(f"W3.1 — INDEPENDENT RECHECK   ·   {n_enc} enclosed stations (deficit > 0.05)")
    print("=" * 78)
    def _wtl_line(w):
        return (f"   win/tie/loss  field {w['n_field_ahead']} · tied {w['n_tied']} "
                f"(at zero {w['n_tied_at_zero']}, above zero {w['n_tied_above_zero']}) · "
                f"control {w['n_control_ahead']}")

    def _bs_line(bs):
        if bs.get("null_reason"):
            return f"   bootstrap     null — {bs['null_reason']}"
        return (f"   bootstrap     {bs['point_estimate_pts']:+.2f} pts   95% CI "
                f"[{bs['ci95_low_pts']:+.2f}, {bs['ci95_high_pts']:+.2f}]   "
                f"P(delta<=0) {bs['frac_resamples_le_zero']:.4f}   "
                f"excludes zero: {bs['excludes_zero']}")

    def _sv_lines(blk):
        bs, pd = blk["bootstrap"], blk["paired_delta"]
        L = [f"   serviceable   n {blk['n_serviceable']} of {blk['n_full_population']} "
             f"({blk['n_excluded_both_zero']} excluded, both canopies at zero)",
             f"                 field {blk['field_driven']['mean_recaptured_serviceable']*100:6.2f}%"
             f"   control {blk['uniform_equal_member_b']['mean_recaptured_serviceable']*100:6.2f}%"
             f"   delta {pd['serviceable_pts']:+.2f} pts"
             f"   (full-population {pd['full_population_pts']:+.2f} pts)"]
        if bs.get("null_reason"):
            L.append(f"                 bootstrap null — {bs['null_reason']}")
        else:
            L.append(f"                 bootstrap {bs['point_estimate_pts']:+.2f} pts  95% CI "
                     f"[{bs['ci95_low_pts']:+.2f}, {bs['ci95_high_pts']:+.2f}]  "
                     f"P(delta<=0) {bs['frac_resamples_le_zero']:.4f}  "
                     f"excludes zero: {bs['excludes_zero']}")
        return "\n".join(L)

    hrb = out["handrolled"]
    print(f"\nhand-rolled (hl_core, the instrument under test), unrounded:")
    print(f"   field-driven {hr_mean_f*100:6.2f}%     uniform (b) {hr_mean_b*100:6.2f}%"
          f"     delta {hr_delta_unrounded*100:+.2f} pts")
    print(_wtl_line(hrb["win_tie_loss"]))
    print(_bs_line(hrb["bootstrap"]))
    print(_sv_lines(hrb["secondary_serviceable_population"]))
    for key, R in results.items():
        f_, b_ = R["field_driven"], R["uniform_equal_member_b"]
        pd = R["paired_delta"]; sd = R["sign_disagreement"]
        print(f"\n{key}  ({R['sun_model']['n_timesteps']} timesteps, lat "
              f"{R['sun_model']['latitude']})")
        print(f"   field-driven {f_['mean_recaptured_enclosed']*100:6.2f}%   "
              f"r {f_['vs_handrolled_r']:+.3f}   RMSE {f_['vs_handrolled_rmse']:.4f}   "
              f"shift {f_['mean_shift_pts']:+.2f} pts")
        print(f"   uniform  (b) {b_['mean_recaptured_enclosed']*100:6.2f}%   "
              f"r {b_['vs_handrolled_r']:+.3f}   RMSE {b_['vs_handrolled_rmse']:.4f}   "
              f"shift {b_['mean_shift_pts']:+.2f} pts")
        print(f"   PAIRED DELTA  ladybug {pd['ladybug_pts']:+.2f} pts   vs   "
              f"hand-rolled {pd['handrolled_pts']:+.2f} pts   "
              f"(difference {pd['delta_of_deltas_pts']:+.2f} pts)")
        print(f"   sign disagreement {sd['n_sign_differs']} of {n_enc}   "
              f"(strict flips {sd['n_strict_flip']}, tie mismatches {sd['n_tie_mismatch']})")
        print(_wtl_line(R["win_tie_loss"]))
        print(_bs_line(R["bootstrap"]))
        print(_sv_lines(R["secondary_serviceable_population"]))
        A = R["uniform_equal_max_height_a"]; pa = R["paired_delta_field_vs_a"]
        print(f"   uniform  (a) {A['mean_recaptured_enclosed']*100:6.2f}%   "
              f"r {A['vs_handrolled_r']:+.3f}   RMSE {A['vs_handrolled_rmse']:.4f}   "
              f"shift {A['mean_shift_pts']:+.2f} pts")
        print(f"   FIELD vs (a)  ladybug {pa['ladybug_pts']:+.2f} pts   vs   "
              f"hand-rolled {pa['handrolled_pts']:+.2f} pts   "
              f"(difference {pa['delta_of_deltas_pts']:+.2f} pts)")
        print(_bs_line(R["bootstrap_field_vs_a"]).replace("bootstrap    ", "boot f-vs-a "))
    print("\n" + "=" * 78)
    print("PRE-REGISTERED PREDICTION — (a) should deflate MORE than the field-driven form")
    print("=" * 78)
    for k, v in pred["outcome"]["per_instrument"].items():
        print(f"  {k:18s} (a) {v['deflation_a_pts']:+.2f} · field "
              f"{v['deflation_field_driven_pts']:+.2f} · control (b) "
              f"{v['deflation_control_b_pts']:+.2f}   ordering held: "
              f"{v['predicted_ordering_held']}   ((a) vs field "
              f"{v['margin_a_vs_field_pts']:+.2f} pts)")
    print(f"\n  {pred['outcome']['verdict']}")

    print("\n" + "-" * 78)
    print(f"the full enclosed population (n = {n_enc}) is primary and the headline "
          f"denominator;\nthe serviceable cut is SECONDARY, was defined after that result "
          f"was known, and must\nnever be reported without the full-population figure "
          f"beside it.")
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
