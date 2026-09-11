# hl_ingest.py — Houdini Python SOP: The Answering Line -> geometry
#
# Reads the project's own provenance-stamped JSON and builds geometry. No modelling.
# Nothing here invents a number; every attribute is carried straight from the engine output.
#
# USE
#   Create a Python SOP. Paste this file's contents in, or use:
#       exec(open(r"<...>/5.CV_Highline/houdini/hl_ingest.py").read())
#   Set MODE below (or add a spare string parm named "mode" on the SOP to override).
#
# MODES
#   "ribs"    -> 232 open polylines from data/envelope.json, one per deck station.
#                Sweep these. Every driver is on the prim AND on each point.
#   "context" -> 176 building footprints from data/highline_footprints.json as closed
#                polygons with a `height` prim attrib. Feed a PolyExtrude, Distance = height.
#   "deck"    -> the High Line centreline as one open polyline at deck level.
#   "access"  -> the 10 access points, as points with name + weight.
#
# COORDINATES
#   The project stores (x, z) as the ground plane with y up — the same convention Houdini
#   uses. Rib vertices are already [x, y, z] in metres, deck level ~y=9.0. No swizzle,
#   no rescale. Do not "fix" the axes; the geometry is already in world metres.
#
# HONESTY NOTE
#   THE_ANSWERING_LINE.md: "No vertical exaggeration anywhere. The canopy is small because
#   the towers are the problem — that honesty is the argument." Do not scale y to make the
#   canopy read better. If it looks small, that IS the finding.

import json
import os

import hou

# --- configure -------------------------------------------------------------------------
PROJECT = r"C:\Users\ReiChiquita\Desktop\jobs\sriya-portfolio-handoff\sriya-portfolio\Projects\5.CV_Highline"
MODE = "ribs"          # ribs | context | deck | access
DECK_Y = 9.0           # metres; matches the rib base elevation in envelope.json
# ---------------------------------------------------------------------------------------

node = hou.pwd()
geo = node.geometry()

# a spare string parm named "mode" wins if you add one
_p = node.parm("mode")
if _p is not None:
    MODE = _p.evalAsString().strip() or MODE
_pp = node.parm("project")
if _pp is not None and _pp.evalAsString().strip():
    PROJECT = _pp.evalAsString().strip()

DATA = os.path.join(PROJECT, "data")


def _load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        raise hou.NodeError(
            "missing %s\nRun the engines first (see 5.CV_Highline/CLAUDE.md)." % path
        )
    with open(path, "r") as fh:
        return json.load(fh)


def _add_point_attribs(names):
    for n in names:
        if geo.findPointAttrib(n) is None:
            geo.addAttrib(hou.attribType.Point, n, 0.0)


def _add_prim_attribs(names):
    for n in names:
        if geo.findPrimAttrib(n) is None:
            geo.addAttrib(hou.attribType.Prim, n, 0.0)


def _detail(name, value):
    if geo.findGlobalAttrib(name) is None:
        geo.addAttrib(hou.attribType.Global, name, type(value)())
    geo.setGlobalAttribValue(name, value)


# ========================================================================================
# ribs — the canopy, one open polyline per deck station
# ========================================================================================
if MODE == "ribs":
    env = _load("envelope.json")
    pts = env["points"]
    meta = env.get("_meta", {})

    # drivers carried from the engine. these are measurements, not styling knobs.
    SCALARS = [
        "s_m",                        # arc length along the deck
        "deficit_svf",                # stolen sky: svf_prepark - svf_deck
        "svf_deck", "svf_prepark",
        "winter_sun_now", "winter_sun_prepark",
        "aperture_az_deg", "aperture_alt_deg",
        "directionality",
        "rib_height_m", "reach_m",
        "recaptured_winter_sun_frac",
    ]

    _add_prim_attribs(SCALARS)
    _add_point_attribs(SCALARS + ["ribt", "apexdist"])
    if geo.findPrimAttrib("station") is None:
        geo.addAttrib(hou.attribType.Prim, "station", 0)

    for i, p in enumerate(pts):
        rib = p.get("rib") or []
        if len(rib) < 2:
            continue  # a flat station with no canopy — skip rather than emit a degenerate prim

        apex = p.get("apex")
        poly = geo.createPolygon()
        poly.setIsClosed(False)

        n = len(rib)
        made = []
        for j, xyz in enumerate(rib):
            pt = geo.createPoint()
            pt.setPosition(hou.Vector3(float(xyz[0]), float(xyz[1]), float(xyz[2])))
            # 0..1 along the rib, for profile taper / ramp lookups on the sweep
            pt.setAttribValue("ribt", float(j) / float(n - 1))
            if apex:
                d = (pt.position() - hou.Vector3(*[float(a) for a in apex])).length()
                pt.setAttribValue("apexdist", float(d))
            for k in SCALARS:
                if k in p:
                    pt.setAttribValue(k, float(p[k]))
            poly.addVertex(pt)
            made.append(pt)

        poly.setAttribValue("station", int(i))
        for k in SCALARS:
            if k in p:
                poly.setAttribValue(k, float(p[k]))

    _detail("hl_source", "data/envelope.json")
    _detail("hl_model", str(meta.get("model", "")))
    _detail("hl_generated", str(meta.get("generated", "")))
    _detail("hl_n_stations", int(meta.get("n_stations", len(pts))))
    rb = meta.get("readback", {})
    for k, v in rb.items():
        if isinstance(v, (int, float)):
            _detail("hl_" + k, float(v))


# ========================================================================================
# context — the real NYC massing. the canopy must never be rendered in a void.
# ========================================================================================
elif MODE == "context":
    fc = _load("highline_footprints.json")

    if geo.findPrimAttrib("height") is None:
        geo.addAttrib(hou.attribType.Prim, "height", 0.0)
    if geo.findPrimAttrib("year") is None:
        geo.addAttrib(hou.attribType.Prim, "year", 0)
    if geo.findPrimAttrib("bin") is None:
        geo.addAttrib(hou.attribType.Prim, "bin", "")
    if geo.findPrimAttrib("post2009") is None:
        geo.addAttrib(hou.attribType.Prim, "post2009", 0)

    def emit_ring(ring, props):
        # GeoJSON repeats the first vertex last; drop it or the poly self-degenerates.
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) < 3:
            return
        poly = geo.createPolygon()
        poly.setIsClosed(True)
        for xz in ring:
            pt = geo.createPoint()
            pt.setPosition(hou.Vector3(float(xz[0]), 0.0, float(xz[1])))
            poly.addVertex(pt)

        h = props.get("height")
        poly.setAttribValue("height", float(h) if h is not None else 0.0)
        poly.setAttribValue("bin", str(props.get("id", "")))
        yr = props.get("construction_year")
        try:
            yr = int(yr)
        except (TypeError, ValueError):
            yr = 0
        poly.setAttribValue("year", yr)
        # the attribution argument: post-2009 towers own 53.7% of the deck's enclosure
        poly.setAttribValue("post2009", 1 if yr >= 2009 else 0)

    for feat in fc.get("features", []):
        g = feat.get("geometry") or {}
        props = feat.get("properties", {})
        gt = g.get("type")
        coords = g.get("coordinates") or []
        if gt == "MultiPolygon":
            for polygon in coords:
                if polygon:
                    emit_ring(polygon[0], props)   # exterior ring; holes ignored for massing
        elif gt == "Polygon":
            if coords:
                emit_ring(coords[0], props)

    _detail("hl_source", "data/highline_footprints.json")
    _detail("hl_n_buildings", len(fc.get("features", [])))


# ========================================================================================
# deck — the centreline, at deck level
# ========================================================================================
elif MODE == "deck":
    fc = _load("highline_footprints.json")
    hl = fc.get("high_line") or {}
    line = hl.get("centerline") or []
    if len(line) < 2:
        raise hou.NodeError("high_line.centerline missing or too short")

    poly = geo.createPolygon()
    poly.setIsClosed(False)
    for xz in line:
        pt = geo.createPoint()
        pt.setPosition(hou.Vector3(float(xz[0]), DECK_Y, float(xz[1])))
        poly.addVertex(pt)

    _detail("hl_source", "data/highline_footprints.json :: high_line.centerline")
    _detail("hl_length_m", float(hl.get("length_m", 0.0)))
    # NOTE: this is the coarse stored centreline (10 pts). hl_core resamples it before
    # ray-casting. Resample in Houdini before sweeping anything along it.


# ========================================================================================
# access — the 10 weighted access points
# ========================================================================================
elif MODE == "access":
    fc = _load("highline_footprints.json")
    hl = fc.get("high_line") or {}
    if geo.findPointAttrib("weight") is None:
        geo.addAttrib(hou.attribType.Point, "weight", 0.0)
    if geo.findPointAttrib("name") is None:
        geo.addAttrib(hou.attribType.Point, "name", "")

    for a in hl.get("access_points", []):
        pt = geo.createPoint()
        pt.setPosition(hou.Vector3(float(a["x"]), DECK_Y, float(a["z"])))
        pt.setAttribValue("weight", float(a.get("weight", 1.0)))
        pt.setAttribValue("name", str(a.get("name", "")))

    _detail("hl_source", "data/highline_footprints.json :: high_line.access_points")

else:
    raise hou.NodeError("unknown MODE %r — use ribs | context | deck | access" % MODE)
