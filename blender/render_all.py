"""render_all.py — render the W1 plates from the built scene. Nothing is set by hand.

    blender --background blender/answering_line.blend --python blender/render_all.py -- --plate A --final
    blender --background blender/answering_line.blend --python blender/render_all.py -- --all --draft

Everything after `--` is parsed here. `--plate` takes A, B, C, D or their full ids.

WHAT THIS DOES NOT DO
    It does not build the scene. `build_lookdev.py` does that, from JSON, including the
    materials, the world, the compositor and the figures — so this script never has to
    trust a .blend it cannot regenerate. If answering_line.blend is missing or stale:

        blender --background --factory-startup --python blender/build_lookdev.py

    It also never touches the camera, the sun or any geometry. BUILD_STEPS §13.2: camera
    placement, light direction and geometry are not render-time controls. This script
    chooses a camera from the ones cameras.json already committed, and nothing else.

OUTPUT — §12.3
    exports/blender/<id>.exr      OpenEXR MultiLayer: combined, depth, mist, AO, normal,
                                  albedo, cryptomatte object + material
    exports/blender/<id>.png      the composited grade, 16-bit
    exports/blender/captions.txt  pick_cameras.py --captions, written beside the images so
                                  every plate lands next to the caption block that
                                  describes it and no figure is ever transcribed
"""

import contextlib
import io
import os
import sys
import time

import bpy

PROJECT = r"C:\Users\ReiChiquita\Desktop\jobs\sriya-portfolio-handoff\sriya-portfolio\Projects\5.CV_Highline"
sys.path.insert(0, os.path.join(PROJECT, "blender"))
sys.path.insert(0, os.path.join(PROJECT, "houdini"))

import build_lookdev as bl           # noqa: E402  — RESOLUTION, MIST, AXO_ID, setup_cycles
import pick_cameras as pc            # noqa: E402  — the caption emitter

OUT = os.path.join(PROJECT, "exports", "blender")

# The short names the plan and the build steps use, in the priority order §"What ships"
# gives: A ships first, then C, then D; B only if time allows.
PLATES = {
    "A": "A_hero_eye_level",
    "C": "C_section_worst_core",
    "D": "D_corridor_axo",
    "B": "B_open_contrast",
}


def log(*a):
    print(*a)
    sys.stdout.flush()


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    want, final, ev = [], False, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--plate":
            i += 1
            key = argv[i]
            if key in PLATES:
                want.append(PLATES[key])
            elif key in PLATES.values():
                want.append(key)
            else:
                raise SystemExit("unknown plate %r — use one of %s or %s"
                                 % (key, list(PLATES), list(PLATES.values())))
        elif a == "--all":
            want = list(PLATES.values())
        elif a == "--final":
            final = True
        elif a == "--draft":
            final = False
        elif a == "--exposure":
            i += 1
            ev = float(argv[i])
        elif a == "--suffix":
            i += 1
            globals()["SUFFIX"] = argv[i]
        else:
            raise SystemExit("unknown argument %r" % a)
        i += 1
    if not want:
        want = list(PLATES.values())
    return want, final, ev


def write_captions():
    """§12.3 — the caption blocks land beside the images, generated, never transcribed."""
    doc_path = os.path.join(PROJECT, "houdini", "cameras.json")
    import json
    doc = json.load(open(doc_path, encoding="utf-8"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        pc.render_captions(doc)
    path = os.path.join(OUT, "captions.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(buf.getvalue())
    log("[caption] %s — every number on a plate comes out of this file, not out of a doc"
        % path)


def section_poche(cam):
    """Cut the context at the section plane, capping the cut so it reads as solid.

    WHY IT IS GEOMETRY AND NOT A CLIP PLANE
        Since the 2026-08-20 clearance fix camera C stands in open air, but the DECK at the
        worst core does not: it is inside a building, and roughly half the camera->deck
        sight line is inside a prism. A near clip plane lands inside that prism and renders
        its hollow interior — pure black, which is what the first drafts showed. A boolean
        difference removes the near half AND caps the opening, so the cut face is a lit
        solid. That is a section drawing; a clip plane is a hole.

    WHAT IS CUT
        Everything nearer to the lens than `hl_section_plane_m`, which build_lookdev
        derived as (camera -> target) - DECK_HALF_W: the near edge of the deck. Nothing
        beyond the plane is touched, and the cut is a LIVE modifier removed again after
        the render, so it never reaches the saved .blend or any other plate.
    """
    import bmesh
    from mathutils import Vector

    d = cam.get("hl_section_plane_m")
    if d is None:
        return []
    bpy.context.view_layer.update()
    fwd = (cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    org = cam.matrix_world.translation

    # a box filling the half-space nearer than the plane, sized from the scene itself
    span = max(o.dimensions.length for o in bpy.context.view_layer.objects if o.type == "MESH")
    reach = 4000.0 + span
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    me = bpy.data.meshes.new("HL_SectionCutter")
    bm.to_mesh(me)
    bm.free()
    cutter = bpy.data.objects.new("HL_SectionCutter", me)
    bpy.context.scene.collection.objects.link(cutter)
    cutter.scale = (reach, reach, reach)
    # centre it so its far face sits exactly on the section plane
    cutter.location = org + fwd * (d - reach / 2.0)
    cutter.rotation_euler = cam.rotation_euler
    cutter.hide_render = True
    bpy.context.view_layer.update()

    touched = []
    for name in ("HL_Context_ranked", "HL_Context_unranked", "HL_Site"):
        for o in bpy.data.collections[name].objects:
            if o.type != "MESH":
                continue
            ds = [(o.matrix_world @ Vector(cb) - org).dot(fwd) for cb in o.bound_box]
            # beyond the plane -> untouched; entirely behind the lens -> invisible anyway,
            # and cutting it was costing ~1,900 pointless booleans a frame.
            if min(ds) >= d or max(ds) <= 0.0:
                continue
            m = o.modifiers.new("HL_SectionPoche", "BOOLEAN")
            m.operation = "DIFFERENCE"
            m.solver = "EXACT"
            m.object = cutter
            touched.append(o)
    log("[section] cut plane %.2f m from the lens; %d objects boolean-cut and capped "
        "(live modifiers, removed after this frame)" % (d, len(touched)))
    return [cutter] + touched


def clear_poche(objs):
    if not objs:
        return
    cutter, rest = objs[0], objs[1:]
    for o in rest:
        m = o.modifiers.get("HL_SectionPoche")
        if m:
            o.modifiers.remove(m)
    bpy.data.objects.remove(cutter, do_unlink=True)


SUFFIX = ""


def set_exposure(plate_id, override):
    """§12.2's Exposure node. Grade here, never on the sun's strength."""
    ng = bpy.context.scene.compositing_node_group
    node = next((n for n in ng.nodes if n.type == "EXPOSURE"), None)
    if node is None:
        raise RuntimeError("no Exposure node in the compositor — rebuild with build_lookdev")
    ev = bl.EXPOSURE[plate_id] if override is None else override
    node.inputs["Exposure"].default_value = ev
    return ev


def rib_material_for(plate_id):
    """Plate D gets §9.4's colour-by-height steel; A, B and C keep §7's single MAT_Steel.

    Swapped for the frame and restored afterwards, so the saved .blend and the other three
    plates are untouched.
    """
    ribs = bpy.data.objects["HL_Ribs"]
    was = ribs.data.materials[0] if ribs.data.materials else None
    if plate_id != bl.AXO_ID:
        return was, was
    want = bpy.data.materials.get("MAT_Steel_ByHeight")
    if want is None:
        log("[warn] MAT_Steel_ByHeight missing — rebuild with build_lookdev.py")
        return was, was
    ribs.data.materials.clear()
    ribs.data.materials.append(want)
    log("[ribs] plate D uses MAT_Steel_ByHeight (§9.4). NOTE: measured 2026-08-20, this "
        "buys nothing at whole-corridor scale — 0.49 m/px makes the tube sub-pixel, so "
        "there is nothing wide enough to colour. Useful only on a shorter stretch.")
    return was, want


def context_material_for(plate_id):
    """Swap the ranked context to neutral on every plate but the analysis one.

    See build_lookdev.CONTEXT_RAMP_PLATES for why. Restored after the frame, so the saved
    .blend and the other plates are untouched — same pattern as rib_material_for().
    """
    ranked = list(bpy.data.collections["HL_Context_ranked"].objects)
    was = ranked[0].data.materials[0] if ranked and ranked[0].data.materials else None
    if plate_id in bl.CONTEXT_RAMP_PLATES:
        log("[ctx] plate carries the sky-share ramp (S03 analysis register)")
        return ranked, was
    neutral = bpy.data.materials["MAT_Context_Neutral"]
    for o in ranked:
        o.data.materials.clear()
        o.data.materials.append(neutral)
    log("[ctx] %d ranked buildings rendered NEUTRAL for this plate — the ramp is an "
        "analysis overlay and at eye level it would be 80%% of the frame (S03/S06)"
        % len(ranked))
    return ranked, was


def restore_context(ranked, was):
    if was is None:
        return
    for o in ranked:
        o.data.materials.clear()
        o.data.materials.append(was)


def prepare(plate_id, final):
    s = bpy.context.scene
    cam = bpy.data.objects.get("CAM_" + plate_id)
    if cam is None:
        raise RuntimeError("CAM_%s is not in the .blend. Run build_lookdev.py — do not "
                           "place it by hand (§13.2)." % plate_id)
    s.camera = cam

    rx, ry = bl.RESOLUTION[plate_id]
    s.render.resolution_x, s.render.resolution_y = rx, ry
    s.render.resolution_percentage = 100

    start, depth = bl.mist_range_for(cam)
    s.world.mist_settings.use_mist = True
    s.world.mist_settings.start = start
    s.world.mist_settings.depth = depth

    bl.setup_cycles(draft=not final)

    s.render.filepath = os.path.join(OUT, plate_id + SUFFIX)
    ng = s.compositing_node_group
    png = ng.nodes.get("HL_PNG") if ng else None
    if png is None:
        raise RuntimeError("the HL_PNG File Output node is missing from the compositor — "
                           "rebuild with build_lookdev.py")
    png.directory = OUT
    png.file_name = plate_id + SUFFIX

    kind = "PERSP %.0f mm" % cam.data.lens if cam.data.type == "PERSP" \
        else "ORTHO scale %.0f" % cam.data.ortho_scale
    log("[plate] %-22s %s  %dx%d  mist %.0f..%.0f m  %s"
        % (plate_id, kind, rx, ry, start, start + depth, "FINAL" if final else "DRAFT"))
    return png


def tidy_png(plate_id):
    """The File Output node appends the socket name; §12.3's names do not carry one."""
    want = os.path.join(OUT, plate_id + SUFFIX + ".png")
    got = os.path.join(OUT, plate_id + SUFFIX + bl.PNG_SLOT + ".png")
    if not os.path.exists(got):
        got = None
        for name in os.listdir(OUT):
            if (name.startswith(plate_id + SUFFIX) and name.endswith(".png")
                    and name != os.path.basename(want)):
                got = os.path.join(OUT, name)
                break
    if got is None:
        log("[warn] no PNG written for %s — check the HL_PNG node's link" % plate_id)
        return None
    if os.path.exists(want):
        os.remove(want)
    os.rename(got, want)
    return want


def main():
    want, final, ev_override = parse_args()
    os.makedirs(OUT, exist_ok=True)
    log("=" * 74)
    log("render_all — %s, %d plate(s): %s"
        % ("FINAL" if final else "DRAFT", len(want), ", ".join(want)))
    log("cameras, sun and geometry come from the .blend as built. None is set here.")
    log("=" * 74)
    write_captions()

    for plate_id in want:
        prepare(plate_id, final)
        ev = set_exposure(plate_id, ev_override)
        was_mat, _ = rib_material_for(plate_id)
        ranked, was_ctx = context_material_for(plate_id)
        log("[grade] exposure %+.2f stops%s"
            % (ev, "  (--exposure override)" if ev_override is not None else ""))
        poche = section_poche(bpy.context.scene.camera)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - t0
        clear_poche(poche)
        ribs = bpy.data.objects["HL_Ribs"]
        ribs.data.materials.clear()
        if was_mat is not None:
            ribs.data.materials.append(was_mat)
        restore_context(ranked, was_ctx)
        exr = os.path.join(OUT, plate_id + SUFFIX + ".exr")
        png = tidy_png(plate_id)
        sz = (os.path.getsize(exr) / 1e6) if os.path.exists(exr) else 0.0
        log("[done]  %-22s %6.1f s   %s (%.1f MB)%s"
            % (plate_id, dt, os.path.basename(exr), sz,
               "  +  " + os.path.basename(png) if png else ""))
    log("=" * 74)
    log("Rendered at §11.3 sizes. Downsample and compress in Stage 6 of the render plan —")
    log("do not paste these into the PDF at full size (§11.3 size budget).")
    log("=" * 74)


if __name__ == "__main__":
    main()
