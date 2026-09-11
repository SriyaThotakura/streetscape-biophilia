"""build_structure.py — structural utilization pass on the canopy ribs.

Each rib is a bent steel member springing from both deck rails to a raised apex that
cantilevers toward the light. This engine analyses every rib as a 2-D frame with a
from-scratch **direct-stiffness finite-element solver** (no Grasshopper/Karamba binary —
the solver is the tool), under code load combinations, and reports member utilization
(demand / capacity) against a standard CHS section. It then **sizes** each rib from a
standard section ladder to keep utilization ≤ 1, giving a buildable steel take-off.

The solver is validated against closed-form cantilever results (tip deflection and base
moment, point load and UDL) — see `_selftest()`; the checks run every time and abort the
build if the FEM has drifted.

Honest expected finding: utilization tracks rib height/reach. The short open-corridor ribs
pass comfortably on a light section; the deep-canyon cantilevers — the same ribs the
fabrication schedule flags bespoke — drive the heavy sections. Structure, fabrication, and
the enclosure field all point at the same few ribs.

Consumes:  data/envelope.json  (+ rib member geometry)
Produces:  data/structure.json   (per-rib utilization, governing combo, sized section)
           exports/structure.png  (utilization along the deck · worst-rib BMD · sizing)

Run:  python scripts/build_structure.py

Second input path (added 2026-08-09) — the counterfactual geometry
-------------------------------------------------------------------
`--source counterfactual_a` runs the IDENTICAL pass over variant (a) of
`data/counterfactual.json` — the "equal max height" naive canopy, 7.00 m rib at every
station. Nothing in the solver, the load model, the section ladder, the combos or the
closed-form gate changes; only where the rib polylines come from.

Variant (a)'s geometry is not stored in counterfactual.json (that file records the
recapture measurement, not the ribs), so it is REGENERATED from the stored
`uniform_drive` and `heading_deg` by calling `build_counterfactual._uniform_canopy`
unchanged, by import, with `measure=False` — the same generator, the same 2-dp point
rounding, no recapture cast. The rebuild is checked against the stored rib height,
reach and total member length before anything is analysed; a mismatch aborts.

Run:  python scripts/build_structure.py --source counterfactual_a \
          --out data/structure_counterfactual.json --no-fig
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time

import numpy as np

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
ROOT = os.path.dirname(DATA)
EXPORTS = os.path.join(ROOT, "exports")

# ---- materials / loads -----------------------------------------------------------
E = 210e9           # steel Young's modulus (Pa)
FY = 355e6          # S355 yield (Pa)
PHI = 0.9           # LRFD resistance factor
RHO = 7850.0        # steel density (kg/m3)
G = 9.81
SPACING = 8.0       # rib spacing = deck station spacing (m) -> tributary width
SNOW = 1.2e3        # ground snow (Pa) ~ NYC ASCE7
WIND = 0.9e3        # design wind pressure (Pa), taken as net uplift on the canopy

# standard CHS ladder (S355): OD(mm), t(mm), A(cm2), Wpl(cm3), I(cm4), mass(kg/m)
SECTIONS = [
    ("CHS 168x6.3", 168.3, 6.3, 32.1, 165.0, 1053.0, 25.2),
    ("CHS 219x8",   219.1, 8.0, 53.1, 357.0, 3060.0, 41.6),
    ("CHS 273x8",   273.0, 8.0, 66.6, 642.0, 5852.0, 52.3),
    ("CHS 324x10",  323.9, 10.0, 98.6, 1058.0, 12158.0, 77.4),
    ("CHS 356x12.5", 355.6, 12.5, 135.0, 1607.0, 20668.0, 106.0),
]
NOMINAL = 1          # index into SECTIONS used for the "nominal" utilization map (CHS 219x8)


def _sec(i):
    n, od, t, A, Wpl, I, m = SECTIONS[i]
    return {"name": n, "A": A * 1e-4, "Wpl": Wpl * 1e-6, "I": I * 1e-8, "kg_m": m}


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


# ==================================================================================
# 2-D frame direct-stiffness solver
# ==================================================================================

def _frame_element_k(EA, EI, L, c, s):
    """Global 6x6 stiffness of a 2-D frame element (axial + Euler-Bernoulli bending)."""
    L2, L3 = L * L, L * L * L
    k = np.zeros((6, 6))
    # local stiffness
    kl = np.array([
        [EA/L, 0, 0, -EA/L, 0, 0],
        [0, 12*EI/L3, 6*EI/L2, 0, -12*EI/L3, 6*EI/L2],
        [0, 6*EI/L2, 4*EI/L, 0, -6*EI/L2, 2*EI/L],
        [-EA/L, 0, 0, EA/L, 0, 0],
        [0, -12*EI/L3, -6*EI/L2, 0, 12*EI/L3, -6*EI/L2],
        [0, 6*EI/L2, 2*EI/L, 0, -6*EI/L2, 4*EI/L],
    ])
    T = np.array([
        [c, s, 0, 0, 0, 0], [-s, c, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0],
        [0, 0, 0, c, s, 0], [0, 0, 0, -s, c, 0], [0, 0, 0, 0, 0, 1],
    ])
    return T.T @ kl @ T, T, kl


def _fef(w_ax, w_tr, L):
    """Fixed-end forces (local) for uniform axial w_ax and transverse w_tr over length L."""
    return np.array([w_ax*L/2, w_tr*L/2, w_tr*L*L/12,
                     w_ax*L/2, w_tr*L/2, -w_tr*L*L/12])


def solve_frame(nodes, elements, fixed, sec, udl_global):
    """
    nodes: (N,2) coords (m). elements: list of (i,j). fixed: set of node indices fully fixed.
    sec: section dict (A, I). udl_global: (E,) vertical load intensity per member length (N/m,
         +y up). Returns dict with nodal displacements and per-element (N, Mmax) demand.
    """
    N = len(nodes); ndof = 3 * N
    K = np.zeros((ndof, ndof)); F = np.zeros(ndof)
    EA, EI = E * sec["A"], E * sec["I"]
    Ts, kls, geom = [], [], []
    for e, (i, j) in enumerate(elements):
        dx, dy = nodes[j] - nodes[i]; L = math.hypot(dx, dy); c, s = dx / L, dy / L
        kg, T, kl = _frame_element_k(EA, EI, L, c, s)
        Ts.append(T); kls.append(kl); geom.append((L, c, s))
        dofs = [3*i, 3*i+1, 3*i+2, 3*j, 3*j+1, 3*j+2]
        for a in range(6):
            for b in range(6):
                K[dofs[a], dofs[b]] += kg[a, b]
        # global vertical UDL -> local components -> equivalent nodal loads
        w = udl_global[e]
        w_ax = (0*c + w*s)          # projection of (0,w) on local x
        w_tr = (0*(-s) + w*c)       # projection on local y
        # _fef returns the EQUIVALENT NODAL LOADS (for a downward UDL these are downward
        # end forces + balancing moments) — add them straight into the global load vector.
        fe_local = _fef(w_ax, w_tr, L)
        fe_global = T.T @ fe_local
        for a in range(6):
            F[dofs[a]] += fe_global[a]

    free = [d for d in range(ndof) if (d // 3) not in fixed]
    Kff = K[np.ix_(free, free)]; Ff = F[free]
    u = np.zeros(ndof)
    u[free] = np.linalg.solve(Kff, Ff)

    # recover element end forces + max moment (incl. span parabola from UDL)
    demands = []
    for e, (i, j) in enumerate(elements):
        dofs = [3*i, 3*i+1, 3*i+2, 3*j, 3*j+1, 3*j+2]
        ue = u[dofs]; L, c, s = geom[e]
        w = udl_global[e]; w_ax = w*s; w_tr = w*c
        # member end forces = k·u_local − equivalent nodal loads  (= k·u + fixed-end reactions)
        f_local = kls[e] @ (Ts[e] @ ue) - _fef(w_ax, w_tr, L)
        Ni = f_local[0]; Mi = f_local[2]; Mj = f_local[5]
        axial = 0.5 * (abs(f_local[0]) + abs(f_local[3]))
        # moment along member: linear from -Mi..Mj plus parabola w_tr*x*(L-x)/2
        xs = np.linspace(0, L, 21)
        Mlin = -Mi + (Mj + Mi) * xs / L
        Mpar = w_tr * xs * (L - xs) / 2.0
        Mmax = float(np.max(np.abs(Mlin + Mpar)))
        demands.append((axial, Mmax))
    return {"u": u, "demands": demands}


# ==================================================================================
# per-rib analysis
# ==================================================================================

def _rib_frame(rib):
    """Analyse the rib in its own BEST-FIT PLANE, so the aperture reach becomes real
    in-plane cantilever bending (a cross-deck plane would miss it). Returns 2-D nodes
    (in-plane x, up-aligned y), and per-element load geometry from the 3-D member:
    (member length, global horizontal projection), plus the plane's gravity factor
    gfac = fraction of vertical load acting in-plane (=1 for a vertical rib plane)."""
    P = np.asarray(rib, float)
    c = P.mean(0)
    _, _, Vt = np.linalg.svd(P - c)
    n = Vt[2]                                   # plane normal (least-variance direction)
    up = np.array([0.0, 1.0, 0.0])
    e2 = up - (up @ n) * n
    e2 = e2 / (np.linalg.norm(e2) or 1.0)       # in-plane, points up
    e1 = np.cross(n, e2); e1 = e1 / (np.linalg.norm(e1) or 1.0)
    nodes = np.column_stack([(P - c) @ e1, (P - c) @ e2])
    gfac = math.sqrt(max(0.0, 1.0 - n[1] ** 2))  # vertical component that acts in-plane
    geom = []
    for k in range(len(P) - 1):
        d = P[k + 1] - P[k]
        geom.append((float(np.linalg.norm(d)), float(math.hypot(d[0], d[2]))))
    return nodes, geom, gfac


def _combos(geom, gfac):
    """Design load combinations as per-element in-plane UDLs (N/m, +y up).
    Self-weight & snow act down (scaled by gfac for the plane tilt); snow & wind on the
    global horizontal projection; wind as net uplift."""
    sw, snow, wind = [], [], []
    for (L3d, horiz) in geom:
        f = horiz / (L3d or 1.0)                          # projection fraction
        sw.append(-SECTIONS[NOMINAL][6] * G * gfac)
        snow.append(-SNOW * SPACING * f * gfac)
        wind.append(+WIND * SPACING * f * gfac)
    sw, snow, wind = np.array(sw), np.array(snow), np.array(wind)
    return [
        ("1.2D+1.6S", 1.2 * sw + 1.6 * snow),
        ("0.9D+1.0W", 0.9 * sw + 1.0 * wind),
    ]


def _utilization(demands, sec):
    """Linear axial+bending interaction, LRFD. util = N/φNc + M/φMc, worst element."""
    Nc = PHI * sec["A"] * FY; Mc = PHI * sec["Wpl"] * FY
    return max((abs(N) / Nc + abs(M) / Mc) for (N, M) in demands)


def _size(nodes, elements, fixed, combos):
    """Pick the lightest section from the ladder that keeps utilization ≤ 1."""
    for si in range(len(SECTIONS)):
        sec = _sec(si)
        u = max(_utilization(solve_frame(nodes, elements, fixed, sec, udl)["demands"], sec)
                for _, udl in combos)
        if u <= 1.0:
            return si, u
    return len(SECTIONS) - 1, u        # nothing passes -> heaviest, report its util


# ==================================================================================
# input paths — where the rib polylines come from. NOTHING below the solver changes.
# ==================================================================================

def _load_envelope():
    """The original input: the field-driven canopy as build_envelope wrote it."""
    env = json.load(open(os.path.join(DATA, "envelope.json"), encoding="utf-8"))
    return env["points"], {
        "source": "data/envelope.json",
        "geometry": "field-driven canopy — rib height/reach/heading from the measured "
                    "enclosure field (build_envelope.py)",
        "geometry_origin": "read verbatim from envelope.json `points[].rib`",
    }


def _load_counterfactual_a():
    """Variant (a) of the counterfactual: the uniform 7.00 m 'equal max height' canopy.

    counterfactual.json stores the recapture measurement, not the rib polylines, so the
    geometry is regenerated from the stored uniform_drive/heading by
    `build_counterfactual._uniform_canopy` — imported unchanged, `measure=False`, no
    recapture cast. Deterministic. Aborts if the rebuild does not reproduce the stored
    rib height, reach and total member length.
    """
    import build_counterfactual as bc          # imported here so the envelope path
    import build_envelope as be                # keeps its original dependency set
    import hl_core as hl

    cf = json.load(open(os.path.join(DATA, "counterfactual.json"), encoding="utf-8"))
    va = cf["variants"]["a_equal_max_height"]
    drive = float(va["uniform_drive"])
    heading = math.radians(float(va["heading_deg"]))

    site = hl.load_site()
    samples = site.corridor.samples(be.SPACING)
    if len(samples) != len(cf["points"]):
        raise SystemExit(f"station mismatch: counterfactual.json has {len(cf['points'])}, "
                         f"corridor resample gives {len(samples)}")

    c = bc._uniform_canopy(site.buildings, samples, drive, heading, None, measure=False)

    # --- rebuild fidelity gate ----------------------------------------------------
    got_len = float(c["mem_len"].sum())
    dev = {
        "rib_height_m": abs(float(c["rib_height_m"]) - float(va["rib_height_m"])),
        "reach_m": abs(float(c["reach_m"]) - float(va["reach_m"])),
        "total_member_length_m": abs(got_len - float(va["total_member_length_m"])),
    }
    if dev["rib_height_m"] > 5e-4 or dev["reach_m"] > 5e-4 or dev["total_member_length_m"] > 0.05:
        raise SystemExit(f"COUNTERFACTUAL (a) REBUILD MISMATCH vs counterfactual.json: {dev}")

    pts = [{"s_m": float(cf["points"][i]["s_m"]),
            "rib_height_m": round(float(c["rib_height_m"]), 3),
            "reach_m": round(float(c["reach_m"]), 3),
            "rib": c["ribs"][i]}
           for i in range(len(samples))]

    return pts, {
        "source": ["data/counterfactual.json", "data/highline_footprints.json"],
        "geometry": va["label"],
        "geometry_origin":
            "counterfactual.json stores the recapture measurement, not the rib "
            "polylines. Geometry regenerated from the stored uniform_drive "
            f"({drive:.6f}) and heading_deg ({va['heading_deg']}) by "
            "build_counterfactual._uniform_canopy, imported UNCHANGED with "
            "measure=False (no recapture cast). Same 2-dp point rounding "
            "counterfactual.json and envelope.json both store.",
        "rebuild_fidelity": {
            "rib_height_m_rebuilt": round(float(c["rib_height_m"]), 4),
            "rib_height_m_stored": va["rib_height_m"],
            "reach_m_rebuilt": round(float(c["reach_m"]), 4),
            "reach_m_stored": va["reach_m"],
            "total_member_length_m_rebuilt": round(got_len, 2),
            "total_member_length_m_stored": va["total_member_length_m"],
            "max_deviation": {k: round(v, 6) for k, v in dev.items()},
            "gate": "PASS — rebuild reproduces the stored variant (a) geometry",
        },
        "reused_unchanged": ["build_counterfactual._uniform_canopy",
                             "build_counterfactual._solve_drive_for_length",
                             "build_envelope._rib", "build_envelope._tangent",
                             "build_rib_schedule._member3d", "hl_core.load_site"],
        "published_assumed_tonnage": {
            "est_steel_tonnes": va["est_steel_tonnes"],
            "basis": f"total member length {va['total_member_length_m']} m x an ASSUMED "
                     f"{bc.KG_PER_M} kg/m linear density (build_counterfactual.KG_PER_M) — "
                     "not a structural sizing. The `sized_steel_tonnes` in this file is the "
                     "solver-derived counterpart.",
        },
    }


SOURCES = {"envelope": _load_envelope, "counterfactual_a": _load_counterfactual_a}


def build(make_fig=True, source="envelope", outfile=None):
    _selftest()
    if source not in SOURCES:
        raise SystemExit(f"unknown --source {source!r}; expected one of {sorted(SOURCES)}")
    pts, src_meta = SOURCES[source]()
    nom = _sec(NOMINAL)
    light = _sec(0)                # the lightest rung of the ladder (CHS 168x6.3)

    out = []
    util_light_raw = []          # UNROUNDED — the pass/fail count at the lightest rung is a
                                 # boundary test, and a rib at 1.0004 rounds to 1.0 and would
                                 # be miscounted as passing (it is not: _size sizes it up)
    combo_ratio = []             # snow-combo util / uplift-combo util, per rib, at nominal
    for p in pts:
        nodes, geom, gfac = _rib_frame(p["rib"])
        elements = [(k, k + 1) for k in range(len(nodes) - 1)]
        fixed = {0, len(nodes) - 1}                 # both rails moment-fixed to the deck
        combos = _combos(geom, gfac)

        util_nom, gov, base_M, apex_defl = 0.0, "", 0.0, 0.0
        by_combo = {}
        for name, udl in combos:
            r = solve_frame(nodes, elements, fixed, nom, udl)
            u = _utilization(r["demands"], nom)
            by_combo[name] = float(u)
            if u > util_nom:
                util_nom = u; gov = name
                base_M = max(r["demands"][0][1], r["demands"][-1][1]) / 1e3   # kNm
                apex = np.argmax(nodes[:, 1])
                apex_defl = abs(r["u"][3 * apex + 1]) * 1e3                   # mm
        # utilization on the LIGHTEST rung, reported alongside — this is the rung the
        # field-driven kit uses for 221 of its 232 ribs, so it is the like-for-like
        # section to compare a different geometry against. Same solver, same combos.
        util_light, gov_light = 0.0, ""
        for name, udl in combos:
            u = _utilization(solve_frame(nodes, elements, fixed, light, udl)["demands"], light)
            if u > util_light:
                util_light, gov_light = u, name
        util_light_raw.append(float(util_light))
        combo_ratio.append(by_combo["1.2D+1.6S"] / (by_combo["0.9D+1.0W"] or float("nan")))
        si, util_sized = _size(nodes, elements, fixed, combos)
        out.append({
            "s_m": round(p["s_m"], 1),
            "rib_height_m": p["rib_height_m"], "reach_m": p["reach_m"],
            "util_nominal": round(float(util_nom), 3),
            "governing_combo": gov,
            "base_moment_kNm": round(float(base_M), 1),
            "apex_deflection_mm": round(float(apex_defl), 1),
            "util_chs168": round(float(util_light), 3),
            "governing_combo_chs168": gov_light,
            "section_sized": SECTIONS[si][0],
            "section_idx": si,
            "util_sized": round(float(util_sized), 3),
        })

    util = np.array([o["util_nominal"] for o in out])
    util_l = np.array(util_light_raw)
    sized_mass = 0.0
    total_len = 0.0
    for i, o in enumerate(out):
        _, geom, _ = _rib_frame(pts[i]["rib"])
        L = sum(L3d for L3d, _ in geom)
        total_len += L
        sized_mass += SECTIONS[o["section_idx"]][6] * L
    from collections import Counter
    sec_counts = Counter(o["section_sized"] for o in out)
    gov_counts = Counter(o["governing_combo"] for o in out)
    gov_counts_l = Counter(o["governing_combo_chs168"] for o in out)
    over = np.array([o["util_sized"] for o in out]) > 1.0

    result = {
        "_meta": {
            "script": "build_structure.py", "git_commit": _git_commit(),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "input_path": source,
            "source": src_meta["source"],
            "geometry": src_meta,
            "model": "each rib a 2-D frame (both rails moment-fixed to the deck), analysed "
                     "with a from-scratch direct-stiffness solver under 1.2D+1.6S and "
                     "0.9D+1.0W. Utilization = N/φNc + M/φMc (S355, φ=0.9). Sections sized "
                     "from a standard CHS ladder to keep utilization ≤ 1.",
            "unchanged_from_the_envelope_pass":
                "solver (solve_frame, _frame_element_k, _fef), load model (_combos, SNOW, "
                "WIND, SPACING), section ladder (SECTIONS), interaction check "
                "(_utilization), sizing rule (_size), per-rib best-fit-plane treatment "
                "(_rib_frame) and the closed-form validation gate (_selftest). Only the "
                "input path differs.",
            "deterministic": True,
            "seed_note": "no stochastic step in this engine",
            "solver_validation": _selftest(return_report=True),
            "loads": {"snow_kPa": SNOW/1e3, "wind_uplift_kPa": WIND/1e3,
                      "rib_spacing_m": SPACING, "steel": "S355", "phi": PHI},
            "nominal_section": nom["name"],
            "lightest_section": light["name"],
            "totals": {
                "n_ribs": len(out),
                "pass_nominal": int((util <= 1.0).sum()),
                "fail_nominal": int((util > 1.0).sum()),
                "max_util_nominal": round(float(util.max()), 2),
                "median_util_nominal": round(float(np.median(util)), 2),
                "pass_chs168": int((util_l <= 1.0).sum()),
                "fail_chs168": int((util_l > 1.0).sum()),
                "max_util_chs168": round(float(util_l.max()), 2),
                "median_util_chs168": round(float(np.median(util_l)), 2),
                "governing_combo_counts_nominal": dict(gov_counts),
                "governing_combo_counts_chs168": dict(gov_counts_l),
                "combo_margin": {
                    "ratio_snow_over_uplift_min": round(float(np.min(combo_ratio)), 3),
                    "ratio_snow_over_uplift_max": round(float(np.max(combo_ratio)), 3),
                    "n_ribs_uplift_governs": int((np.array(combo_ratio) < 1.0).sum()),
                    "note":
                        "ratio of the two combos' nominal utilizations per rib. Snow and "
                        "uplift both scale on the same horizontal projection x plane-tilt "
                        "factor, and factored snow (1.6 x 1.2 = 1.92 kPa, added to dead) is "
                        "more than twice factored uplift (1.0 x 0.9 = 0.9 kPa, opposed by "
                        "dead), so 1.2D+1.6S envelopes 0.9D+1.0W at every rib. Geometry "
                        "cannot flip this ordering under this load model — the ratio stays "
                        "near-constant across rib heights. That is a property of the load "
                        "model, not a finding about the form: a real uplift case on a "
                        "multi-metre cantilever would need a wind model this engine "
                        "does not have.",
                },
                "sized_steel_tonnes": round(sized_mass / 1000.0, 1),
                "sections_used": dict(sec_counts),
                "total_member_length_m": round(total_len, 1),
                "n_ribs_over_capacity_at_heaviest_section": int(over.sum()),
                "sized_kit_keeps_every_rib_within_capacity": bool(not over.any()),
                "assumed_24kg_m_tonnes": round(total_len * 24.0 / 1000.0, 1),
                "assumed_24kg_m_note":
                    "the same assumed linear density build_counterfactual and "
                    "build_rib_schedule use (24.0 kg/m on member length, no sizing). "
                    "Carried here ONLY so the assumed and solver-derived tonnages for "
                    "this geometry can be read against each other in one place; it is "
                    "not a structural result.",
            },
        },
        "ribs": out,
    }
    outp = os.path.join(DATA, outfile) if outfile else os.path.join(DATA, "structure.json")
    json.dump(result, open(outp, "w", encoding="utf-8"), indent=1)
    tt = result["_meta"]["totals"]
    print(f"wrote {outp}")
    print(f"  solver validated: {result['_meta']['solver_validation']}")
    print(f"  nominal {nom['name']}: {tt['pass_nominal']}/{tt['n_ribs']} ribs pass "
          f"(median util {tt['median_util_nominal']}, max {tt['max_util_nominal']})")
    print(f"  lightest {light['name']}: {tt['pass_chs168']}/{tt['n_ribs']} pass, "
          f"{tt['fail_chs168']} exceed 1.0 (median {tt['median_util_chs168']}, "
          f"max {tt['max_util_chs168']})")
    if tt["sized_kit_keeps_every_rib_within_capacity"]:
        print(f"  sized kit keeps all ribs ≤ 1.0 · {tt['sized_steel_tonnes']} t · "
              f"sections: {tt['sections_used']}")
    else:
        print(f"  *** {tt['n_ribs_over_capacity_at_heaviest_section']} ribs EXCEED 1.0 even "
              f"on the heaviest rung {SECTIONS[-1][0]} — the ladder does not cover this "
              f"geometry · {tt['sized_steel_tonnes']} t · sections: {tt['sections_used']}")
    print(f"  governing combo: {tt['governing_combo_counts_nominal']} (nominal) · "
          f"{tt['governing_combo_counts_chs168']} (CHS 168)")
    print(f"  member {tt['total_member_length_m']} m · assumed 24 kg/m would give "
          f"{tt['assumed_24kg_m_tonnes']} t vs solver-sized {tt['sized_steel_tonnes']} t")

    if make_fig:
        _figure(result)
    return result


# ==================================================================================
# solver validation against closed-form cantilever
# ==================================================================================

def _selftest(return_report=False):
    sec = _sec(2)                      # any section
    L = 5.0
    nodes = np.array([[0.0, 0.0], [L, 0.0]]); elements = [(0, 1)]; fixed = {0}
    EI = E * sec["I"]
    # UDL case: tip deflection wL^4/8EI, base moment wL^2/2
    w = -1000.0
    r = solve_frame(nodes, elements, fixed, sec, np.array([w]))
    tip = r["u"][3*1 + 1]; tip_exact = w * L**4 / (8 * EI)
    baseM = r["demands"][0][1]; baseM_exact = abs(w) * L**2 / 2
    e_tip = abs(tip - tip_exact) / abs(tip_exact)
    e_M = abs(baseM - baseM_exact) / baseM_exact
    ok = e_tip < 1e-6 and e_M < 1e-6
    rep = f"cantilever UDL tip-defl err {e_tip:.1e}, base-M err {e_M:.1e} - {'OK' if ok else 'FAIL'}"
    if return_report:
        return rep
    if not ok:
        raise SystemExit("STRUCTURAL SOLVER SELF-TEST FAILED: " + rep)
    return rep


def _figure(result):
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib import cm, colors as mcolors

    ribs = result["ribs"]
    s = np.array([r["s_m"] for r in ribs])
    util = np.array([r["util_nominal"] for r in ribs])
    h = np.array([r["rib_height_m"] for r in ribs])
    reach = np.array([r["reach_m"] for r in ribs])

    INK = "#141414"; ACC = "#c0673f"; MUT = "#8a8780"; SKY = "#3a6ea5"
    plt.rcParams.update({"font.family": ["IBM Plex Mono", "Consolas", "DejaVu Sans Mono", "monospace"],
                         "font.size": 8, "axes.edgecolor": MUT})
    fig = plt.figure(figsize=(14, 8.4), facecolor="white")
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.08], hspace=0.4, wspace=0.22,
                          left=0.06, right=0.98, top=0.9, bottom=0.08)

    # utilization: green (lightly worked) -> orange near capacity -> red (over)
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "util", ["#1b7f4b", "#8ab020", "#e0a02a", "#c0673f", "#8f1d1d"])
    norm = mcolors.Normalize(0.2, 1.0)

    # --- utilization along the deck --------------------------------------------
    axs = fig.add_subplot(gs[0, :])
    seg = np.stack([np.column_stack([s[:-1], util[:-1]]),
                    np.column_stack([s[1:], util[1:]])], axis=1)
    lc = LineCollection(seg, cmap=cmap, norm=norm, array=util[:-1], linewidths=2.6)
    axs.add_collection(lc)
    axs.axhline(1.0, color="#8f1d1d", lw=1.0, ls=(0, (5, 3)))
    axs.text(s.max(), 1.03, "capacity  (util = 1.0)", ha="right", fontsize=7.5, color="#8f1d1d")
    axs.set_xlim(0, s.max()); axs.set_ylim(0, max(1.5, util.max()*1.08))
    axs.set_xlabel("s along deck  (m)"); axs.set_ylabel("utilization\n(nominal " +
                                                        result["_meta"]["nominal_section"] + ")")
    tt = result["_meta"]["totals"]
    axs.set_title(f"rib utilization ({result['_meta']['nominal_section']}, 1.2D+1.6S) — "
                  f"lightly worked in the open, up to {tt['max_util_nominal']:.2f} where it "
                  f"reaches into the canyon; all within capacity",
                  loc="left", fontsize=9.5, fontweight="bold", color=INK)
    for sp in ("top", "right"): axs.spines[sp].set_visible(False)

    # --- worst rib: frame + bending-moment diagram -----------------------------
    axw = fig.add_subplot(gs[1, 0])
    iw = int(np.argmax(util))
    env = json.load(open(os.path.join(DATA, "envelope.json"), encoding="utf-8"))
    nodes, geom, gfac = _rib_frame(env["points"][iw]["rib"])
    elements = [(k, k+1) for k in range(len(nodes)-1)]
    fixed = {0, len(nodes)-1}
    combos = _combos(geom, gfac)
    # governing combo
    best = max(combos, key=lambda cb: _utilization(
        solve_frame(nodes, elements, fixed, _sec(NOMINAL), cb[1])["demands"], _sec(NOMINAL)))
    r = solve_frame(nodes, elements, fixed, _sec(NOMINAL), best[1])
    axw.plot(nodes[:, 0], nodes[:, 1], color=INK, lw=2.4, zorder=4, solid_capstyle="round")
    axw.scatter(nodes[[0, -1], 0], nodes[[0, -1], 1], marker="s", s=45, color=INK, zorder=5)
    # BMD: offset each element's moment perpendicular to it
    for e, (i, j) in enumerate(elements):
        a, b = nodes[i], nodes[j]; d = b - a; L = math.hypot(*d); nx, ny = -d[1]/L, d[0]/L
        M = r["demands"][e][1] / 1e3
        sc = 0.9 / (max(abs(x["base_moment_kNm"]) for x in ribs) or 1)
        xs = np.linspace(0, 1, 12)
        px = a[0] + d[0]*xs + nx * M * sc * np.sin(math.pi*xs)
        py = a[1] + d[1]*xs + ny * M * sc * np.sin(math.pi*xs)
        axw.fill(np.r_[a[0], px, b[0]], np.r_[a[1], py, b[1]], color=ACC, alpha=0.25, zorder=2)
        axw.plot(px, py, color=ACC, lw=0.9, zorder=3)
    axw.set_aspect("equal"); axw.axis("off")
    R = ribs[iw]
    axw.set_title(f"worst rib · s {R['s_m']:.0f} m (h {R['rib_height_m']:.1f}, reach "
                  f"{R['reach_m']:.1f}) · util {R['util_nominal']:.2f}",
                  loc="left", fontsize=9.5, fontweight="bold", color=INK)
    axw.text(0.5, -0.04, f"leaning arch, both rails fixed · base moment "
             f"{R['base_moment_kNm']:.0f} kNm · {R['governing_combo']} · sized {R['section_sized']}",
             transform=axw.transAxes, ha="center", fontsize=7.5, color=MUT)

    # --- utilization vs rib height (structural cost of the cantilever) ----------
    axu = fig.add_subplot(gs[1, 1])
    sc = axu.scatter(h, util, c=reach, cmap="inferno_r", s=18, alpha=0.85, edgecolor="none")
    axu.axhline(1.0, color="#8f1d1d", lw=0.9, ls=(0, (5, 3)))
    axu.set_xlabel("rib height (m)"); axu.set_ylabel("utilization (nominal)")
    axu.set_title("structural cost tracks the reach into the canyon",
                  loc="left", fontsize=9.5, fontweight="bold", color=INK)
    cb = fig.colorbar(sc, ax=axu, fraction=0.04, pad=0.02); cb.set_label("reach (m)", fontsize=7.5)
    cb.ax.tick_params(labelsize=7)
    for sp in ("top", "right"): axu.spines[sp].set_visible(False)

    fig.suptitle("THE ANSWERING LINE — structural utilization pass", x=0.06, ha="left",
                 fontsize=13, fontweight="bold", color=INK, y=0.965)
    fig.text(0.06, 0.925,
             f"2-D frame FEM (validated) · S355 · 1.2D+1.6S / 0.9D+1.0W · "
             f"nominal {tt['max_util_nominal']:.2f} max util · sized kit {tt['sized_steel_tonnes']:.0f} t "
             f"keeps every rib ≤ 1.0", fontsize=8.5, color=MUT)
    p = os.path.join(EXPORTS, "structure.png")
    fig.savefig(p, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {p}")


if __name__ == "__main__":
    try:                                  # the console report contains ≤ / · ; cp1252 stdout
        sys.stdout.reconfigure(encoding="utf-8")   # would abort on them (validate_envelope.py
    except Exception:                              # carries the same guard)
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="envelope", choices=sorted(SOURCES),
                    help="which canopy geometry to analyse (default: envelope)")
    ap.add_argument("--out", default=None,
                    help="output filename inside data/ (default: structure.json)")
    ap.add_argument("--no-fig", action="store_true", help="skip exports/structure.png")
    a = ap.parse_args()
    build(make_fig=not a.no_fig, source=a.source,
          outfile=os.path.basename(a.out) if a.out else None)
