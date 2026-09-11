"""render_massing.py — the sky-share ramp painted on the 3-D massing.

    blender --background blender/answering_line.blend --python blender/render_massing.py

WHAT THIS IS COPYING, AND WHY
    `refrences/pintest_layouts/visual-language.html` assigns this project S03 Analysis Ramp
    and S06 White-Ground Line Density, and its own reference image for the ramp is a
    structural displacement painted onto a shell with the mesh drawn over it, floating on
    white, with a vertical bar carrying the unit. That is those two systems in one image:

        S03  "Simulation output painted onto the geometry it belongs to."
        S06  "Ink on paper, no fill anywhere ... let density be the only value."

    So: the ramp fills the massing, Freestyle draws every edge over it in ink, the ground
    is paper, and the bar is added by scripts/build_massing_plate.py.

WHY A TIGHT AXO AND NOT THE CORRIDOR AXO
    Plate D frames all 1.73 km and the buildings are 20 px wide. The attribution ramp needs
    the buildings to read AS OBJECTS, so this camera is fitted to the top-ranked culprits
    from data/attribution.json plus the deck that runs between them. The frame is derived
    from those buildings' own bounding boxes — it is not an eye pick.

WHAT IT DOES NOT DO
    It does not move a vertex, change a height, or touch the ramp's normalisation. The
    material is the same MAT_Context_Share every other plate uses, driven by the same
    per-object `sky_share_norm` the ingest wrote.
"""

import json
import math
import os
import sys

import bpy
import mathutils
from mathutils import Vector

PROJECT = r"C:\Users\ReiChiquita\Desktop\jobs\sriya-portfolio-handoff\sriya-portfolio\Projects\5.CV_Highline"
sys.path.insert(0, os.path.join(PROJECT, "blender"))
import build_lookdev as bl              # noqa: E402  — palette, setup_cycles, mist_range_for

OUT = os.path.join(PROJECT, "exports", "blender")
RES = (3000, 2200)

# How many of the attribution leaderboard the frame is fitted to. The ramp is normalised on
# the whole ranked set regardless; this only decides what is IN SHOT.
TOP_N = 12
# Framing choice, stated: a high oblique from the south-east so the deck reads across the
# cluster rather than end-on. Everything else about the camera is fitted.
VIEW_DIR = Vector((-0.62, 0.55, -0.56)).normalized()
MARGIN = 1.10
# Exposure stays at 0 and the LIGHT comes down instead, because they are not equivalent
# here: the paper ground IS the world, so pulling exposure darkens the page itself. At
# -1.7 stops the massing stopped clipping and the paper went grey — the plate lost the one
# thing the whole register is built on. So the world sits at exactly paper value and the
# key is lowered until the lit white faces land under 1.0.
#
# §8's 3.0 is explicitly a "start" value and editorial; the sun's ANGLE is the measured
# thing and is untouched. Set for this plate only — the .blend is not saved here.
EXPOSURE = 0.0
MASSING_SUN = 1.35       # W/m^2, this plate only
MASSING_WORLD = 1.0      # background renders as #f2f0ec exactly


def log(*a):
    print(*a)
    sys.stdout.flush()


def top_bins(n):
    with open(os.path.join(PROJECT, "data", "attribution.json"), encoding="utf-8") as fh:
        lead = json.load(fh)["leaderboard"]
    return [str(r["id"]) for r in lead[:n]], lead


def fit_axo(objs, aspect):
    """An orthographic camera fitted to the objects it must contain."""
    quat = (-VIEW_DIR).to_track_quat("Z", "Y")
    R = quat.to_matrix()
    Rt = R.transposed()
    pts = []
    for o in objs:
        for cb in o.bound_box:
            pts.append(Rt @ (o.matrix_world @ Vector(cb)))
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    scale = max(max(xs) - min(xs), (max(ys) - min(ys)) * aspect) * MARGIN

    cam = bpy.data.cameras.get("CAM_E_massing") or bpy.data.cameras.new("CAM_E_massing")
    obj = bpy.data.objects.get("CAM_E_massing")
    if obj is None:
        obj = bpy.data.objects.new("CAM_E_massing", cam)
        bpy.context.scene.collection.objects.link(obj)
    obj.data = cam
    cam.type = "ORTHO"
    cam.ortho_scale = scale
    cam.clip_start = 0.1
    back = max(zs) + 2000.0
    cam.clip_end = back - min(zs) + 2000.0
    obj.rotation_euler = quat.to_euler()
    obj.location = R @ Vector((cx, cy, back))
    bpy.context.view_layer.update()
    log("[cam] fitted ortho scale %.1f m over %d objects" % (scale, len(objs)))
    return obj


def enable_freestyle():
    """S06's ink, over S03's fill. Silhouette, border and crease only — no chartjunk."""
    s = bpy.context.scene
    s.render.use_freestyle = True
    s.render.line_thickness_mode = "ABSOLUTE"
    s.render.line_thickness = 1.1
    vl = bpy.context.view_layer
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    for ls in list(fs.linesets):
        fs.linesets.remove(ls)
    ls = fs.linesets.new("HL_ink")
    ls.select_silhouette = True
    ls.select_border = True
    ls.select_crease = True
    ls.select_edge_mark = False
    ls.select_material_boundary = False
    fs.crease_angle = math.radians(80.0)
    st = ls.linestyle
    st.color = bl.PAL["steel"][:3]
    st.thickness = 1.1
    st.alpha = 0.85
    log("[ink] Freestyle on — silhouette + border + crease at %.0f deg, %.1f px steel"
        % (math.degrees(fs.crease_angle), st.thickness))


def main():
    bins, lead = top_bins(TOP_N)
    ranked = bpy.data.collections["HL_Context_ranked"]
    wanted = [o for o in ranked.objects if str(o.get("bin", "")) in bins]
    if not wanted:
        raise SystemExit("none of the top %d BINs found in HL_Context_ranked" % TOP_N)
    log("[fit] framing the top %d of the attribution leaderboard: %d objects found"
        % (TOP_N, len(wanted)))
    for r in lead[:5]:
        log("      BIN %-9s %6.2f%%" % (r["id"], r["sky_share_pct"]))

    # the deck between them, so the corridor reads through the cluster
    deck = bpy.data.objects["HL_Deck"]
    ribs = bpy.data.objects["HL_Ribs"]

    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = RES
    s.render.resolution_percentage = 100
    cam = fit_axo(wanted + [deck], RES[0] / RES[1])
    s.camera = cam

    # the ramp stays on — this is the one plate it is FOR
    log("[ctx] ranked context keeps MAT_Context_Share; %d objects" % len(ranked.objects))

    # The deck is the thing being measured and at this scale MAT_Paving is invisible
    # against a white city. It goes steel for this plate so the corridor reads as the
    # subject — and steel, not the accent, because the accent means sky share here and
    # colouring the deck with it would claim the deck took someone's sky.
    was_deck = deck.data.materials[0] if deck.data.materials else None
    deck.data.materials.clear()
    deck.data.materials.append(bpy.data.materials["MAT_Steel"])
    log("[deck] rendered in steel for this plate so the corridor is legible")

    # no haze on an object plate
    s.world.mist_settings.use_mist = True
    s.world.mist_settings.start = 0.0
    s.world.mist_settings.depth = 1e6

    lamp = bpy.data.objects["SUN_winter_peak"].data
    lamp.energy = MASSING_SUN
    bg = next(n for n in s.world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[1].default_value = MASSING_WORLD
    log("[light] key %.2f W/m2, world %.2f — angle untouched, exposure stays at 0 so the "
        "paper stays paper" % (MASSING_SUN, MASSING_WORLD))

    enable_freestyle()
    bl.setup_cycles(draft=("--final" not in sys.argv))

    ng = s.compositing_node_group
    ex = next((n for n in ng.nodes if n.type == "EXPOSURE"), None)
    if ex is not None:
        # A near-white city under a paper sky through a Standard transform has no highlight
        # rolloff at all: at 0.0 stops 71% of this frame clipped to pure white and the
        # massing lost its shading entirely. Graded here, per §12.2, never on the sun.
        ex.inputs["Exposure"].default_value = EXPOSURE
    png = ng.nodes.get("HL_PNG")
    if png is not None:
        png.directory = OUT
        png.file_name = "E_massing_ramp"

    s.render.filepath = os.path.join(OUT, "E_massing_ramp")
    bpy.ops.render.render(write_still=True)

    src = os.path.join(OUT, "E_massing_ramp" + bl.PNG_SLOT + ".png")
    dst = os.path.join(OUT, "E_massing_ramp.png")
    if os.path.exists(src):
        if os.path.exists(dst):
            os.remove(dst)
        os.rename(src, dst)
    log("[done] %s" % dst)


# ═════════════════════════════════════════════════════════════════════════════
# --layers : the exploded axo's strata
# ═════════════════════════════════════════════════════════════════════════════
LAYERS = [
    ("massing", ["HL_Context_ranked", "HL_Context_unranked"],
     "THE CITY", "ranked context carries the measured sky share; unranked is neutral"),
    ("corridor", ["HL_Canopy", "HL_Site"],
     "THE LINE", "the deck lofted from the 232 rib rails, and the canopy above it"),
]


def dump_camera(cam, res):
    """The exact projection, so a second tool can draw in register with this render.

    An orthographic camera is a pure affine map: world -> camera space through the
    inverse of matrix_world, then a SINGLE scale to pixels for both axes, because
    ortho_scale spans the larger image dimension. Writing the matrix out is what lets
    build_exploded_plate.py add a layer Blender never rendered without any guesswork
    about where it lands.
    """
    inv = cam.matrix_world.inverted()
    k = res[0] / cam.data.ortho_scale
    doc = {
        "world_to_cam": [list(r) for r in inv],
        "px_per_m": k,
        "res": list(res),
        "ortho_scale": cam.data.ortho_scale,
        "note": "px = (res/2) + (world_to_cam @ p).xy * px_per_m, y inverted",
    }
    p = os.path.join(OUT, "E_massing_cam.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    log("[cam] %s  ·  %.4f px/m" % (p, k))


def render_layers():
    """Each stratum alone, on transparent film, from the identical camera."""
    s = bpy.context.scene
    s.render.film_transparent = True
    ng = s.compositing_node_group
    png = ng.nodes.get("HL_PNG")
    if png is not None:
        png.mute = True                     # the layer files come off the scene output
    s.render.image_settings.media_type = "IMAGE"
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGBA"
    s.render.image_settings.color_depth = "8"

    names = [n for n, _, _, _ in LAYERS]
    all_colls = sorted({c for _, cs, _, _ in LAYERS for c in cs})
    lc = bpy.context.view_layer.layer_collection
    for key, colls, _, _ in LAYERS:
        for name in all_colls:
            child = lc.children.get(name)
            if child is not None:
                child.exclude = name not in colls
        # the invented ground never appears in an exploded drawing
        g = bpy.data.objects.get("HL_Ground")
        if g is not None:
            g.hide_render = True
        bpy.context.view_layer.update()
        s.render.filepath = os.path.join(OUT, "E_layer_%s" % key)
        bpy.ops.render.render(write_still=True)
        log("[layer] %s -> E_layer_%s.png" % (", ".join(colls), key))
    for name in all_colls:
        child = lc.children.get(name)
        if child is not None:
            child.exclude = False
    log("[layers] %d written, transparent film, identical camera" % len(names))


if __name__ == "__main__":
    main()
    if "--layers" in sys.argv:
        dump_camera(bpy.data.objects["CAM_E_massing"], RES)
        render_layers()
