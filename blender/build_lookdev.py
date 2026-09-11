"""build_lookdev.py — everything between the ingest and the render, built from JSON.

    blender --background --factory-startup --python blender/build_lookdev.py

Writes blender/answering_line.blend: geometry (via hl_ingest_bpy) + materials, world,
sun, the four cameras, the scale figures, Cycles settings, passes and the compositor.

WHY THIS EXISTS
    BLENDER_BUILD_STEPS.md §"Scope" deferred a headless render script, on the grounds that
    a script which only re-renders is "reproducible given a .blend nobody can regenerate."
    Its own conclusion was: build it WHOLE when you build it, materials included. This is
    that script. Nothing in the scene is hand-set, so a lost .blend costs look-dev nothing.

WHAT IS DERIVED AND WHAT IS A CHOICE
    Derived (do not edit — change the data or the emitter instead):
        clip end, section ortho scale, expected counts, shadow reference tower
            -> pick_cameras.render_build_constants(), parsed, never re-derived here
        camera positions and targets                     -> cameras.json :: stations[]
        sun direction                                    -> cameras.json :: key_light
        context colour per building                      -> attribution.json, via the
                                                            sky_share_norm object property
        plate D's ortho scale and camera position        -> fitted to the geometry
        figure positions along the deck                  -> nearest stations to the camera

    Editorial (yours to change — BUILD_STEPS §13.2 says composition, palette and framing
    are the author's, and this file is where they live instead of in a .blend):
        the material values in MATERIALS                 -> §7 starting values
        the ramp stops in RAMP                           -> §6.2 starting values
        LENS_MM, MIST, the exposure and the curve        -> framing and grade
        AXO_VIEW_DIR                                     -> plate D's framing, §9.4
        FIGURE_DISTANCES_M                               -> where the people stand, §10

WHAT IT REFUSES TO DO
    - move, scale or exaggerate any geometry (THE_ANSWERING_LINE.md)
    - place a light that is not the measured winter vector
    - position a camera by eye where cameras.json has one
    - type a constant that pick_cameras.py already emits
"""

import contextlib
import io
import json
import math
import os
import re
import sys

import bpy
import mathutils
from mathutils import Euler, Vector

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
PROJECT = r"C:\Users\ReiChiquita\Desktop\jobs\sriya-portfolio-handoff\sriya-portfolio\Projects\5.CV_Highline"
BLEND_OUT = os.path.join(PROJECT, "blender", "answering_line.blend")

sys.path.insert(0, os.path.join(PROJECT, "blender"))
sys.path.insert(0, os.path.join(PROJECT, "houdini"))

import hl_ingest_bpy as ing          # noqa: E402  — P(), DECK_Y, the whole ingest
import pick_cameras as pc            # noqa: E402  — the constants authority

# §1: the axis map lives in ONE place — ing.P. Never redefine it here; only wrap it,
# because it returns a plain tuple and every use below wants a Vector.
_P = ing.P


def P(v):
    return Vector(_P(v))


DECK_Y = ing.DECK_Y

# ─────────────────────────────────────────────────────────────────────────────
# THE PALETTE — not invented here.
#
# `refrences/pintest_layouts/visual-language.html`, project id "5", names five colours by
# role and three visual systems: ramp (S03), line (S06), studio (S12). §7's original
# values predate that file and were a different register entirely — a photographic
# architectural render, where the governing note asks for
#
#     "Neutral light, no lens flare, no volumetrics. The register is measurement,
#      not cinema."
#
# S03 also decides how the context is coloured: "put the analysed surface on a plain grey
# or white context so the ramp is the only saturated thing on the page." So the city is
# near-paper and the ONLY saturated thing in the frame is the sky-share ramp.
# ─────────────────────────────────────────────────────────────────────────────
PAL = {
    "paper":    (0.949, 0.941, 0.925),   # #f2f0ec
    "steel":    (0.169, 0.169, 0.157),   # #2b2b28
    "shade":    (0.604, 0.643, 0.682),   # #9aa4ae
    "detected": (0.310, 0.690, 0.659),   # #4fb0a8 — reserved for the CV overlay strip
    "flagged":  (0.878, 0.282, 0.239),   # #e0483d
}


def _srgb(c):
    """sRGB -> linear. Blender's Base Color is linear; a hex pasted raw renders too light."""
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


MATERIALS = {
    "MAT_Steel":            dict(base=_srgb(PAL["steel"]), metallic=1.0, rough=0.42),
    # "not measured" — near-paper, so it reads as the plain white context S03 asks for
    "MAT_Context_Neutral":  dict(base=_srgb((0.898, 0.890, 0.875)), metallic=0.0, rough=0.85),
    "MAT_Paving":           dict(base=_srgb((0.836, 0.828, 0.812)), metallic=0.0, rough=0.80),
    "MAT_Ground":           dict(base=_srgb(PAL["paper"]), metallic=0.0, rough=0.95),
    # §10 requires figures and gives them no material. `steel`, so they read as silhouette.
    "MAT_Figure":           dict(base=_srgb(PAL["steel"]), metallic=0.0, rough=0.85),
}
# §6.2's ramp: linear, two stops, no gamma on the Fac input. The stops are now the
# palette's own — a near-paper floor for "takes nothing measurable", `flagged` for the top.
RAMP = [(0.00, _srgb((0.878, 0.867, 0.847))),
        (1.00, _srgb(PAL["flagged"]))]

LENS_MM = 35.0                           # §9.2 — the honest compromise. 24 cheats, 50 is flat.

# §9.4 — plate D is the one camera with no cameras.json entry, so its DIRECTION is a
# framing choice and is stated here rather than hidden inside a .blend. Everything else
# about D (position, ortho scale, clip range) is fitted to the geometry below. Looking
# west and slightly south, pitched down ~34°, so the 1.73 km corridor lies across the
# wide frame and the height/reach gradient can be read along its length.
AXO_VIEW_DIR = Vector((-1.0, -0.25, -0.70)).normalized()
AXO_FIT_RADIUS_M = 150.0                 # context within this distance of a rib is framed
# §9.3's own rule for the section frame: the tallest wall plus this much headroom.
SECTION_HEADROOM_M = 5.0

# §10 — three figures, at these distances in front of camera A, on the deck. Composition.
FIGURE_DISTANCES_M = (12.0, 26.0, 58.0)
FIGURE_HEIGHT_M = 1.70                   # §10, and asserted against SCALE_CHECK_1m7

# §12.1 gives A (50 / 1200) and the axo (0 / 2000) as starting numbers, and warns that
# "mist that saturates to white by 100 m gives a flat card." Typed ranges did exactly that
# here — the first drafts came back washed to pale at every distance — so the range is now
# DERIVED per camera from how far that camera's own subject actually is: see
# mist_range_for(). MIST_PCT is the only choice left, and it is a grade choice.
MIST_PCT = (2.0, 98.0)           # percentile of visible depth for mist start / mist end

# §12.2: "Do the brightness here, not by raising the sun strength, so the sun keeps its
# measured angle." It also says work in +/-0.5 stops — which assumes every camera stands in
# open air. Camera A does not (see the [clearance] report): it stands inside a prism, in a
# relief-cut passage, and the frame it returns is legitimately several stops darker than the
# other three. So exposure is per plate. THESE ARE GRADE CHOICES AND THEY ARE YOURS —
# override any of them from the command line with `--exposure N`.
EXPOSURE = {"A_hero_eye_level":    -0.9,
            "B_open_contrast":      0.0,
            "C_section_worst_core": 0.0,
            "D_corridor_axo":       0.0}
# ALL FOUR ARE 0.0 AGAIN. A carried +2.5 between 2026-08-20 morning and the clearance fix
# that afternoon, and that was never a grade decision — it was compensation for a camera
# buried inside BIN 1089968, which returned a mean of 23/255. With the camera in open air
# the same plate reads 132/255 at 0.0 and 196/255 at +2.5, where the deck and the sky-share
# tint on the canyon wall both wash out. Fixing the cause removed the need for the fudge.
# Compare for yourself with `--exposure N --suffix _evN`.

# §9.4: "Colour the ribs by height if you wish — but by reading rib_height_m from
# envelope.json by index, not by hand-selecting." Used on plate D only; see
# _steel_by_height() for how it reads height without hand-selecting anything.
RIB_HEIGHT_RAMP = [(0.00, (0.30, 0.32, 0.35)),     # at the deck plane
                   (1.00, (0.86, 0.42, 0.20))]     # at the tallest realised apex

# §11.3 — plate resolutions.
RESOLUTION = {"A_hero_eye_level":     (3508, 2480),
              "B_open_contrast":      (3508, 2480),
              "C_section_worst_core": (2400, 3000),
              "D_corridor_axo":       (4000, 1600)}

# RENDER-ONLY RELIEF CUT — read build_corridor_relief()'s docstring before touching this.
# The High Line physically passes THROUGH buildings, and highline_footprints.json extrudes
# every footprint as a solid prism from Z=0, so 40.8% of the deck is buried inside solid
# geometry and camera A renders the inside of a black box.
CORRIDOR_RELIEF = True

# S12's "soft fill". One flat value, no gradient — the sun lamp is the only key.
WORLD_FILL = 1.15

# WHICH PLATES CARRY THE SKY-SHARE RAMP.
#
# S03: "put the analysed surface on a plain grey or white context so the ramp is the only
# saturated thing on the page." S06: "if you need emphasis, add exactly one colour and use
# it on under 5% of the marks."
#
# At EYE LEVEL both canyon walls are high-ranked buildings, so the ramp paints most of the
# frame and satisfies neither rule — the first render in this register came back solid
# pink, walls and bounced light together. The ramp is an ANALYTICAL overlay and it belongs
# on the plate that shows the whole city, where the hot buildings really are a small
# fraction of the marks. The hero is S12 Studio Object: a near-white city, a dark steel
# canopy, and people.
#
# Nothing is hidden by this. The ramp still carries the same measurement on D, the object
# properties are unchanged on every plate, and a cryptomatte pick still finds any BIN.
CONTEXT_RAMP_PLATES = {"D_corridor_axo"}

AXO_ID = "D_corridor_axo"
# the File Output socket name. Blender appends it to file_name, so render_all.py
# strips it back off — see tidy_png() there.
PNG_SLOT = "Grade"


def log(*a):
    print(*a)
    sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# THE CONSTANTS — parsed from pick_cameras, never re-derived
# ─────────────────────────────────────────────────────────────────────────────
def build_constants():
    """Run pick_cameras' own emitter and read the numbers off it.

    Deliberately a PARSE and not a re-implementation. If the emitter's formula for the
    clip end or the section ortho scale ever changes, this picks the change up; if a label
    changes, the parse fails loudly and the build stops. The alternative — copying the
    three-line formulas into this file — is exactly the drift that
    §"Every number in this document is a KEY" exists to prevent.
    """
    doc = json.load(open(os.path.join(PROJECT, "houdini", "cameras.json"), encoding="utf-8"))
    src = pc._load_sources()
    if src is None:
        raise RuntimeError("houdini/sources.json not found")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        text = pc.render_build_constants(doc, src)

    def grab(pattern, cast=float, label=""):
        m = re.search(pattern, text)
        if not m:
            raise RuntimeError(
                "BUILD CONSTANTS PARSE FAILED for %s.\n"
                "pick_cameras.render_build_constants() no longer emits the line this build "
                "reads. Fix the pattern here — do NOT re-derive the value locally." % label)
        return cast(m.group(1).replace(",", ""))

    c = dict(
        clip_end=grab(r"-> CLIP END[^\n]*?([\d,]+) m", float, "CLIP END"),
        ortho_c=grab(r"-> ORTHO_SCALE\s+([\d.]+)", float, "ORTHO_SCALE"),
        n_splines=grab(r"HL_Ribs splines\s+(\d+)", int, "splines"),
        n_ctrlpts=grab(r"HL_Ribs control points\s+(\d+)", int, "control points"),
        n_ranked=grab(r"HL_Context_ranked\s+(\d+)", int, "ranked"),
        n_unranked=grab(r"HL_Context_unranked\s+(\d+)", int, "unranked"),
        n_deck_verts=grab(r"HL_Deck vertices / faces\s+(\d+)", int, "deck verts"),
        n_access=grab(r"HL_Access empties\s+(\d+)", int, "access"),
        rib_max_m=grab(r"rib height, realised maximum\s+([\d.]+)", float, "rib max"),
        tall_wall_c=grab(r"tallest wall within 80 m\s+([\d.]+)", float, "tallest wall"),
        ref_bin=grab(r"REFERENCE TOWER\s+BIN (\d+)", str, "reference tower BIN"),
        ref_h=grab(r"REFERENCE TOWER\s+BIN \d+\s+([\d.]+) m tall", float, "tower height"),
        ref_shadow=grab(r"must cast ([\d,.]+) m of shadow", float, "shadow length"),
    )
    c["doc"] = doc
    log("[const] parsed from pick_cameras.render_build_constants() — nothing re-derived here")
    log("[const]   clip end %.0f m · ortho C %.0f · rib max %.2f m"
        % (c["clip_end"], c["ortho_c"], c["rib_max_m"]))
    log("[const]   reference tower BIN %s, %.2f m -> %.1f m of shadow, running NORTH"
        % (c["ref_bin"], c["ref_h"], c["ref_shadow"]))
    return c


# ─────────────────────────────────────────────────────────────────────────────
# GEOMETRY — reuse the ingest, do not duplicate a line of it
# ─────────────────────────────────────────────────────────────────────────────
def ensure_geometry():
    if bpy.data.objects.get("HL_Ribs") is None:
        log("[geom] no HL_Ribs in scene — running hl_ingest_bpy.main()")
        ing.main()
    else:
        log("[geom] HL_Ribs present — reusing the ingested scene")
    # factory-startup ships a cube, a camera and a light; the ingest's clear_scene()
    # removes mesh/curve/empty objects but the default camera and light survive.
    for name in ("Camera", "Light"):
        o = bpy.data.objects.get(name)
        if o is not None:
            log("[geom] removing factory-startup %r" % name)
            bpy.data.objects.remove(o, do_unlink=True)


def verify_counts(c):
    ribs = bpy.data.objects["HL_Ribs"]
    got = dict(
        n_splines=len(ribs.data.splines),
        n_ctrlpts=sum(len(s.bezier_points) or len(s.points) for s in ribs.data.splines),
        n_ranked=len(bpy.data.collections["HL_Context_ranked"].objects),
        n_unranked=len(bpy.data.collections["HL_Context_unranked"].objects),
        n_deck_verts=len(bpy.data.objects["HL_Deck"].data.vertices),
        n_access=len(bpy.data.collections["HL_Access"].objects),
    )
    bad = [(k, c[k], got[k]) for k in got if c[k] != got[k]]
    if bad:
        raise RuntimeError("COUNT MISMATCH vs build constants: "
                           + ", ".join("%s expected %s got %s" % b for b in bad))
    log("[counts] PASS — %d splines / %d control points, %d ranked + %d unranked, "
        "deck %d verts, %d access"
        % (got["n_splines"], got["n_ctrlpts"], got["n_ranked"], got["n_unranked"],
           got["n_deck_verts"], got["n_access"]))


# ─────────────────────────────────────────────────────────────────────────────
# MATERIALS — §6.2 and §7
# ─────────────────────────────────────────────────────────────────────────────
def _plain(name, spec):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*spec["base"], 1.0)
    b.inputs["Metallic"].default_value = spec["metallic"]
    b.inputs["Roughness"].default_value = spec["rough"]
    return m


def _share_material():
    """Attribute(Object, 'sky_share_norm') -> ColorRamp -> Base Color.

    ONE material shades every ranked building from its own measured value. §6.2: never
    assign a colour per object. The ramp is LINEAR in share — a building that takes twice
    the sky reads twice as hot — and there is deliberately no gamma on the Fac input.
    """
    name = "MAT_Context_Share"
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Roughness"].default_value = 0.75

    for n in list(nt.nodes):
        if n.type in ("ATTRIBUTE", "VALTORGB"):
            nt.nodes.remove(n)
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "OBJECT"
    attr.attribute_name = "sky_share_norm"
    attr.location = (-620, 0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-400, 0)
    els = ramp.color_ramp.elements
    while len(els) > len(RAMP):
        els.remove(els[-1])
    for i, (pos, col) in enumerate(RAMP):
        el = els[i] if i < len(els) else els.new(pos)
        el.position = pos
        el.color = (*col, 1.0)
    ramp.color_ramp.interpolation = "LINEAR"
    nt.links.new(attr.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def _steel_by_height(c):
    """§9.4's rib colouring, driven by geometry rather than by hand-selection.

    §4's Spreadsheet warning is the constraint: Blender curve splines do NOT carry arbitrary
    named attributes, so `rib_height_m` cannot simply be put on the curve the way
    `sky_share_norm` sits on a context object. What CAN be read per-point in a shader is
    world position — and the identity that makes that sufficient is exact:

        apex Z  ==  DECK_Y + rib_height_m          (asserted every run by verify_ribs)

    So ramping on (world Z - DECK_Y) / envelope_rib_max_m gives every rib's apex precisely
    its own normalised height, and fades down its legs toward the deck. Nothing is
    hand-selected, nothing is invented, and no vertex moves. The ceiling is the REALISED
    maximum, never RIB_MAX_H.

    This is a plate-D material. §7's one-material MAT_Steel still governs A, B and C: on
    those plates the ribs differ in SIZE, which is the argument there.
    """
    m = bpy.data.materials.get("MAT_Steel_ByHeight") or \
        bpy.data.materials.new("MAT_Steel_ByHeight")
    m.use_nodes = True
    nt = m.node_tree
    for node in list(nt.nodes):
        if node.type in ("NEW_GEOMETRY", "SEPXYZ", "MAP_RANGE", "VALTORGB"):
            nt.nodes.remove(node)
    b = nt.nodes["Principled BSDF"]
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.35

    geo = nt.nodes.new("ShaderNodeNewGeometry"); geo.location = (-900, 0)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); sep.location = (-720, 0)
    rng = nt.nodes.new("ShaderNodeMapRange");    rng.location = (-540, 0)
    rng.inputs["From Min"].default_value = DECK_Y
    rng.inputs["From Max"].default_value = DECK_Y + c["rib_max_m"]
    rng.clamp = True
    ramp = nt.nodes.new("ShaderNodeValToRGB");   ramp.location = (-340, 0)
    els = ramp.color_ramp.elements
    while len(els) > len(RIB_HEIGHT_RAMP):
        els.remove(els[-1])
    for i, (pos, col) in enumerate(RIB_HEIGHT_RAMP):
        el = els[i] if i < len(els) else els.new(pos)
        el.position = pos
        el.color = (*col, 1.0)
    ramp.color_ramp.interpolation = "LINEAR"

    nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], rng.inputs["Value"])
    nt.links.new(rng.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    # Nothing is assigned this material at build time — render_all swaps it in for plate D
    # only. Without a fake user Blender purges a zero-user material on save, and the swap
    # then silently no-ops: plate D comes back in plain MAT_Steel with no warning worth the
    # name. This one line is the difference.
    m.use_fake_user = True
    log("[mat] MAT_Steel_ByHeight: world Z ramped %.2f .. %.2f m (DECK_Y .. DECK_Y + "
        "realised rib max). Plate D only — §9.4." % (DECK_Y, DECK_Y + c["rib_max_m"]))
    return m


def assign(objs, mat):
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(mat)


def build_materials(c):
    mats = {k: _plain(k, v) for k, v in MATERIALS.items()}
    mats["MAT_Context_Share"] = _share_material()
    mats["MAT_Steel_ByHeight"] = _steel_by_height(c)

    assign([bpy.data.objects["HL_Ribs"]], mats["MAT_Steel"])
    assign(bpy.data.collections["HL_Context_ranked"].objects, mats["MAT_Context_Share"])
    assign(bpy.data.collections["HL_Context_unranked"].objects, mats["MAT_Context_Neutral"])
    assign([bpy.data.objects["HL_Deck"]], mats["MAT_Paving"])
    assign([bpy.data.objects["HL_Ground"]], mats["MAT_Ground"])
    log("[mat] 6 materials · ramp on %d ranked, neutral on %d unranked, steel on the ribs"
        % (len(bpy.data.collections["HL_Context_ranked"].objects),
           len(bpy.data.collections["HL_Context_unranked"].objects)))

    # §6.2's own CHECK, run as an assertion instead of by eye.
    ranked = list(bpy.data.collections["HL_Context_ranked"].objects)
    top = sorted(ranked, key=lambda o: -float(o.get("sky_share_norm", -1.0)))[:5]
    att = ing._load("attribution.json")
    lead = att["leaderboard"][:5]
    mx = float(lead[0]["sky_share_pct"])
    for o, row in zip(top, lead):
        want = float(row["sky_share_pct"]) / mx
        got = float(o["sky_share_norm"])
        if abs(want - got) > 1e-9 or o["bin"] != str(row["id"]):
            raise RuntimeError("RAMP JOIN FAILED: %s has norm %.9f, attribution rank says "
                               "BIN %s norm %.9f" % (o.name, got, row["id"], want))
    log("[mat] PASS — top 5 by sky_share_norm are attribution ranks 1-5, "
        "norms = share / %.2f%% (BIN %s)" % (mx, lead[0]["id"]))
    for o in bpy.data.collections["HL_Context_unranked"].objects:
        if float(o.get("sky_share_norm", 0.0)) != -1.0:
            raise RuntimeError("UNRANKED LEAK: %s carries sky_share_norm %s — unranked must "
                               "be -1.0 so a mis-assignment to the ramp is visible rather "
                               "than silent (§6.2)" % (o.name, o.get("sky_share_norm")))
    log("[mat] PASS — every unranked building carries sky_share_norm = -1.0 (not measured, "
        "not measured-as-zero)")

    # §2's 1.70 m reference cube is a VIEWPORT check — "CHECK, by eye in the viewport,
    # numeric front view" — and §10 uses it the same way, to compare an imported figure
    # against. It is not scene furniture and it must never reach a plate. It sits on the
    # deck at station 0, which is 48 m from camera B: close enough to appear in frame as an
    # unexplained grey box. Caught 2026-08-20 by the material verifier, in a rendered plate.
    cube = bpy.data.objects.get("SCALE_CHECK_1m7")
    if cube is not None:
        cube.hide_render = True
        log("[mat] SCALE_CHECK_1m7 hidden from render — it is a viewport check (§2, §10), "
            "not scene furniture, and it stands on the deck 48 m from camera B")

    return mats


def verify_materials_visible():
    """Every object the CAMERA can see must carry a material. Run last, not in
    build_materials(), because the figures do not exist yet at that point.

    "Assigned" is not "visible", and this project has now been bitten by both directions:
    MAT_Steel_ByHeight was assigned and then PURGED on save for having no users, and
    SCALE_CHECK_1m7 was visible while carrying no material at all — a debug cube rendering
    as default grey on the deck, 48 m from camera B. Neither showed up in a build log that
    only reported what it had assigned.
    """
    bad = []
    for o in bpy.data.objects:
        if o is None or o.type not in ("MESH", "CURVE") or o.hide_render:
            continue
        if not o.material_slots or o.material_slots[0].material is None:
            bad.append(o.name)
    if bad:
        raise RuntimeError(
            "%d renderable objects have NO material: %s. An unmaterialed object still "
            "renders — as default grey — so this is a visible defect, not a warning."
            % (len(bad), bad[:6]))
    used = {}
    for o in bpy.data.objects:
        if o is None or o.type not in ("MESH", "CURVE") or o.hide_render:
            continue
        nm = o.material_slots[0].material.name
        used[nm] = used.get(nm, 0) + 1
    log("[mat] PASS — every object visible to the render carries a material: "
        + " · ".join("%s x%d" % kv for kv in sorted(used.items())))


# ─────────────────────────────────────────────────────────────────────────────
# SUN — §8. Vector method, checked against the explicit Euler.
# ─────────────────────────────────────────────────────────────────────────────
def report_clearance(c, cams):
    """Report which committed cameras stand inside a footprint prism. DOES NOT ABORT.

    `pick_cameras.py` positions the cameras by offsetting from a station — HERO_BACK 25 m
    along the deck, SECTION_OFFSET 45 m across it — and never tests whether the resulting
    point is in open air. On the current footprint set it is not, twice. That is an upstream
    question: fixing it means a clearance test in pick_cameras.py and a regenerated
    cameras.json, which moves s_m and every caption with it. So this reports rather than
    decides, and it reports on EVERY build so the condition can never go quiet again.
    """
    fc = ing._load("highline_footprints.json")
    prisms = [(f["properties"]["id"], float(f["properties"]["height"]),
               f["geometry"]["coordinates"][0][0]) for f in fc["features"]]

    def inside(x, y, ring):
        c_, j = False, len(ring) - 1
        for i in range(len(ring)):
            xi, yi = float(ring[i][0]), float(ring[i][1])
            xj, yj = float(ring[j][0]), float(ring[j][1])
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                c_ = not c_
            j = i
        return c_

    bad = 0
    for st in c["doc"]["stations"]:
        cam = cams[st["id"]]
        x, y, z = cam.location
        hits = [(b, h) for b, h, r in prisms if h > z and inside(x, y, r)]
        if hits:
            bad += 1
            worst = max(hits, key=lambda t: t[1])
            log("[clearance] *** %s IS INSIDE prism BIN %s (%.2f m tall, camera Z %.2f). "
                "pick_cameras.py has no clearance test; this camera renders the inside of a "
                "closed box unless something cuts it open. ***"
                % (st["id"], worst[0], worst[1], z))
        else:
            log("[clearance] %-22s in open air" % st["id"])
    if bad:
        log("[clearance] %d of %d committed cameras are buried. Plate A relies on the §6.6 "
            "relief cut and plate C on render_all.section_poche() to be renderable at all."
            % (bad, len(c["doc"]["stations"])))
    return bad


def build_sun(c):
    kl = c["doc"]["key_light"]
    to_sun = P([float(v) for v in kl["to_sun_unit"]])    # §1, via the ingest's own P()
    alt, azim = float(kl["elev_deg"]), float(kl["azim_deg"])

    lamp = bpy.data.lights.get("SUN_winter_peak")
    if lamp is None:
        lamp = bpy.data.lights.new("SUN_winter_peak", "SUN")
    lamp.type = "SUN"
    lamp.energy = 3.0                                    # §8 start value — editorial
    lamp.angle = math.radians(0.526)                     # the real solar disc
    obj = bpy.data.objects.get("SUN_winter_peak")
    if obj is None:
        obj = bpy.data.objects.new("SUN_winter_peak", lamp)
        bpy.context.scene.collection.objects.link(obj)
    obj.location = (0.0, 0.0, 500.0)                     # a sun lamp's position is irrelevant
    obj.rotation_euler = to_sun.to_track_quat("Z", "Y").to_euler()
    bpy.context.view_layer.update()          # matrix_world is stale until this runs

    # CHECK 1 — the lamp's +Z must point AT the sun; light then travels along -Z.
    plusZ = (obj.matrix_world.to_quaternion() @ Vector((0, 0, 1))).normalized()
    err = (plusZ - to_sun).length
    if err > 1e-6:
        raise RuntimeError("SUN FAILED: lamp +Z is %r, to_sun is %r (err %.3e)"
                           % (tuple(plusZ), tuple(to_sun), err))
    # CHECK 2 — the explicit Euler of §8.2, as an independent second opinion.
    e = Euler((math.radians(90.0 - alt), 0.0, math.radians(180.0 - azim)), "XYZ")
    alt_dir = (e.to_quaternion() @ Vector((0, 0, 1))).normalized()
    err2 = (alt_dir - to_sun).length
    if err2 > 1e-5:
        raise RuntimeError("SUN FAILED: the vector method and the explicit Euler disagree "
                           "by %.3e" % err2)
    # CHECK 3 — light travel must run north and downward (§8.3's shadow direction).
    travel = -plusZ
    if not (travel.y > 0 and travel.z < 0):
        raise RuntimeError("SUN FAILED: light travels %r — it must go north (+Y) and down "
                           "(-Z). A lamp 180 deg out passes every visual check."
                           % (tuple(travel),))

    log("[sun] day %s · elevation %.4f deg · azimuth %.1f deg  [cameras.json :: key_light]"
        % (kl["day_of_year"], alt, azim))
    log("[sun]   to_sun blender      (%.6f, %.6f, %.6f)" % tuple(to_sun))
    log("[sun]   rotation_euler      (%.6f, %.6f, %.6f) rad" % tuple(obj.rotation_euler))
    log("[sun]   PASS — lamp +Z matches to_sun to %.3e; the explicit Euler agrees to %.3e"
        % (err, err2))
    log("[sun]   PASS — light travels north (+Y %.6f) and downward (Z %.6f)"
        % (travel.y, travel.z))
    log("[sun]   shadow check: BIN %s at %.2f m must cast %.1f m to the NORTH (1/tan %.4f deg)"
        % (c["ref_bin"], c["ref_h"], c["ref_shadow"], alt))
    return obj


def build_world(c):
    """A seamless paper sweep, and deliberately NOT a sky.

    This used to be a physically-modelled sky (Nishita, driven from the measured winter
    vector, sun disc off). That was defensible and it was the wrong register: it puts a
    blue-grey gradient behind every plate and makes the frame read as a photograph.
    `visual-language.html` asks this project for **S12 Studio Object** — "fix the light and
    the ground, then never change them; one key at a consistent angle, a soft fill, a
    seamless sweep" — and for "neutral light, no volumetrics".

    So the world is one flat `paper` value acting as the soft fill, and the measured sun
    lamp remains the single key. Nothing about §8 changes: the key light is still the
    study's own winter vector and every one of its assertions still runs.

    S12 says "dark ground for pale models, pale ground for dark ones". The model is a
    near-white city with a dark steel canopy in front of it, and the portfolio-wide rule is
    that pages are paper — so the sweep is pale.
    """
    w = bpy.data.worlds.get("HL_World") or bpy.data.worlds.new("HL_World")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    for node in list(nt.nodes):
        if node.type == "TEX_SKY":
            nt.nodes.remove(node)
    bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (*_srgb(PAL["paper"]), 1.0)
    bg.inputs[1].default_value = WORLD_FILL
    w.light_settings.distance = 10.0          # the AO pass's ray length, §12.1
    log("[world] seamless paper sweep #f2f0ec at strength %.2f — flat fill, no gradient, "
        "no sky model, no horizon. S12: fix the light and the ground, then never change "
        "them." % WORLD_FILL)
    return w


# ─────────────────────────────────────────────────────────────────────────────
# CAMERAS — §9
# ─────────────────────────────────────────────────────────────────────────────
def _new_camera(name, clip_end):
    cam = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, cam)
        bpy.context.scene.collection.objects.link(obj)
    obj.data = cam
    cam.clip_start, cam.clip_end = 0.1, clip_end
    return obj


def build_cameras(c):
    out = {}
    for st in c["doc"]["stations"]:
        k = st["camera"]
        obj = _new_camera("CAM_" + st["id"], c["clip_end"])
        pos, tgt = P(k["position"]), P(k["target"])
        obj.location = pos
        obj.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
        if k["type"] == "orthographic":
            obj.data.type = "ORTHO"
            obj.data.ortho_scale = c["ortho_c"]
            _frame_section(obj, st, c)
        else:
            obj.data.type = "PERSP"
            obj.data.lens = LENS_MM
            eye = float(k["eye_height_above_deck_m"])
            if abs(pos.z - (DECK_Y + eye)) > 1e-6:
                raise RuntimeError("CAMERA %s sits at Z %.4f, not deck %.2f + eye %.2f. "
                                   "Raising a camera is indistinguishable from lowering the "
                                   "towers (§9.2)." % (st["id"], pos.z, DECK_Y, eye))
            log("[cam] %-22s PERSP  %.0f mm  Z %.2f m = deck %.2f + eye %.2f  s = %.2f m"
                % (st["id"], LENS_MM, pos.z, DECK_Y, eye, st["s_m"]))
        out[st["id"]] = obj
    return out


def _frame_section(obj, st, c):
    """Two corrections plate C needs, both derived, both stated.

    1. SHIFT — the emitter derives ORTHO_SCALE from `tallest wall - target Z + 5 m`, i.e.
       from a half-extent measured UPWARDS. Centring the frame on the target then spends
       the lower half of the plate on empty ground: at target Z 12.62 and scale 219 the
       frame runs -97 m to +122 m. Shifting so the frame's bottom edge sits at Z = 0
       spends the whole plate on the canyon. This is framing to fit the CANYON, which
       §9.3 permits explicitly; it does not change the ortho scale, so the canopy is not
       enlarged by one pixel.

    2. THE SECTION PLANE — §9.3 assumes clip start 0.1 m because it assumes there is
       nothing solid between the camera and the deck. Since the 2026-08-20 clearance fix
       the CAMERA is in open air, but that was never the whole problem: at the worst core
       the DECK ITSELF is inside a building, and the sight line from 45 m away crosses its
       wall. Measured on the chosen station, half the camera->deck samples are inside a
       prism. At clip start 0.1 m the plate is therefore a wall, and raising clip start
       just puts the near plane inside that wall and shows its hollow interior — black.

       So the distance is recorded here as `hl_section_plane_m` and the cut is made with
       GEOMETRY at render time — see section_poche() in render_all.py, which boolean-cuts
       every straddling prism at the plane so the cut face is a capped solid rather than
       a hole. That is what a section drawing IS, and it is why the clearance test for
       this camera is camera-position-only: a buried target is the subject here, not a
       fault. The distance is derived: camera -> target from cameras.json, less
       DECK_HALF_W, so the plane lands on the near edge of the deck.
    """
    pos, tgt = P(st["camera"]["position"]), P(st["camera"]["target"])
    scale = c["ortho_c"]
    rx, ry = RESOLUTION[st["id"]]
    frame_v = scale if ry >= rx else scale * ry / rx     # world height of the frame

    top = c["tall_wall_c"] + SECTION_HEADROOM_M
    # Centre the frame on the canyon's own span (ground to tallest wall + headroom) rather
    # than on the camera target. The ORTHO SCALE is UNCHANGED — the canopy does not gain a
    # pixel — this only re-aims a frame that was spending 97 m of its height below ground.
    # The frame is still 1.8x taller than the canyon, because the emitter derives the scale
    # by DOUBLING an upward-only half-extent; that is an upstream question, not one to fix
    # by narrowing the scale here (§9.3 forbids exactly that direction).
    want_centre = top / 2.0
    obj.data.shift_y = (want_centre - tgt.z) / scale     # shift_y is in units of the LARGER dim

    env = ing._load("envelope.json")
    half_w = float(env["_meta"]["params"]["DECK_HALF_W"])
    obj.data.clip_start = 0.1
    obj["hl_section_plane_m"] = (tgt - pos).length - half_w

    log("[cam] %-22s ORTHO  scale %.0f  (derived from that station's canyon)"
        % (st["id"], scale))
    log("[cam]   frame %.0f m tall, shifted %+.2f (bottom edge Z %.1f m, top %.1f m) so the "
        "plate is canyon, not empty ground"
        % (frame_v, obj.data.shift_y, want_centre - frame_v / 2.0, want_centre + frame_v / 2.0))
    log("[cam]   section plane %.2f m from the lens (camera->target less DECK_HALF_W). "
        "The camera is in open air since the 2026-08-20 clearance fix, but the DECK is not "
        "— the worst core is inside a building — so the cut is still made with geometry at "
        "render time, not with clip start. See section_poche()."
        % obj["hl_section_plane_m"])


def _fit_points():
    """The points plate D must contain: every rib knot, the deck, and the context near it."""
    bpy.context.view_layer.update()
    pts = []
    ribs = bpy.data.objects["HL_Ribs"]
    mw = ribs.matrix_world
    for sp in ribs.data.splines:
        for bp in sp.bezier_points:
            pts.append(mw @ bp.co)
    deck = bpy.data.objects["HL_Deck"]
    dmw = deck.matrix_world
    for v in deck.data.vertices:
        pts.append(dmw @ v.co)
    n_line = len(pts)

    kd = mathutils.kdtree.KDTree(n_line)
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    near = 0
    for coll in ("HL_Context_ranked", "HL_Context_unranked"):
        for o in bpy.data.collections[coll].objects:
            corners = [o.matrix_world @ Vector(cb) for cb in o.bound_box]
            centre = sum(corners, Vector()) / 8.0
            _, _, d = kd.find(Vector((centre.x, centre.y, DECK_Y)))
            if d is not None and d <= AXO_FIT_RADIUS_M:
                pts.extend(corners)
                near += 1
    log("[axo] fitting to %d rib/deck points + %d context prisms within %.0f m of the corridor"
        % (n_line, near, AXO_FIT_RADIUS_M))
    return pts


def build_axo(c):
    """Plate D — the one camera with no cameras.json entry (§9.4).

    The DIRECTION is a stated framing choice (AXO_VIEW_DIR). The ortho scale and the camera
    position are then FITTED to the geometry, so the plate cannot be tightened around the
    canopy to flatter it: narrowing the frame would crop the corridor, and the fit is what
    decides the number, not the eye.
    """
    obj = _new_camera("CAM_" + AXO_ID, c["clip_end"])
    obj.data.type = "ORTHO"
    quat = (-AXO_VIEW_DIR).to_track_quat("Z", "Y")   # a camera looks down its own -Z
    obj.rotation_euler = quat.to_euler()
    R = quat.to_matrix()
    Rt = R.transposed()

    pts = _fit_points()
    cam_space = [Rt @ p for p in pts]
    xs = [p.x for p in cam_space]
    ys = [p.y for p in cam_space]
    zs = [p.z for p in cam_space]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    w_need, h_need = max(xs) - min(xs), max(ys) - min(ys)

    rx, ry = RESOLUTION[AXO_ID]
    aspect = rx / ry
    margin = 1.06
    # ortho_scale is the world size of the LARGER image dimension (§9.3)
    scale = max(w_need, h_need * aspect) * margin
    obj.data.ortho_scale = scale

    back = max(zs) + 500.0
    obj.location = R @ Vector((cx, cy, back))
    obj.data.clip_start = 0.1
    obj.data.clip_end = max(c["clip_end"], back - min(zs) + 500.0)

    log("[axo] direction %r (framing choice, §9.4)"
        % (tuple(round(v, 3) for v in AXO_VIEW_DIR),))
    log("[axo] needs %.0f m across x %.0f m up at %d:%d  ->  ORTHO_SCALE %.0f "
        "(fitted, %.0f%% margin)" % (w_need, h_need, rx, ry, scale, (margin - 1) * 100))
    log("[axo] the tallest rib is %.2f m in a %.0f m frame height — %.2f%% of it. If that "
        "looks too small it is correct (§9.3)."
        % (c["rib_max_m"], scale / aspect, 100.0 * c["rib_max_m"] / (scale / aspect)))
    return obj


# -----------------------------------------------------------------------------
# CORRIDOR RELIEF - the one intervention this build makes on the context
# -----------------------------------------------------------------------------
def build_corridor_relief(c):
    """Cut the deck+canopy volume out of the prisms the viaduct passes through.

    WHY THIS IS NEEDED, AND WHY IT IS NOT A CHEAT
        The High Line runs THROUGH buildings - Chelsea Market and the Standard are the
        famous ones. `highline_footprints.json` carries those buildings' footprints and
        `hl_ingest` extrudes every footprint as a solid prism from Z = 0 to `height`,
        which knows nothing about the slot the viaduct occupies. Measured on the data:
        102 of 232 deck stations, and 284 of the 696 rail/centre points, fall INSIDE a
        footprint; 40 prisms taller than the 9.0 m deck bury part of the line. Camera A
        stands inside BIN 1089968 and renders solid black - the inside of a closed box.

        So this is not a look-dev preference. Without it plate A does not exist.

    WHAT IS CUT - every dimension comes from the data, none is invented
        the volume between the 232 rib-endpoint rails (width = DECK_HALF_W x 2 = 9.0 m,
        the same rails 6.4 lofts the deck from), from Z = DECK_Y up to
        Z = DECK_Y + envelope_rib_max_m. That is EXACTLY the volume the deck and its
        canopy occupy - no clearance margin, no rounding up. Nothing above the tallest
        rib, nothing below the deck plane, nothing wider than the deck.

    WHAT IT IS NOT
        It does not lower a tower, widen the deck or enlarge the canopy. A prism keeps
        its full height and its full footprint everywhere the design does not stand. The
        buildings that lose volume are the ones the deck already passes through, and they
        lose precisely the volume the deck already occupies.

    IT IS DECLARED, LIKE HL_Ground
        Every cut object carries `hl_corridor_relief` naming what was removed, so a
        cryptomatte pick or a spreadsheet query finds it. Set CORRIDOR_RELIEF = False to
        render the raw extrusion and see the black frame for yourself.
    """
    import bmesh

    env = ing._load("envelope.json")
    pts = env["points"]
    half_w = float(env["_meta"]["params"]["DECK_HALF_W"])
    H = c["rib_max_m"]                       # realised maximum, never RIB_MAX_H

    rails = [(P(p["rib"][0]), P(p["rib"][-1])) for p in pts]
    width = (rails[0][0] - rails[0][1]).length
    if abs(width - 2.0 * half_w) > 0.06:     # 3.4's own source-rounding tolerance
        raise RuntimeError("relief cutter width %.4f m does not match DECK_HALF_W x 2 = "
                           "%.2f m" % (width, 2.0 * half_w))

    bm = bmesh.new()
    ring = []
    for L, R in rails:
        lb = bm.verts.new((L.x, L.y, DECK_Y))
        rb = bm.verts.new((R.x, R.y, DECK_Y))
        lt = bm.verts.new((L.x, L.y, DECK_Y + H))
        rt = bm.verts.new((R.x, R.y, DECK_Y + H))
        ring.append((lb, rb, lt, rt))
    for i in range(len(ring) - 1):
        a0, b0, c0, d0 = ring[i]
        a1, b1, c1, d1 = ring[i + 1]
        bm.faces.new((a0, b0, b1, a1))       # floor
        bm.faces.new((c0, d0, d1, c1))       # ceiling
        bm.faces.new((a0, c0, c1, a1))       # left wall
        bm.faces.new((b0, d0, d1, b1))       # right wall
    bm.faces.new((ring[0][0], ring[0][1], ring[0][3], ring[0][2]))
    bm.faces.new((ring[-1][0], ring[-1][1], ring[-1][3], ring[-1][2]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new("HL_CorridorCutter")
    bm.to_mesh(me)
    bm.free()
    cutter = bpy.data.objects.new("HL_CorridorCutter", me)
    cutter["hl_source"] = ("NOT IN THE DATA - render-only relief solid: the deck+canopy "
                           "volume, %.2f m wide x Z %.2f..%.2f m, swept along the 232 "
                           "rib rails" % (width, DECK_Y, DECK_Y + H))
    bpy.context.scene.collection.objects.link(cutter)
    cutter.hide_render = True
    cutter.hide_viewport = True
    bpy.context.view_layer.update()

    # candidates: a prism can only matter if it rises above the deck plane and reaches
    # the strip. Deliberately a superset, so a miss is impossible and a false positive
    # is a boolean that changes nothing.
    rail_pts = [v for pair in rails for v in pair]
    kd = mathutils.kdtree.KDTree(len(rail_pts))
    for i, v in enumerate(rail_pts):
        kd.insert(Vector((v.x, v.y, 0.0)), i)
    kd.balance()

    cands = []
    for name in ("HL_Context_ranked", "HL_Context_unranked"):
        for o in bpy.data.collections[name].objects:
            if float(o.get("height_m", 0.0)) <= DECK_Y:
                continue
            mw = o.matrix_world
            for v in o.data.vertices:
                p = mw @ v.co
                _, _, d = kd.find(Vector((p.x, p.y, 0.0)))
                if d is not None and d <= 6.0:
                    cands.append(o)
                    break

    cut, unchanged = 0, 0
    for o in cands:
        before = len(o.data.polygons)
        m = o.modifiers.new("HL_CorridorRelief", "BOOLEAN")
        m.operation = "DIFFERENCE"
        m.solver = "EXACT"
        m.object = cutter
        dg = bpy.context.evaluated_depsgraph_get()
        new_me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        o.modifiers.clear()
        old = o.data
        o.data = new_me
        bpy.data.meshes.remove(old)
        if len(new_me.polygons) == before:
            unchanged += 1
            continue
        cut += 1
        o["hl_corridor_relief"] = (
            "NOT IN THE DATA - the deck+canopy volume (%.2f m wide, Z %.2f..%.2f) was "
            "removed from this prism because the viaduct passes through it"
            % (width, DECK_Y, DECK_Y + H))

    log("[relief] cutter: %.2f m wide (DECK_HALF_W %.2f x 2), Z %.2f .. %.2f m "
        "(DECK_Y + realised rib max %.2f). No margin, nothing invented."
        % (width, half_w, DECK_Y, DECK_Y + H, H))
    log("[relief] %d prisms tested, %d actually cut, %d untouched - every cut object is "
        "tagged hl_corridor_relief" % (len(cands), cut, unchanged))
    log("[relief] this is the ONE intervention on the context. Set CORRIDOR_RELIEF = False "
        "to render the raw extrusion instead.")
    return cutter


# ─────────────────────────────────────────────────────────────────────────────
# FIGURES — §10
# ─────────────────────────────────────────────────────────────────────────────
def _cyl(cx, cy, z0, z1, r, rx=1.0, ry=1.0, seg=12):
    verts, faces = [], []
    for z in (z0, z1):
        for i in range(seg):
            a = 2 * math.pi * i / seg
            verts.append((cx + r * rx * math.cos(a), cy + r * ry * math.sin(a), z))
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((i, j, seg + j, seg + i))
    faces.append(tuple(range(seg - 1, -1, -1)))
    faces.append(tuple(range(seg, 2 * seg)))
    return verts, faces


def _sphere(cx, cy, cz, r, seg=12, rings=8):
    verts, faces = [], []
    for j in range(rings + 1):
        phi = math.pi * j / rings
        for i in range(seg):
            th = 2 * math.pi * i / seg
            verts.append((cx + r * math.sin(phi) * math.cos(th),
                          cy + r * math.sin(phi) * math.sin(th),
                          cz + r * math.cos(phi)))
    for j in range(rings):
        for i in range(seg):
            a = j * seg + i
            b = j * seg + (i + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    return verts, faces


def _figure_mesh():
    """A 1.70 m standing figure, generated. No download, no licence, no scale trap.

    §10: at this distance silhouette beats mesh detail, and the classic failure is an
    imported human arriving at centimetre scale. Generating it removes that failure mode
    entirely — the only dimension that carries meaning is the total height, and it is
    asserted here and again against SCALE_CHECK_1m7 once placed.
    """
    parts = [
        _cyl(0.0, -0.10, 0.00, 0.92, 0.075),                    # legs — soles at Z 0
        _cyl(0.0, 0.10, 0.00, 0.92, 0.075),
        _cyl(0.0, 0.00, 0.86, 1.44, 0.175, rx=0.72, ry=1.0),    # torso, shoulders-wide
        _cyl(0.0, -0.20, 0.96, 1.40, 0.055),                    # arms
        _cyl(0.0, 0.20, 0.96, 1.40, 0.055),
        _sphere(0.0, 0.0, 1.600, 0.100),                        # head — crown at 1.70
    ]
    verts, faces = [], []
    for v, f in parts:
        off = len(verts)
        verts.extend(v)
        faces.extend(tuple(i + off for i in face) for face in f)
    me = bpy.data.meshes.new("FIGURE_1m70")
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    top = max(v[2] for v in verts)
    bot = min(v[2] for v in verts)
    if abs((top - bot) - FIGURE_HEIGHT_M) > 1e-6:
        raise RuntimeError("FIGURE HEIGHT %.6f m, expected %.2f m"
                           % (top - bot, FIGURE_HEIGHT_M))
    return me


def build_figures(c, cams):
    """Two or three figures on the deck, in front of camera A, feet at Z = DECK_Y.

    The distances are composition (FIGURE_DISTANCES_M). The POSITIONS are not: each figure
    is snapped to the nearest envelope.json station in front of the camera, so a figure
    stands on the measured deck rather than on an eyeballed point in space.
    """
    coll = bpy.data.collections.get("HL_Figures")
    if coll is None:
        coll = bpy.data.collections.new("HL_Figures")
        bpy.context.scene.collection.children.link(coll)
    for o in list(coll.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    bpy.context.view_layer.update()
    st = c["doc"]["stations"][0]
    cam = cams[st["id"]]
    pos = cam.location
    fwd = (cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    fwd_flat = Vector((fwd.x, fwd.y, 0.0)).normalized()
    left = Vector((-fwd_flat.y, fwd_flat.x, 0.0))

    env = ing._load("envelope.json")
    stations = [(P([p["x"], DECK_Y, p["z"]]), p) for p in env["points"]]

    me = _figure_mesh()
    mat = bpy.data.materials["MAT_Figure"]
    lateral = (-1.4, 1.9, -0.6)      # metres off the centreline, inside the 9.0 m deck
    heading = (0.6, -2.4, 2.9)       # radians, so they are not all facing the lens

    placed = []
    for k, want in enumerate(FIGURE_DISTANCES_M):
        best, bd = None, None
        for wp, p in stations:
            v = wp - pos
            if v.dot(fwd_flat) <= 0:
                continue
            d = abs(v.length - want)
            if bd is None or d < bd:
                best, bd = (wp, p), d
        if best is None:
            raise RuntimeError("no station in front of camera A at ~%.0f m" % want)
        wp, p = best
        loc = wp + left * lateral[k % len(lateral)]
        o = bpy.data.objects.new("FIGURE_%02d" % (k + 1), me)
        o.location = (loc.x, loc.y, DECK_Y)
        o.rotation_euler = (0.0, 0.0, heading[k % len(heading)])
        o.data.materials.clear()
        o.data.materials.append(mat)
        coll.objects.link(o)
        placed.append((o, (wp - pos).length, p["s_m"]))

    bpy.context.view_layer.update()
    cube = bpy.data.objects["SCALE_CHECK_1m7"]
    cz = [(cube.matrix_world @ Vector(cb)).z for cb in cube.bound_box]
    cube_h = max(cz) - min(cz)
    if abs(cube_h - FIGURE_HEIGHT_M) > 1e-4:
        raise RuntimeError("SCALE_CHECK_1m7 is %.4f m tall, not %.2f — the figure check has "
                           "no reference to stand on" % (cube_h, FIGURE_HEIGHT_M))
    for o, d, s in placed:
        fz = [(o.matrix_world @ Vector(cb)).z for cb in o.bound_box]
        h = max(fz) - min(fz)
        if abs(h - cube_h) > 1e-4:
            raise RuntimeError("FIGURE SCALE: %s is %.4f m, the cube is %.4f m (§10)"
                               % (o.name, h, cube_h))
        if abs(min(fz) - DECK_Y) > 1e-4:
            raise RuntimeError("%s has its feet at Z %.4f, not the deck plane %.2f"
                               % (o.name, min(fz), DECK_Y))
    log("[fig] PASS — %d figures, each %.4f m = SCALE_CHECK_1m7 exactly, feet at Z %.2f"
        % (len(placed), cube_h, DECK_Y))
    for o, d, s in placed:
        log("[fig]   %s  %.1f m in front of camera A, on station s = %.2f m"
            % (o.name, d, s))
    return coll


# ─────────────────────────────────────────────────────────────────────────────
# CYCLES, PASSES, COMPOSITOR — §§11, 12
# ─────────────────────────────────────────────────────────────────────────────
def setup_cycles(draft=True):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    # Under --factory-startup the device list starts EMPTY and stays empty until this
    # call. Without it every device query returns nothing and the GPU check below would
    # report a false negative — §11.1's silent failure with the sign reversed.
    try:
        prefs.refresh_devices()
    except Exception as exc:
        log("[cycles] refresh_devices() failed: %s" % exc)
    chosen = "CPU"
    for want in ("OPTIX", "CUDA"):
        devs = [d for d in prefs.devices if d.type == want]
        if not devs:
            continue
        try:
            prefs.compute_device_type = want
        except Exception as exc:
            log("[cycles] compute_device_type = %s rejected (%s); relying on the device "
                "use flags" % (want, exc))
        for d in prefs.devices:
            d.use = (d.type == want)
        chosen = want
        break
    if chosen == "CPU":
        # §11.1's silent failure, promoted to a loud one.
        log("[cycles] *** NO GPU DEVICE — Cycles falls back to CPU with no error. Enable one "
            "in Preferences > System > Cycles Render Devices. ***")
        s.cycles.device = "CPU"
    else:
        s.cycles.device = "GPU"
        log("[cycles] device %s: %s"
            % (chosen, ", ".join(d.name for d in prefs.devices if d.use)))
        try:
            s.cycles.denoiser = "OPTIX" if chosen == "OPTIX" else "OPENIMAGEDENOISE"
        except Exception:
            pass

    c = s.cycles
    c.use_adaptive_sampling = True
    if draft:
        c.samples, c.adaptive_min_samples, c.adaptive_threshold = 128, 0, 0.05
        c.time_limit = 60.0
    else:
        c.samples, c.adaptive_min_samples, c.adaptive_threshold = 1024, 64, 0.01
        c.time_limit = 0.0
    c.use_denoising = True
    c.denoising_prefilter = "ACCURATE"
    c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    c.use_auto_tile = True
    c.tile_size = 2048
    s.render.use_persistent_data = True
    # AgX rolls off highlights and desaturates them, which is right for a photographic
    # plate and wrong here: a #f2f0ec world does not come out #f2f0ec through it, so the
    # named palette stops being the palette. "Measurement, not cinema" decides it.
    # Switched on ALL plates together — §12.2's rule is that they must not DIFFER.
    s.view_settings.view_transform = "Standard"
    s.view_settings.look = "None"
    log("[cycles] %s · %d sample ceiling · adaptive %.3f · denoise %s/ACCURATE · view transform"
        % ("DRAFT" if draft else "FINAL", c.samples, c.adaptive_threshold,
           getattr(c, "denoiser", "?")), s.view_settings.view_transform)


def setup_passes():
    vl = bpy.context.view_layer
    vl.use_pass_combined = True
    vl.use_pass_z = True
    vl.use_pass_mist = True
    vl.use_pass_ambient_occlusion = True
    vl.use_pass_normal = True
    vl.use_pass_diffuse_color = True          # albedo, for the denoiser
    vl.use_pass_cryptomatte_object = True
    vl.use_pass_cryptomatte_material = True
    vl.pass_cryptomatte_depth = 6
    s = bpy.context.scene
    # Blender 5.x split the old OPEN_EXR_MULTILAYER enum into file_format + media_type.
    s.render.image_settings.media_type = "MULTI_LAYER_IMAGE"
    s.render.image_settings.file_format = "OPEN_EXR_MULTILAYER"
    s.render.image_settings.color_depth = "16"
    s.render.image_settings.exr_codec = "ZIP"
    log("[pass] combined · Z · mist · AO · normal · albedo · cryptomatte object+material")
    log("[pass] output OpenEXR MultiLayer, Half, ZIP — objects are BLD_<bin>_<ring>, so a "
        "cryptomatte pick maps straight back to an attribution row")


def _sock(sockets, identifier):
    """Look a socket up by IDENTIFIER, not by name.

    ShaderNodeMix carries four same-named pairs ("A"/"B"/"Result", one per data type) and
    only the identifier distinguishes them. Indexing by name silently grabs the wrong one
    or raises, depending on the build.
    """
    for s in sockets:
        if s.identifier == identifier:
            return s
    raise KeyError("no socket %r in %r" % (identifier, [s.identifier for s in sockets]))


def build_compositor():
    """§12.2's six nodes.

    Blender 5.x replaced the scene compositor node tree with a node GROUP whose interface
    output is the result: CompositorNodeComposite and CompositorNodeMixRGB no longer exist.
    The graph is the same graph; only the container changed.
    """
    s = bpy.context.scene
    old = s.compositing_node_group
    ng = bpy.data.node_groups.new("HL_Compositor", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    n = ng.nodes

    rl = n.new("CompositorNodeRLayers")
    rl.location = (-900, 0)
    have = {o.name for o in rl.outputs}
    missing = {"Mist", "Ambient Occlusion"} - have
    if missing:
        raise RuntimeError("Render Layers is missing %s — setup_passes() must run BEFORE the "
                           "compositor, or the pass names changed. Present: %s"
                           % (sorted(missing), sorted(have)))
    ex = n.new("CompositorNodeExposure")
    ex.location = (-650, 60)
    ex.inputs["Exposure"].default_value = 0.0     # grade HERE, never on the sun's strength

    mfac = n.new("ShaderNodeMath")
    mfac.location = (-650, -260)
    mfac.operation = "MULTIPLY"
    # 0.0 = the depth cue is OFF. §12.2 offers it and "~0.5" was its starting value, but
    # the governing note for this project is "no volumetrics", and a mist blend toward pale
    # is exactly the atmospheric cue that rule refuses. The node stays wired so the graph
    # still matches §12.2 and the pass is still in the EXR; only the factor is zero.
    mfac.inputs[1].default_value = 0.0

    haze = n.new("ShaderNodeMix")
    haze.location = (-420, 0)
    haze.data_type = "RGBA"
    haze.blend_type = "MIX"
    _sock(haze.inputs, "B_Color").default_value = (0.72, 0.75, 0.78, 1.0)

    ao = n.new("ShaderNodeMix")
    ao.location = (-190, 0)
    ao.data_type = "RGBA"
    ao.blend_type = "MULTIPLY"
    _sock(ao.inputs, "Factor_Float").default_value = 0.25

    cur = n.new("CompositorNodeCurveRGB")
    cur.location = (60, 0)
    cur.inputs["Fac"].default_value = 1.0
    # LINEAR, not the gentle S §12.2 suggests. An S-curve is a photographic contrast move;
    # in a measurement register it makes the pale context darker than the palette says it
    # is. The node stays so the graph matches §12.2 and so a grade is one edit away.
    cur.mapping.update()

    out = n.new("NodeGroupOutput")
    out.location = (520, 0)
    # Blender 5.x reworked File Output too: base_path/file_slots became
    # directory/file_name plus a file_output_items collection that creates the sockets.
    # The written name is <file_name><item name>, so render_all sets file_name per plate.
    png = n.new("CompositorNodeOutputFile")
    png.location = (520, -240)
    png.name = "HL_PNG"
    png.label = "HL_PNG"
    item = png.file_output_items.new("RGBA", PNG_SLOT)
    # WITHOUT THIS THE PNG IS BLACK. save_as_render applies the scene view transform
    # (AgX); with it off the node writes raw linear data, which for a sunlit exterior
    # clips to near-zero in 16-bit sRGB and looks exactly like a failed render.
    item.save_as_render = True
    png.save_as_render = True
    # the node inherits the scene's media_type, which setup_passes() just set to
    # MULTI_LAYER_IMAGE — under which PNG is not a legal file_format. Reset it first.
    png.format.media_type = "IMAGE"
    png.format.file_format = "PNG"
    png.format.color_mode = "RGB"
    png.format.color_depth = "16"
    png.format.compression = 15

    L = ng.links.new
    L(rl.outputs["Image"], ex.inputs["Image"])
    L(rl.outputs["Mist"], mfac.inputs[0])
    L(ex.outputs["Image"], _sock(haze.inputs, "A_Color"))
    L(mfac.outputs[0], _sock(haze.inputs, "Factor_Float"))
    L(_sock(haze.outputs, "Result_Color"), _sock(ao.inputs, "A_Color"))
    L(rl.outputs["Ambient Occlusion"], _sock(ao.inputs, "B_Color"))
    L(_sock(ao.outputs, "Result_Color"), cur.inputs["Image"])
    L(cur.outputs["Image"], out.inputs[0])
    L(cur.outputs["Image"], png.inputs[PNG_SLOT])

    s.compositing_node_group = ng
    if old is not None and old.users == 0:
        bpy.data.node_groups.remove(old)
    log("[comp] Render Layers -> Exposure -> Mix(mist) -> Mix(AO x0.25) -> RGB curve -> out, "
        "plus a PNG File Output")
    return ng


def fit_ground(axo):
    """Grow HL_Ground so its edge is not in the axo frame.

    The ingest sizes the ground to the footprint extent + 200 m and declares it invented
    scene furniture with no source. The fitted axo frame is wider than that, so the plate
    showed the plane's straight edge cutting across the sky. Resizing declared furniture
    is not scaling the site; the object keeps its hl_source note and gains a second one.
    """
    g = bpy.data.objects["HL_Ground"]
    before = max(g.dimensions.x, g.dimensions.y)
    # The frame is ortho_scale wide, but an oblique camera sees a much LONGER strip of Z=0
    # than it is tall: frame_height / sin(pitch). At 1.6x the plane's edge was still cutting
    # across the sky in the top corner. 3x covers the strip and the frame's offset from the
    # site origin, and a bigger flat matte plane costs nothing to render.
    need = axo.data.ortho_scale * 3.0
    if need > before:
        f = need / before
        g.scale = (g.scale.x * f, g.scale.y * f, 1.0)
        bpy.context.view_layer.update()
        g["hl_ground_resized"] = ("NOT IN THE DATA — the invented ground plane was widened "
                                  "from %.0f m to %.0f m so its edge falls outside the axo "
                                  "frame" % (before, need))
        log("[ground] widened invented ground plane %.0f m -> %.0f m so its edge is out of "
            "the axo frame (still declared, still not in the data)" % (before, need))
    else:
        log("[ground] invented ground plane %.0f m already covers the axo frame" % before)


def mist_range_for(cam):
    """Mist start/depth from the depth range this camera actually sees.

    A typed range cannot be right for four cameras whose subjects sit at 25 m, 45 m and
    1.7 km. Sampling the geometry in front of the lens and taking percentiles gives a
    haze that reads as depth on every plate instead of as a flat card on three of them.
    """
    bpy.context.view_layer.update()
    fwd = (cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    org = cam.matrix_world.translation

    depths = []
    ribs = bpy.data.objects["HL_Ribs"]
    mw = ribs.matrix_world
    for sp in ribs.data.splines:
        for bp in sp.bezier_points:
            depths.append((mw @ bp.co - org).dot(fwd))
    for name in ("HL_Context_ranked", "HL_Context_unranked"):
        for o in bpy.data.collections[name].objects:
            for cb in o.bound_box:
                depths.append((o.matrix_world @ Vector(cb) - org).dot(fwd))
    depths = sorted(d for d in depths if d > 0.0)
    if len(depths) < 2:
        raise RuntimeError("no geometry in front of %s — mist cannot be derived" % cam.name)

    def pct(p):
        return depths[min(len(depths) - 1, max(0, int(round(p / 100.0 * (len(depths) - 1)))))]

    lo, hi = pct(MIST_PCT[0]), pct(MIST_PCT[1])
    return lo, max(1.0, hi - lo)


def set_viewport_clip(c):
    n = 0
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for sp in area.spaces:
                if sp.type == "VIEW_3D":
                    sp.clip_start, sp.clip_end = 0.1, c["clip_end"]
                    n += 1
    log("[clip] viewport clip 0.1 .. %.0f m on %d 3D views; the 100 m default hides most of "
        "the site with no error (§3)" % (c["clip_end"], n))


# ─────────────────────────────────────────────────────────────────────────────
def main():
    log("=" * 74)
    log("build_lookdev — materials, sun, world, cameras, figures, passes, compositor")
    log("=" * 74)
    c = build_constants()
    ensure_geometry()
    verify_counts(c)
    build_materials(c)
    build_sun(c)
    build_world(c)
    if CORRIDOR_RELIEF:
        build_corridor_relief(c)
    else:
        log("[relief] SKIPPED - CORRIDOR_RELIEF is False. 40.8% of the deck is inside "
            "solid prisms and camera A will render black.")
    cams = build_cameras(c)
    report_clearance(c, cams)
    cams[AXO_ID] = build_axo(c)
    fit_ground(cams[AXO_ID])
    build_figures(c, cams)
    verify_materials_visible()
    setup_cycles(draft=True)
    setup_passes()
    build_compositor()
    set_viewport_clip(c)

    s = bpy.context.scene
    s.camera = cams[c["doc"]["stations"][0]["id"]]
    s.unit_settings.system = "METRIC"
    s.unit_settings.length_unit = "METERS"
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
    log("=" * 74)
    log("saved %s" % BLEND_OUT)
    log("nothing was scaled; no vertical exaggeration was applied; no camera was placed by eye")
    log("=" * 74)


if __name__ == "__main__":
    main()
