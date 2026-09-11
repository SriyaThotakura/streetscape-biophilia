"""pick_cameras.py — choose the render stations from the data, and commit them.

The render plan used to say "pick one with high `deficit_svf`". That is an instruction to
choose by eye at render time, which means the image and the caption can drift apart and
nobody can tell which station a finished render actually shows. This script picks the three
stations by stated rules, writes the camera geometry and — critically — **the exact list of
numbers each image is allowed to carry**, so a plate can be checked against its source.

Selection rules (stated, not tuned; each recorded in the output):

  hero     max `deficit_svf` subject to `recaptured_winter_sun_frac` > 0
           — the worst enclosure at which the canopy demonstrably still works.

  open     max `svf_deck` subject to `svf_deck` >= 0.75 AND `river_view` is true
           (`river_view` from data/highline_viewshed.json) — the open contrast, where the
           generator deliberately holds the rib at its minimum so river views aren't shaded.

  section  max `deficit_svf` over all stations — the worst core, which recovers ~0%.

  ⚠️ NOTE ON `section`: "worst deep-canyon" is defined on **deficit_svf (stolen sky)**, NOT
  on minimum `svf_deck`. The three lowest-`svf_deck` stations on the line (s ~= 104.5,
  112.5, 128.6 m) all have `deficit_svf == 0.0`: they were always enclosed and lost nothing
  to the tower boom, and the generator holds their ribs at the 1.20 m minimum. They are not
  what this project is about, and a section drawn there would illustrate the wrong argument.
  Selecting on deficit picks s ~= 1253.9 m, which carries the tallest rib in the family.

Camera geometry — no scaling, no vertical exaggeration, world metres throughout:
  deck plane y = 9.0 m (matches hl_ingest.DECK_Y and the rib bases in envelope.json)
  eye height  1.65 m above the deck -> y = 10.65 m
  Deck tangent is taken from the neighbouring stations' own (x, z) in envelope.json, so the
  cameras sit on the same centreline the engines ray-cast along.

Key light comes from data/sun_vectors.json (winter, day 355): the measured peak, 25.8 deg
elevation at due south. Not placed by eye.

Consumes:  data/envelope.json, data/highline_viewshed.json, data/sun_vectors.json
Produces:  houdini/cameras.json

Reads only. Touches nothing under data/ and nothing in hl_ingest.py.

Run:  python houdini/pick_cameras.py
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
DATA = os.path.join(PROJECT, "data")

DECK_Y = 9.0            # metres, deck plane — same constant hl_ingest.py uses
EYE_H = 1.65            # metres above the deck; standing eye height
OPEN_SVF_MIN = 0.75     # the brief's open threshold, and the generator's own hold-flat gate

# Image B must show the deck open to the sky WITH the city still in frame — an open station
# with no building within sight illustrates nothing about a corridor. This is the "built
# context in frame" gate, applied as a hard constraint on B's selection pool.
CONTEXT_MAX_WALL_M = 40.0

# framing distances along / across the deck, in metres. These position the camera; they do
# not scale or exaggerate anything.
HERO_BACK, HERO_FWD = 25.0, 15.0
OPEN_BACK, OPEN_FWD = 20.0, 30.0
SECTION_OFFSET = 45.0


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=PROJECT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def _load(name):
    with open(os.path.join(DATA, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _r(v, n=3):
    """Round, but keep None as None — a value that cannot be computed stays null."""
    return None if v is None else round(float(v), n)


def _tangent(pts, i):
    """Unit deck tangent at station i, from the neighbouring stations' own coordinates."""
    a = pts[max(0, i - 1)]
    b = pts[min(len(pts) - 1, i + 1)]
    dx, dz = b["x"] - a["x"], b["z"] - a["z"]
    n = math.hypot(dx, dz) or 1.0
    return dx / n, dz / n


# ─────────────────────────────────────────────────────────────────────────────
# camera clearance — added 2026-08-20
#
# Every camera here is placed by OFFSETTING from a station: HERO_BACK along the deck,
# OPEN_BACK along it, SECTION_OFFSET across it. Until now nothing tested whether the
# resulting point was in open air, and on the complete footprint set it was not: A landed
# inside BIN 1089968 (41.15 m) and C inside BIN 1089395 (100.28 m). A camera inside a
# closed prism renders the INSIDE OF A BOX — solid black, with nothing in the viewport or
# the console to say so. 102 of the 232 deck stations sit inside a footprint, so this is
# not a rare corner: it is the normal condition of a viaduct that runs through buildings.
#
# The test is applied to the SELECTION, not to the emitted camera. A station whose camera
# cannot be placed in open air is skipped and the next-best station BY THE SAME RULE is
# taken. Every skip is recorded in the station's `clearance` block, so a moved station is
# auditable and never silent.
# ─────────────────────────────────────────────────────────────────────────────
CLEARANCE_SAMPLES = 6      # camera, target, and the points between, inclusive

_FOOTPRINT_CACHE = None


def _footprints():
    """(bin, height, outer_ring) per building. Read-only; data/ is frozen."""
    global _FOOTPRINT_CACHE
    if _FOOTPRINT_CACHE is None:
        fc = _load("highline_footprints.json")
        out = []
        for f in fc["features"]:
            props = f["properties"]
            for poly in f["geometry"]["coordinates"]:
                out.append((str(props.get("id", "")), float(props["height"]), poly[0]))
                break                      # outer ring only, as hl_ingest does
        _FOOTPRINT_CACHE = out
    return _FOOTPRINT_CACHE


def _in_ring(x, z, ring):
    """Even-odd point-in-polygon in the project's own (x, z) ground plane."""
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, zi = float(ring[i][0]), float(ring[i][1])
        xj, zj = float(ring[j][0]), float(ring[j][1])
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            inside = not inside
        j = i
    return inside


def _buried(x, z, y):
    """Prisms that enclose (x, z) AND rise above height y. Empty list means open air.

    The height test is what makes this meaningful: standing over a 4 m shed at eye height
    10.65 m is open air, standing inside a 41 m tower is not.
    """
    return [(b, h) for b, h, ring in _footprints() if h > y and _in_ring(x, z, ring)]


def _blockers(cam, tgt, whole_sightline):
    """Where the camera (and optionally its whole sight line) is buried.

    `whole_sightline` is the difference between a perspective plate and a section:

      * PERSPECTIVE (A, B) — nothing cuts geometry away at render time, so a buried TARGET
        or a buried point between is a wall filling the frame. The whole line must be clear.
      * ORTHOGRAPHIC SECTION (C) — everything nearer than the deck is cut away by
        construction, and the target is the worst core, which is inside a building BECAUSE
        it is the worst core. Requiring a clear target there would reject the subject of the
        plate. Only the camera position is tested.
    """
    hits = []
    cb = _buried(cam[0], cam[2], cam[1])
    if cb:
        hits.append(("camera", 0.0, cb[0]))
    if whole_sightline:
        for k in range(1, CLEARANCE_SAMPLES):
            t = k / float(CLEARANCE_SAMPLES - 1)
            x = cam[0] + (tgt[0] - cam[0]) * t
            z = cam[2] + (tgt[2] - cam[2]) * t
            y = cam[1] + (tgt[1] - cam[1]) * t
            hb = _buried(x, z, y)
            if hb:
                hits.append(("target" if t >= 1.0 else "sight line", round(t, 3), hb[0]))
    return hits


def _pick_clear(ordered, camera_of, whole_sightline, rule):
    """First candidate in rule order whose camera can actually be placed.

    `ordered` is already sorted by the plate's own selection rule, so taking the first
    clear one IS that rule plus a physical-placement constraint — not a new preference.
    """
    rejected = []
    for rank, (i, p) in enumerate(ordered):
        cam, tgt = camera_of(i, p)[:2]
        hits = _blockers(cam, tgt, whole_sightline)
        if not hits:
            return i, p, {
                "rule": rule,
                "test": ("whole camera->target sight line" if whole_sightline
                         else "camera position only"),
                "test_reason": (
                    "a perspective plate has nothing cutting geometry away, so a buried "
                    "target is a wall in frame" if whole_sightline else
                    "the section plane cuts everything nearer than the deck, and the worst "
                    "core is inside a building because it IS the worst core"),
                "samples_along_sightline": CLEARANCE_SAMPLES if whole_sightline else 1,
                "chosen_rank_in_pool": rank,
                "rejected_ahead_of_it": rejected,
                "note": ("The unconstrained argmax is rank 0. Ranks skipped here were "
                         "skipped because the camera could not be placed in open air, not "
                         "because the selection rule changed."),
            }
        rejected.append({
            "rank_in_pool": rank,
            "s_m": _r(p["s_m"], 2),
            "blocked_at": [{"where": w, "t": t, "bin": b, "height_m": _r(h, 2)}
                           for w, t, (b, h) in hits],
        })
    raise SystemExit("CLEARANCE: no station in the pool for %r has a placeable camera. "
                     "That is a finding about the site, not a bug — widen the pool or "
                     "change the offset, deliberately." % rule)


def _viewshed_index(vs):
    """s_m -> viewshed row, plus a nearest-key lookup (the two engines resample identically,
    but they round s to different precision, so match on nearest rather than on equality)."""
    rows = {round(p["s_m"], 1): p for p in vs["points"]}
    keys = sorted(rows)

    def nearest(s):
        return rows[min(keys, key=lambda k: abs(k - s))]

    return nearest


def _recapture_caveats():
    """The three caveats that must travel with any recapture figure, read from the single
    place they are written: houdini/sources.json. Duplicating them here is what let them go
    stale across the 2026-08-15 re-fetch."""
    path = os.path.join(HERE, "sources.json")
    ids = ["recapture_instrument", "recapture_nonsignificance", "sensor_apex"]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            cav = json.load(fh)["caveats"]
    except Exception as exc:
        raise SystemExit(
            "cannot read caveats from houdini/sources.json (%r). Refusing to write "
            "cameras.json with retyped caveat text — that is the failure mode this "
            "indirection exists to prevent." % exc)
    missing = [i for i in ids if i not in cav]
    if missing:
        raise SystemExit("houdini/sources.json is missing caveat id(s): %s" % missing)
    return [cav[i] for i in ids]


def _numbers(p, vrow):
    """The numbers this station's image is allowed to carry, each with its source.

    `recaptured_winter_sun_frac` is SUPPRESSED (null + reason) where the station lost no sky:
    recovering 100% of a zero deficit is not a measurement, and printing "100%" on a plate
    would read as the canopy performing when nothing was ever taken.
    """
    deficit = float(p["deficit_svf"])
    recap_quotable = deficit > 0.0
    return {
        "deficit_svf": {
            "value": _r(deficit, 4),
            "source": "data/envelope.json :: points[].deficit_svf",
            "gloss": "stolen sky — svf_prepark minus svf_deck",
        },
        "svf_deck": {
            "value": _r(p["svf_deck"], 4),
            "source": "data/envelope.json :: points[].svf_deck",
            "gloss": "sky view factor at the deck today (2.5-D isovist; reads systematically "
                     "more open than Ladybug — never present raw and calibrated as "
                     "interchangeable)",
        },
        "recaptured_winter_sun_frac": {
            "value": _r(p["recaptured_winter_sun_frac"], 3) if recap_quotable else None,
            "quotable": recap_quotable,
            "null_reason": None if recap_quotable else
                           "deficit_svf == 0.0 — this station lost no sky, so the recapture "
                           "fraction is undefined as a performance claim, not zero and not "
                           "100%. DO NOT print a recapture number on this plate.",
            "source": "data/envelope.json :: points[].recaptured_winter_sun_frac",
            "instrument": "hand-rolled hl_core ray cast",
            # NOT retyped here. Pulled from houdini/sources.json's caveat registry so the
            # wording exists in exactly one place — these were duplicated once and went
            # stale the moment the footprint re-fetch moved every figure in them.
            "caveats_that_must_travel_with_it": _recapture_caveats(),
            "caveats_source": "houdini/sources.json :: caveats["
                              "recapture_instrument, recapture_nonsignificance, sensor_apex]",
        },
        "rib_height_m": {
            "value": _r(p["rib_height_m"], 2),
            "source": "data/envelope.json :: points[].rib_height_m",
        },
        "reach_m": {
            "value": _r(p["reach_m"], 2),
            "source": "data/envelope.json :: points[].reach_m",
        },
        "enclosure_deg": {
            "value": _r(vrow.get("enclosure_deg"), 1),
            "source": "data/highline_viewshed.json :: points[].enclosure_deg",
        },
        "nearest_wall_m": {
            "value": _r(vrow.get("nearest_wall_m"), 1),
            "source": "data/highline_viewshed.json :: points[].nearest_wall_m",
            "gloss": "how much built context is actually within frame at this station",
        },
        "dom_occ_year": {
            "value": vrow.get("dom_occ_year"),
            "source": "data/highline_viewshed.json :: points[].dom_occ_year",
            "gloss": "construction year of the dominant occluder — post-2009 means the "
                     "enclosure in frame is tower-boom, not pre-existing fabric",
        },
    }


def _eye(x, z):
    return [_r(x, 2), _r(DECK_Y + EYE_H, 3), _r(z, 2)]


# ─────────────────────────────────────────────────────────────────────────────
# captions — the template lives here, the NUMBER lives only in `numbers`
# ─────────────────────────────────────────────────────────────────────────────
def _caption(title, line_specs, note=None, omitted=None):
    """A caption block holds label + key + format ONLY.

    It deliberately does NOT store a copy of the value. `--captions` resolves each `key`
    against the station object at emit time, so every figure that reaches a plate exists in
    exactly one place — `numbers.<field>.value` — and cannot drift from a transcribed copy
    in the render plan or in this template.
    """
    return {
        "title": title,
        "lines": [{"label": lab, "key": key, "format": fmt}
                  for lab, key, fmt in line_specs],
        "caveats_key": "numbers.recaptured_winter_sun_frac.caveats_that_must_travel_with_it",
        "caveats_trigger": "include the caveats iff the plate prints "
                           "recaptured_winter_sun_frac",
        "note": note,
        "omitted_lines": omitted or [],
        "contract": "Values are NOT stored here. Each line names a key path into this "
                    "station object; `python houdini/pick_cameras.py --captions` resolves "
                    "them. Never transcribe a number into the render plan — reference the "
                    "key and regenerate.",
    }


def resolve(obj, path):
    """Resolve a dotted key path. Integer segments index into lists; `[*]` maps the rest of
    the path over every element of a list, yielding a list. A segment containing dots as
    part of a real dict key (e.g. 'CHS 219x8') still works because dict lookup is tried
    first. Returns (value, found)."""
    cur = obj
    parts = path.split(".")
    for i, part in enumerate(parts):
        if part == "[*]":
            if not isinstance(cur, list):
                return None, False
            rest = ".".join(parts[i + 1:])
            out = []
            for el in cur:
                v, ok = (el, True) if not rest else resolve(el, rest)
                if not ok:
                    return None, False
                out.append(v)
            return out, True
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
                continue
            return None, False
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
                continue
            except (ValueError, IndexError):
                return None, False
        return None, False
    return cur, True


REDUCERS = {
    "min": lambda v: min(v),
    "max": lambda v: max(v),
    "sum": lambda v: sum(v),
    "mean": lambda v: sum(v) / len(v),
    "count": lambda v: len(v),
    "count_zero": lambda v: sum(1 for x in v if x == 0),
    "count_nonzero": lambda v: sum(1 for x in v if x != 0),
    "span": lambda v: max(v) - min(v),
}


# ─────────────────────────────────────────────────────────────────────────────
# population plates — captions for the images that describe the whole family
# ─────────────────────────────────────────────────────────────────────────────
def _load_sources():
    path = os.path.join(HERE, "sources.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_source_key(src, key, _seen=None):
    """Resolve one sources.json key to (value, note). Handles `derive` specs.

    Returns (value, null_reason). value is None when it cannot be resolved, and the reason
    says why — null, never 0.
    """
    _seen = _seen or set()
    if key in _seen:
        return None, f"circular derive involving `{key}`"
    _seen = _seen | {key}

    spec = src["keys"].get(key)
    if spec is None:
        return None, f"key `{key}` is not defined in houdini/sources.json"

    if "derive" in spec:
        d = spec["derive"]
        if d.get("op") == "ratio":
            num, rn = _resolve_source_key(src, d["numerator"], _seen)
            den, rd = _resolve_source_key(src, d["denominator"], _seen)
            if num is None:
                return None, f"numerator unresolved — {rn}"
            if den is None:
                return None, f"denominator unresolved — {rd}"
            if not den:
                return None, "denominator is zero — ratio undefined, not 0"
            return float(num) / float(den), None
        return None, f"unknown derive op `{d.get('op')}`"

    fpath = os.path.join(DATA, os.path.basename(spec["file"]))
    if not os.path.exists(fpath):
        return None, f"source file {spec['file']} not found — run the engine that writes it"
    with open(fpath, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    val, found = resolve(doc, spec["path"])
    if not found:
        return None, f"path `{spec['path']}` not present in {spec['file']}"
    if val is None:
        return None, f"`{spec['path']}` is null in {spec['file']}"
    red = spec.get("reduce")
    if red:
        if not isinstance(val, list):
            return None, f"`reduce: {red}` needs a list; `{spec['path']}` gave {type(val).__name__}"
        if not val:
            return None, f"`{spec['path']}` resolved to an empty list — nothing to reduce"
        fn = REDUCERS.get(red)
        if fn is None:
            return None, f"unknown reduce op `{red}` (have {', '.join(sorted(REDUCERS))})"
        try:
            val = fn(val)
        except TypeError as exc:
            return None, f"`reduce: {red}` failed on `{spec['path']}`: {exc}"
    return val, None


def render_population_captions(src, out):
    """Append population-plate caption blocks, resolved through sources.json."""
    w = out.append
    for plate_id, plate in src.get("plates", {}).items():
        w("─" * 78)
        w(plate["title"])
        w("─" * 78)
        fired = []
        for key in plate["lines"]:
            spec = src["keys"].get(key, {})
            label = spec.get("label", key)
            val, reason = _resolve_source_key(src, key)
            if val is None:
                w(f"  {label:<34} null  — DO NOT PRINT ON THIS PLATE")
                for chunk in _wrap(reason or "unresolved", 70):
                    w(f"  {'':<34}   {chunk}")
                continue
            try:
                shown = spec.get("format", "{}").format(val)
            except (ValueError, TypeError):
                shown = str(val)
            w(f"  {label:<34} {shown}   [{key}]")
            fired.extend(spec.get("caveats", []))

        if plate.get("note"):
            w("")
            for chunk in _wrap(plate["note"], 74):
                w(f"  {chunk}")

        seen, ordered = set(), []
        for c in fired:
            if c not in seen:
                seen.add(c)
                ordered.append(c)
        if ordered:
            w("")
            w("  CAVEATS — these travel with the numbers above, on the plate:")
            for i, cid in enumerate(ordered, 1):
                text = src["caveats"].get(cid, f"<undefined caveat `{cid}`>")
                lines = _wrap(text, 68)
                w(f"    {i}. [{cid}] {lines[0]}")
                for extra in lines[1:]:
                    w(f"       {extra}")
        w("")


def render_captions(doc, stream=None):
    """Print each image's caption block, filled from cameras.json."""
    out = []
    w = out.append
    kl = doc["key_light"]
    w("=" * 78)
    w("CAPTION BLOCKS — generated from houdini/cameras.json. Do not retype these.")
    w(f"  generated {doc['_meta']['generated']}   ·   source {doc['_meta']['script']}")
    w("=" * 78)
    w("")
    w(f"KEY LIGHT (all plates): winter day {kl['day_of_year']} · "
      f"{kl['elev_deg']}° elevation at {kl['azim_deg']}° azimuth")
    w(f"  to_sun {kl['to_sun_unit']}   ·   light travel {kl['light_travel_unit']}")
    w("")

    for st in doc["stations"]:
        cap = st["caption"]
        w("─" * 78)
        w(cap["title"])
        w("─" * 78)
        prints_recapture = False
        for ln in cap["lines"]:
            val, found = resolve(st, ln["key"])
            if not found:
                w(f"  {ln['label']:<34} <MISSING KEY {ln['key']}>")
                continue
            if val is None:
                reason, _ = resolve(st, ln["key"].rsplit(".", 1)[0] + ".null_reason")
                w(f"  {ln['label']:<34} null  — DO NOT PRINT ON THIS PLATE")
                if reason:
                    for chunk in _wrap(str(reason), 70):
                        w(f"  {'':<34}   {chunk}")
                continue
            try:
                shown = ln["format"].format(val)
            except (ValueError, TypeError):
                shown = str(val)
            w(f"  {ln['label']:<34} {shown}")
            if ln["key"].startswith("numbers.recaptured_winter_sun_frac"):
                prints_recapture = True

        if cap.get("note"):
            w("")
            for chunk in _wrap(cap["note"], 74):
                w(f"  {chunk}")

        for om in cap.get("omitted_lines", []):
            w("")
            w(f"  OMITTED — \"{om['line']}\" is deliberately not on this plate:")
            for chunk in _wrap(om["reason"], 70):
                w(f"    {chunk}")
            for chunk in _wrap(om["not_a_threshold_change"], 70):
                w(f"    {chunk}")

        if prints_recapture:
            cav, found = resolve(st, cap["caveats_key"])
            if found and cav:
                w("")
                w("  CAVEATS — these travel with the recapture number, on the plate:")
                for i, c in enumerate(cav, 1):
                    lines = _wrap(c, 70)
                    w(f"    {i}. {lines[0]}")
                    for extra in lines[1:]:
                        w(f"       {extra}")
        w("")

    src = _load_sources()
    if src:
        w("")
        w("=" * 78)
        w("POPULATION PLATES — resolved through houdini/sources.json")
        w("=" * 78)
        w("")
        render_population_captions(src, out)
    else:
        w("  (houdini/sources.json not found — population plates not rendered)")

    text = "\n".join(out)
    print(text, file=stream) if stream else print(text)
    return text


def render_build_constants(doc, src):
    """Emit every constant blender/BLENDER_BUILD_STEPS.md needs, resolved at emit time.

    The build steps hold key references; this resolves them. Nothing here is stored — camera
    values come from cameras.json, population figures from sources.json, and the geometric
    quantities (scene extent, ortho scale, the shadow reference tower, camera A's nearest
    neighbour) are DERIVED from the same data the engines read. Every line names its origin.
    """
    out = []
    w = out.append
    m = doc["_meta"]
    env = _load("envelope.json")
    fc = _load("highline_footprints.json")
    att = _load("attribution.json")

    w("=" * 78)
    w("BUILD CONSTANTS — generated. blender/BLENDER_BUILD_STEPS.md holds the keys.")
    w(f"  cameras.json generated {m['generated']}   ·   do not transcribe any of this")
    w("=" * 78)

    # ── rig ────────────────────────────────────────────────────────────────────
    deck = float(m["deck_plane_y_m"])
    eye = float(m["eye_height_m"])
    w("")
    w("RIG                                     [cameras.json :: _meta]")
    w(f"  deck plane y                         {deck:.2f} m")
    w(f"  eye height above deck                {eye:.2f} m   -> camera Z {deck + eye:.2f} m")
    w(f"  stations available                   {m['n_stations_available']}")

    # ── scene extent ───────────────────────────────────────────────────────────
    xs, zs, hs = [], [], []
    for f in fc["features"]:
        hs.append(float(f["properties"]["height"]))
        for poly in f["geometry"]["coordinates"]:
            for c in poly[0]:
                xs.append(float(c[0])); zs.append(float(c[1]))
    rx = [v[0] for p in env["points"] for v in p["rib"]]
    ry = [v[1] for p in env["points"] for v in p["rib"]]
    rz = [v[2] for p in env["points"] for v in p["rib"]]
    X0, X1 = min(min(xs), min(rx)), max(max(xs), max(rx))
    Z0, Z1 = min(min(zs), min(rz)), max(max(zs), max(rz))
    H1 = max(hs)
    diag = math.hypot(X1 - X0, Z1 - Z0)
    corner = math.sqrt((X1 - X0) ** 2 + (Z1 - Z0) ** 2 + H1 ** 2)
    clip = 500 * math.ceil(corner * 1.5 / 500)
    w("")
    w("SCENE EXTENT              [derived from highline_footprints.json + envelope.json]")
    w(f"  footprints  X {min(xs):9.2f} .. {max(xs):9.2f}   Z {min(zs):9.2f} .. {max(zs):9.2f}"
      f"   H 0 .. {H1:.2f}")
    w(f"  ribs        X {min(rx):9.2f} .. {max(rx):9.2f}   Z {min(rz):9.2f} .. {max(rz):9.2f}"
      f"   Y {min(ry):.2f} .. {max(ry):.2f}")
    w(f"  plan diagonal                        {diag:,.0f} m")
    w(f"  corner-to-corner (incl. height)      {corner:,.0f} m")
    w(f"  -> CLIP END, viewport and every camera   {clip:,.0f} m   (1.5x corner, rounded up)")
    w("     clip start 0.10 m")

    # ── cameras ────────────────────────────────────────────────────────────────
    w("")
    w("CAMERAS                                 [cameras.json :: stations[].camera]")
    w(f"  {'id':<24}{'type':<14}{'position (project x,y,z)':<30}target")
    for st in doc["stations"]:
        c = st["camera"]
        w(f"  {st['id']:<24}{c['type']:<14}{str(c['position']):<30}{c['target']}")
    w("  Blender = (x, z, y) — see BUILD_STEPS §1. Apply once, in ingest.")

    # ── per-station geometry ───────────────────────────────────────────────────
    def neighbours(px, pz, R):
        got = []
        for f in fc["features"]:
            p = f["properties"]
            for poly in f["geometry"]["coordinates"]:
                ring = poly[0]
                d = min(math.hypot(float(c[0]) - px, float(c[1]) - pz) for c in ring)
                if d <= R:
                    got.append((d, float(p["height"]), p.get("construction_year"), p["id"]))
                break
        return sorted(got)

    share = {str(r["id"]): r["sky_share_pct"] for r in att["leaderboard"]}
    w("")
    w("STATION GEOMETRY                        [derived, 80 m neighbourhood]")
    for st in doc["stations"]:
        x, z = st["station_xz"]
        nb = neighbours(x, z, 80.0)
        if not nb:
            w(f"  {st['id']:<24} no building within 80 m")
            continue
        near_d, near_h, near_y, near_b = nb[0]
        tall = max(nb, key=lambda r: r[1])
        w(f"  {st['id']}  (s = {st['s_m']:.2f} m)")
        w(f"    nearest building                   {near_d:6.2f} m away, {near_h:6.2f} m tall"
          f"   BIN {near_b}, {near_y}")
        w(f"    tallest within 80 m                {tall[1]:6.2f} m at {tall[0]:.1f} m"
          f"   BIN {tall[3]}, {tall[2]}"
          + (f"  (sky share {share[tall[3]]:.2f}%)" if tall[3] in share else ""))

    # ── ortho scale for the section camera ─────────────────────────────────────
    sec = next((s for s in doc["stations"] if s["camera"]["type"] == "orthographic"), None)
    if sec:
        x, z = sec["station_xz"]
        tz = float(sec["camera"]["target"][1])
        nb = neighbours(x, z, 80.0)
        tall = max(nb, key=lambda r: r[1])
        v_half = tall[1] - tz + 5.0                 # tallest wall + 5 m headroom above target
        h_full = max(2.0 * tall[0], 40.0)           # both walls, floor of 40 m
        ortho = max(2.0 * v_half, h_full)
        w("")
        w("ORTHO SCALE — section camera            [derived from that station's canyon]")
        w(f"  target Z                             {tz:.2f} m")
        w(f"  tallest wall within 80 m             {tall[1]:.2f} m at {tall[0]:.1f} m (BIN {tall[3]})")
        w(f"  vertical half-extent needed          {v_half:.1f} m  -> full {2*v_half:.1f} m")
        w(f"  horizontal extent needed             {h_full:.1f} m")
        w(f"  -> ORTHO_SCALE                       {ortho:.0f}   (the larger of the two)")
        w("  Widen to fit the CANYON if it clips; never narrow it to fill frame with canopy.")

    # ── sun and the shadow check ───────────────────────────────────────────────
    kl = doc["key_light"]
    alt = float(kl["elev_deg"])
    mult = 1.0 / math.tan(math.radians(alt))
    w("")
    w("SUN + SHADOW CHECK                      [cameras.json :: key_light, + derived]")
    w(f"  winter day {kl['day_of_year']}, elevation {alt:.4f} deg, azimuth {kl['azim_deg']:.1f} deg")
    w(f"  to_sun (project)                     {kl['to_sun_unit']}")
    w(f"  light travel (project)               {kl['light_travel_unit']}")
    w(f"  rotation_euler                       ({math.radians(90-alt):.6f}, 0.0, "
      f"{math.radians(180-float(kl['azim_deg'])):.6f}) rad"
      f"  = ({90-alt:.4f} deg, 0, {180-float(kl['azim_deg']):.4f} deg)")
    w(f"  shadow multiplier  1/tan(alt)        {mult:.3f} x height")
    if sec:
        w(f"  REFERENCE TOWER  BIN {tall[3]}  {tall[1]:.2f} m tall")
        w(f"    -> must cast {tall[1]*mult:,.1f} m of shadow, running NORTH (+Y in Blender)")
        w("    Measure it in top view before rendering. Wrong length = wrong scale or altitude;")
        w("    wrong direction = the lamp is aimed along to_sun instead of light travel.")

    # ── counts ─────────────────────────────────────────────────────────────────
    fbins = {str(f["properties"].get("id", "")) for f in fc["features"]}
    n_ranked = len(fbins & set(share))
    n_rings = sum(len(f["geometry"]["coordinates"]) for f in fc["features"])
    n_pts = len(env["points"])
    n_cp = sum(len(p["rib"]) for p in env["points"])
    w("")
    w("EXPECTED COUNTS — check these in the Outliner and Spreadsheet   [derived]")
    w(f"  HL_Ribs splines                      {n_pts}")
    w(f"  HL_Ribs control points               {n_cp}   ({n_pts} x {n_cp//n_pts})")
    w(f"  HL_Context prisms (total)            {n_rings}")
    w(f"    HL_Context_ranked                  {n_ranked}   (carry a measured sky share)")
    w(f"    HL_Context_unranked                {len(fbins) - n_ranked}   (absent from attribution)")
    w(f"  HL_Deck vertices / faces             {2*n_pts} / {n_pts-1}")
    w(f"  HL_Access empties                    "
      f"{len((fc.get('high_line') or {}).get('access_points', []))}")

    # ── rib population, via sources.json ───────────────────────────────────────
    w("")
    w("RIB POPULATION                          [sources.json keys]")
    for key in ("envelope_stations", "envelope_rib_min_m", "envelope_rib_max_m",
                "envelope_reach_max_m", "envelope_reach_nonzero_count",
                "envelope_reach_zero_count", "envelope_open_svf",
                "ribsched_n_bespoke", "ribsched_coverage_pct", "ribsched_t01_share_pct"):
        spec = src["keys"].get(key)
        if spec is None:
            w(f"  {key:<36} <not defined in sources.json>")
            continue
        val, reason = _resolve_source_key(src, key)
        if val is None:
            w(f"  {spec.get('label', key):<36} null — {reason}")
        else:
            try:
                shown = spec.get("format", "{}").format(val)
            except (ValueError, TypeError):
                shown = str(val)
            w(f"  {spec.get('label', key):<36} {shown}   [{key}]")
    w("")
    w("  The scale check tests against the REALISED max rib height above, never")
    w("  RIB_MAX_H in envelope.json _meta.params, which is a ceiling no rib reaches.")
    w("")

    text = "\n".join(out)
    print(text)
    return text


def _wrap(s, width):
    words, lines, cur = str(s).split(), [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def build():
    env = _load("envelope.json")
    vs = _load("highline_viewshed.json")
    sun = _load("sun_vectors.json")
    pts = env["points"]
    nearest = _viewshed_index(vs)

    # ---- selection -----------------------------------------------------------------
    hero_pool = [(i, p) for i, p in enumerate(pts) if p["recaptured_winter_sun_frac"] > 0.0]
    hero_pool.sort(key=lambda ip: -ip[1]["deficit_svf"])

    def _cam_hero(i, p):
        tx, tz = _tangent(pts, i)
        return (_eye(p["x"] - tx * HERO_BACK, p["z"] - tz * HERO_BACK),
                _eye(p["x"] + tx * HERO_FWD, p["z"] + tz * HERO_FWD),
                tx, tz)

    i_hero, p_hero, clear_hero = _pick_clear(
        hero_pool, _cam_hero, True,
        "max deficit_svf subject to recaptured_winter_sun_frac > 0")

    # B's pool is gated on built context as a HARD constraint, not chosen after the fact.
    # Without it the argmax lands at the north rail-yard end with the nearest wall 136.8 m
    # away — genuinely the most open station on the line, and useless as a corridor image.
    open_pool_all = [(i, p) for i, p in enumerate(pts)
                     if p["svf_deck"] >= OPEN_SVF_MIN and nearest(p["s_m"]).get("river_view")]
    open_pool = [ip for ip in open_pool_all
                 if (nearest(ip[1]["s_m"]).get("nearest_wall_m") is not None
                     and nearest(ip[1]["s_m"])["nearest_wall_m"] <= CONTEXT_MAX_WALL_M)]
    open_pool.sort(key=lambda ip: -ip[1]["svf_deck"])

    def _cam_open(i, p):
        tx, tz = _tangent(pts, i)
        return (_eye(p["x"] - tx * OPEN_BACK, p["z"] - tz * OPEN_BACK),
                _eye(p["x"] + tx * OPEN_FWD, p["z"] + tz * OPEN_FWD),
                tx, tz)

    i_open, p_open, clear_open = _pick_clear(
        open_pool, _cam_open, True,
        f"max svf_deck subject to svf_deck >= {OPEN_SVF_MIN}, river_view, and "
        f"nearest_wall_m <= {CONTEXT_MAX_WALL_M}")

    # the station the context gate passed over — recorded, not silently dropped
    i_max_open, p_max_open = max(open_pool_all, key=lambda ip: ip[1]["svf_deck"])
    v_max_open = nearest(p_max_open["s_m"])

    sec_pool = sorted(enumerate(pts), key=lambda ip: -ip[1]["deficit_svf"])

    def _section_side(i, p):
        """The side the rib reaches AWAY from, so the cantilever reads broadside."""
        tx, tz = _tangent(pts, i)
        a = math.radians(float(p["aperture_az_deg"]))
        ax, azz = math.sin(a), math.cos(a)
        n1, n2 = (tz, -tx), (-tz, tx)
        return (n1 if (n1[0] * ax + n1[1] * azz) < 0 else n2), tx, tz

    def _cam_section(i, p):
        side, tx, tz = _section_side(i, p)
        my = DECK_Y + float(p["rib_height_m"]) / 2.0
        return ([p["x"] + side[0] * SECTION_OFFSET, my, p["z"] + side[1] * SECTION_OFFSET],
                [p["x"], my, p["z"]], side, tx, tz, my)

    i_sec, p_sec, clear_sec = _pick_clear(
        sec_pool, _cam_section, False, "max deficit_svf over all stations")

    # ---- the sun, straight from the measured winter peak ----------------------------
    w = sun["days"]["winter"]
    peak = w["peak"]
    to_sun = [float(c) for c in peak["dir"]]
    key_light = {
        "day_of_year": w["day_of_year"],
        "label": "winter solstice peak — the exact condition the recapture figure counts",
        "elev_deg": _r(peak["elev_deg"], 4),
        "azim_deg": _r(peak["azim_deg"], 4),
        "to_sun_unit": [_r(c, 6) for c in to_sun],
        "light_travel_unit": [_r(-c, 6) for c in to_sun],
        "frame": sun["_meta"]["frame"],
        "source": "data/sun_vectors.json :: days.winter.peak",
        "usage": "to_sun_unit points FROM the site TO the sun. A Houdini distant light aims "
                 "down its own -z, so orient it along light_travel_unit. Place the sun from "
                 "this vector, never by eye — the caption has to be able to name the day.",
        "n_daylight_timesteps": w["n_timesteps"],
    }

    stations = []

    # ---- A · hero, eye level under the working canopy --------------------------------
    a_pos, a_tgt, tx, tz = _cam_hero(i_hero, p_hero)
    stations.append({
        "id": "A_hero_eye_level",
        "image": "Stage 3 — Image A, the eye-level hero",
        "selection_rule": "max deficit_svf subject to recaptured_winter_sun_frac > 0",
        "why_this_station":
            "the worst enclosure on the line at which the canopy still demonstrably works "
            f"AND the camera can stand in open air — {p_hero['recaptured_winter_sun_frac']:.1%} "
            f"of winter sun recovered under a {p_hero['rib_height_m']:.2f} m rib. Stations "
            "with a higher deficit exist; the ones that recover nothing are the section's "
            "subject rather than the hero's, and the ones whose camera falls inside a "
            "building are listed in `clearance.rejected_ahead_of_it`.",
        "station_index": i_hero,
        "s_m": _r(p_hero["s_m"], 2),
        "station_xz": [_r(p_hero["x"], 2), _r(p_hero["z"], 2)],
        "deck_y": DECK_Y,
        "camera": {
            "type": "perspective",
            "eye_height_above_deck_m": EYE_H,
            "position": a_pos,
            "target": a_tgt,
            "framing": f"stands {HERO_BACK:.0f} m back along the deck and looks "
                       f"{HERO_BACK + HERO_FWD:.0f} m down it, so the hero rib sits in the "
                       "middle distance with the canyon closing behind it",
            "deck_tangent_xz": [_r(tx, 6), _r(tz, 6)],
        },
        "must_carry": ["human figures at correct scale", "real materiality on deck and steel",
                       "the towers in frame — the antagonist has to be visible"],
        "clearance": clear_hero,
        "numbers": _numbers(p_hero, nearest(p_hero["s_m"])),
        "caption": _caption(
            "IMAGE A · Stage 3 — the eye-level hero",
            [("station", "s_m", "s = {:.2f} m"),
             ("stolen sky (deficit_svf)", "numbers.deficit_svf.value", "{:.4f}"),
             ("sky view today (svf_deck)", "numbers.svf_deck.value", "{:.4f}"),
             ("winter sun recaptured", "numbers.recaptured_winter_sun_frac.value", "{:.1%}"),
             ("rib height", "numbers.rib_height_m.value", "{:.2f} m"),
             ("reach", "numbers.reach_m.value", "{:.2f} m"),
             ("enclosure angle", "numbers.enclosure_deg.value", "{:.1f}°"),
             ("nearest wall", "numbers.nearest_wall_m.value", "{:.1f} m"),
             ("dominant occluder built", "numbers.dom_occ_year.value", "{:d}")],
            note="The dominant occluder here post-dates the park, so the enclosure in frame "
                 "is the tower boom itself — that is the argument, and it is worth a clause "
                 "in the caption."),
    })

    # ---- B · open contrast, river ----------------------------------------------------
    b_pos, b_tgt, tx, tz = _cam_open(i_open, p_open)
    v_open = nearest(p_open["s_m"])
    az = math.radians(float(p_open["aperture_az_deg"]))
    ax, az_z = math.sin(az), math.cos(az)     # hl_core: az measured from +z (north), toward +x
    stations.append({
        "id": "B_open_contrast",
        "image": "Stage 3b — Image B, the open contrast (river)",
        "selection_rule": f"max svf_deck subject to svf_deck >= {OPEN_SVF_MIN} AND "
                          "river_view (data/highline_viewshed.json) AND nearest_wall_m <= "
                          f"{CONTEXT_MAX_WALL_M} (built context in frame)",
        "why_this_station": "the deck open to its sky WITH the city still around it — the "
                            "generator holds the rib near its minimum because svf_deck is "
                            "already high, which is the design rule 'river-view segments "
                            "aren't shaded' shown rather than asserted. The context gate is "
                            "a hard constraint on the pool, not a post-hoc override; see "
                            "`passed_over`.",
        "station_index": i_open,
        "s_m": _r(p_open["s_m"], 2),
        "station_xz": [_r(p_open["x"], 2), _r(p_open["z"], 2)],
        "deck_y": DECK_Y,
        "camera": {
            "type": "perspective",
            "eye_height_above_deck_m": EYE_H,
            "position": b_pos,
            "target": b_tgt,
            "framing": "along the deck, so the open sky above the flat rib is the subject",
            "deck_tangent_xz": [_r(tx, 6), _r(tz, 6)],
            "aperture_heading_xz": [_r(ax, 6), _r(az_z, 6)],
            "aperture_note": "aperture_az_deg "
                             f"{_r(p_open['aperture_az_deg'], 1)} — swing toward this "
                             "heading if the river itself must be in shot rather than the "
                             "corridor.",
        },
        "passed_over": {
            "s_m": _r(p_max_open["s_m"], 2),
            "svf_deck": _r(p_max_open["svf_deck"], 4),
            "deficit_svf": _r(p_max_open["deficit_svf"], 4),
            "rib_height_m": _r(p_max_open["rib_height_m"], 2),
            "nearest_wall_m": _r(v_max_open.get("nearest_wall_m"), 1),
            "recaptured_winter_sun_frac_stored": _r(
                p_max_open["recaptured_winter_sun_frac"], 3),
            "reason":
                "This is the maximum-openness station on the line and it was PASSED OVER. "
                f"Its nearest wall is {_r(v_max_open.get('nearest_wall_m'), 1)} m away — the "
                "north rail-yard end, with effectively no built context in frame. An open "
                "contrast image has to show the deck open WITHIN the city; a station with no "
                "city in sight illustrates nothing about a corridor. It also has "
                "deficit_svf = 0.0, so its stored recapture of 1.000 is 100% of nothing and "
                "could not have been printed at all.",
            "not_a_data_problem": "both facts are true properties of that station, correctly "
                                  "measured. It is the wrong station for this image, not a "
                                  "wrong number.",
        },
        "alternates": [
            {
                "s_m": _r(p["s_m"], 2),
                "svf_deck": _r(p["svf_deck"], 4),
                "deficit_svf": _r(p["deficit_svf"], 4),
                "rib_height_m": _r(p["rib_height_m"], 2),
                "nearest_wall_m": _r(nearest(p["s_m"]).get("nearest_wall_m"), 1),
            }
            for j, p in open_pool if j != i_open
        ][:3],
        "alternates_rule": "runners-up from the same context-gated pool, ordered by "
                           "openness. Substituting one stays a sourced choice — re-run with "
                           "the station changed rather than retyping numbers.",
        "clearance": clear_open,
        "numbers": _numbers(p_open, v_open),
        "caption": _caption(
            "IMAGE B · Stage 3b — the open contrast (river)",
            [("station", "s_m", "s = {:.2f} m"),
             ("sky view today (svf_deck)", "numbers.svf_deck.value", "{:.4f}"),
             ("stolen sky (deficit_svf)", "numbers.deficit_svf.value", "{:.4f}"),
             ("rib height", "numbers.rib_height_m.value", "{:.2f} m"),
             ("reach", "numbers.reach_m.value", "{:.2f} m"),
             ("enclosure angle", "numbers.enclosure_deg.value", "{:.1f}°"),
             ("nearest wall", "numbers.nearest_wall_m.value", "{:.1f} m")],
            note="The subject of this plate is the FLAT rib over an open sky — the generator "
                 "standing down where the deck can still see out. It is a plate about "
                 "restraint, not about performance.",
            omitted=[{
                "line": "winter sun recaptured",
                "key": "numbers.recaptured_winter_sun_frac.value",
                "status": "OMITTED FROM THIS PLATE BY EDITORIAL CHOICE — the value is "
                          "present and quotable in `numbers`, and is NOT suppressed.",
                "reason":
                    "This station's deficit_svf is ~0.01: it lost about one percent of its "
                    "sky. The recapture fraction over that loss is real and passes the "
                    "suppression rule, but on a plate a large-looking percentage sitting "
                    "beside a near-zero deficit reads as the canopy performing, when what it "
                    "actually describes is recovering a trivial loss. The number is not "
                    "wrong; it is misleading at this station, and the honest fix is to leave "
                    "it off rather than to print it with a disclaimer.",
                "not_a_threshold_change":
                    "The suppression rule is unchanged and stays `deficit_svf > 0 strictly`. "
                    "Suppression is a property of the DATA (no loss means no recovery to "
                    "measure); this omission is a property of THIS PLATE. Moving the "
                    "threshold to catch this case would mean inventing a tuned cutoff, which "
                    "is exactly what the project refuses to do elsewhere.",
                "if_you_want_it_back": "add the line to B's caption template in "
                                       "pick_cameras.py and re-run; the value resolves from "
                                       "`numbers` and brings its three caveats with it.",
            }]),
    })

    # ---- C · section through the worst core -------------------------------------------
    # true cross-section: perpendicular to the deck tangent, standing on the side the rib
    # reaches AWAY from so the cantilever reads broadside. Built by the same closure the
    # selection tested, so the emitted camera and the cleared camera cannot disagree.
    c_pos, c_tgt, side, tx, tz, mid_y = _cam_section(i_sec, p_sec)
    stations.append({
        "id": "C_section_worst_core",
        "image": "Stage 5b — Image C, the section through the worst core",
        "selection_rule": f"max deficit_svf over all {len(pts)} stations, subject to a "
                          "camera position in open air",
        "why_this_station":
            "the deepest core the tower boom created at which the section camera can stand "
            f"in open air: {p_sec['deficit_svf']:.1%} of the sky gone, a "
            f"{p_sec['rib_height_m']:.2f} m rib, and "
            f"{p_sec['recaptured_winter_sun_frac']:.1%} winter sun recovered. The canopy at "
            "its most ambitious, failing — which THE_ANSWERING_LINE.md already states as "
            "the honest limit. Deeper cores exist; their cameras land inside the towers "
            "that make them deep, and they are listed in `clearance.rejected_ahead_of_it`.",
        "selection_trap_avoided":
            "NOT selected on minimum svf_deck. "
            + ", ".join(f"s = {q['s_m']:.1f} m" for _, q in
                        sorted(enumerate(pts), key=lambda ip: ip[1]["svf_deck"])[:3])
            + " are the three lowest-svf_deck stations and every one of them has "
              "deficit_svf == 0.0 — always enclosed, nothing taken by the towers, ribs held "
              "at the generator minimum. A section drawn there would show enclosure this "
              "project does not claim to have measured the cause of.",
        "station_index": i_sec,
        "s_m": _r(p_sec["s_m"], 2),
        "station_xz": [_r(p_sec["x"], 2), _r(p_sec["z"], 2)],
        "deck_y": DECK_Y,
        "camera": {
            "type": "orthographic",
            "position": [_r(c_pos[0], 2), _r(c_pos[1], 3), _r(c_pos[2], 2)],
            "target": [_r(c_tgt[0], 2), _r(c_tgt[1], 3), _r(c_tgt[2], 2)],
            "target_deck_level": [_r(p_sec["x"], 2), DECK_Y, _r(p_sec["z"], 2)],
            "framing": f"true cross-section — {SECTION_OFFSET:.0f} m perpendicular to the "
                       "deck tangent, level at mid-rib height so the view is horizontal and "
                       "the canyon walls stay parallel. Orthographic: a section that "
                       "converges is a perspective, and the caption calls it a section.",
            "deck_tangent_xz": [_r(tx, 6), _r(tz, 6)],
            "section_normal_xz": [_r(side[0], 6), _r(side[1], 6)],
            "side_choice": "the side the rib reaches away from, so the cantilever reads "
                           "broadside rather than foreshortened",
        },
        "must_carry": ["the canyon walls at true height", "a human figure on the deck for "
                       "scale", "the rib reaching and still not clearing the wall"],
        "clearance": clear_sec,
        "numbers": _numbers(p_sec, nearest(p_sec["s_m"])),
        "caption": _caption(
            "IMAGE C · Stage 5b — the section through the worst core",
            [("station", "s_m", "s = {:.2f} m"),
             ("stolen sky (deficit_svf)", "numbers.deficit_svf.value", "{:.4f}"),
             ("sky view today (svf_deck)", "numbers.svf_deck.value", "{:.4f}"),
             ("winter sun recaptured", "numbers.recaptured_winter_sun_frac.value", "{:.1%}"),
             ("rib height", "numbers.rib_height_m.value", "{:.2f} m"),
             ("reach", "numbers.reach_m.value", "{:.2f} m"),
             ("enclosure angle", "numbers.enclosure_deg.value", "{:.1f}°"),
             ("nearest wall", "numbers.nearest_wall_m.value", "{:.1f} m"),
             ("dominant occluder built", "numbers.dom_occ_year.value", "{:d}")],
            note="Print the 0.0% rather than omitting it. This is the tallest rib in the "
                 "family reaching as far as the generator allows and recovering nothing — "
                 "THE_ANSWERING_LINE.md's stated limit, made visible: the worst cores are a "
                 "massing problem a canopy cannot fix."),
    })

    out = {
        "_meta": {
            "script": "houdini/pick_cameras.py",
            "git_commit": _git_commit(),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": ["data/envelope.json", "data/highline_viewshed.json",
                       "data/sun_vectors.json"],
            "purpose": "IMPLEMENTATION_PLAN.md W1 — the committed camera rig. Stations are "
                       "chosen from the data by stated rules so a finished render can be "
                       "checked against its caption, instead of being picked by eye at "
                       "render time.",
            "deterministic": True,
            "seed_note": "no stochastic step in this script; selection is argmax over stored "
                         "values and is fully reproducible",
            "reads_only": "this script writes only houdini/cameras.json. Nothing under data/ "
                          "and nothing in hl_ingest.py is touched.",
            "units": "metres throughout, world frame: +x east, +y up, +z north — the frame "
                     "envelope.json, highline_footprints.json and Houdini all already share. "
                     "No swizzle, no rescale.",
            "no_exaggeration": "THE_ANSWERING_LINE.md: no vertical exaggeration anywhere. "
                               "The camera constants position the viewer; none of them scale "
                               "geometry. The canopy is small because the towers are the "
                               "problem — if it reads slight, that is the finding rendering "
                               "itself correctly.",
            "deck_plane_y_m": DECK_Y,
            "eye_height_m": EYE_H,
            "n_stations_available": len(pts),
            "selection_rules": {
                "A_hero_eye_level": "max deficit_svf subject to recaptured_winter_sun_frac > 0",
                "B_open_contrast": f"max svf_deck subject to svf_deck >= {OPEN_SVF_MIN} AND "
                                   "river_view",
                "C_section_worst_core": "max deficit_svf over all stations",
            },
            "number_rule": "Each station carries the numbers that image is allowed to print, "
                           "each with its source path. A figure absent from a station's "
                           "`numbers` block is not board-ready for that plate. Recapture is "
                           "explicitly nulled with a reason where deficit_svf == 0 — null, "
                           "never 0, and never 100%.",
        },
        "key_light": key_light,
        "stations": stations,
    }

    outp = os.path.join(HERE, "cameras.json")
    with open(outp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)

    print(f"wrote {outp}")
    print(f"  key light: winter day {key_light['day_of_year']}, "
          f"{key_light['elev_deg']}deg elev at {key_light['azim_deg']}deg azimuth")
    for st in stations:
        n = st["numbers"]
        rec = n["recaptured_winter_sun_frac"]
        rec_s = f"{rec['value']:.3f}" if rec["value"] is not None else "null (suppressed)"
        print(f"  {st['id']:22s} s {st['s_m']:8.2f} m  deficit {n['deficit_svf']['value']:.4f}"
              f"  svf_deck {n['svf_deck']['value']:.4f}  recap {rec_s}"
              f"  rib {n['rib_height_m']['value']:.2f} m")
    return out


if __name__ == "__main__":
    import argparse
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # the caption blocks carry ° and ⚠
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--captions", action="store_true",
                    help="print each image's caption block, filled from cameras.json, "
                         "instead of rebuilding it. Nothing is written.")
    ap.add_argument("--build-constants", action="store_true",
                    help="print every constant blender/BLENDER_BUILD_STEPS.md needs, resolved "
                         "at emit time. Nothing is written.")
    a = ap.parse_args()
    if a.captions or a.build_constants:
        path = os.path.join(HERE, "cameras.json")
        if not os.path.exists(path):
            raise SystemExit("houdini/cameras.json not found — run "
                             "`python houdini/pick_cameras.py` first")
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        if a.captions:
            render_captions(doc)
        if a.build_constants:
            src = _load_sources()
            if src is None:
                raise SystemExit("houdini/sources.json not found")
            render_build_constants(doc, src)
    else:
        build()
