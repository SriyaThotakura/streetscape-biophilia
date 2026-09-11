# Blender build steps — The Answering Line (W1 renders)

**Target:** Blender 4.x, Cycles, Windows, RTX 4060 8 GB, 64 GB RAM.
**Assumes:** you can navigate Blender; you have not built a lit architectural render in it.
**Follow in order. Do not skip a check.** Several failures here are silent — the scene looks
plausible and the numbers are wrong — so each step ends with the check that catches it.

> ### ⚠️ THE SCENE IS BUILT BY SCRIPT NOW — read §"The two scripts" at the end first
> Since 2026-08-20 every step from §4 to §12 is executed by
> **`blender/build_lookdev.py`**, and the plates by **`blender/render_all.py`**:
>
> ```powershell
> blender --background --factory-startup --python blender/build_lookdev.py
> blender --background blender/answering_line.blend --python blender/render_all.py -- --all --draft
> ```
>
> **The steps below are still the specification** — they say what is built, why each value is
> what it is, and which failures are silent. What changed is that they are no longer clicked
> by hand, and every CHECK in them is now an assertion that aborts the build. Read a step to
> understand a value; change a value in `build_lookdev.py`, never in the `.blend`.
>
> Verified on **Blender 5.2 LTS**, not 4.x. Several APIs this document describes moved — see
> the boxes in §12.1 and §12.2.

**The JSON contract does not change.** `houdini/hl_ingest.py`, `pick_cameras.py`,
`cameras.json`, `sources.json` and everything under `data/` are untouched. Only the consumer
changed.

> ### Every number in this document is a KEY, not a value
>
> ```powershell
> python houdini/pick_cameras.py --build-constants
> ```
>
> That prints the rig, the scene extent and clip end, the three cameras, each station's
> neighbourhood geometry, the section camera's ortho scale, the sun vectors with the shadow
> reference tower, the expected object counts, and the rib population — **all resolved at emit
> time** from `cameras.json`, `sources.json` and the engine outputs. Names in `THIS STYLE`
> below refer to blocks in that output; names like `envelope_rib_max_m` are `sources.json` keys.
>
> **This document deliberately contains almost no numbers.** It used to, and every one of them
> went stale on 2026-08-15 when the footprint re-fetch moved all three camera stations and the
> whole scene extent. If you find yourself typing a figure into a build step, stop — add it to
> `sources.json` or the emitter instead.

> **Governing constraint, from `THE_ANSWERING_LINE.md`:** *No vertical exaggeration anywhere.
> The canopy is small because the towers are the problem — that honesty is the argument.*
>
> **If a step below would make the canopy read better by changing its size, it is not in this
> document, and it must not be added.** Framing, lens, exposure and composition are all fair
> game. Geometry is not.

---

## 0 · What you are building

| Plate | Camera | Priority |
|---|---|---|
| **A** — eye-level hero | `cameras.json` → `stations[0]`, perspective | **ships first; §4.2 blocker** |
| **C** — section, worst core | `stations[2]`, orthographic | ships second |
| **D** — corridor axo | not in `cameras.json`; framed by hand per §9.4 | ships third |
| **B** — open contrast | `stations[1]`, perspective | only if time allows |

Time box is two working days (see the render plan's *Render direction*). If there is no
usable frame by then, stop and fall back to Rhino + Enscape — the ingest contract ports.

---

## 1 · Axis conversion — state it once, apply it once, check it before anything else

The data is a **(x, z) ground plane with y up**. Blender is **z up**.

```
project  +x east   +y UP     +z north
blender  +X east   +Y north  +Z UP

    blender = (px, pz, py)
```

This is implemented in exactly one place — `P()` at the top of `hl_ingest_bpy.py` — and
nowhere else. Do not convert again downstream.

**Why the determinant is −1 and why that is not a mirror.** The project frame is
(east, up, north); Blender's is (east, north, up). Mapping semantic axis to semantic axis
between a left- and a right-handed frame is necessarily a determinant −1 permutation. East
still lands on east, north on north, up on up, so the site, the sun and the shadows are all
preserved exactly. **You have not mirrored anything.**

> ### ⚠️ SILENT FAILURE — the classic one
> Swapping Y and Z the wrong way builds a scene that looks completely normal: a corridor
> with buildings along it. It is lying flat. The corridor is 1.7 km long and only 83 m tall,
> so a Y/Z swap reads as "a long site seen from above" and can survive all the way to a
> render. **Nothing in the viewport will tell you.**

**CHECK — run before any geometry exists.** `axis_check()` runs automatically at the top of
`hl_ingest_bpy.py` and asserts, against station index 100 of `envelope.json`:

```
[axis] station s=803.79  apex project (x=-42.05, y_up=11.69, z_north=-96.05)
[axis]                 apex blender (X=-42.05, Y=-96.05, Z=11.69)
[axis] PASS — Z carries height (11.69 m = 9.0 + 2.69), Y carries north
```

⚠️ **Those coordinates are a transcript of one run, not a constant.** They moved once
already (the 2026-08-15 footprint re-fetch changed every rib). **Read them off your own
run; never check against the numbers printed here.**

The load-bearing assertion is the last one: **apex Z must equal `DECK_Y` + `rib_height_m`**.
Height can only ever be in Z. If that assert fires, stop; nothing downstream is meaningful.

---

## 2 · Scale sanity — a 1.7 m cube, checked against the deck plane and the realised max rib

`scale_check()` places a 1.70 m cube at deck level at station 0 and prints:

```
[scale] 1.70 m cube placed at deck level Z=<deck_plane_y_m>
[scale] realised max rib height <envelope_rib_max_m>  (generator ceiling RIB_MAX_H is NOT reached)
```

**Test against `envelope_rib_max_m` — the realised maximum — not `RIB_MAX_H` in
`_meta.params`.** The ceiling is a generator bound no rib reaches; sizing the scene to it
quietly overstates the canopy.

**CHECK, by eye in the viewport, numeric front view (Numpad 1):**

- the cube's base sits at Z = `deck_plane_y_m`
- the tallest rib is **`envelope_rib_max_m` / 1.70** cube-heights
- the deck plane is **`deck_plane_y_m` / 1.70** cube-heights above ground

**If any of those three is wrong, STOP.** Everything after this — sun angle, camera height,
figure placement, ortho scale — inherits the error, and all of it will still look fine.

> ### ⚠️ THE CUBE IS A VIEWPORT CHECK AND MUST NEVER RENDER
> It stands **on the deck at station 0**, which is 48 m from camera B — close enough to appear
> in frame as an unexplained grey box, and it did, in a rendered plate on 2026-08-20. It had no
> material either, so it rendered as default grey.
>
> `build_lookdev.py` sets `hide_render` on it, and then asserts something stricter that would
> have caught it on day one: **every object visible to the render must carry a material.**
> "Assigned" is not "visible", and this project has been bitten in both directions — a material
> that was assigned and then silently **purged on save for having no users**, and an object
> that was **visible while carrying no material at all.** A build log that only reports what it
> assigned catches neither.

---

## 3 · Scene extent and clipping — set this before you look at anything

Measured from the data:

| | X (east) | Y (north) | Z (up) |
|---|---|---|---|
| context footprints | `SCENE EXTENT` → footprints X | … Z | … H |
| rib geometry | `SCENE EXTENT` → ribs X | … Z | … Y |

**Plan diagonal and corner-to-corner: `SCENE EXTENT`.** Both are derived from the footprints and
the rib geometry, so they follow the data.

> ### ⚠️ SILENT FAILURE — the default clip end is 100 m
> Blender's default viewport and camera clip end is **100 m**. This corridor is **1.7 km**.
> Context towers simply will not be drawn, and there is no warning — the viewport shows an
> apparently complete scene that is missing most of its buildings. Every "why is the site
> empty" hour starts here.

**Set all four, now:**

| Where | Setting | Value |
|---|---|---|
| Viewport `N` panel → View | Clip Start | `0.1 m` |
| Viewport `N` panel → View | **Clip End** | **`SCENE EXTENT` → CLIP END** |
| Each camera → Object Data → Lens | Clip Start | `0.1 m` |
| Each camera → Object Data → Lens | **Clip End** | **`SCENE EXTENT` → CLIP END** |

Clip start of 0.1 m matters for plate **C**: the nearest canyon wall at that station is
**`STATION GEOMETRY` → C → nearest building** from the deck centreline, and camera A's nearest is
**`STATION GEOMETRY` → A → nearest building**. Both are metres, not tens of metres.

**CHECK:** press `Home` in the viewport to frame all. You should see a long thin corridor of
buildings ~1.7 km on the Y axis. If it looks like a small cluster, clipping is still wrong.

### 3.4 The deck-width bound — derived from source rounding, not typed

The deck is lofted between the 232 rib rails (§6.4) and the check is that the rail-to-rail
distance is the width the generator intended. **Both the expected width and its tolerance are
derived.** Live run:

```
[deck] source precision   2 dp -> quantum 0.010 m; bound = quantum*sqrt(2) + float32 = 0.014245 m
[deck] tolerance          4.0 x bound = 0.056981 m   (expected width 9.00 m from DECK_HALF_W 4.50)
[deck] rail-to-rail width min 8.9917 m  max 9.0100 m  ->  worst deviation 0.0100 m (0.70x the source-rounding bound)
```

**The expected width** comes from `envelope.json._meta.params.DECK_HALF_W × 2`, not from a
typed 9.0. If the generator's half-width ever changes, the check follows it — and if the
*parameter* changes without the geometry, the check catches exactly that (negative test 3
below).

**The bound** has a different dominant error source from §4.3's. Here it is not float32
storage but the **2-decimal quantisation `envelope.json` applies before Blender ever sees the
number** — a term ~300× larger at this scale. Both are included:

```python
dp       = _detect_decimals(rail_coords)        # detected from the data: 2
quantum  = 10 ** -dp                            # 0.010 m
src_term = quantum * sqrt(2)                    # two endpoints, each rounded in 2 axes
f32_term = EPS32 * max_abs_rail_coord           # ~1.0e-04 m, 0.7% of src_term
bound    = src_term + f32_term                  # 0.014245 m
tol      = SOURCE_ROUND_MULT * bound            # 4.0 x  ->  0.056981 m
```

`src_term` is `quantum × sqrt(2)` because each rail endpoint is a 2-D point rounded
independently in each axis, displacing it by at most `(quantum/2)·sqrt(2)`, and the distance
between two such points is off by at most the sum of the two displacements.

**`SOURCE_ROUND_MULT` is deliberately the same 4× as `HALF_ULP_MULT`**, for the same reason:
the theoretical bound is a hard ceiling on one rounding pass, 4× absorbs a second, and it stays
far clear of any real error. A wrong axis map, mis-taken rails, or a `DECK_HALF_W` that no
longer matches the geometry all move the width by *centimetres to metres* — negative test 3
lands at 70.78× the bound.

> ### ⚠️ WHY THIS REPLACED A TYPED 0.01
> The previous tolerance was a typed `0.01 m`, which is **0.70× the theoretical bound** — it
> sat *below* the error the source rounding can legitimately produce. The observed spread
> (0.0100 m) was saturating it exactly, so a correct regeneration of `envelope.json` shifting
> one rail coordinate by one hundredth could have aborted the build on **valid data**. A
> tolerance tighter than the known error of its own inputs is not a strict check; it is a
> false alarm waiting for a rebuild.

**Reading a failure.** The deviation is reported as a multiple of the bound, the same way
§4.3 reports half-ULPs, so a failure reads as *"6.89× the source-rounding bound"* rather than
as a bare number you have to calibrate by eye. Verified against deliberate faults:

| injected fault | worst deviation | ratio | result |
|---|---|---|---|
| one station 3 cm wide | 0.0300 m | 2.1× | passes — inside the 4× tolerance |
| one station 10 cm wide | 0.0982 m | **6.89×** | **aborts** |
| `DECK_HALF_W` set to 5.0, geometry unchanged | 1.0083 m | **70.78×** | **aborts** |

The 3 cm case passing is the honest limit, and it is the same trade as §4.3: the check cannot
separate a small real error from accumulated source rounding, so it is calibrated to catch the
class of failure that actually occurs — an axis, rail or parameter mistake — not a millimetric
one. **Do not raise `SOURCE_ROUND_MULT` to silence a failure.** Above 4× it is not rounding.

---

## 4 · Ingest — run `hl_ingest_bpy.py`

Open `blender/hl_ingest_bpy.py` in the Scripting workspace. Set `PROJECT` if the tree moved.
Leave `MODE = "all"`. **Run Script.**

### What you should see in the Outliner

| Collection | Contents |
|---|---|
| `HL_Canopy` | `HL_Ribs` — one CURVE object, `EXPECTED COUNTS` → splines |
| `HL_Context_ranked` | `EXPECTED COUNTS` → ranked (carry a measured sky share) |
| `HL_Context_unranked` | `EXPECTED COUNTS` → unranked (absent from attribution) |
| `HL_Site` | `HL_Deck`, `HL_Ground` |
| `HL_Access` | 10 empties |
| `HL_Checks` | `SCALE_CHECK_1m7` |

### What must appear in the console

```
[join] OK — 232 stations, index-aligned, s_m agrees within 0.1 m at every index
[verify ribs] PASS — smoothing changed no geometry
[attribution] <ranked> of <total> footprints carry a sky share; <unranked> do not
[attribution] normalising on max sky_share_pct = <max>% (BIN <bin>) — the ramp is LINEAR
[deck] rail-to-rail width  min 8.9917 m  max 9.0100 m  (expected 9.00)
```

**If the join assertion fires, do not "fix" it by relaxing the tolerance.** It means
`envelope.json` and `structure.json` are out of step and one of them needs regenerating.

### 4.3 The rib verification, and why its tolerance is magnitude-scaled

Two separate checks run on the ribs. **They test different things and neither substitutes for
the other.** Confirmed on a real headless run, Blender 5.2:

```
[verify ribs] spline types            232/232 BEZIER, all handles AUTO
[verify ribs] PASS — smoothing changed no geometry (interpolating spline, knots are on the curve)
[verify ribs] float32 eps 1.192093e-07 · tolerance = 4.0 half-ULP x |coord|, floor 1e-06 m
[verify ribs] coord magnitude range   10.70 .. 864.70 m  ->  tol 2.551e-06 .. 2.062e-04 m
[verify ribs] max knot deviation      2.930e-05 m   (0.956 half-ULP of its own scale)
[verify ribs] max reach shift         2.961e-05 m   (storage invariance)
[verify ribs] max apex-height error   9.155e-07 m   (vs rib_height_m, abs tol 1e-06)
[verify ribs] max endpoint-Z error    0.000e+00 m   (vs DECK_Y 9.0, abs tol 1e-06)
[verify ribs] PASS — knots match envelope.json within float32 storage precision at every rib
```

#### `verify_spline_types` — the smoothing guard

Asserts **every spline is BEZIER and every handle is AUTO**, aborting with the
offending spline index and what it actually is.

**This is the check that catches NURBS.** A coordinate comparison never could, and the earlier
version of this document was wrong to imply otherwise: **converting to NURBS does not move a
control point.** It changes whether the evaluated curve passes *through* the control points at
all. The coordinates read back identical while the rendered tube no longer touches the measured
apex. Every Bezier handle type — AUTO, VECTOR, ALIGNED, FREE — likewise leaves knots exactly in
place; handles steer tangents only.

So spline type and handle type are the only things that decide whether the curve interpolates
its knots, and they are now asserted directly rather than inferred.

#### `verify_ribs` — knot fidelity against `envelope.json`

Asserts the coordinates in the scene are the coordinates the engine wrote. **This is not a
smoothing test.** What it catches is a wrong axis map, a stray object or collection transform,
a units change, or a mis-indexed join — anything that puts a knot somewhere the JSON did not.

**Why the tolerance is magnitude-scaled.** Blender stores curve control points as **float32**.
The representable step at magnitude *m* is `eps32 × m`, so round-to-nearest storage bounds the
per-coordinate error at **half** that. This corridor runs to |Y| = 864.70 m, where half-ULP is
**5.15e-05 m** — so an absolute 1e-6 tolerance is roughly **50× tighter than the storage can
hold**, and fails on arithmetic that is exactly correct. It did: the first run aborted at
2.930e-05 m.

**The evidence that this is storage and not movement**, measured across all 232 ribs:
deviation correlates with coordinate magnitude at **r = +0.908** (ribs near the origin read
4.6e-07, ribs at the corridor ends 2–3e-05), and **every rib sits inside one half-ULP of its
own magnitude — max ratio 0.956, never above 1.** Half-ULP is the exact theoretical bound for
round-to-nearest; real displacement has no reason to respect it on all 232 ribs at once.

**The tolerance, derived not typed:**

```python
EPS32 = float(numpy.finfo(numpy.float32).eps)          # 1.1920929e-07
HALF_ULP_MULT = 4.0
tol_per_rib = max(1e-6, HALF_ULP_MULT * 0.5 * EPS32 * max_abs_coord_of_that_rib)
```

`HALF_ULP_MULT = 4` because a single round-trip is bounded by 1.0 half-ULP and the observed
worst case is 0.956, so 4× absorbs a second conversion (a matrix apply, a re-read) while
staying three to four orders of magnitude clear of anything real: at 864 m the bound is
**2.06e-04 m**, and a botched transform or a NURBS conversion displaces a knot by centimetres
to metres. The floor of 1e-6 keeps ribs near the origin from being held to a tolerance tighter
than the absolute one used elsewhere.

> ### ⚠️ A DEVIATION THAT DOES NOT SCALE WITH MAGNITUDE IS REAL MOVEMENT
> The bound is per-rib and proportional to that rib's own coordinates. A rib near the origin is
> held to 2.6e-06 m; one at the corridor end to 2.1e-04 m. **A displacement that is constant
> across ribs, or that is large on a rib near the origin, blows through its own scaled bound
> and the build stops** — naming the spline index, its `s_m`, its magnitude, the deviation, the
> tolerance, and the deviation in half-ULPs so you can see immediately whether it is storage or
> not. **The point of the check is unchanged.** Do not raise `HALF_ULP_MULT` to make a failure
> go away; if a deviation exceeds four half-ULPs, it is not storage.

**Apex height and endpoint Z stay at an absolute 1e-6** and are deliberately not scaled. They
operate on small magnitudes — apex Z is 9–16 m, the endpoint test is against 9.0 — where
half-ULP is ~1e-6 and ~5e-7, so an absolute tolerance is already appropriate. The endpoint error
is exactly **0.000e+00** because 9.0 is exactly representable in binary32.

**On `reach`:** `envelope.json` stores rib coordinates at 2 dp and `reach_m` at 2 dp, so reach
recomputed from stored coordinates differs from stored `reach_m` by up to ~0.005 m. That is
**source rounding, not error**, and it is why the test compares reach recomputed from the knots
before and after storage rather than against the stored value.

### Spreadsheet editor

Switch an area to **Spreadsheet**, select `HL_Ribs`. With a curve you will see **Control
Point** and **Spline** domains. Confirm the spline and control-point counts from
`EXPECTED COUNTS`. Select `HL_Deck` and confirm its vertex and face counts from the same block.

> ### ⚠️ SILENT FAILURE — attributes did not port
> Houdini's `hl_ingest` writes 12 float attributes onto every rib point and prim.
> **Blender curve splines do not carry arbitrary named attributes the same way**, so this
> port keeps the per-rib values in the JSON and encodes only what geometry needs: the sized
> section, as per-point `radius`. If you later need `deficit_svf` for a shader, read it from
> `envelope.json` by index — do not assume it is on the curve.

---

## 5 · Rib geometry — curves, bevel, and the sized sections

Ribs arrive as 5-point polylines. The structural pass sized each one to **CHS 168x6.3** or
**CHS 219x8** (`structure.json` → `ribs[].section_sized`).

### 5.1 The diameters are imported, never typed

`structure.json` stores only the section **name**. The outside diameter exists in exactly one
place — `build_structure.py`'s `SECTIONS` table — and `load_sections()` obtains it
programmatically:

1. **import** `build_structure.py` and read the live `SECTIONS` value (authoritative), else
2. **AST-parse** the module-level `SECTIONS` literal (no execution, no numpy needed), else
3. **abort with a message telling you to decide.** It will not fall back to a typed number.

The import is practical — Blender bundles numpy, which is `build_structure.py`'s only
third-party import, and the module is guarded by `if __name__ == "__main__"` so importing it
runs no engine code. The AST path exists so a missing numpy cannot force a transcription.

Console confirms which path was used:

```
[sections] imported build_structure.SECTIONS (module executed)
[sections] {'CHS 168x6.3': 0.1683, 'CHS 219x8': 0.2191, ...}
```

### 5.2 One bevel, two diameters

Rather than splitting the canopy into two objects, the ingest sets **`bevel_depth` to the
largest radius** and gives each control point a **`radius` multiplier**:

```
bevel_depth        = OD_max / 2            = 0.10955 m   (CHS 219.1)
point.radius       = (OD_rib / 2) / bevel_depth
                     CHS 219x8   -> 1.000
                     CHS 168x6.3 -> 0.768
```

Object Data → Geometry → Bevel: **Round**, Depth `0.10955 m`, Resolution `4` (a 12-sided
tube — ample at 170–220 mm). **Fill Caps on.**

> ### ⚠️ SILENT FAILURE — bevel depth is a radius, not a diameter
> Entering `0.2191` gives every rib **double** its true thickness, and a 219 mm tube looks
> entirely reasonable at 438 mm in a 1.7 km scene. **Check against the cube:** the thickest
> rib must be ~1/8 the width of the 1.7 m scale cube. If a rib looks like a structural
> member rather than a tube, you doubled it.

### 5.3 Smoothing — allowed, because it moves nothing

5 knots will facet visibly at the apex under a bevel. The ingest builds **BEZIER splines with
`AUTO` handles**, which **pass exactly through all five original control points** and only
interpolate between them. `resolution_u = 12`.

Two checks run automatically — **see §4.3 for what each one tests and why the tolerances
differ.** In short:

- **`verify_spline_types`** asserts every spline is BEZIER with AUTO handles. **This is
  the smoothing guard.**
- **`verify_ribs`** asserts knot fidelity against `envelope.json` (magnitude-scaled tolerance,
  4 half-ULPs of float32), plus apex height and endpoint Z at an absolute 1e-6.

**Any smoothing that moves the apex is disallowed.** But note *what actually detects it*:

> ⚠️ **NURBS does not fail the coordinate check, and an earlier version of this document
> wrongly said it would.** Converting to NURBS leaves every control point exactly where it
> was — it changes whether the *evaluated curve* passes through them. The coordinates read
> back clean while the rendered tube stops touching the measured apex. `VECTOR`, `ALIGNED`
> and `FREE` handles likewise keep knots in place and only alter the curve between them.
>
> **`verify_spline_types` is what catches all of these**, by asserting the type directly.
> If you change the spline or handle type for any reason, that assertion is the one that
> will stop you — as intended.

### 5.4 What the rib population actually looks like

**`envelope_reach_zero_count` of `envelope_stations` ribs have `reach_m` exactly 0.0** — pure arches with
no cantilever at all, sitting at or near the 1.20 m generator floor. This is not a defect and
must not be smoothed over: it is the material-variation story, and framing the axo (§9.4) to
include both regimes is the point of that plate.

---

## 6 · Context, deck, ground

### 6.1 Context prisms

Built directly as closed prisms — bottom ring at Z = 0, top ring at Z = `height`, walls plus
a roof n-gon. No `Solidify`, no `Extrude` operator, so it is headless-safe and deterministic.
Interior rings (**2 exist**) are ignored, matching `hl_ingest`.

### 6.2 Context shading — a continuous ramp on measured sky share

**The visual variable is `sky_share_pct` from `data/attribution.json`, joined by BIN.** How
much of the deck's sky each building actually takes. **No threshold, no categories, no date
rule.**

Join, verified against the data:

All four counts are in `EXPECTED COUNTS` — footprints total, ranked, unranked — and the ingest
**aborts** if any attribution BIN has no footprint.

Normalisation is generated, not chosen: `sky_share_norm = sky_share_pct / max_share`, where
`max_share` is the top row of `data/attribution.json`'s leaderboard. The ramp is **linear in
share**, so a building that takes twice the sky reads twice as hot. The ingest prints the
normalising BIN and value on every run.

#### Why the date rule was dropped

> ### ⚠️ THE ARGUMENT THAT USED TO BE HERE WAS BUILT ON DEAD NUMBERS
> Until 2026-08-20 this section argued the date rule was wrong because the top two culprits
> were both built 2006 and owned 37.98% between them. **Those figures came from the 81.6%
> partial footprint set.** On the complete data the leaderboard has no such pair — the
> distribution is a long tail, the top building takes single digits, and no two buildings
> come close to a third of the sky. The old sentences are deleted rather than restated,
> because the ramp does not need them.

The old binary tint keyed on `construction_year >= 2009`. **The reason it is the wrong
visual variable does not depend on any leaderboard row: a binary tint shows MEMBERSHIP, and
the thing worth showing is MAGNITUDE.** The enclosure is spread across the whole ranked set
with a long tail; a tint flattens that distribution into two buckets, while the ramp shows
it. `houdini/ANSWERING_LINE_RENDER_PLAN.md` carries the same conclusion and the same reason.

A top-N rule would fix the picture by **inventing a threshold** the data does not contain,
which is the move this project refuses everywhere else. A continuous ramp needs no threshold:
it shows exactly what was measured, and the buildings that matter emerge because they *are*
hot, not because a rule selected them.

**The era split belongs in the caption**, quoted from `data/attribution.json` →
`metadata.cuts` — where the **2005 West Chelsea rezoning** is now the primary cut and the
**2009 opening** the secondary one, each with its own over-representation figure — rather
than as a tint a reader must decode. ⚠️ Take both from that file; neither has a
`Projects/README.md` §5 row yet.

The date tag is **still computed and still written onto every object** (`post2009`, `era`,
`year`, `year_known`) so it remains queryable and available to a future plate. It is simply not
rendered.

#### Building the material

One material, `MAT_Context_Share`, on the `HL_Context_ranked` collection:

```
Attribute ──> ColorRamp ──> Base Color   (Principled BSDF)
 Type: Object
 Name: "sky_share_norm"        <- the per-object custom property the ingest wrote
        (use the Fac output)
```

The **Attribute** node with `Type: Object` reads object custom properties by name, so one
material shades every ranked building from its own value — `EXPECTED COUNTS` → ranked says
how many. **Never assign a colour per object.** `build_lookdev.py` builds this graph, and
asserts the join: the top five by `sky_share_norm` must be attribution ranks 1–5, with each
norm equal to its `sky_share_pct` divided by the maximum.

ColorRamp stops — constant-interpolation-free, two stops is enough to start:

| Position | Colour | Meaning |
|---|---|---|
| `0.00` | `0.42, 0.38, 0.35` (masonry) | takes nothing measurable |
| `1.00` | `0.62, 0.24, 0.16` (deep terracotta) | takes the most |

Roughness `0.75`, Metallic `0.0` throughout. **No glass on the ramp** — see §7.

`MAT_Context_Neutral` goes on `HL_Context_unranked`: `0.50, 0.50, 0.50`, Roughness `0.70`. It
must read as *neither end of the ramp*, because **absent from the attribution set means "not
measured", not "measured as zero."** The ingest writes `sky_share_norm = -1.0` for these
specifically so that a mis-assignment to the ramp material is visible rather than silent.

> ### ⚠️ SILENT FAILURE — the ramp will look broken, and it is correct
> **The large majority of ranked buildings take less than 0.1% each** — the ingest prints the
> count on every run, alongside the top eight. So the ramp leaves almost every building at the
> cold end and picks out a couple of dozen. That is the measurement, not a rendering failure.
>
> **The temptation is to "fix" it** with a square-root or logarithmic ramp so more buildings
> show colour. **Do not do this without deciding it explicitly** — a non-linear ramp
> overstates small contributors, and a building taking 0.05% would read as a meaningful
> culprit. If you want it, it is a stated editorial choice that belongs in the caption, not a
> silent gamma on the Fac input.
>
> **CHECK, and it is now an assertion rather than an eyeball:** `build_lookdev.py` aborts
> unless the five hottest objects are attribution ranks 1–5 and every unranked object carries
> `sky_share_norm = -1.0`. What you should SEE from above is **one building at full heat and
> a falloff through a couple of dozen**, because the ingest reports on every run how many
> ranked buildings take less than 0.1% each — and it is most of them. If everything is warm,
> something non-linear crept in. If nothing is warm, the Attribute node name does not match
> `sky_share_norm`.

### 6.3 Unparseable years no longer affect shading

Some footprints carry `construction_year: None` — the ingest counts and names them on every
run, and it is **not** the single small building this section used to name. Under the old date
rule that mattered, because `hl_ingest.py` coerces the value to `0` and silently calls it
pre-2009.

**Under share-based shading it is irrelevant to the image**: sky share does not depend on the
year. The building is shaded by its measured share like any other. The ingest still tags it
`year_unknown` and still names it in the console, so the data defect stays visible even though
it no longer has a visual consequence.

### 6.4 Deck — lofted from the rib rails

**Do not resample the stored centreline.** `high_line.centerline` is **10 points across
1856.7 m** — ~206 m per segment. Sweeping it would cut every corner of a curved corridor.

Instead the deck is lofted between the **232 rib start points** and the **232 rib end
points**, in station order — the true alignment at ~8 m spacing, taken from the same geometry
the engines ray-cast against. 231 quads, 464 verts.

**CHECK (automatic, aborts on failure):**

```
[deck] rail-to-rail width  min 9.0000 m  max 9.0000 m  (expected 9.00)
```

9.00 m = `DECK_HALF_W` 4.5 × 2. A width that is not 9.00 means either the axis conversion is
wrong or the rib endpoints are not the rails. The ingest raises rather than continuing.

### 6.5 Ground

A flat plane at Z = 0, sized to the footprint extent + 200 m. **This is invented** — there is
no ground, terrain or street surface in any source file — and the object carries
`hl_source = "NOT IN THE DATA — scene furniture, invented for the render"`. Keep it matte and
unobtrusive; it exists so the towers have something to cast onto.

`build_lookdev.py` widens this plane if the fitted axo frame is larger than it, because the
plane's straight edge was cutting across the sky in plate D. It records that on the object as
`hl_ground_resized`. Resizing declared furniture is not scaling the site.

### 6.6 ⚠️ The corridor relief cut — the one intervention on the context

> **The High Line runs THROUGH buildings.** `highline_footprints.json` carries the footprints
> of the buildings the viaduct passes through, and `hl_ingest` extrudes **every** footprint as
> a solid prism from Z = 0 to `height`, knowing nothing about the slot the viaduct occupies.

Measured on the current data, and printed by the build on every run:

- **102 of the 232 deck stations sit inside a footprint.**
- **284 of the 696 rail/centre points — 40.8% of the deck — are inside solid geometry.**
- **40 prisms taller than the 9.0 m deck bury part of the line.**
- Until the 2026-08-20 clearance fix (§9), **camera A stood inside BIN 1089968 and rendered
  solid black.** That particular symptom is gone — the cameras are now placed in open air — but
  **the cause is not**, and the relief cut is still required: the deck itself runs through
  those buildings whatever the camera does, and without the cut the corridor is buried
  geometry for two-fifths of its length.

So this is not a look-dev preference. **The clearance fix moved the cameras out of the
buildings; it did not move the buildings off the deck.**

`build_lookdev.build_corridor_relief()` boolean-subtracts, from the prisms the deck passes
through, exactly the volume the design occupies:

| dimension | value | where it comes from |
|---|---|---|
| width | `DECK_HALF_W × 2` | `envelope.json` → `_meta.params` — the same rails §6.4 lofts the deck from |
| floor | `DECK_Y` | the deck plane |
| ceiling | `DECK_Y` + `envelope_rib_max_m` | the **realised** maximum rib height, never `RIB_MAX_H` |

**No clearance margin, no rounding up, nothing invented.** A prism keeps its full height and
its full footprint everywhere the design does not stand; the buildings that lose volume are the
ones the deck already passes through, and they lose precisely the volume the deck already
occupies. Every cut object carries `hl_corridor_relief` naming what was removed, so a
Cryptomatte pick or a Spreadsheet query finds it.

**Set `CORRIDOR_RELIEF = False` and re-render to see the black frame for yourself.** That is
the point of the flag.

> ### ⚠️ WHAT THIS DOES NOT LICENCE
> It does not lower a tower, widen the deck, or enlarge the canopy by one millimetre. If you
> ever find yourself raising the ceiling above `envelope_rib_max_m` "so the canopy reads",
> that is the no-exaggeration rule being broken by the back door — the same move §9.3 refuses
> for `ortho_scale`.

---

## 7 · Materials — five, Principled BSDF, minimal

This is architecture, not product viz. No procedural grunge, no imperfection maps, no
fingerprints. Five materials, flat-shaded parameters, all on **Principled BSDF**:

| Material | Assign to | Base Color | Metallic | Roughness | Notes |
|---|---|---|---|---|---|
| `MAT_Steel` | `HL_Ribs` | `0.22, 0.22, 0.23` | `1.0` | `0.35` | the canopy. One material, no variation — the ribs differ in *size*, which is the argument |
| `MAT_Context_Share` | `HL_Context_ranked` | **ColorRamp, see §6.2** | `0.0` | `0.75` | driven by the `sky_share_norm` object attribute |
| `MAT_Context_Neutral` | `HL_Context_unranked` | `0.50, 0.50, 0.50` | `0.0` | `0.70` | not measured — must read as neither end of the ramp |
| `MAT_Figure` | `HL_Figures` | `0.16, 0.15, 0.14` | `0.0` | `0.85` | **not in the original five.** §10 requires figures and gives them no material; dark and matte so they read as silhouette |
| `MAT_Paving` | `HL_Deck` | `0.38, 0.36, 0.34` | `0.0` | `0.65` | |
| `MAT_Ground` | `HL_Ground` | `0.30, 0.30, 0.30` | `0.0` | `0.90` | |

Add `MAT_Planting` (`0.18, 0.26, 0.14`, Roughness `0.80`) only if you model planting; do not
fake it with a texture on the deck.

**Assign by collection**, not by selection: select all objects in a collection
(`Select → Select Grouped → Collection`), assign, done.

**No glass anywhere in the context.** The old palette gave transmissive glass to the six
post-2009 buildings; with the date rule gone there is no principled subset to glaze, and
glazing by share would confuse two variables in one surface. Opaque, matte context throughout —
the ramp is the only thing the context is saying.

> ### ⚠️ SILENT FAILURE — transmission is the render-time cliff
> If you add transmission anyway, add it to a handful of objects at most. Transmission across
> all the context prisms on an 8 GB card — there are `EXPECTED COUNTS` → prisms of them, an
> order of magnitude more than this document assumed before the re-fetch — is the difference
> between a 4-minute and a 40-minute frame,
> and Cycles gives no warning — it just gets slow. If a draft render suddenly takes 10× longer,
> check whether a glass material reached the context collections.

---

## 8 · Sun — built from the measured vector, not placed by eye

`cameras.json` → `key_light` carries the study's own winter peak:

```
day_of_year        355
elev_deg           25.8191
azim_deg           180.0
to_sun_unit        [ 0.0,  0.435531, -0.900174]     project frame
light_travel_unit  [-0.0, -0.435531,  0.900174]
frame              "+x east, +y up, +z north; unit vector site -> sun"
```

### 8.1 Which convention the stored vector uses

**`to_sun_unit` points FROM the site TOWARD the sun.** Confirmed by arithmetic, not by the
label: azimuth 180° is due south, and in a `+z = north` frame a southward vector must have
negative z — it does (−0.900174). `sin(25.8191°) = 0.4355` matches the y component.

Azimuth is measured **from +z (north) toward +x (east)** — a compass bearing.

### 8.2 Conversion to Blender

Apply the §1 axis map:

```
to_sun (blender) = (0.0, -0.900174, 0.435531)      south and up
```

**Blender's sun lamp emits along its own local −Z.** So the lamp's **+Z must point at the
sun**, and the light then travels along −Z toward the site.

Two equivalent ways; use the first, check with the second.

**Vector method (convention-free, preferred):**

```python
from mathutils import Vector
d = Vector((0.0, -0.900174, 0.435531))          # to_sun, blender frame
sun.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
```

**Explicit Euler (for checking):**

```
rotation_euler = ( radians(90 - altitude), 0, radians(180 - azimuth) )
               = ( radians(64.1809),       0, radians(0.0) )
               = ( 1.120168 rad,           0, 0.0 )
               = ( 64.1809°,               0, 0° )
```

Verified: rotating the lamp's +Z by that Euler yields `(0.0, −0.900174, 0.435531)`, agreeing
with the stored vector to **3.7e-07** (the residual is the stored vector's own 6-dp
rounding). The lamp's −Z then points `(0.0, +0.900174, −0.435531)` — **north and downward**,
which is light travelling north from a southern sun.

**Lamp settings:** Sun, Strength `3.0` (start), **Angle `0.526°`** (the real solar disc —
this gives correct shadow softness and costs nothing).

> ### ⚠️ SILENT FAILURE — a sun 180° out still looks like sunlight
> If you aim the lamp along `to_sun` instead of `light_travel`, the scene is lit from the
> **north** at the same altitude. It looks completely convincing. Every shadow points the
> wrong way and the raking light the recapture figure counts is coming from the wrong
> hemisphere. Nothing in the render says so.

### 8.3 CHECK — shadows must run north, at a measured length

**Do this in plan view, before any render.** Top view (Numpad 7), viewport shading →
Rendered, over the corridor:

- **Shadows run NORTH — toward +Y.** A shadow pointing −Y means the lamp is reversed.
- **Shadow length = height / tan(elevation) = `SUN + SHADOW CHECK` → shadow multiplier.**
  Concretely: `SUN + SHADOW CHECK` names a **reference tower** near station C by BIN and
  height, and states the shadow length it must cast. Measure that one.

Measure it: `Shift+Spacebar → Measure`, drag from the tower base to the shadow tip. If it does
not match the length `SUN + SHADOW CHECK` names for that tower, either the altitude or the
scale is wrong — and both are silent. **The figure this sentence used to print was for a
different reference tower and is deleted; take it from the emitter.**

The winter sun at 25.8° is *low*. Long raking shadows are correct, not a mistake.

---

## 9 · Cameras — built from `cameras.json`, not flown by hand

All positions and targets are in the project frame and need the §1 conversion. Never
hand-position these — the whole point of `pick_cameras.py` is that the plate and the caption
describe the same station.

**Every position and target comes from `CAMERAS` in the build-constants block** — which reads
them straight out of `cameras.json`. They are not reproduced here, because `pick_cameras.py`
moves them whenever the data moves, and it has: all three stations changed after the
2026-08-15 footprint re-fetch.

> ### CAMERA CLEARANCE — the trap, and the fix that closed it (2026-08-20)
> `pick_cameras.py` places a camera by **offsetting** from its station — `HERO_BACK` 25 m along
> the deck, `OPEN_BACK` 20 m along it, `SECTION_OFFSET` 45 m across it. Until 2026-08-20 nothing
> tested whether the resulting point was **in open air**, and on the complete footprint set two
> of the three were not: A landed inside BIN 1089968 (41.15 m), C inside BIN 1089395 (100.28 m).
>
> **A camera inside a closed prism renders the inside of a box** — pure black, with nothing in
> the viewport or the console to say so. It is the §3 clip-end failure's twin. 102 of the 232
> deck stations sit inside a footprint, so this is not a corner case; it is the normal condition
> of a viaduct that runs through buildings.
>
> **`pick_cameras.py` now tests clearance during SELECTION.** Candidates are walked in the
> plate's own rule order and the first one whose camera can actually be placed is taken, so the
> rule is unchanged and only gains a physical-placement constraint. Every skip is recorded in
> that station's **`clearance`** block — pool rank, `s_m`, and the BIN that blocked it — so a
> moved station is auditable and never silent.
>
> **The test differs by plate type, and the reason is what the plate is:**
>
> | plate | tested | why |
> |---|---|---|
> | **A, B** perspective | the **whole camera→target sight line**, 6 samples | nothing cuts geometry away at render time, so a buried target is a wall filling the frame |
> | **C** ortho section | the **camera position only** | the section plane cuts everything nearer than the deck, and the worst core is inside a building *because* it is the worst core — requiring a clear target would reject the subject |
>
> A camera-position-only test on **A** would have picked s = 184.87 m, whose camera is clear but
> whose target is inside BIN 1089295 (53.04 m) — unusable for the same reason, one step later.
>
> **What moved.** A: rank 0 → rank 3 of its pool, s 1358.40 → **176.83 m**, deficit 0.7606 →
> 0.6272 — and recapture **1.9% → 15.1%**, so the hero now actually shows the canopy working.
> C: rank 0 → rank 4, s 1406.63 → **1398.59 m**, deficit 0.8539 → 0.8110, rib 7.23 → 7.03 m,
> recapture 0.000 either way — the *worst core, tallest ribs, recovers nothing* story is intact.
> B did not move. **Every caption regenerates from the same JSON; nothing was hand-typed.**
>
> `build_lookdev.py` still prints a `[clearance]` line per camera on every build. **It must read
> `in open air` three times.** If it ever does not, the selector and the scene have diverged.

### 9.1 Building one

```python
import bpy, json, math
from mathutils import Vector
def P(v): return Vector((v[0], v[2], v[1]))          # §1

doc = json.load(open(r"<PROJECT>/houdini/cameras.json", encoding="utf-8"))
for st in doc["stations"]:
    c = st["camera"]
    cam = bpy.data.cameras.new("CAM_" + st["id"])
    obj = bpy.data.objects.new("CAM_" + st["id"], cam)
    bpy.context.scene.collection.objects.link(obj)
    pos, tgt = P(c["position"]), P(c["target"])
    obj.location = pos
    obj.rotation_euler = (tgt - pos).to_track_quat('-Z', 'Y').to_euler()
    cam.clip_start, cam.clip_end = 0.1, CLIP_END  # from build-constants, see §3
    if c["type"] == "orthographic":
        cam.type = 'ORTHO'
        cam.ortho_scale = ORTHO_SCALE                 # from build-constants, see 9.3
    else:
        cam.lens = 35.0                               # see 9.2
```

`to_track_quat('-Z','Y')` is the camera equivalent of the sun's `('Z','Y')`: Blender cameras
look down **−Z**, with **+Y** up.

### 9.2 A and B — perspective at eye height

Both sit at **Z = 10.65 m** = deck 9.0 + eye 1.65, straight from
`camera.eye_height_above_deck_m`. **Do not raise the camera to "see more."** Raising it is
indistinguishable from lowering the towers.

**Focal length 35 mm** to start (`cam.lens = 35`). 24 mm exaggerates the canyon and is the
easy way to cheat this image; 50 mm is closer to how the deck actually feels. 35 mm is the
honest compromise. **This is a framing choice and it is allowed** — it changes the lens, not
the building heights.

Camera A's nearest building — distance, height, BIN and year — is in `STATION GEOMETRY` → A.
It is metres away, not tens, so clip start 0.1 m matters.

### 9.3 C — orthographic, and the ortho scale

`ortho_scale` is the world size of the **larger** image dimension.

**`ORTHO SCALE — section camera` derives it** from that station's own canyon: the tallest wall
within 80 m, its distance, and the camera target height. The block prints the vertical and
horizontal extents it needs and the resulting value.

```
vertical half-extent  = tallest wall - target Z + 5 m margin
horizontal extent     = 2 x distance to that wall, floored at 40 m
ORTHO_SCALE           = max(2 x vertical half-extent, horizontal extent)
```

Use a square or portrait plate; landscape wastes most of the frame on empty ground.

> ### ⚠️ ON A PORTRAIT PLATE THIS RULE MAKES A FRAME 1.8× ITS SUBJECT — UNRESOLVED
> `vertical half-extent` is measured **upwards only** (tallest wall − target Z + 5 m) and then
> **doubled**, which is only right if the frame must be symmetric about the target. It must
> not: the canyon runs from the ground to the tallest wall, so the vertical need is
> `tallest wall + 5 m`, not twice the upward half. At station C the canyon is ~122 m and the
> emitter returns 219, so **44% of a portrait plate falls below ground level.**
>
> `build_lookdev.py` does **not** narrow the scale to fix this — §9.3 forbids exactly that
> direction, and narrowing would enlarge the canopy in frame. It only **re-aims** the frame,
> via `shift_y`, onto the canyon's own span instead of onto the camera target. The canopy does
> not gain a pixel.
>
> **The fix belongs in `pick_cameras.render_build_constants()`**, and it changes a number this
> document quotes, so it is left as a decision rather than made silently.

**CHECK:** both canyon walls fully in frame, the full rib in frame, and the rib occupying a
small fraction of the frame height — the ratio is `envelope_rib_max_m` / `ORTHO_SCALE`.
*If that looks too small, it is correct.*
The instinct to reduce `ortho_scale` until the canopy fills the frame is the no-exaggeration
rule being broken by the back door — you would be cropping the towers out to make the canopy
look bigger. Adjusting `ortho_scale` to fit the **canyon** is framing; adjusting it to
flatter the **canopy** is not.

### 9.4 D — the corridor axo (no `cameras.json` entry)

Orthographic, high oblique along the corridor's long axis (**Y**, 1.73 km). This plate is the
argument image: it must show **the whole gradient** — the `envelope_reach_zero_count` ribs at
the `envelope_rib_min_m` floor where
the deck still sees sky, and the tall ribs rising to `envelope_rib_max_m` in the canyon. Frame the length so
both are visible in one read; do not crop to the dramatic half.

Colour the ribs by height if you wish — but by reading `rib_height_m` from `envelope.json` by
index, not by hand-selecting. `build_lookdev.py` builds **`MAT_Steel_ByHeight`** for this and
`render_all.py` swaps it in for plate D only; §7's single `MAT_Steel` still governs A, B and C,
where the ribs differ in *size* and that is the argument.

It drives the ramp from **world Z**, not from a curve attribute, and the reason is §4's own
warning: Blender curve splines do not carry arbitrary named attributes, so `rib_height_m`
cannot sit on the curve the way `sky_share_norm` sits on a context object. The identity that
makes world Z sufficient is exact and is asserted on every run —
**apex Z == `DECK_Y` + `rib_height_m`** — so ramping `(Z − DECK_Y) / envelope_rib_max_m` gives
every apex precisely its own normalised height. Nothing is hand-selected and no vertex moves.

> ### ⚠️ MEASURED 2026-08-20: THE RIB GRADIENT IS NOT LEGIBLE AT WHOLE-CORRIDOR SCALE
> The fitted frame is ~1,951 m across 4,000 px — **0.49 m per pixel**. At that scale the
> tallest rib is about **15 px high and its tube is under one pixel wide.** Colouring by height
> does not rescue it, because there is nothing more than a pixel wide to colour; the ramp was
> built, rendered and measured, and the corridor still reads as a line.
>
> **This is a real limit, not a bug and not something to fix by exaggeration.** Any of these
> would break the no-vertical-exaggeration rule or the framing rule: scaling the ribs, widening
> the tubes, or cropping to the dramatic stretch and calling it the corridor.
>
> What the plate CAN carry honestly is the render plan's own reading — *"a canopy that answers
> everywhere and is dwarfed anyway"* — plus the sky-share ramp, which **is** legible at this
> scale because buildings are hundreds of pixels wide. If you want the gradient itself visible,
> that is a **second, shorter plate** over a named stretch of the line, not a change to this
> one.

---

## 10 · Human figures — image A only

**Required by `Projects/README.md` §4.2**: one image per project carrying scale, site context
and a human figure. This project has never had one; plate A is that image.

**Placement:** on the deck surface, **standing height 1.70 m**, feet at Z = 9.00. Two or three
figures at different depths — one in the near-middle ground, one further down the corridor.
Use the `HL_Access` empties as plausible positions if you want people entering.

Note the camera sits at **1.65 m** and figures are **1.70 m** tall. Those are consistent, not
contradictory — a standing person's eyes are a little below the top of their head. If you want
the camera at a figure's eye line, that is ~1.60–1.65 m, which is what `cameras.json` already
uses.

**Candidate free sources — confirm one before I reference it anywhere.** I am not giving URLs
because I will not invent them; check the licence yourself at the source:

| Option | What it is | Licence to verify |
|---|---|---|
| **Blender Studio — Human Base Meshes** | Official Blender Foundation base meshes, ships as a `.blend` | CC0 (verify) |
| **MakeHuman** | Open-source parametric human generator with a Blender exchange add-on | AGPL tool, CC0 output (verify) |
| **Mixamo** | Rigged characters, free with an Adobe account | free-use terms (verify) |
| **BlenderKit** | Free tier inside Blender's asset browser; some scanned people | mixed per-asset (verify) |
| **Quaternius / Kenney** | Stylised low-poly people | CC0 (verify) |

For an architectural plate at this distance, **silhouette quality matters far more than mesh
detail** — a clean low-poly figure at correct height beats a detailed one at the wrong scale.

> ### ⚠️ SILENT FAILURE — imported figures arrive at the wrong scale
> Most downloaded humans import at centimetre scale or at some arbitrary unit, landing 100×
> too large or too small. In a 1.7 km scene a 170 m human reads as a building and a 1.7 cm
> one is invisible.
> **CHECK:** put the figure beside `SCALE_CHECK_1m7`. It must be the same height as the cube.
> Do this before duplicating it.

---

## 11 · Cycles — RTX 4060 8 GB

### 11.1 Enable the GPU (once per install)

`Edit → Preferences → System → Cycles Render Devices` → **OptiX** → tick the RTX 4060.
Then `Render Properties → Device: GPU Compute`.

**OptiX, not CUDA** — roughly 1.5–2× faster on RTX hardware and it enables the OptiX denoiser.

> ### ⚠️ SILENT FAILURE — "GPU Compute" with nothing ticked
> If no device is ticked in Preferences, Blender falls back to **CPU** without an error. Your
> 64 GB machine will render it, slowly, and you will conclude Cycles is slow.
> **CHECK:** during a render the status bar reads *"Rendering | Sample 12/512"* and moves in
> large jumps; the Windows Task Manager → Performance → GPU shows load. If the CPU is at 100%
> and the GPU idle, no device is ticked.

### 11.2 Sampling

| | Draft (look dev) | Final |
|---|---|---|
| Max Samples | `128` | `1024` |
| Min Samples | `0` | `64` |
| Noise Threshold (adaptive) | `0.05` | `0.01` |
| Denoise | on, **OptiX**, Prefilter `Accurate` | same |
| Denoising passes | Albedo + Normal | same |
| Time Limit | `60 s` | `0` (off) |

Adaptive sampling means the final number is a *ceiling*, not a cost — open sky reaches the
threshold in ~100 samples and stops.

**Also set:** `Performance → Final Render → Persistent Data` **on** (big win when re-rendering
the same scene from several cameras); `Performance → Memory → Use Tiling` on with tile size
`2048` for the 8 GB card at 4K.

### 11.3 Resolution

| Plate | Resolution | Ratio |
|---|---|---|
| **A** hero | `3508 × 2480` | A4 landscape @ 300 dpi |
| **B** open | `3508 × 2480` | same |
| **C** section | `2400 × 3000` | portrait, suits the section |
| **D** axo | `4000 × 1600` | long, matches the corridor |

> **Size budget.** `portfolio_master.pdf` is **11.4 MB of a 12 MB ceiling** before any of these
> exist. Render at these sizes, then downsample and compress in Stage 6 of the render plan —
> do not render small to save PDF weight, and do not paste 4K PNGs into the PDF.

### 11.4 Expected render times — ranges, not promises

On a 4060 8 GB with OptiX, a scene of this complexity (`EXPECTED COUNTS` → splines bevelled
curves and prisms, one sun, no volumetrics, **no glass anywhere** — see §7):

| | Draft 128 spp @ 1920 | Final 1024 spp @ 3508 |
|---|---|---|
| **A** eye level, glass in frame | 20 – 60 s | **4 – 12 min** |
| **B** open, little glass | 15 – 40 s | 3 – 8 min |
| **C** ortho section | 20 – 50 s | 4 – 10 min |
| **D** corridor axo, whole site | 40 – 120 s | **8 – 25 min** |

> ### MEASURED, 2026-08-20, on this machine — the estimates above were pessimistic
> RTX 4060 Laptop, OptiX, `render_all.py`, Blender 5.2, whole scene, adaptive sampling:
>
> | plate | draft 128 spp | final 1024 spp |
> |---|---|---|
> | **A** eye level | 40 s | **5 min 43 s** |
> | **B** open | 29 s | 2 min 38 s |
> | **C** ortho section | 23 s | 1 min 38 s |
> | **D** corridor axo | 22 s | 1 min 40 s |
> | **all four** | 1 min 54 s | **11 min 39 s** |
>
> **D is NOT the expensive one — A is**, by 3.4×, which inverts the guess above. The axo has
> the whole site in frame but every surface is far, flat and cheap; the hero sits inside the
> corridor relief cut where the bevelled tubes fill the frame at close range. Adaptive
> sampling gives the axo's open sky away almost free.
>
> There is **no glass anywhere** (§7), so the transmission cliff below cannot be the cause of
> a slow frame here. If one exceeds ~40 minutes, check the denoiser first.

If any frame exceeds ~40 minutes, something is wrong; look first at glass assignment (§7) and
second at whether the denoiser is actually running.

**Memory:** this scene should sit well under 3 GB. If you approach 8 GB, the cause is imported
human figures with 4K textures, not the site.

---

## 12 · Output and post

### 12.1 Passes

`Output Properties → Output`: **OpenEXR MultiLayer**, Color Depth `Float (Half)`, Codec `ZIP`.

> **Blender 5.x, scripted:** the old `OPEN_EXR_MULTILAYER` enum was split in two. Set
> `image_settings.media_type = 'MULTI_LAYER_IMAGE'` **first** — until you do, that
> `file_format` is not in the enum and the assignment raises; afterwards it is the *only*
> value in the enum, so a `File Output` node that wants PNG must set its own
> `format.media_type = 'IMAGE'` before its `file_format`.

`View Layer Properties`, enable:

| Pass | What it is for |
|---|---|
| **Combined** | the image |
| **Z** (Depth) | precise masking, focus work; raw distance in metres |
| **Mist** | normalised 0–1 depth for atmospheric cueing — easier than Z in the compositor |
| **Ambient Occlusion** | contact shading; lets you deepen crevices without re-rendering |
| **Cryptomatte Object + Material** | select the canopy, or any named BIN, *after* the render with no re-render and no manual masking |

Set the **Mist** range in `World Properties → Mist Pass`: Start `50 m`, Depth `1200 m` for
plate A; Start `0`, Depth `2000 m` for the axo. Mist that saturates to white by 100 m gives a
flat card.

**Cryptomatte is the one that saves the project.** If a reviewer asks for the canopy tinted
differently, or the top-ranked culprits picked out more strongly, you do it in the compositor
in two minutes instead of re-rendering for twenty. Objects are named `BLD_<bin>_<ring>`, so a
Cryptomatte pick maps straight back to an attribution row.

### 12.2 Minimal compositor

`Compositing` workspace, tick **Use Nodes**. Six nodes, in order:

> ### ⚠️ SCRIPTING THE COMPOSITOR IN BLENDER 5.x — four traps, all silent-ish
> The graph below is unchanged; the container is not. `scene.node_tree` is gone.
>
> - The compositor is now a **node group**: `bpy.data.node_groups.new(name,
>   'CompositorNodeTree')`, assigned to `scene.compositing_node_group`. Its result is a
>   `NodeGroupOutput` fed from an interface socket you create — **`CompositorNodeComposite`
>   no longer exists.**
> - **`CompositorNodeMixRGB` no longer exists either.** Use `ShaderNodeMix` with
>   `data_type='RGBA'`. Its sockets are named "A"/"B"/"Result" **four times over**, once per
>   data type, so `node.inputs["B"]` is ambiguous and `node.inputs["B_Color"]` raises —
>   look sockets up by **`identifier`** (`A_Color`, `B_Color`, `Factor_Float`,
>   `Result_Color`).
> - The Render Layers sockets are **"Depth"** and **"Ambient Occlusion"**, not "Z" and "AO",
>   and they only exist after the passes are enabled — so enable passes *before* you build
>   the graph.
> - **`File Output` writes a black image unless `save_as_render = True`** on the node and on
>   the item. Without it the node saves raw linear data, which for a sunlit exterior clips to
>   near-zero in 16-bit sRGB and looks exactly like a failed render. Its API also changed:
>   `base_path`/`file_slots` became `directory`/`file_name` plus a `file_output_items`
>   collection, and the written name is `<file_name><item name>`.

```
Render Layers ──> Exposure ──> Mix (depth cue) ──> Mix (AO) ──> Film-ish curve ──> Composite
                                    ▲                   ▲
                              Mist ─┘             AO ───┘
```

1. **Exposure** (`Color → Adjust → Exposure`) — do the brightness here, not by raising the sun
   strength, so the sun keeps its measured angle. **Per plate**, in `build_lookdev.EXPOSURE`,
   overridable with `render_all.py -- --exposure N`.

   > **All four plates are at `0.0`, and the story of how they got back there is the point.**
   > For part of 2026-08-20 plate A carried **+2.5**, because from inside a buried camera it
   > returned a mean of **23/255** against 195–206 for the other three. That was never a grade
   > decision — it was **compensation for a bug** (§9). With the camera in open air the same
   > plate reads **132/255 at 0.0**, and at +2.5 the deck and the sky-share tint on the canyon
   > wall both wash out.
   >
   > **A grade knob that is quietly correcting a geometry fault will look like a taste
   > decision forever.** Fix the cause; the knob goes back to zero on its own. Compare any
   > setting yourself with `--exposure N --suffix _evN`, which writes a separate file rather
   > than overwriting the plate.
2. **Depth cue** — `Mix` node, Factor ← **Mist**, Blend `Screen` or `Mix` toward a pale
   `0.72, 0.75, 0.78`, factor scaled ~0.5. Makes 1.7 km read as depth rather than clutter.
3. **AO multiply** — `Mix`, Blend `Multiply`, Factor `0.25`, second input ← **AO**.
4. **RGB Curves** — a gentle S. Do not crush the blacks; the section plate needs shadow
   detail in the canyon, which is the entire subject.
5. **Composite** + a **Viewer** so you can see it live.

> ### ⚠️ SILENT FAILURE — Filmic/AgX vs Standard
> Blender 4.x defaults to **AgX** view transform, which desaturates highlights heavily. It is
> good for the raking winter sun and bad if you then correct saturation by hand and bake it in.
> Set `Render Properties → Color Management → View Transform` deliberately — **AgX** for the
> lit plates — and leave `Look` at `None`. Do not switch transforms between plates: four
> images in three transforms will not read as one portfolio, and `spread.css` exists precisely
> to stop that kind of drift.

### 12.3 Where files land, and how they pair with the captions

Suggested, matching the plate ids so nothing has to be matched by memory:

```
5.CV_Highline/exports/blender/
    A_hero_eye_level.exr        A_hero_eye_level.png
    B_open_contrast.exr         B_open_contrast.png
    C_section_worst_core.exr    C_section_worst_core.png
    D_corridor_axo.exr          D_corridor_axo.png
```

The stems are exactly `cameras.json` → `stations[].id`, and `D_corridor_axo` matches the
`D_corridor` plate in `houdini/sources.json`. So:

```powershell
python houdini/pick_cameras.py --captions
```

emits caption blocks whose titles and ids line up one-to-one with these files. **Every number
that goes beside an image comes out of that command.** Do not read a figure off this document
and type it onto a plate — this document deliberately contains almost none, and the few site
facts quoted here (building heights, distances, counts) are context for *building the scene*,
not caption copy.

---

## 13 · Working with the Blender MCP connector

Claude can be connected to the live Blender session for look-dev. This section defines what
that connection is for, what it is **not** for, and the order in which to open it.

### 13.1 What it is used for

**Scene inspection and verification.** Reading back what is actually in the scene and
comparing it to the JSON — object counts, transforms, spline counts, custom properties,
material assignments, camera and lamp values. This is the highest-value use: the checks in
steps 1, 2, 3 and 8 stop being things you eyeball and become things that are queried.

**Batch operations.** The scene has `EXPECTED COUNTS` → prisms context objects and → splines
rib splines. Anything
applied uniformly — assigning `MAT_Context_Share` across a collection, setting `clip_end` on
every camera, renaming, re-linking collections, toggling visibility for a draft — is faster and
less error-prone issued once than clicked two thousand times.

**Shader and compositor node graphs.** Building the `Attribute → ColorRamp → Principled` graph
in §6.2, and the six-node compositor in §12.2, is fiddly by hand and exact in script. Node
graphs are also the thing most likely to need rebuilding after a mistake, and rebuilding them
by instruction is cheap.

### 13.2 What it is NOT used for — this is a rule, not a preference

> **Claude does not make the picture.**
>
> **Camera placement and framing** come from `houdini/cameras.json`, which was generated by
> `pick_cameras.py` from the measured data precisely so that no one — human or model — picks a
> viewpoint by eye. A camera moved during look-dev silently breaks the tie between the plate
> and its caption.
>
> **Composition** — what is in frame, what is cropped, where the horizon sits — is yours.
>
> **The material palette** — which colours, how saturated, how the ramp reads — is yours.
> §6.2 and §7 give starting values; changing them is a design decision.
>
> **Where light falls** comes from `key_light` in `cameras.json`, which is the study's own
> measured winter vector. The sun is not a look-dev control. If a shadow is inconvenient, that
> is a finding about the site, not a lighting problem to solve.
>
> Claude may **verify** all four of those and report a mismatch. It must not **choose** any of
> them.

The reason is the same one that governs the captions: every number and every viewpoint in this
project traces to a file. A viewpoint chosen conversationally has no source, and there is no
way to check it later.

### 13.3 The verification checks, as executable queries

Steps 1, 2, 3 and 8 were written as manual checks. Against a live session they become queries.
Each one names the file it is checked against.

**Step 1 — axis conversion, against `envelope.json`**

> *"Read `envelope.json` station index 100. Take `points[100].rib[2]` — the apex knot — and
> convert it with (px, pz, py). Then find spline 100 of `HL_Ribs`, read bezier point 2, and
> report both. They must agree to 1e-6. Also confirm the apex Z equals 9.0 + `rib_height_m`."*

Expected: whatever `hl_ingest_bpy.py`'s own `[axis]` line printed on the run that built the
scene — see §1, which now carries a current transcript and a warning not to check against it.
The load-bearing part is the relation, not the coordinates: **apex Z must equal `DECK_Y` plus
that station's `rib_height_m`.** **A Y/Z swap passes every other check in this document and
fails only this one.**

**Step 2 — scale, against the realised maximum**

> *"Report the world-space Z of the top of `SCALE_CHECK_1m7`, the max Z of `HL_Ribs`, and the
> max Z across the context collections. Confirm the cube is 1.70 m tall, and check the rib apex
> and tallest-building maxima against `SCENE EXTENT` and `envelope_rib_max_m` in the
> build-constants block."*

Test against `envelope_rib_max_m` — the realised maximum — never the `RIB_MAX_H` ceiling.

**Step 3 — clip range, against the measured extent**

> *"Report `clip_start` and `clip_end` for every camera and for the 3D viewport. Then report
> the bounding box of all objects. Confirm `clip_end` exceeds the scene diagonal."*

Expected diagonal and the required `clip_end` are both in `SCENE EXTENT`. The 100 m default hides most of the
site with no error.

**Step 8 — sun rotation and shadow direction, against `cameras.json`**

> *"Read `key_light.to_sun_unit` from `cameras.json` and convert it to Blender axes. Read the
> sun lamp's `rotation_euler`, compute the world-space direction of its local +Z, and confirm
> the two agree to 1e-6. Then confirm local −Z has a positive Y component and a negative Z
> component."*

Expected values are in `SUN + SHADOW CHECK` — `to_sun`, `light travel`, and the resulting
`rotation_euler`. The lamp's −Z must end up **travelling north and downward.** A lamp 180° out passes a visual check and fails this one.

**Step 8b — shadow length, geometric**

> *"Confirm the shadow multiplier and the reference tower's expected shadow length against
> `SUN + SHADOW CHECK` in the build-constants block."*

This one is arithmetic rather than a scene query, but it is the check that catches a scale
error the transform checks miss.

**Step 9 — camera clearance, against `highline_footprints.json`** *(added 2026-08-20)*

> *"For each camera in `cameras.json`, test its world position against every footprint ring
> whose building is taller than the camera's Z. Report any camera that falls inside one, with
> the BIN and the height."*

`build_lookdev.report_clearance()` runs this on every build and prints a `[clearance]` line per
camera. **Expect `in open air` three times.** Since the 2026-08-20 clearance fix (§9) the
selector in `pick_cameras.py` guarantees it, so a hit here means the selector and the scene have
diverged — a stale `cameras.json`, or a footprint set that moved under it. A camera inside a
prism renders a black frame and nothing else says so.

**Step 6.2 — context shading, against `attribution.json`**

> *"Count objects in `HL_Context_ranked` and `HL_Context_unranked` and check them against
> `EXPECTED COUNTS`. Then report the five objects with the highest `sky_share_norm` and confirm
> they match the top five in `data/attribution.json`'s leaderboard, with norms equal to each
> one's `sky_share_pct` divided by the maximum. Confirm every object in `HL_Context_unranked`
> has `sky_share_norm == -1.0`."*

### 13.4 Sequencing — ingest first, headless, then connect

**Run `hl_ingest_bpy.py` and get all of its assertions passing *before* opening the MCP
connection.** The ingest already verifies the axis conversion, the scale, the envelope↔structure
join, the rib smoothing and the deck width, and it does so in one deterministic pass with no
network in the loop.

> ### ⚠️ The failure this ordering prevents
> If you connect first and ingest through the connection, a geometry bug and a connection bug
> present identically — an object that is not where you expect it might be a wrong axis, or a
> call that silently did not land. **You would be debugging two systems at once with one
> symptom.** Ingest headlessly, confirm the console shows every PASS, save, and only then
> connect. After that, anything wrong is a look-dev problem, because the geometry is already
> proven.

Order:

```powershell
# 1. geometry + everything between the ingest and the render, from JSON. ~2 min.
blender --background --factory-startup --python blender/build_lookdev.py

# 2. the plates.
blender --background blender/answering_line.blend --python blender/render_all.py -- --all --draft
blender --background blender/answering_line.blend --python blender/render_all.py -- --plate A --final
```

1. Run `build_lookdev.py`. It runs `hl_ingest_bpy.main()` itself, so confirm `[axis] PASS`,
   `[verify ribs] PASS`, `[join] OK`, the deck-width line and the attribution counts — **and
   then** `[counts] PASS`, both `[mat] PASS` lines, both `[sun] PASS` lines and `[fig] PASS`.
2. Units, clipping, materials, world, sun, cameras, figures, passes and the compositor are all
   set by that script. There is nothing to set by hand.
3. It saves `blender/answering_line.blend` itself.
4. Connect Claude — **only now.**
5. Look-dev: judging the ramp, the exposure and the grade. **If you change something you want
   to keep, change it in `build_lookdev.py`, not in the `.blend`** — that is the whole reason
   the script builds materials as well as geometry.

### 13.5 Save before any batch operation

**Save the `.blend` before every batch operation, without exception.** A batch that touches
two thousand
objects and goes wrong is not something you undo reliably — `Ctrl+Z` across scripted operations
is unreliable, and a partially-applied material assignment across two collections is worse than
a cleanly wrong one because it looks half-right.

Incremental saves (`File → Save As`, or `Ctrl+Alt+S`) cost nothing and give you a rollback
point per look-dev step. `hl_ingest_bpy.py` can always rebuild the geometry from JSON; it
cannot rebuild your materials, world, compositor graph or figure placement, none of which live
in version control.

---

## The two scripts — BUILT 2026-08-20, and built whole

This section used to read *"Scope — a headless render script (DEFERRED, not written)"*, and it
deferred the work with a good argument: a script that only re-renders is *"reproducible given a
`.blend` nobody can regenerate"*, which is a faster button, not reproducibility. Its own
conclusion was **build it whole when you build it, materials included.** That is what exists
now.

```powershell
# 1 · geometry AND look-dev, from JSON. Overwrites blender/answering_line.blend.
blender --background --factory-startup --python blender/build_lookdev.py

# 2 · the plates.
blender --background blender/answering_line.blend --python blender/render_all.py -- --all --draft
blender --background blender/answering_line.blend --python blender/render_all.py -- --plate A --final
```

### `blender/build_lookdev.py` — everything between the ingest and the render

It calls `hl_ingest_bpy.main()` itself, so one command rebuilds the whole scene from `data/`
and `houdini/`. What it builds, and where each thing comes from:

| built | source |
|---|---|
| geometry | `hl_ingest_bpy.py`, unchanged — imported, not copied |
| clip end · section ortho scale · expected counts · shadow reference tower | **parsed** out of `pick_cameras.render_build_constants()` |
| the six materials, including the `Attribute → ColorRamp` graph | §6.2 and §7 values, in `MATERIALS` / `RAMP` |
| the sun | `cameras.json` → `key_light`, by the vector method, checked against the explicit Euler |
| the world sky | the **same** measured vector; `sun_disc` off so the lamp still owns every shadow |
| cameras A, B, C | `cameras.json` → `stations[]` |
| camera D | direction stated in `AXO_VIEW_DIR`; position and ortho scale **fitted** to the geometry |
| the corridor relief cut | §6.6 |
| the figures | generated at 1.70 m, snapped to deck stations in front of camera A |
| Cycles, passes, compositor | §§11, 12 |

**The axis map is imported, never re-implemented** — `P()` is `hl_ingest_bpy.P`, wrapped only to
return a `Vector`. §1's "implemented in exactly one place" still holds.

**Nothing is typed that the emitter already owns.** `build_constants()` *parses* the emitter's
own output rather than re-deriving the formulas, so a change to the clip-end or ortho-scale
rule propagates, and a change to a LABEL fails the build loudly instead of drifting.

### `blender/render_all.py` — the plates

Reads `--plate A|B|C|D` (or `--all`) and `--draft|--final`. It sets the camera, the resolution,
the mist range and the sampling preset, renders, and tidies the filenames. **It never touches a
camera, a light or a vertex** — §13.2 as code.

Per plate it writes, to `exports/blender/`:

- `<id>.exr` — OpenEXR MultiLayer: combined, depth, mist, AO, normal, albedo, Cryptomatte
  object + material
- `<id>.png` — the composited grade, 16-bit
- `captions.txt` — `pick_cameras.py --captions`, written beside the images so no figure is ever
  transcribed onto a plate

Two things it derives that this document used to type:

- **the mist range**, per camera, from the depth range that camera actually sees. Typed ranges
  produced exactly the flat card §12.1 warns about, on three plates out of four.
- **the section cut** for plate C — see §9.3 and `section_poche()`. It is a live boolean removed
  after the frame, so it reaches no other plate and no saved `.blend`.

### What this buys, in the terms the deferral used

A lost `.blend` now costs **nothing**. Materials, world, compositor, figures and collection
assignments are all in Python, so "reproducible" no longer means "reproducible given a file
nobody can regenerate." The cost the deferral predicted is real and unchanged: **every look-dev
tweak you want to keep is a code edit.** Make it in `build_lookdev.py`, not in the `.blend`.
