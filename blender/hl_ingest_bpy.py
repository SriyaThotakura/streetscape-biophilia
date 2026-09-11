"""hl_ingest_bpy.py — Blender port of houdini/hl_ingest.py. Same JSON, different consumer.

The JSON contract does not change. Every number here is carried straight from the engine
output; nothing is invented, nothing is scaled, nothing is exaggerated.

USE
    Blender text editor: open this file, set CONFIG below, press Run Script.
    Headless:            blender --background --python blender/hl_ingest_bpy.py

MODES (same four as hl_ingest.py, plus "all")
    ribs     -> one CURVE object, 232 POLY/BEZIER splines from data/envelope.json.
                Per-point radius encodes the SIZED SECTION from data/structure.json, so a
                single bevel_depth produces true CHS 168.3 / CHS 219.1 diameters.
    context  -> 176 prism MESH objects from data/highline_footprints.json, extruded by
                `height`, tagged post2009 / pre2009 / year_unknown.
    deck     -> ONE lofted MESH between the 232 rib start points and the 232 rib end
                points. NOT a resample of the stored 10-point centreline.
    access   -> 10 empties at the weighted entrances, for placing figures.

AXIS CONVERSION — stated once, applied once, checked once.
    Project frame:  +x east, +y UP,    +z north   (documented in data/*.json _meta)
    Blender frame:  +X east, +Y north, +Z UP
    Therefore:      blender = (px, pz, py)                      <- P() below

    The permutation determinant is -1. That is NOT a mirror of the site: it is the
    handedness difference between a (east, up, north) frame and a (east, north, up) frame.
    Semantic axes map one-to-one — east stays east, north stays north, up stays up — so the
    geography, the sun and the shadows are all preserved exactly.

WHAT THIS SCRIPT REFUSES TO DO
    - hardcode a section diameter (imported from build_structure.SECTIONS, or it aborts)
    - join envelope <-> structure on s_m (index only, with a hard assertion)
    - silently treat an unparseable construction_year as pre-2009
    - move a rib vertex for any reason, including to make the canopy read better
"""

import ast
import importlib.util
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
PROJECT = r"C:\Users\ReiChiquita\Desktop\jobs\sriya-portfolio-handoff\sriya-portfolio\Projects\5.CV_Highline"
MODE = "all"              # ribs | context | deck | access | all
SMOOTH_RIBS = True        # BEZIER with AUTO handles: passes exactly through all 5 knots
RIB_RESOLUTION_U = 12     # render-time subdivision between knots. Geometry unchanged.
CLEAR_SCENE = True        # wipe mesh/curve/empty objects before ingesting

DATA = os.path.join(PROJECT, "data")
SCRIPTS = os.path.join(PROJECT, "scripts")
DECK_Y = 9.0              # metres, project frame. Matches hl_ingest.DECK_Y.
EPS = 1e-6                # absolute tolerance, for SMALL-magnitude comparisons only

# ── verification tolerances ──────────────────────────────────────────────────
# Blender stores curve control points as float32. The representable step at a
# coordinate of magnitude m is EPS32 * m, so round-to-nearest storage bounds the
# per-coordinate error at HALF that: 0.5 * EPS32 * m.
#
# This corridor runs to |Y| = 864.70 m, where half-ULP is 5.15e-05 m. An absolute
# 1e-6 tolerance is therefore ~50x tighter than the storage can possibly hold, and
# fails on arithmetic that is exactly correct.
#
# Measured across all 232 ribs (float32 round-trip of envelope.json):
#     worst deviation 2.930e-05 m at |coord| 840 m
#     r(max|coord|, deviation) = +0.908
#     deviation / (EPS32 * max|coord|): max 0.4782  -> 0.956 half-ULPs, never above 1
# i.e. every rib sits inside one half-ULP of its own magnitude, which is the exact
# signature of storage rounding and nothing else.
#
# HALF_ULP_MULT is the headroom over that bound. 4 is chosen because a single
# round-trip is bounded by 1.0 half-ULP and the observed worst case is 0.956, so 4x
# absorbs a second conversion (a matrix apply, a re-read) without ever approaching
# real movement: at 864 m the bound is 2.06e-04 m, while a NURBS conversion or a
# botched transform displaces a knot by centimetres to metres — three to four orders
# of magnitude clear.
EPS32 = float(np.finfo(np.float32).eps)     # 1.1920929e-07, derived not typed
HALF_ULP_MULT = 4.0

# The deck-width check has a DIFFERENT dominant error source: not float32 storage but the
# 2-decimal quantisation envelope.json applies to rib coordinates before they are ever read.
# That term is ~300x larger than the float32 one at this scale, so it governs. The headroom
# multiple is deliberately THE SAME as HALF_ULP_MULT, for the same reason: the theoretical
# bound is a hard ceiling on one rounding pass, and 4x absorbs a second without coming near
# a real error (a wrong DECK_HALF_W or a bad axis map moves the width by metres).
SOURCE_ROUND_MULT = HALF_ULP_MULT


def _detect_decimals(values, max_dp=8):
    """Smallest number of decimal places at which every value is an exact multiple.

    Derives the stored precision from the data instead of assuming it. Returns None if the
    values are not quantised at any dp <= max_dp, which is itself worth aborting on.
    """
    for dp in range(max_dp + 1):
        q = 10.0 ** dp
        if all(abs(v * q - round(v * q)) < 1e-6 for v in values):
            return dp
    return None


def deck_width_bound(coords, max_abs_coord):
    """(theoretical_bound_m, tolerance_m, decimals) for the rail-to-rail distance.

    Two independent error terms, both derived:

    1. SOURCE QUANTISATION — envelope.json stores rib coordinates rounded to `dp` decimals,
       detected from the data. Each coordinate carries up to half a quantum; a 2-D point
       rounded independently in each axis is displaced by at most (quantum/2)*sqrt(2); and
       the distance between two such points is off by at most the sum of the two
       displacements (triangle inequality). So: quantum * sqrt(2).

    2. FLOAT32 STORAGE — the same term verify_ribs uses, evaluated at the largest rail
       coordinate. At this corridor's scale it is ~0.4% of term 1 and is included only so
       the bound is complete rather than approximately right.
    """
    dp = _detect_decimals(coords)
    if dp is None:
        raise RuntimeError(
            "DECK BOUND ABORT: rib coordinates are not quantised at any decimal place "
            "<= 8, so the source-rounding bound cannot be derived. Do not fall back to a "
            "typed tolerance — find out what wrote them.")
    quantum = 10.0 ** (-dp)
    src_term = quantum * math.sqrt(2.0)          # = 2 * (quantum/2) * sqrt(2)
    f32_term = EPS32 * float(max_abs_coord)
    bound = src_term + f32_term
    return bound, SOURCE_ROUND_MULT * bound, dp


def knot_tol(max_abs_coord):
    """Magnitude-scaled tolerance for a coordinate comparison at this scale.

    Floored at EPS so a rib sitting near the origin is not held to a tolerance
    tighter than the absolute one used elsewhere.
    """
    return max(EPS, HALF_ULP_MULT * 0.5 * EPS32 * float(max_abs_coord))


# ─────────────────────────────────────────────────────────────────────────────
# axis conversion — the single place it happens
# ─────────────────────────────────────────────────────────────────────────────
def P(v):
    """Project (x, y_up, z_north) -> Blender (X_east, Y_north, Z_up)."""
    return (float(v[0]), float(v[2]), float(v[1]))


def P2(x, z, y=DECK_Y):
    """Project ground (x, z) at height y -> Blender."""
    return (float(x), float(z), float(y))


def _load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        raise RuntimeError(
            "missing %s\nRun the engines first (see 5.CV_Highline/CLAUDE.md)." % path)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ─────────────────────────────────────────────────────────────────────────────
# SECTIONS — imported, never transcribed
# ─────────────────────────────────────────────────────────────────────────────
def load_sections():
    """Return ({section_name: outside_diameter_m}, provenance_string).

    data/structure.json stores only the section NAME ("CHS 168x6.3"). The outside diameter
    lives in build_structure.py's SECTIONS table and nowhere else in any JSON. Two
    acquisition paths, both programmatic; if both fail this ABORTS rather than falling back
    to a hardcoded number.

    SECTIONS rows are (name, OD_mm, t_mm, A_cm2, Wpl_cm3, I_cm4, kg_m) — OD is index 1.
    """
    src = os.path.join(SCRIPTS, "build_structure.py")
    if not os.path.exists(src):
        raise RuntimeError("cannot find %s — section diameters are unavailable" % src)

    # path 1: import the module and read the live value (authoritative)
    try:
        if SCRIPTS not in sys.path:
            sys.path.insert(0, SCRIPTS)
        spec = importlib.util.spec_from_file_location("_hl_build_structure", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rows = list(mod.SECTIONS)
        how = "imported build_structure.SECTIONS (module executed)"
    except Exception as exc_import:
        # path 2: parse the literal out of the source. No execution, no numpy needed.
        try:
            with open(src, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            rows = None
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                        getattr(t, "id", None) == "SECTIONS" for t in node.targets):
                    rows = [tuple(r) for r in ast.literal_eval(node.value)]
                    break
            if rows is None:
                raise RuntimeError("no module-level SECTIONS assignment found")
            how = ("AST-parsed build_structure.SECTIONS (import failed: %s)"
                   % type(exc_import).__name__)
        except Exception as exc_ast:
            raise RuntimeError(
                "COULD NOT OBTAIN SECTION DIAMETERS.\n"
                "  import path failed: %r\n"
                "  AST path failed:    %r\n"
                "structure.json carries only the section NAME; the diameter lives in\n"
                "%s. Refusing to hardcode it — tell the author and decide explicitly."
                % (exc_import, exc_ast, src))

    table = {r[0]: float(r[1]) / 1000.0 for r in rows}   # OD mm -> m
    return table, how


# ─────────────────────────────────────────────────────────────────────────────
# housekeeping
# ─────────────────────────────────────────────────────────────────────────────
def clear_scene():
    for obj in list(bpy.data.objects):
        if obj.type in {"MESH", "CURVE", "EMPTY"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    for block in (bpy.data.meshes, bpy.data.curves):
        for b in list(block):
            if b.users == 0:
                block.remove(b)


def collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def set_units():
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.unit_settings.scale_length = 1.0
    s.unit_settings.length_unit = "METERS"


# ─────────────────────────────────────────────────────────────────────────────
# ribs
# ─────────────────────────────────────────────────────────────────────────────
def build_ribs():
    env = _load("envelope.json")
    pts = env["points"]
    sections, how = load_sections()
    print("[sections] %s" % how)
    print("[sections] %s" % {k: round(v, 4) for k, v in sections.items()})

    # ---- structure join: BY INDEX, with a hard assertion --------------------------
    try:
        struct = _load("structure.json")
        sribs = struct["ribs"]
    except Exception as exc:
        raise RuntimeError(
            "data/structure.json is required for rib diameters and could not be read: %r\n"
            "Run `python scripts/build_structure.py` first." % exc)

    if len(sribs) != len(pts):
        raise RuntimeError(
            "JOIN ABORT: envelope.json has %d stations, structure.json has %d ribs. "
            "They must be the same length and in the same order." % (len(pts), len(sribs)))
    if len(pts) != 232:
        raise RuntimeError("JOIN ABORT: expected 232 stations, found %d" % len(pts))
    for i, (p, r) in enumerate(zip(pts, sribs)):
        if abs(float(p["s_m"]) - float(r["s_m"])) > 0.1:
            raise RuntimeError(
                "JOIN ABORT at index %d: envelope s_m=%.4f vs structure s_m=%.4f "
                "(differ by more than 0.1 m). The two arrays are not aligned; do NOT "
                "proceed." % (i, p["s_m"], r["s_m"]))
    print("[join] OK — 232 stations, index-aligned, s_m agrees within 0.1 m at every index")

    missing = sorted({r["section_sized"] for r in sribs} - set(sections))
    if missing:
        raise RuntimeError("structure.json names sections absent from SECTIONS: %s" % missing)

    od_max = max(sections[r["section_sized"]] for r in sribs)
    bevel_depth = od_max / 2.0

    cu = bpy.data.curves.new("HL_Ribs", type="CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = RIB_RESOLUTION_U
    cu.bevel_depth = bevel_depth
    cu.bevel_resolution = 4          # 12-gon tube; plenty at these diameters
    cu.use_fill_caps = True

    per_rib = []
    for i, p in enumerate(pts):
        rib = p["rib"]
        if len(rib) < 2:
            continue                  # matches hl_ingest; 0 qualify in the current data
        od = sections[sribs[i]["section_sized"]]
        rad_factor = (od / 2.0) / bevel_depth

        if SMOOTH_RIBS:
            sp = cu.splines.new("BEZIER")
            sp.bezier_points.add(len(rib) - 1)
            for j, v in enumerate(rib):
                bp = sp.bezier_points[j]
                bp.co = P(v)
                bp.handle_left_type = "AUTO"
                bp.handle_right_type = "AUTO"
                bp.radius = rad_factor
        else:
            sp = cu.splines.new("POLY")
            sp.points.add(len(rib) - 1)
            for j, v in enumerate(rib):
                x, y, z = P(v)
                sp.points[j].co = (x, y, z, 1.0)
                sp.points[j].radius = rad_factor
        sp.use_cyclic_u = False
        per_rib.append((i, p, sribs[i], od))

    obj = bpy.data.objects.new("HL_Ribs", cu)
    collection("HL_Canopy").objects.link(obj)

    # per-rib values as object-level custom props are useless for 232 splines, so the
    # authoritative record stays the JSON. What we DO store is the provenance:
    obj["hl_source"] = "data/envelope.json + data/structure.json"
    obj["hl_generated"] = str(env["_meta"].get("generated", ""))
    obj["hl_n_stations"] = int(env["_meta"].get("n_stations", len(pts)))
    obj["hl_bevel_depth_m"] = bevel_depth
    obj["hl_sections"] = json.dumps({k: round(v, 6) for k, v in sections.items()})
    obj["hl_section_provenance"] = how
    for k, v in env["_meta"].get("readback", {}).items():
        if isinstance(v, (int, float)):
            obj["hl_" + k] = float(v)

    verify_spline_types(obj)       # the smoothing guard
    verify_ribs(obj, pts)          # knot fidelity against envelope.json

    n_flat = sum(1 for p in pts if float(p["reach_m"]) == 0.0)
    counts = {}
    for _, _, r, _ in per_rib:
        counts[r["section_sized"]] = counts.get(r["section_sized"], 0) + 1
    print("[ribs] %d splines · bevel_depth %.5f m (OD %.1f mm) · sections %s"
          % (len(cu.splines), bevel_depth, od_max * 1000, counts))
    print("[ribs] %d of %d ribs have reach_m == 0.0 exactly — pure arches, no cantilever. "
          "That is the material-variation story, not a defect." % (n_flat, len(pts)))
    return obj


def verify_spline_types(obj):
    """THE SMOOTHING GUARD. Assert every spline is BEZIER with AUTO handles.

    This is the check the coordinate comparison could never do. Converting to NURBS does
    NOT move a control point — it changes whether the evaluated curve passes THROUGH the
    control points at all — so a coordinate comparison reads clean while the rendered
    tube no longer touches the measured apex. Likewise every Bezier handle type (AUTO,
    VECTOR, ALIGNED, FREE) leaves knots exactly in place; handles steer tangents only.

    So spline type and handle type are the only things that actually decide whether the
    curve interpolates its knots, and they are asserted directly.
    """
    cu = obj.data
    bad_type, bad_handle = [], []
    for si, sp in enumerate(cu.splines):
        if sp.type != "BEZIER":
            bad_type.append((si, sp.type))
            continue
        for bi, bp in enumerate(sp.bezier_points):
            if bp.handle_left_type != "AUTO" or bp.handle_right_type != "AUTO":
                bad_handle.append((si, bi, bp.handle_left_type, bp.handle_right_type))

    if bad_type:
        head = ", ".join("spline %d is %s" % (si, t) for si, t in bad_type[:6])
        raise RuntimeError(
            "SPLINE TYPE ASSERTION FAILED — %d of %d splines are not BEZIER: %s%s\n"
            "A non-BEZIER spline (NURBS especially) does NOT interpolate its control "
            "points, so the rendered curve stops passing through the measured apex while "
            "every coordinate check still reads clean. This is the disallowed case."
            % (len(bad_type), len(cu.splines), head,
               "" if len(bad_type) <= 6 else " ... and %d more" % (len(bad_type) - 6)))
    if bad_handle:
        head = ", ".join("spline %d point %d (%s/%s)" % h for h in bad_handle[:6])
        raise RuntimeError(
            "HANDLE TYPE ASSERTION FAILED — %d control points are not AUTO/AUTO: %s%s\n"
            "Only AUTO is sanctioned here. Other handle types still pass through the "
            "knots, but they change the curve between them, and the rib profile is a "
            "measured shape rather than a styling choice."
            % (len(bad_handle), head,
               "" if len(bad_handle) <= 6 else " ... and %d more" % (len(bad_handle) - 6)))

    print("[verify ribs] spline types            %d/%d BEZIER, all handles AUTO"
          % (len(cu.splines), len(cu.splines)))
    print("[verify ribs] PASS — smoothing changed no geometry (interpolating spline, "
          "knots are on the curve)")


def verify_ribs(obj, pts):
    """KNOT FIDELITY against envelope.json — that the coordinates in the scene are the
    coordinates the engine wrote, within float32 storage precision.

    This is NOT the smoothing guard; `verify_spline_types` is. What this catches is a
    wrong axis map, a stray transform, a units error, a mis-indexed join — anything that
    puts a knot somewhere the JSON did not.

    Tolerance is magnitude-scaled (see knot_tol). A deviation that does NOT scale with
    coordinate magnitude is real movement, not storage, and still aborts.

    Note on `reach_m`: envelope.json stores rib coordinates at 2 dp and reach_m at 2 dp, so
    reach recomputed from the stored coordinates differs from stored reach_m by up to
    ~0.005 m. That is SOURCE ROUNDING, not error. The meaningful test is reach recomputed
    from the knots before vs after storage, which is what is compared here.
    """
    cu = obj.data
    worst_knot = worst_height = worst_end = worst_reach = 0.0
    worst_ratio = 0.0                      # deviation in half-ULPs of its own magnitude
    fail_knot, fail_reach = [], []

    for si, sp in enumerate(cu.splines):
        p = pts[si]
        rib = p["rib"]
        if sp.type == "BEZIER":
            got = [tuple(bp.co) for bp in sp.bezier_points]
        else:
            got = [tuple(pt.co)[:3] for pt in sp.points]
        want = [P(v) for v in rib]

        mag = max(abs(c) for k in want for c in k)
        tol = knot_tol(mag)
        half_ulp = max(0.5 * EPS32 * mag, 1e-30)

        dev = max(abs(a - b) for g, w in zip(got, want) for a, b in zip(g, w))
        worst_knot = max(worst_knot, dev)
        worst_ratio = max(worst_ratio, dev / half_ulp)
        if dev > tol:
            fail_knot.append((si, p["s_m"], mag, dev, tol, dev / half_ulp))

        ai = max(range(len(got)), key=lambda k: got[k][2])
        worst_height = max(worst_height,
                           abs((got[ai][2] - DECK_Y) - float(p["rib_height_m"])))
        worst_end = max(worst_end, abs(got[0][2] - DECK_Y), abs(got[-1][2] - DECK_Y))

        st = (float(p["x"]), float(p["z"]))
        r_now = math.dist(st, (got[ai][0], got[ai][1]))
        r_src = math.dist(st, (want[ai][0], want[ai][1]))
        r_dev = abs(r_now - r_src)
        worst_reach = max(worst_reach, r_dev)
        if r_dev > tol:
            fail_reach.append((si, p["s_m"], mag, r_dev, tol, r_dev / half_ulp))

    mags = [max(abs(c) for v in p["rib"] for c in P(v)) for p in pts]
    print("[verify ribs] float32 eps %.6e · tolerance = %.1f half-ULP x |coord|, floor %.0e m"
          % (EPS32, HALF_ULP_MULT, EPS))
    print("[verify ribs] coord magnitude range   %.2f .. %.2f m  ->  tol %.3e .. %.3e m"
          % (min(mags), max(mags), knot_tol(min(mags)), knot_tol(max(mags))))
    print("[verify ribs] max knot deviation      %.3e m   (%.3f half-ULP of its own scale)"
          % (worst_knot, worst_ratio))
    print("[verify ribs] max reach shift         %.3e m   (storage invariance)" % worst_reach)
    print("[verify ribs] max apex-height error   %.3e m   (vs rib_height_m, abs tol %.0e)"
          % (worst_height, EPS))
    print("[verify ribs] max endpoint-Z error    %.3e m   (vs DECK_Y 9.0, abs tol %.0e)"
          % (worst_end, EPS))

    problems = []
    if fail_knot:
        problems.append("knot fidelity on %d rib(s)" % len(fail_knot))
    if fail_reach:
        problems.append("reach on %d rib(s)" % len(fail_reach))
    if worst_height > EPS:
        problems.append("apex height %.3e > %.0e" % (worst_height, EPS))
    if worst_end > EPS:
        problems.append("endpoint Z %.3e > %.0e" % (worst_end, EPS))

    if problems:
        lines = ["RIB KNOT-FIDELITY CHECK FAILED: " + ", ".join(problems),
                 "",
                 "These coordinates are NOT where envelope.json put them, by more than",
                 "float32 storage can explain. A deviation that does not scale with",
                 "coordinate magnitude is real movement — suspect the axis map, a stray",
                 "object/collection transform, a units change, or a mis-indexed join.",
                 "This check does NOT test smoothing; verify_spline_types does that.", ""]
        for si, s_m, mag, d, tol, ratio in (fail_knot + fail_reach)[:8]:
            lines.append("  spline %3d  s=%8.2f m  |coord| %7.2f m  dev %.3e  "
                         "tol %.3e  (%.2f half-ULP)" % (si, s_m, mag, d, tol, ratio))
        raise RuntimeError("\n".join(lines))

    print("[verify ribs] PASS — knots match envelope.json within float32 storage "
          "precision at every rib")


# ─────────────────────────────────────────────────────────────────────────────
# context
# ─────────────────────────────────────────────────────────────────────────────
def build_context():
    """Context prisms, shaded on a CONTINUOUS ramp by per-building sky share.

    The visual variable is `sky_share_pct` from data/attribution.json, joined by BIN — how
    much of the deck's sky each building actually takes. No threshold, no categories.

    The post-2009 date tag is still computed and still written onto every object as DATA
    (`post2009`, `era`, `year`, `year_known`). It is simply no longer the visual variable:
    the date rule leaves the two largest culprits untinted (both 2006), and a top-N rule
    would invent a threshold the data does not contain. The 2009 date belongs in the
    caption, not in the shading.
    """
    fc = _load("highline_footprints.json")

    # ---- attribution join, by BIN ---------------------------------------------------
    try:
        att = _load("attribution.json")
        share = {str(r["id"]): float(r["sky_share_pct"]) for r in att["leaderboard"]}
    except Exception as exc:
        raise RuntimeError(
            "data/attribution.json is required to shade the context and could not be read: "
            "%r\nRun `python scripts/build_attribution.py` first." % exc)

    fbins = {str(f["properties"].get("id", "")) for f in fc["features"]}
    orphan = sorted(b for b in share if b not in fbins)
    if orphan:
        raise RuntimeError(
            "ATTRIBUTION JOIN ABORT: %d BIN(s) in attribution.json have no footprint: %s\n"
            "The two files are out of step; regenerate rather than shading a partial set."
            % (len(orphan), orphan[:8]))

    ranked = [b for b in fbins if b in share]
    max_share = max((share[b] for b in ranked), default=0.0)
    if max_share <= 0.0:
        raise RuntimeError("ATTRIBUTION ABORT: max sky_share_pct is 0 — nothing to shade.")
    print("[attribution] %d of %d footprints carry a sky share; %d do not"
          % (len(ranked), len(fbins), len(fbins) - len(ranked)))
    print("[attribution] normalising on max sky_share_pct = %.2f%% (BIN %s) — the ramp is "
          "LINEAR in share, so a building that takes twice the sky reads twice as hot"
          % (max_share, max((ranked), key=lambda b: share[b])))

    col_ranked = collection("HL_Context_ranked")
    col_unranked = collection("HL_Context_unranked")

    n_post = n_pre = n_unk = 0
    n_ranked = n_unranked = 0
    post_bins, unk_bins = [], []
    top = []

    for feat in fc.get("features", []):
        g = feat.get("geometry") or {}
        props = feat.get("properties", {})
        gt = g.get("type")
        coords = g.get("coordinates") or []
        rings = []
        if gt == "MultiPolygon":
            for poly in coords:
                if poly:
                    rings.append(poly[0])          # exterior only; holes ignored (2 exist)
        elif gt == "Polygon" and coords:
            rings.append(coords[0])

        h = props.get("height")
        h = float(h) if h is not None else 0.0
        bin_id = str(props.get("id", ""))

        raw_year = props.get("construction_year")
        try:
            year = int(raw_year)
            year_known = True
        except (TypeError, ValueError):
            year = None
            year_known = False

        # the date tag is still recorded as DATA — it is simply not the visual variable
        if not year_known:
            era = "year_unknown"
            n_unk += 1
            unk_bins.append((bin_id, raw_year, h))
        elif year >= 2009:
            era = "post2009"
            n_post += 1
            post_bins.append((bin_id, year, h))
        else:
            era = "pre2009"
            n_pre += 1

        # the SHADING variable
        has_share = bin_id in share
        s_pct = share.get(bin_id)
        s_norm = (s_pct / max_share) if has_share else None
        col = col_ranked if has_share else col_unranked
        if has_share:
            n_ranked += 1
            top.append((s_pct, bin_id, year if year_known else None, h))
        else:
            n_unranked += 1

        for ri, ring in enumerate(rings):
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3 or h <= 0.0:
                continue
            obj = _prism(ring, h, "BLD_%s_%d" % (bin_id, ri))
            obj["bin"] = bin_id
            obj["height_m"] = h
            # --- data, not shading ---
            obj["year"] = year if year_known else -1
            obj["year_known"] = year_known
            obj["era"] = era
            obj["post2009"] = 1 if era == "post2009" else 0
            # --- shading ---
            obj["has_sky_share"] = has_share
            obj["sky_share_pct"] = float(s_pct) if has_share else 0.0
            # sky_share_norm is what the Attribute node reads. Unranked buildings get the
            # NEUTRAL material, not norm 0 on the ramp — "not measured" is not "measured
            # as zero", and the ramp must not be asked to represent an absence.
            obj["sky_share_norm"] = float(s_norm) if has_share else -1.0
            col.objects.link(obj)

    print("[context] shading variable: sky_share_pct (continuous, linear, no threshold)")
    print("[context] ranked %d -> MAT_Context_Share · unranked %d -> MAT_Context_Neutral"
          % (n_ranked, n_unranked))
    print("[context] %d buildings are ABSENT from attribution.json and are shaded neutral. "
          "Absent means not measured, NOT measured-as-zero." % n_unranked)
    top.sort(reverse=True)
    print("[context] top 8 by sky share (this is what the ramp will pick out):")
    for s_pct, b, y, h in top[:8]:
        print("            bin %-10s %6.2f%%  norm %.3f  year %-6s height %6.2f m"
              % (b, s_pct, s_pct / max_share, y if y is not None else "?", h))
    n_low = sum(1 for s, _, _, _ in top if s < 0.1)
    print("[context] %d of %d ranked buildings take less than 0.1%% each — the ramp will "
          "leave them near the floor, which is the measurement, not a rendering failure"
          % (n_low, n_ranked))
    print("[context] date tag retained as DATA only: post2009 %d · pre2009 %d · "
          "year_unknown %d" % (n_post, n_pre, n_unk))
    for b, y, h in sorted(post_bins, key=lambda r: -r[2]):
        print("            post2009  bin %-10s year %d  height %6.2f m" % (b, y, h))
    if unk_bins:
        print("[context] construction_year unparseable (still shaded by share, since share "
              "does not depend on the year):")
        for b, raw, h in unk_bins:
            print("            bin %-10s raw year %r  height %6.2f m" % (b, raw, h))
    return n_ranked, n_unranked


def _prism(ring, h, name):
    """Closed prism from a footprint ring: bottom at Z=0, top at Z=h, walls + cap.
    Built directly, no operators — deterministic and headless-safe."""
    n = len(ring)
    verts = [(float(c[0]), float(c[1]), 0.0) for c in ring]          # project (x,z) -> Blender (X,Y)
    verts += [(float(c[0]), float(c[1]), float(h)) for c in ring]
    faces = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    faces.append([n + i for i in range(n)])                          # roof
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    return bpy.data.objects.new(name, me)


# ─────────────────────────────────────────────────────────────────────────────
# deck — lofted between the rib rails, NOT resampled from the 10-point centreline
# ─────────────────────────────────────────────────────────────────────────────
def build_deck():
    env = _load("envelope.json")
    pts = env["points"]
    left = [P(p["rib"][0]) for p in pts]
    right = [P(p["rib"][-1]) for p in pts]

    # expected width is derived from the generator's own parameter, not typed
    half_w = float(env["_meta"]["params"]["DECK_HALF_W"])
    expected = 2.0 * half_w

    # the bound is derived from the stored decimal precision of the rail coordinates
    coords = [c for p in pts for v in (p["rib"][0], p["rib"][-1]) for c in (v[0], v[2])]
    bound, tol, dp = deck_width_bound(coords, max(abs(c) for c in coords))

    widths = [math.dist(l, r) for l, r in zip(left, right)]
    w_min, w_max = min(widths), max(widths)
    dev = max(abs(w_min - expected), abs(w_max - expected))
    ratio = dev / bound

    print("[deck] source precision   %d dp -> quantum %.3f m; bound = quantum*sqrt(2) + "
          "float32 = %.6f m" % (dp, 10.0 ** (-dp), bound))
    print("[deck] tolerance          %.1f x bound = %.6f m   (expected width %.2f m from "
          "DECK_HALF_W %.2f)" % (SOURCE_ROUND_MULT, tol, expected, half_w))
    print("[deck] rail-to-rail width min %.4f m  max %.4f m  ->  worst deviation %.4f m "
          "(%.2fx the source-rounding bound)" % (w_min, w_max, dev, ratio))
    if dev > tol:
        raise RuntimeError(
            "DECK WIDTH CHECK FAILED: rail-to-rail width %.4f..%.4f m against an expected "
            "%.2f m (DECK_HALF_W %.2f x 2).\n"
            "  worst deviation %.4f m = %.2fx the source-rounding bound of %.6f m, "
            "tolerance %.6f m\n"
            "A deviation this far beyond the bound is not 2-dp storage — the axis "
            "conversion is wrong, or rib[0]/rib[-1] are not the rails, or DECK_HALF_W no "
            "longer matches the geometry. Stop."
            % (w_min, w_max, expected, half_w, dev, ratio, bound, tol))

    zs = [v[2] for v in left + right]
    if max(abs(z - DECK_Y) for z in zs) > 1e-9:
        raise RuntimeError("DECK LEVEL CHECK FAILED: rail endpoints are not all at Z=9.0")

    n = len(pts)
    verts = left + right
    faces = [[i, i + 1, n + i + 1, n + i] for i in range(n - 1)]
    me = bpy.data.meshes.new("HL_Deck")
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    obj = bpy.data.objects.new("HL_Deck", me)
    collection("HL_Site").objects.link(obj)
    obj["hl_source"] = "data/envelope.json :: lofted between points[].rib[0] and rib[-1]"
    obj["hl_method"] = ("lofted across 232 stations at ~8 m spacing — NOT a resample of "
                        "high_line.centerline, whose 10 points span 1856.7 m and would cut "
                        "corners on every curve")
    print("[deck] %d quads across %d stations" % (len(faces), n))
    return obj


def build_ground():
    """A flat ground plane at Z=0, sized to the real extent. Absent from all source data —
    this is scene furniture, declared as such, and it does not touch the canopy."""
    fc = _load("highline_footprints.json")
    xs, ys = [], []
    for feat in fc["features"]:
        for poly in feat["geometry"]["coordinates"]:
            for c in poly[0]:
                xs.append(float(c[0]))
                ys.append(float(c[1]))
    pad = 200.0
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    verts = [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)]
    me = bpy.data.meshes.new("HL_Ground")
    me.from_pydata(verts, [], [[0, 1, 2, 3]])
    me.update()
    obj = bpy.data.objects.new("HL_Ground", me)
    collection("HL_Site").objects.link(obj)
    obj["hl_source"] = "NOT IN THE DATA — scene furniture, invented for the render"
    print("[ground] %.0f x %.0f m plane at Z=0 (declared invented; no source)"
          % (x1 - x0, y1 - y0))
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# access
# ─────────────────────────────────────────────────────────────────────────────
def build_access():
    fc = _load("highline_footprints.json")
    hl = fc.get("high_line") or {}
    col = collection("HL_Access")
    for a in hl.get("access_points", []):
        e = bpy.data.objects.new("ACCESS_%s" % a.get("name", "?"), None)
        e.empty_display_type = "PLAIN_AXES"
        e.empty_display_size = 3.0
        e.location = P2(a["x"], a["z"], DECK_Y)
        e["weight"] = float(a.get("weight", 1.0))
        e["name_src"] = str(a.get("name", ""))
        col.objects.link(e)
    print("[access] %d entrances placed at deck level" % len(hl.get("access_points", [])))


# ─────────────────────────────────────────────────────────────────────────────
# the axis check that must pass before anything else is trusted
# ─────────────────────────────────────────────────────────────────────────────
def axis_check():
    """Verify the conversion against a known rib, by value, before any geometry is built."""
    env = _load("envelope.json")
    p = env["points"][100]
    v = p["rib"][2]                                   # the apex knot
    b = P(v)
    print("[axis] station s=%.2f  apex project (x=%.2f, y_up=%.2f, z_north=%.2f)"
          % (p["s_m"], v[0], v[1], v[2]))
    print("[axis]                 apex blender (X=%.2f, Y=%.2f, Z=%.2f)" % b)
    assert abs(b[0] - v[0]) < EPS, "X must carry project x (east)"
    assert abs(b[1] - v[2]) < EPS, "Y must carry project z (north)"
    assert abs(b[2] - v[1]) < EPS, "Z must carry project y (up)"
    assert abs(b[2] - (DECK_Y + p["rib_height_m"])) < 0.005, (
        "apex Z must equal DECK_Y + rib_height_m; got %.4f vs %.4f"
        % (b[2], DECK_Y + p["rib_height_m"]))
    print("[axis] PASS — Z carries height (%.2f m = 9.0 + %.2f), Y carries north"
          % (b[2], p["rib_height_m"]))


def scale_check():
    """A 1.7 m reference cube at deck level. Checked against DECK_Y and the REALISED
    maximum rib height (7.04 m), not the 7.5 m generator ceiling in _meta.params."""
    env = _load("envelope.json")
    h_max = max(float(p["rib_height_m"]) for p in env["points"])
    me = bpy.data.meshes.new("SCALE_CHECK_1m7")
    s = 1.7
    verts = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0),
             (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4],
             [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new("SCALE_CHECK_1m7", me)
    p0 = env["points"][0]
    obj.location = P2(p0["x"], p0["z"], DECK_Y)
    collection("HL_Checks").objects.link(obj)
    print("[scale] 1.70 m cube placed at deck level Z=%.2f" % DECK_Y)
    print("[scale] realised max rib height %.2f m  (generator ceiling RIB_MAX_H=%.1f is NOT "
          "reached)" % (h_max, env["_meta"]["params"]["RIB_MAX_H"]))
    print("[scale] the cube must be ~1/4 the height of the tallest rib and ~1/5 the deck "
          "elevation. If it is not, STOP.")
    return obj


# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 74)
    print("hl_ingest_bpy — mode %r" % MODE)
    print("=" * 74)
    set_units()
    if CLEAR_SCENE:
        clear_scene()

    axis_check()
    scale_check()

    if MODE in ("ribs", "all"):
        build_ribs()
    if MODE in ("context", "all"):
        build_context()
    if MODE in ("deck", "all"):
        build_deck()
        build_ground()
    if MODE in ("access", "all"):
        build_access()

    print("=" * 74)
    print("done. Nothing was scaled; no vertical exaggeration was applied.")
    print("=" * 74)


if __name__ == "__main__":
    main()
