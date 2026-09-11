# Blender build steps — The Answering Line (W1 renders)

**Blender 5.2 LTS · Cycles · Windows · RTX 4060 8 GB · 64 GB RAM**
**Time box: two working days.** No usable frame by then → fall back to Rhino + Enscape; the
ingest contract ports.

> ## The one rule
> **No vertical exaggeration. No scaling of the canopy. Ever.**
>
> From `THE_ANSWERING_LINE.md`: *the canopy is small because the towers are the problem — that
> honesty is the argument.*
>
> Framing, lens, exposure and composition are fair game. Geometry is not.

---

## Where you are

✅ **Ingest is done and verified.** `hl_ingest_bpy.py` ran headless on Blender 5.2 and passed
every assertion: axis, scale, sections import, envelope↔structure join, spline types, knot
fidelity, deck width. The geometry in your scene is the geometry the engines wrote.

**Everything below is what remains.** The reasoning behind the ingest checks is in
**Appendix A** — reference, not a step.

```
▢ 1  Clipping                      ← do first, 2 minutes
▢ 2  GPU / OptiX                   ← once per install
▢ 3  Save the .blend
▢ 4  Connect the MCP
▢ 5  Materials
▢ 6  Sun + the shadow check
▢ 7  Cameras
▢ 8  DRAFT RENDER OF PLATE A       ← the checkpoint
▢ 9  Human figures
▢ 10 Final render settings
▢ 11 Output and post
```

## What you are building

| Plate | Camera source | Priority |
|---|---|---|
| **A** — eye-level hero | `cameras.json` → `stations[0]`, perspective | **ships first — §4.2 blocker** |
| **C** — section, worst core | `stations[2]`, orthographic | ships second |
| **D** — corridor axo | framed by hand, step 7.3 | ships third — the argument image |
| **B** — open contrast | `stations[1]`, perspective | only if time allows |

## Silent failures — the index

Each of these produces a scene that looks completely normal and is wrong.

| Failure | Looks like | Caught by | Step |
|---|---|---|---|
| Clip end left at 100 m | a small cluster of buildings | `Home` frames 1.7 km or it doesn't | 1 |
| GPU Compute, no device ticked | slow Cycles | Task Manager GPU load | 2 |
| Ramp attribute name mismatch | context all one colour | exactly 2 buildings hot | 5 |
| Bevel depth as diameter | plausible structural members | rib ≈ 1/8 the cube's width | 5 |
| Sun 180° out | convincing sunlight | shadows run **+Y north** | 6 |
| Scale error | everything, consistently | shadow = 2.067 × height | 6 |
| Figures at cm scale | a 170 m person, or none | figure height == scale cube | 9 |
| View transform drift | four images, three looks | AgX on all four, `Look = None` | 11 |

---

# 1 · Clipping

Measured extents:

| | X (east) | Y (north) | Z (up) |
|---|---|---|---|
| context footprints | −297.79 → 419.31 | −828.32 → 711.17 | 0 → 83.21 |
| rib geometry | −282.69 → 198.45 | −863.50 → 864.70 | 9.00 → 16.04 |

Plan diagonal ≈ 1.87 km; **corner-to-corner ≈ 2.3 km.**

| Where | Clip Start | Clip End |
|---|---|---|
| Viewport `N` panel → View | `0.1 m` | **`5000 m`** |
| Every camera → Object Data → Lens | `0.1 m` | **`5000 m`** |

Clip start of 0.1 m matters: camera C's nearest canyon wall is **2.0 m** away, camera A's
nearest building **6.8 m**.

> ⚠️ **Blender's default clip end is 100 m against a 1.7 km corridor.** Context towers are simply
> not drawn, with no warning — the viewport shows an apparently complete scene missing most of
> its buildings. Every "why is the site empty" hour starts here.

**CHECK:** press `Home`. A long thin corridor ~1.7 km on Y. A small cluster means clipping is
still wrong.

---

# 2 · GPU

`Edit → Preferences → System → Cycles Render Devices` → **OptiX** tab → tick the RTX 4060.
Then `Render Properties → Device: GPU Compute`.

**OptiX, not CUDA** — ~1.5–2× faster on RTX hardware, and it enables the OptiX denoiser.

> ⚠️ With no device ticked, `GPU Compute` falls back to **CPU with no error**. Your 64 GB machine
> renders it slowly and you conclude Cycles is slow.
> **CHECK:** during a render, Task Manager → Performance → GPU shows load. CPU at 100% and GPU
> idle means nothing is ticked.

---

# 3 · Save the `.blend`

Before connecting anything. `hl_ingest_bpy.py` can always rebuild the geometry from JSON — it
cannot rebuild materials, world, compositor or figures, none of which are in version control.

**Save before every batch operation from here on, without exception.** `Ctrl+Z` across scripted
operations is unreliable, and a half-applied material assignment across two collections is worse
than a cleanly wrong one because it looks half-right. `Ctrl+Alt+S` costs nothing.

---

# 4 · Connect the MCP

Ingest first, headless, **then** connect — which is the order you've followed.

> ⚠️ **Why the order matters.** If you ingest through the connection, a geometry bug and a
> connection bug present identically: an object not where you expect might be a wrong axis, or a
> call that silently didn't land. You would debug two systems with one symptom. The geometry is
> proven, so anything wrong from here is look-dev.

## What it is for

- **Scene inspection** — reading back what's actually there against the JSON. Queries in
  Appendix B.
- **Batch operations** — 176 context objects, 232 rib splines. Anything uniform is faster and
  safer issued once than clicked 176 times.
- **Node graphs** — the ramp material and the compositor are fiddly by hand, exact in script, and
  the thing most likely to need rebuilding after a mistake.

## What it is not for — a rule, not a preference

> **Claude does not make the picture.**
>
> **Camera placement and framing** come from `cameras.json`, generated by `pick_cameras.py` from
> the measured data precisely so no one — human or model — picks a viewpoint by eye. A camera
> moved during look-dev silently breaks the tie between the plate and its caption.
>
> **Composition** — what's in frame, what's cropped, where the horizon sits — is yours.
>
> **The material palette** — which colours, how saturated, how the ramp reads — is yours.
>
> **Where light falls** comes from `key_light`, the study's own measured winter vector. The sun
> is not a look-dev control. If a shadow is inconvenient, that is a finding about the site.
>
> Claude may **verify** all four and report a mismatch. It must not **choose** any of them.

---

# 5 · Materials

Five materials, Principled BSDF, flat parameters. Architecture, not product viz — no procedural
grunge, no imperfection maps.

| Material | Assign to | Base Color | Metallic | Roughness |
|---|---|---|---|---|
| `MAT_Steel` | `HL_Ribs` | `0.22, 0.22, 0.23` | `1.0` | `0.35` |
| `MAT_Context_Share` | `HL_Context_ranked` (113) | **ColorRamp — 5.1** | `0.0` | `0.75` |
| `MAT_Context_Neutral` | `HL_Context_unranked` (63) | `0.50, 0.50, 0.50` | `0.0` | `0.70` |
| `MAT_Paving` | `HL_Deck` | `0.38, 0.36, 0.34` | `0.0` | `0.65` |
| `MAT_Ground` | `HL_Ground` | `0.30, 0.30, 0.30` | `0.0` | `0.90` |

One steel material for all 232 ribs, **no variation — the ribs differ in size, and that is the
argument.**

**Assign by collection**, never by selection: `Select → Select Grouped → Collection`.

**No glass anywhere in the context.** With the date rule gone there is no principled subset to
glaze, and glazing by share would put two variables on one surface.

> ⚠️ **Transmission is the render-time cliff.** Across all 176 prisms on an 8 GB card it is the
> difference between a 4-minute and a 40-minute frame, with no warning. A draft suddenly 10×
> slower → check for glass on a context collection.

## 5.1 Context shading — a continuous ramp on measured sky share

The visual variable is **`sky_share_pct` from `data/attribution.json`, joined by BIN.** No
threshold, no categories, no date rule.

| | count |
|---|---|
| footprints total | 176 |
| carry a sky share → `HL_Context_ranked` | **113** |
| absent from attribution → `HL_Context_unranked` | **63** |
| attribution BINs with no footprint | **0** |

Normalisation is generated, not chosen: `sky_share_norm = sky_share_pct / 19.49` (BIN
`1080359`). **Linear** — a building taking twice the sky reads twice as hot.

```
Attribute ──> ColorRamp ──> Base Color   (Principled BSDF)
 Type: Object
 Name: "sky_share_norm"     ← the per-object custom property the ingest wrote
        (use the Fac output)
```

`Type: Object` reads object custom properties by name, so **one material shades all 113 buildings
from their own value.** Never assign a colour per object.

| Ramp position | Colour | Meaning |
|---|---|---|
| `0.00` | `0.42, 0.38, 0.35` (masonry) | takes nothing measurable |
| `1.00` | `0.62, 0.24, 0.16` (deep terracotta) | takes the most |

`MAT_Context_Neutral` must read as **neither end of the ramp** — absent from attribution means
*not measured*, not *measured as zero*. The ingest writes `sky_share_norm = -1.0` for these so a
mis-assignment to the ramp is visible rather than silent.

> ⚠️ **The ramp will look broken, and it is correct.**
> **97 of the 113 ranked buildings take less than 0.1% each.** Median share is 0.0000. The ramp
> leaves almost everything cold and picks out about ten. **That is the measurement:** the
> enclosure is the work of roughly ten buildings.
>
> The temptation is to fix it with a sqrt or log ramp. **Not silently** — a non-linear ramp
> overstates small contributors, and 0.05% would read as a meaningful culprit. If you want it, it
> is a stated editorial choice that belongs in the caption, not a gamma on the Fac input.
>
> **CHECK:** Rendered view from above — exactly **two** buildings at or near full heat, visible
> falloff through about eight more. Everything warm → something non-linear crept in. Nothing warm
> → the Attribute node name doesn't match `sky_share_norm`.

**Why the date rule was dropped.** The old binary tint keyed on `construction_year >= 2009`.
Faithful to the 53.7% figure and wrong as a picture: attribution ranks 1 and 2 are BIN `1080359`
(19.49%) and `1012203` (18.49%), **both built 2006** — 37.98% between them, more than all six
post-2009 buildings combined, and rank 1 is the tallest building on the site at 83.2 m. A top-N
rule would invent a threshold the data doesn't contain. **The 2009 date belongs in the caption**,
not as a tint a reader must decode. The tag is still written onto every object and simply not
rendered.

## 5.2 The rib bevel

Already set by the ingest, but verify:

```
bevel_depth   = 0.10955 m         (OD 219.1 mm ÷ 2)
point.radius  = CHS 219x8 → 1.000 · CHS 168x6.3 → 0.768
sections      = {'CHS 168x6.3': 221, 'CHS 219x8': 11}
```

Bevel: **Round**, Depth `0.10955 m`, Resolution `4`, **Fill Caps on**.

> ⚠️ **Bevel depth is a radius, not a diameter.** `0.2191` gives every rib double its thickness,
> and a 219 mm tube looks reasonable at 438 mm in a 1.7 km scene.
> **CHECK:** the thickest rib is ~1/8 the width of the 1.7 m scale cube. If a rib reads as a
> structural member rather than a tube, you doubled it.

## 5.3 Ground is invented — keep it quiet

A flat plane at Z = 0, footprint extent + 200 m. **There is no ground, terrain or street surface
in any source file.** The object carries `hl_source = "NOT IN THE DATA — scene furniture, invented
for the render"`. Matte and unobtrusive; it exists so the towers have something to cast onto.

---

# 6 · Sun

`cameras.json` → `key_light`:

```
day_of_year   355
elev_deg      25.8191
azim_deg      180.0
to_sun_unit   [0.0, 0.435531, -0.900174]     project frame, site → sun
```

**`to_sun_unit` points FROM the site TOWARD the sun** — confirmed by arithmetic, not the label:
azimuth 180° is due south, and in a `+z = north` frame a southward vector must have negative z.
It does. `sin(25.8191°) = 0.4355` matches the y component.

**Converted to Blender axes:** `(0.0, -0.900174, 0.435531)` — south and up.

**Blender's sun lamp emits along its own local −Z**, so the lamp's **+Z must point at the sun**.

```python
from mathutils import Vector
d = Vector((0.0, -0.900174, 0.435531))          # to_sun, blender frame
sun.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
```

Cross-check: the explicit Euler is `(1.120168, 0, 0)` rad = `(64.1809°, 0°, 0°)`, and rotating the
lamp's +Z by it reproduces the stored vector to **3.7e-07** (the residual is the stored vector's
own 6-dp rounding).

**Lamp settings:** Sun, Strength `3.0` to start, **Angle `0.526°`** — the real solar disc, which
gives correct shadow softness and costs nothing.

## 6.1 CHECK — shadows run north, at a measured length

**Plan view, before any render.** Numpad 7, viewport shading → Rendered.

- **Shadows run NORTH, toward +Y.** Pointing −Y means the lamp is reversed.
- **Shadow length = height / tan(25.8191°) = 2.067 × height.** The 34.0 m tower at station C
  (BIN `1088519`, 2.0 m from the deck) must cast **≈ 70.3 m** northward.

Measure it: `Shift+Spacebar → Measure`, tower base to shadow tip. Not ~70 m → altitude or scale is
wrong, and both are silent.

The winter sun at 25.8° is *low*. Long raking shadows are correct.

> ⚠️ **A sun 180° out still looks like sunlight.** Aim the lamp along `to_sun` instead of
> light-travel and the scene is lit from the **north** at the same altitude. Completely
> convincing. Every shadow points the wrong way and the raking light the recapture figure counts
> comes from the wrong hemisphere.

---

# 7 · Cameras

Positions and targets are in the **project frame** and need the axis conversion
`blender = (px, pz, py)`. **Never hand-position these.**

| Camera | Type | Position (project) | Target (project) |
|---|---|---|---|
| `CAM_A_hero` | perspective | `[-55.92, 10.65, -133.9]` | `[-42.34, 10.65, -96.28]` |
| `CAM_B_open` | perspective | `[96.88, 10.65, 251.69]` | `[115.88, 10.65, 297.94]` |
| `CAM_C_section` | orthographic | `[84.23, 12.52, 339.33]` | `[125.85, 12.52, 322.23]` |

```python
import bpy, json
from mathutils import Vector
def P(v): return Vector((v[0], v[2], v[1]))

doc = json.load(open(r"<PROJECT>/houdini/cameras.json", encoding="utf-8"))
for st in doc["stations"]:
    c = st["camera"]
    cam = bpy.data.cameras.new("CAM_" + st["id"])
    obj = bpy.data.objects.new("CAM_" + st["id"], cam)
    bpy.context.scene.collection.objects.link(obj)
    pos, tgt = P(c["position"]), P(c["target"])
    obj.location = pos
    obj.rotation_euler = (tgt - pos).to_track_quat('-Z', 'Y').to_euler()
    cam.clip_start, cam.clip_end = 0.1, 5000.0
    if c["type"] == "orthographic":
        cam.type = 'ORTHO'
        cam.ortho_scale = 70.0
    else:
        cam.lens = 35.0
```

`to_track_quat('-Z','Y')` is the camera equivalent of the sun's `('Z','Y')` — Blender cameras look
down −Z with +Y up.

## 7.1 A and B — perspective at eye height

Both at **Z = 10.65 m** = deck 9.0 + eye 1.65, from `camera.eye_height_above_deck_m`.

**Do not raise the camera to "see more." Raising it is indistinguishable from lowering the
towers.**

**35 mm to start.** 24 mm exaggerates the canyon and is the easy way to cheat this image; 50 mm is
closer to how the deck feels. 35 mm is the honest compromise — and it changes the lens, not the
building heights, so it is framing and it is allowed.

Camera A's nearest building is 6.8 m away and 24.4 m tall (BIN `1090199`, built 2016 — the
antagonist is right there).

## 7.2 C — orthographic scale

`ortho_scale` is the world size of the **larger** image dimension.

At that station: deck 9.0 m wide, near canyon wall **34.0 m at 2.0 m**, far wall **41.1 m at
38.2 m**, target at Z = 12.52. Vertical extent needed ≈ 66 m, horizontal ≈ 60 m.

**Start at `ortho_scale = 70`, square or portrait plate.** Landscape wastes the frame on ground.

**CHECK:** both canyon walls fully in frame, the full rib in frame, and the 7.04 m rib occupying
roughly **a tenth of the frame height**.

*If that looks too small, it is correct.* Reducing `ortho_scale` until the canopy fills the frame
is the no-exaggeration rule broken by the back door — you would be cropping the towers out to make
the canopy look bigger. **Adjusting to fit the canyon is framing; adjusting to flatter the canopy
is not.**

## 7.3 D — the corridor axo

Orthographic, high oblique along the corridor's long axis (Y, 1.73 km). **This is the argument
image.** The headline is material variation, not sun recovery, so the frame must show **both rib
regimes** — the **108 ribs at the 1.20 m floor** where the deck still sees sky, and the tall ribs
rising to 7.04 m in the canyon. Do not crop to the dramatic half.

Colour ribs by height if you wish, reading `rib_height_m` from `envelope.json` **by index**, not by
hand-selecting.

---

# 8 · Draft render of plate A — the checkpoint

Set 128 samples at 1920 wide and render. Twenty to sixty seconds.

**Stop and look before doing anything else.** This frame tells you more than any further planning:
where the light actually falls, whether 35 mm reads right, whether the ribs are legible against
the towers at eye level, whether the ramp is doing anything at this angle.

Figures come after this, not before.

---

# 9 · Human figures — plate A only

**Required by `Projects/README.md` §4.2:** one image per project carrying scale, site context and a
human figure. This project has never had one. Plate A is that image.

**Placement:** on the deck, standing height **1.70 m**, feet at Z = 9.00. Two or three at different
depths — one near-middle ground, one further down the corridor. The `HL_Access` empties are
plausible positions for people entering.

Camera at 1.65 m and figures at 1.70 m are consistent, not contradictory: a standing person's eyes
sit a little below the top of their head.

**Candidate free sources — verify the licence yourself at the source.** Base meshes ship untextured
and will read as grey mannequins; at this distance silhouette quality matters far more than mesh
detail.

| Option | What it is |
|---|---|
| Blender Studio — Human Base Meshes | Official Blender Foundation base meshes, ships as a `.blend` |
| MakeHuman | Open-source parametric generator with a Blender exchange add-on |
| Mixamo | Rigged characters, free with an Adobe account |
| BlenderKit | Free tier inside Blender's asset browser; some scanned people |
| Quaternius / Kenney | Stylised low-poly people |

> ⚠️ **Imported figures arrive at the wrong scale.** Most download at centimetre or arbitrary
> units, landing 100× too large or small. In a 1.7 km scene a 170 m human reads as a building and a
> 1.7 cm one is invisible.
> **CHECK:** put the figure beside `SCALE_CHECK_1m7`. Same height as the cube. **Before**
> duplicating it.

---

# 10 · Final render settings

| | Draft (look-dev) | Final |
|---|---|---|
| Max Samples | `128` | `1024` |
| Min Samples | `0` | `64` |
| Noise Threshold | `0.05` | `0.01` |
| Denoise | on, **OptiX**, Prefilter `Accurate` | same |
| Denoising passes | Albedo + Normal | same |
| Time Limit | `60 s` | `0` (off) |

Adaptive sampling makes the final number a *ceiling*, not a cost — open sky hits the threshold in
~100 samples and stops.

**Also:** `Performance → Final Render → Persistent Data` **on** (big win re-rendering the same
scene from several cameras); `Performance → Memory → Use Tiling` on, tile size `2048`.

| Plate | Resolution | Ratio |
|---|---|---|
| A hero | `3508 × 2480` | A4 landscape @ 300 dpi |
| B open | `3508 × 2480` | same |
| C section | `2400 × 3000` | portrait, suits the section |
| D axo | `4000 × 1600` | long, matches the corridor |

Expected times on the 4060 with OptiX — 232 bevelled curves, 176 opaque prisms, one sun, no
volumetrics, **no glass anywhere**:

| | Draft 128 spp @ 1920 | Final 1024 spp @ 3508 |
|---|---|---|
| A eye level | 20 – 60 s | 4 – 12 min |
| B open | 15 – 40 s | 3 – 8 min |
| C ortho section | 20 – 50 s | 4 – 10 min |
| D corridor axo | 40 – 120 s | **8 – 25 min** |

D is the expensive one — the entire 1.7 km site is in frame. Any frame over ~40 minutes means
something is wrong: check first for glass reaching a context collection, second whether the
denoiser is running. Memory should sit well under 3 GB; approaching 8 GB means imported figures
with 4K textures, not the site.

> **Size budget.** `portfolio_master.pdf` is 11.4 MB of a 12 MB ceiling before any of these exist.
> Render at these sizes, then downsample and compress at layout — do not render small to save PDF
> weight, and do not paste 4K PNGs into the PDF.

---

# 11 · Output and post

## 11.1 Passes

`Output Properties → Output`: **OpenEXR MultiLayer**, Color Depth `Float (Half)`, Codec `ZIP`.

`View Layer Properties`, enable:

| Pass | For |
|---|---|
| Combined | the image |
| **Z** (Depth) | precise masking, focus work; raw metres |
| **Mist** | normalised 0–1 depth for atmospheric cueing — easier than Z in the compositor |
| **Ambient Occlusion** | contact shading without re-rendering |
| **Cryptomatte** Object + Material | select the canopy or any named BIN *after* the render |

Mist range in `World Properties → Mist Pass`: Start `50 m` / Depth `1200 m` for plate A;
Start `0` / Depth `2000 m` for the axo. Mist saturating to white by 100 m gives a flat card.

**Cryptomatte is the one that saves the project.** If a reviewer asks for the canopy tinted
differently or the top culprits picked out harder, you do it in the compositor in two minutes
instead of re-rendering for twenty. Objects are named `BLD_<bin>_<ring>`, so a Cryptomatte pick
maps straight back to an attribution row.

## 11.2 Minimal compositor

`Compositing` workspace, tick **Use Nodes**:

```
Render Layers ──> Exposure ──> Mix (depth cue) ──> Mix (AO) ──> RGB Curves ──> Composite
                                    ▲                  ▲
                              Mist ─┘            AO ───┘
```

1. **Exposure** — start `0.0`, work in ±0.5 stops. Do brightness here, **not** by raising sun
   strength, so the sun keeps its measured angle.
2. **Depth cue** — `Mix`, Factor ← Mist, toward a pale `0.72, 0.75, 0.78`, factor ~0.5.
3. **AO multiply** — `Mix`, Blend `Multiply`, Factor `0.25`, second input ← AO.
4. **RGB Curves** — a gentle S. **Do not crush the blacks**; the section plate needs shadow detail
   in the canyon, which is the entire subject.
5. **Composite** + a **Viewer** to see it live.

> ⚠️ **View transform drift.** Blender defaults to **AgX**, which desaturates highlights heavily —
> good for raking winter sun, bad if you then hand-correct saturation and bake it in. Set
> `Color Management → View Transform` deliberately: **AgX for all four plates**, `Look = None`.
> Four images in three transforms will not read as one portfolio.

## 11.3 Where files land

```
5.CV_Highline/exports/blender/
    A_hero_eye_level.exr        A_hero_eye_level.png
    B_open_contrast.exr         B_open_contrast.png
    C_section_worst_core.exr    C_section_worst_core.png
    D_corridor_axo.exr          D_corridor_axo.png
```

Stems are exactly `cameras.json` → `stations[].id`; `D_corridor_axo` matches the `D_corridor` plate
in `houdini/sources.json`. So:

```powershell
python houdini/pick_cameras.py --captions
```

emits caption blocks whose ids line up one-to-one with these files.

> **Every number that goes beside an image comes out of that command.** Do not read a figure off
> this document and type it onto a plate. The site facts here — heights, distances, counts — are
> context for *building the scene*, not caption copy.

---

# Appendix A — what the ingest built and verified

Reference. You have already run all of this successfully; it is here so a future failure is
readable.

## A.1 Axis — `blender = (px, pz, py)`

```
project   +x east   +y UP     +z north
blender   +X east   +Y north  +Z UP
```

Implemented in exactly one place — `P()` at the top of `hl_ingest_bpy.py`. **Never convert again
downstream.** The determinant is −1 and that is not a mirror: mapping semantic axis to semantic
axis between a left- and right-handed frame necessarily is. East lands on east, north on north, up
on up.

The load-bearing assertion is **apex Z == `DECK_Y` + `rib_height_m`**. Station 100: project
`(-41.69, 10.87, -95.41)` → Blender `(-41.69, -95.41, 10.87)`, and `10.87 == 9.0 + 1.87`.

A Y/Z swap builds a corridor with buildings along it that is lying flat, reads as "a long site seen
from above," and survives to a render. **This is the only check that catches it.**

## A.2 Scale — against 7.04 m, never 7.5 m

7.5 is the generator's ceiling in `_meta.params`; no rib reaches it. Sizing to 7.5 would overstate
the canopy by 6%. Against `SCALE_CHECK_1m7` in front ortho: cube base at Z = 9.00; tallest rib
≈ 4.1 cube-heights; deck plane ≈ 5.3 cube-heights.

## A.3 Expected scene contents

| Collection | Contents |
|---|---|
| `HL_Canopy` | `HL_Ribs` — one CURVE, **232 splines**, 1160 control points |
| `HL_Context_ranked` | **113** prisms |
| `HL_Context_unranked` | **63** prisms |
| `HL_Site` | `HL_Deck` (464 verts, 231 faces), `HL_Ground` |
| `HL_Access` | 10 empties |
| `HL_Checks` | `SCALE_CHECK_1m7` |

> ⚠️ **Attributes did not port the Houdini way.** Blender curve splines don't carry arbitrary named
> attributes, so the per-rib values stay in the JSON and only the sized section is encoded, as
> per-point `radius`. If you later need `deficit_svf` for a shader, read it from `envelope.json`
> **by index** — do not assume it is on the curve.

## A.4 The two rib checks — they test different things

**`verify_spline_types` — the smoothing guard.** Asserts all 232 splines are BEZIER with AUTO
handles.

> **This is what catches NURBS.** A coordinate comparison never could: converting to NURBS leaves
> every control point exactly where it was and changes whether the *evaluated curve* passes through
> them. The coordinates read back clean while the rendered tube stops touching the measured apex.
> `VECTOR`, `ALIGNED` and `FREE` handles likewise keep knots in place and only alter the curve
> between them.

**`verify_ribs` — knot fidelity against `envelope.json`.** Asserts the coordinates in the scene are
the coordinates the engine wrote. **Not a smoothing test.** It catches a wrong axis map, a stray
transform, a units change, or a mis-indexed join.

**Why its tolerance is magnitude-scaled.** Blender stores control points as **float32**. The
representable step at magnitude *m* is `eps32 × m`, so round-to-nearest bounds the per-coordinate
error at half that. At |Y| = 864.70 m half-ULP is **5.15e-05 m** — an absolute 1e-6 tolerance is
~50× tighter than the storage can hold, and fails on arithmetic that is exactly correct. It did.

The evidence that this is storage and not movement, across all 232 ribs: deviation correlates with
coordinate magnitude at **r = +0.908**, and **every rib sits inside one half-ULP of its own
magnitude — max ratio 0.956, never above 1.** Half-ULP is the exact theoretical bound for
round-to-nearest; real displacement has no reason to respect it on all 232 ribs at once.

```python
EPS32 = float(numpy.finfo(numpy.float32).eps)          # 1.1920929e-07
HALF_ULP_MULT = 4.0
tol_per_rib = max(1e-6, HALF_ULP_MULT * 0.5 * EPS32 * max_abs_coord_of_that_rib)
```

`HALF_ULP_MULT = 4` absorbs a second conversion while staying three to four orders clear of
anything real: at 864 m the bound is 2.06e-04 m, and a botched transform displaces a knot by
centimetres to metres.

**Apex height and endpoint Z stay absolute at 1e-6** — they operate on small magnitudes where that
is already appropriate. The endpoint error is exactly `0.000e+00` because 9.0 is exactly
representable in binary32.

> ⚠️ **A deviation that does not scale with magnitude is real movement.** The bound is per-rib. A
> displacement constant across ribs, or large on a rib near the origin, blows through its own
> scaled bound and the build stops. **Do not raise `HALF_ULP_MULT` to make a failure go away** —
> above four half-ULPs it is not storage.

## A.5 The deck-width bound — derived from source rounding

The deck is lofted between the **232 rib start points and 232 rib end points** — the rib rails *are*
the deck edges, at ~8 m spacing. The 10-point centreline is never resampled: 10 points across
1856.7 m is ~206 m per segment, and sweeping it would cut every corner.

Both the expected width and the tolerance are derived. The expected width comes from
`envelope.json._meta.params.DECK_HALF_W × 2`, not a typed 9.0 — so if the parameter changes without
the geometry, the check catches exactly that.

```python
dp       = _detect_decimals(rail_coords)        # detected from data: 2
quantum  = 10 ** -dp                            # 0.010 m
src_term = quantum * sqrt(2)                    # two endpoints, each rounded in 2 axes
f32_term = EPS32 * max_abs_rail_coord           # ~1.0e-04 m
bound    = src_term + f32_term                  # 0.014245 m
tol      = SOURCE_ROUND_MULT * bound            # 4.0x -> 0.056981 m
```

`quantum × sqrt(2)` because each rail endpoint is a 2-D point rounded independently in each axis,
displacing it by at most `(quantum/2)·sqrt(2)`, and the distance between two such points is off by
at most the sum.

> ⚠️ **Why this replaced a typed `0.01`.** That value was **0.70× the theoretical bound** — it sat
> *below* the error the source rounding can legitimately produce, and the observed spread was
> saturating it exactly. A correct regeneration of `envelope.json` shifting one rail coordinate by
> one hundredth could have aborted the build on **valid data**. A tolerance tighter than the known
> error of its own inputs is not a strict check; it is a false alarm waiting for a rebuild.

Verified against deliberate faults: one station 10 cm wide aborts at 6.89× the bound;
`DECK_HALF_W` set to 5.0 with geometry unchanged aborts at 70.78×. A 3 cm error passes — the honest
limit, and the same trade as A.4. **Do not raise `SOURCE_ROUND_MULT` to silence a failure.**

## A.6 The rib population

**108 of 232 ribs have `reach_m` exactly 0.0** — nearly half the canopy is a pure arch with no
cantilever, at or near the 1.20 m floor. Not a defect and not to be smoothed over: it is the
material-variation story, and framing the axo to show both regimes is the point of that plate.

---

# Appendix B — MCP verification queries

**Axis, against `envelope.json`**
> *"Read `envelope.json` station index 100, take `points[100].rib[2]` — the apex knot — and convert
> with (px, pz, py). Find spline 100 of `HL_Ribs`, read bezier point 2, report both. They must
> agree within the magnitude-scaled tolerance. Confirm apex Z equals 9.0 + `rib_height_m`."*

**Scale**
> *"Report world-space Z of the top of `SCALE_CHECK_1m7`, max Z of `HL_Ribs`, and max Z across both
> context collections. Confirm cube 1.70 m, tallest apex 16.04 m, tallest building 83.21 m."*

**Clip range**
> *"Report `clip_start` and `clip_end` for every camera and the 3D viewport, then the bounding box
> of all objects. Confirm `clip_end` exceeds the scene diagonal."* Expected ≈ 2.3 km; `clip_end`
> must be `5000`.

**Sun, against `cameras.json`**
> *"Read `key_light.to_sun_unit`, convert to Blender axes. Read the sun lamp's `rotation_euler`,
> compute the world direction of its local +Z, confirm agreement to 1e-6. Then confirm local −Z has
> positive Y and negative Z."*
> Expected: to_sun → `(0.0, -0.900174, 0.435531)`; euler ≈ `(1.120168, 0.0, 0.0)`; −Z →
> `(0.0, +0.900174, -0.435531)`.

**Shadow length**
> *"Confirm `tan(25.8191°)` gives a shadow multiplier of 2.067, and that BIN 1088519 (34.0 m) casts
> ≈ 70.3 m northward."*

**Context shading, against `attribution.json`**
> *"Count `HL_Context_ranked` and `HL_Context_unranked` — expect 113 and 63. Report the five highest
> `sky_share_norm` and confirm BINs 1080359, 1012203, 1089968, 1089697, 1090204 with norms 1.000,
> 0.949, 0.841, 0.568, 0.530. Confirm every unranked object has `sky_share_norm == -1.0`."*

---

# Appendix C — headless render script (DEFERRED)

```powershell
blender --background scene.blend --python blender/render_all.py -- --plate A --final
```

Would read `cameras.json` and build all four cameras; build the sun from `key_light` with the 1e-6
assertion; apply a draft/final preset and per-plate resolution; loop the plates; re-run
`pick_cameras.py --captions` beside the images. **~80–120 lines**, an hour or two.

**Why deferred: it would not deliver reproducibility on its own, and that is the only reason to
build it.** `scene.blend` would still hold the materials (including the ramp graph that carries the
entire context argument), the world and mist range, the compositor graph, the figures, and the
collection assignments. **None of that is in version control and none would be rebuilt.**
"Reproducible given a `.blend` nobody can regenerate" is a faster button, not reproducibility.

Real reproducibility means building materials, world and compositor in Python too — another 200–300
lines, and every look-dev tweak becomes a code edit, which is the wrong loop while you are still
deciding how the ramp reads.

**Build it when plate A exists and you know you will re-render repeatedly — and build it whole.**

What holds without it: `hl_ingest_bpy.py` guarantees the geometry and the numbers come from the JSON
every time, verified by assertion on every run. A lost `.blend` costs you look-dev, not correctness.
