# The Answering Line — render plan

An ordered queue of stages. Work the first unchecked one, finish it, check it off. No dates.

**What this produces:** the finished images that close the project's arc — *measure the wound
→ design the response → validate the response with an **independent** instrument* — plus the
post-production rules for composing them into the portfolio. Four are station-specific and
committed in `cameras.json` (**A** hero · **B** open contrast · **C** section · **D**
corridor); the specimen array (Stage 4) is a population plate and has no single station.

**What this is not:** a re-render of the analysis. `board1.png` / `board2.png` and the
Streetscape Biophilia axo already carry the diagnosis. This produces the **answer**, which
currently exists only as numbers in `data/envelope.json`.

**Governing constraint, from `THE_ANSWERING_LINE.md`:**

> No vertical exaggeration anywhere. The canopy is small because the towers are the
> problem — that honesty is the argument.

Do not scale the canopy to make it read better. If it looks slight against the towers, that
is the finding rendering itself correctly.

## Captions are generated, not transcribed

**No numeric value appears in this document's station specs.** Every figure lives in exactly
one place — `houdini/cameras.json` → `stations[].numbers.<field>.value` — and this plan holds
only the **caption template and the source key**.

```powershell
python houdini/pick_cameras.py              # select the stations -> houdini/cameras.json
python houdini/pick_cameras.py --captions   # print every caption block, filled
```

`--captions` resolves each caption line's `key` against the station object at emit time. The
caption blocks store label + key + format and **deliberately hold no copy of the value**, so a
figure cannot drift between the JSON, this plan, and a finished plate. If a number is wrong,
it is wrong in one file.

**The rule:** any figure that reaches a plate must come out of `--captions`. If you find
yourself typing a number into a caption, stop — add it to the station's `numbers` block and
regenerate. A figure absent from a station's `numbers` block is not board-ready for that plate.

`pick_cameras.py` selects all three stations by stated rules over `data/envelope.json` and
`data/highline_viewshed.json`, and writes camera position, target and the key-light vector
alongside. The rig constants are keys too — `_meta.deck_plane_y_m`, `_meta.eye_height_m` —
world metres throughout, no rescale. Re-run after any engine re-run; **do not hand-edit
`cameras.json`.**

| Image | Station key | Selection rule |
|---|---|---|
| **A** · eye-level hero | `stations[0].s_m` | max `deficit_svf` where recapture > 0 |
| **B** · open contrast | `stations[1].s_m` | max `svf_deck` where ≥ `OPEN_SVF_MIN`, `river_view`, and `nearest_wall_m` ≤ `CONTEXT_MAX_WALL_M` |
| **C** · section, worst core | `stations[2].s_m` | max `deficit_svf` overall |

Population plates (**E** specimen array, **D** corridor) have no station; their numbers
resolve through `houdini/sources.json`, and `--captions` prints them in the same run.

---

## Render direction

*Direction, not findings. Every figure named here is a key, not a value.*

### What ships, in priority order

1. **A — the eye-level hero.** This is the `Projects/README.md` §4.2 image and the only
   blocking item in the project. Eye level, human figures at **1.7 m**, checked against
   `cameras.json` → `_meta.eye_height_m` so the people and the camera agree. If one image
   gets finished, it is this one.
2. **C — the section.** The plate where the family's tallest rib reaches into the worst core
   and recovers nothing. It is the only image that makes the project's stated limitation
   *visible* rather than written, which is why it outranks the corridor.
3. **D — the longitudinal axo of the corridor.** See below; it has been promoted.

**B renders only if time allows.** It is the least load-bearing of the four — a restraint
plate, valuable but not carrying an argument the others don't.

### The axo is now the argument image

The headline changed: **material variation, not sun recovery.** The recapture figures do not
separate the canopies; the steel does. That makes the corridor axo the plate that carries the
claim, and it must be framed to show it:

**What the canopy now varies in — this changed on 2026-08-15 and the old framing is dead.**
With the complete footprint set, `envelope_reach_nonzero_count` of `envelope_stations` ribs
carry a surviving aperture; only `envelope_reach_zero_count` sit at zero reach. The rib family
runs continuously from `envelope_rib_min_m` to `envelope_rib_max_m`, with reach out to
`envelope_reach_max_m`, and `ribsched_t01_share_pct` is now a minority share rather than a
dominant one. **The canopy is not a flat rail with occasional tall ribs. It varies at nearly
every station.**

- **Frame the gradient, not a contrast.** The old brief asked for two regimes — collapsed
  minimum against canyon maximum — because when the footprints were 81.6% incomplete most
  stations genuinely had no aperture to reach toward. They do now. Show the height and reach
  climbing and falling *continuously along the length*.
- Both extremes still have to be in frame — `envelope_rib_min_m` and `envelope_rib_max_m` —
  but as the ends of a range, not as two states.
- **Reach is the second variable and it is no longer mostly zero.** Rib height alone will read
  as a simple swell; the cantilever direction and length is what shows the canopy *aiming*.
  If only one attribute can drive colour, drive it with height and let reach read in silhouette.
- The `envelope_reach_zero_count` pure arches are now the exception. Do not crop to them and do
  not hide them: they are where the deck kept its sky.
- **Context buildings shaded on a continuous ramp by measured sky share** — `sky_share_pct`
  from `data/attribution.json`, joined by BIN, normalised linearly on the maximum. No
  threshold, no categories. It lets a reader see that the enclosure and the tall ribs share a
  cause, because the hot buildings and the tall ribs are in the same places.

**The date tint stays retired as a visual variable** (superseded 2026-08-10; build per
`blender/BLENDER_BUILD_STEPS.md` §6.2) — **but the original reason for retiring it no longer
applies, and the honest version is different.** The old argument was that a 2009 cut left the
top culprits neutral. Since 2026-08-16 the primary threshold is the **2005 West Chelsea
rezoning**, which *does* capture them: the top three are 2008, 2006 and 2006, all post-rezoning.

The ramp is still the right visual variable, for a better reason: **a binary tint shows
membership, and the thing worth showing is magnitude.** The enclosure is spread across
`attribution.json`'s full ranked set, with a long tail — no single building dominates the way
one did in the incomplete data. A tint would flatten a distribution into two buckets; the ramp
shows the distribution.

**The era split survives as a caption fact, not as a colour.** Quote it from
`attribution.json` → `metadata.cuts` — the **2005 rezoning** cut is primary, the **2009
opening** cut secondary, and both carry their over-representation figures. That is a sentence a
reader can check rather than a colour they must decode. ⚠️ Neither share has a
`Projects/README.md` §5 row yet under the new thresholds; see *Still unsourced* below. The date
tag remains on every object as data.

⚠️ **The old note here said: *"if the axo reads as a thin canopy that mostly isn't there, it is
correct."* That is no longer true and must not be reinstated.** It described a population where
most stations sat at the generator floor. The canopy is now present and varying along nearly
the whole line — what it is *not* is large, against a canyon whose tallest wall stands some
fifty times the tallest rib. **The honest reading is a canopy that answers everywhere and
is dwarfed anyway**, and that is a different, better picture than absence.

### Hard constraints

- **No vertical exaggeration. No scaling of the canopy.** Not to make it read, not for one
  frame, not "just for the hero." `THE_ANSWERING_LINE.md` is unambiguous and this is the
  constraint most likely to be broken under deadline.
- **Key light from the measured winter vector only** — `key_light.to_sun_unit` /
  `key_light.light_travel_unit`. No second light placed for looks, no fill that implies sun
  from a direction the analysis does not have.
- **No number on a plate that did not come out of `--captions`.**

### Time box — two working days

If there is no usable frame by the end of the second day, **stop and fall back to Rhino +
Enscape driven from the same JSON.** The ingest contract ports directly: the geometry is
already world-metre, y-up, in the frame both applications use, and `hl_ingest.py`'s four modes
describe exactly what has to be rebuilt. **The image matters more than the renderer** — this
project has one missing deliverable and it is a picture with a person in it, not a Houdini
scene. Do not spend day three on the tool.

---

## ⊘ Stage 1 · Geometry in — **SUPERSEDED**

> **Superseded 2026-08-10 by `blender/BLENDER_BUILD_STEPS.md` §§1–6.** W1 renders in Blender
> (Cycles), not Houdini, so `hl_ingest_bpy.py` is the ingest that runs. Two substantive
> differences, not just a port: the **deck is lofted between the 232 rib rails**, not swept
> along a resampled centreline (10 points across 1856.7 m cuts every corner), and **rib
> diameters come from `structure.json`'s sized sections** via an imported `SECTIONS` table.
> Kept below as the Houdini fallback and as the readable statement of what each mode owes the
> scene — the JSON contract is identical either way.

`houdini/hl_ingest.py`, four Python SOPs, one per mode.

- `ribs` → 232 open polylines from `data/envelope.json`. Every driver lands on the prim and
  on each point: `deficit_svf`, `rib_height_m`, `reach_m`, `recaptured_winter_sun_frac`,
  `s_m`, plus `ribt` (0–1 along the rib) for profile taper.
- `context` → 176 building footprints, `height` prim attrib → PolyExtrude by attribute.
  Also carries `year` and `post2009` — **as data, not as the shading variable.** The context
  is shaded on the continuous sky-share ramp (see *Render direction*); the date tag stays
  queryable and available to a future plate, and supplies the caption fact.
- `deck` → the centreline at y = 9.0. **Resample before sweeping** — the stored line is 10
  points; `hl_core` resamples it before ray-casting and so must you.
- `access` → the 10 weighted entry points, for placing figures where people actually enter.

**Done when:** ribs, massing and deck coexist in one scene at true scale, and the canopy
sits over the deck without any manual transform. If it doesn't line up, the bug is in the
scene, not the data — all three files share one frame.

---

## ⊘ Stage 2 · The real sun — **SUPERSEDED**

> **Superseded 2026-08-10 by `blender/BLENDER_BUILD_STEPS.md` §8**, which carries the
> Blender-specific conversion: the axis map applied to `to_sun_unit`, the resulting
> `rotation_euler`, which of the two vectors a sun lamp must be aimed along, and the shadow
> check that catches a lamp 180° out. **The measured sun below is unchanged and still
> governs** — `dump_sun.py`, `data/sun_vectors.json` and `key_light` are renderer-agnostic and
> are what both routes read.

`python houdini/dump_sun.py` → `data/sun_vectors.json` (already run; re-run if `hl_core`
changes).

Measured output, from the study's own `sun_path`:

| Day | Daylight steps | Peak elevation | Azimuth at peak |
|---|---|---|---|
| winter (355) | 53 | **25.8°** | 180° |
| equinox (80) | 71 | 48.8° | 180° |
| summer (172) | 89 | 72.7° | 180° |

Light the hero with the **winter** vector. That 25.8° raking sun is the exact condition the
recapture figure counts, and it is why the canopy cantilevers rather than caps.

**Take it from `cameras.json` → `key_light`**, which carries the same measured peak already
resolved for the scene. Keys, not values: `key_light.elev_deg`, `key_light.azim_deg`,
`key_light.to_sun_unit` (site → sun) and `key_light.light_travel_unit` (its negation). A
Houdini distant light aims down its own −z, so orient it along `light_travel_unit`. Frame is
`key_light.frame` — +x east, +y up, +z north, which every file here already shares.
`--captions` prints the resolved values at the head of every run.

**Done when:** the sun in the scene is placed from that vector, not by eye, and the caption
names the day-of-year from `key_light.day_of_year`.

---

## ☐ Stage 3 · Image A — the eye-level hero

**The image the whole portfolio lacks.** On the deck, under the canopy, at the enclosed
station where the canopy demonstrably still works.

**Station · camera · numbers:** `cameras.json` → `stations[0]` (`A_hero_eye_level`). Camera
`camera.position` → `camera.target`, both at eye height above the 9.0 m deck plane; the
framing note is in `camera.framing`.

**Why this station:** `max deficit_svf subject to recapture > 0` — the worst enclosure on the
line at which the canopy still works. A worse station exists (Image C's) but recovers nothing.

**Caption block — generate, do not transcribe:**

```powershell
python houdini/pick_cameras.py --captions
```

| Caption line | Source key |
|---|---|
| station | `stations[0].s_m` |
| stolen sky (`deficit_svf`) | `stations[0].numbers.deficit_svf.value` |
| sky view today (`svf_deck`) | `stations[0].numbers.svf_deck.value` |
| winter sun recaptured | `stations[0].numbers.recaptured_winter_sun_frac.value` |
| rib height / reach | `stations[0].numbers.rib_height_m.value` · `.reach_m.value` |
| enclosure angle | `stations[0].numbers.enclosure_deg.value` |
| nearest wall | `stations[0].numbers.nearest_wall_m.value` |
| dominant occluder built | `stations[0].numbers.dom_occ_year.value` |

⚠️ **The recapture number drags three caveats onto the plate with it** — instrument name, the
n = 56 non-significance, and the apex-not-a-person sensor. They are emitted automatically by
`--captions` whenever a caption prints `recaptured_winter_sun_frac`, from
`stations[0].numbers.recaptured_winter_sun_frac.caveats_that_must_travel_with_it`. **Do not
retype them either.**

- Human figures at correct scale. Real materiality on deck, planting, steel.
- Towers present and looming — the antagonist has to be in frame. `dom_occ_year` here is
  post-2009, so the enclosure in shot *is* the tower boom; that is worth a clause.
- Winter sun raking under the canopy edge, from `key_light`.

**Done when:** it carries scale, site context and a human figure — the three things the
portfolio standard demands and this project has never had.

---

## ☐ Stage 3b · Image B — the open contrast

The other half of the argument: **where the towers barely reach, the deck keeps its sky and
the canopy holds near its minimum.** The design rule *"river-view segments aren't shaded"*
shown rather than asserted.

**Station · camera · numbers:** `cameras.json` → `stations[1]` (`B_open_contrast`). Camera
`camera.position` → `camera.target`, along the deck so the open sky above the flat rib is the
subject; swing toward `camera.aperture_heading_xz` if the river itself must be in shot.

**Why this station:** `max svf_deck subject to svf_deck ≥ OPEN_SVF_MIN AND river_view AND
nearest_wall_m ≤ CONTEXT_MAX_WALL_M`. **The context gate is a hard constraint on the
selection pool, not a post-hoc override.**

### The maximum-openness station was passed over, deliberately

`cameras.json` → `stations[1].passed_over` records it with its numbers. The most open station
on the line sits at the **north rail-yard end**, and it was rejected for two reasons, both of
which are true properties of that station rather than data faults:

1. **No built context in frame.** Its `nearest_wall_m` is an order of magnitude beyond every
   other candidate. An open-contrast image has to show the deck open *within the city*; a
   station with no city in sight illustrates nothing about a corridor.
2. **Its recapture figure could not have been printed at all.** Its `deficit_svf` is exactly
   zero (`passed_over.deficit_svf`), so its stored recapture
   (`passed_over.recaptured_winter_sun_frac_stored`) is a full fraction *of nothing* —
   `numbers` would have carried it as `null` with `quotable: false`, and the plate would have
   had no performance number to print.

Runners-up from the same context-gated pool are in `stations[1].alternates`. Substituting one
means **re-running `pick_cameras.py` with the station changed, never retyping numbers.**

**Caption block — generate, do not transcribe:**

| Caption line | Source key |
|---|---|
| station | `stations[1].s_m` |
| sky view today (`svf_deck`) | `stations[1].numbers.svf_deck.value` |
| stolen sky (`deficit_svf`) | `stations[1].numbers.deficit_svf.value` |
| winter sun recaptured | `stations[1].numbers.recaptured_winter_sun_frac.value` |
| rib height / reach | `stations[1].numbers.rib_height_m.value` · `.reach_m.value` |
| enclosure angle | `stations[1].numbers.enclosure_deg.value` |
| nearest wall | `stations[1].numbers.nearest_wall_m.value` |

⚠️ **Read the recapture figure against the deficit on the same plate.** This station lost only
a sliver of its sky, so a high recapture fraction here describes recovering a trivial loss,
**not the canopy performing**. The subject of this image is the *flat rib over an open sky* —
the generator standing down where the deck can still see out. `--captions` prints that warning
with the block.

⚠️ **The suppression rule still governs.** Where `deficit_svf == 0`, `numbers` carries
recapture as `null` with `quotable: false` and a reason, and `--captions` prints
*"DO NOT PRINT ON THIS PLATE"* instead of a value and withholds the caveats. Null, never 0,
never 100%.

**Done when:** the flat rib, the open sky and the city are legible in one frame, and the
caption can say the canopy is minimal here *by rule*, not by omission.

---

## ☐ Stage 4 · Image E — the specimen array *(population plate — no single station)*

Continuous differentiation meeting a buildable catalogue.

- The standard rib types (`ribsched_n_types`) from `data/rib_schedule.json` drawn as a
  taxonomic grid, consistent scale and orientation, ordered by height, each labelled with its
  count.
- Beside it, the full population (`ribsched_n_ribs`) ordered along `s`, so the gradient is
  visible as a population rather than as a claim.
- Call out the rationalisation: `ribsched_n_types` standard types + `ribsched_n_bespoke`
  bespoke, `ribsched_n_standardized` standardized = `ribsched_coverage_pct` coverage.

**Caption block — generate, do not transcribe.** This is a *population* plate, so its numbers
resolve through `houdini/sources.json` rather than `cameras.json`, and `--captions` prints it
with the station plates:

```powershell
python houdini/pick_cameras.py --captions   # → plate E_specimen_array
```

| Caption line | Source key |
|---|---|
| ribs in the population | `ribsched_n_ribs` |
| standard types / standardized / bespoke | `ribsched_n_types` · `ribsched_n_standardized` · `ribsched_n_bespoke` |
| standardization coverage | `ribsched_coverage_pct` |
| T01 count / share / height | `ribsched_t01_count` · `ribsched_t01_share_pct` · `ribsched_t01_height_m` |
| T10 height / reach (family maximum) | `ribsched_t10_height_m` · `ribsched_t10_reach_m` |
| total member length | `ribsched_member_length_m` |
| sized steel, field-driven | `steel_sized_field_t` |
| sized steel, uniform 7 m | `steel_sized_uniform_a_t` |
| steel ratio | `steel_ratio_sized` *(derived at emit time from the two above — not stored, so it cannot go stale independently of them)* |
| ribs needing the heavy section | `steel_heavy_section_field` · `steel_heavy_section_uniform_a` |
| install deviation, mean / max | `ribsched_tol_mean_mm` · `ribsched_tol_max_mm` |

Each key names its `(file, path)` in `sources.json`. **The tonnage pair is exactly why this
indirection exists** — it changed on 2026-08-09 when the structural sizing replaced the
assumed 24 kg/m density, and a transcribed copy in this document would have survived the
change silently.

### Three things this image must say out loud

1. **The canopy is minimal over most of the line.** T01 — effectively flat — dominates the
   family (`ribsched_t01_count` of `ribsched_n_ribs`). Draw the array to *show* that: T01 at
   its true count, not one token per type at equal weight, or the plate misrepresents the
   population. This is the generator working correctly — stations at `svf_deck` ≥
   `envelope_open_svf` are held at minimum so river-view segments aren't shaded — and it is
   the same argument as "no vertical exaggeration." Said first it is honesty; discovered
   later it looks like concealment. The family does span real range, up to
   `ribsched_t10_height_m` / `ribsched_t10_reach_m`.
2. **Caption the sized tonnage, not an assumed one.** The steel figures come from the
   direct-stiffness pass. ⚠️ The retired assumed-density pair **must not appear on any
   plate**; the `tonnage_is_sized_not_assumed` caveat is emitted automatically with these
   keys and says so.
3. **"Tolerance" is geometric** — the `tolerance_is_geometric` caveat travels with
   `ribsched_tol_*` and states it. Wrong word, wrong room, at a structures firm.

⚠️ **This plate carries the material headline, so it carries the non-significance flag.** The
`recapture_nonsignificance` caveat is attached to every tonnage key and is emitted with them:
the steel ratio is the axis that separates *precisely because* the recapture figures are the
axis that does not. Do not print the ratio without it.

The standardization curve is the honest defence of a chosen `n_types` — nearly flat past ten.
Plot it small beside the array; "chosen at the knee, and here is the curve" beats "we used
ten."

**Done when:** a fabricator can see the rationalisation, an engineer can see what the
tolerance actually measures, and T01's share is visible without reading a caption.

---

## ☐ Stage 5 · Image D — the corridor

The correlation made visible instead of asserted — **and, since the headline changed, the
material-variation image.** See *Render direction* below: this is now the argument plate.

- Longitudinal axo or high oblique along the whole line.
- Rib height mapped to colour across the **full** range `envelope_rib_min_m` →
  `envelope_rib_max_m`, so the canopy visibly grows where the enclosure worsens. ⚠️ Ramp the
  colour over that whole range, not between two poles: `envelope_reach_nonzero_count` of
  `envelope_stations` stations now carry a reach, so a two-tone treatment would flatten a
  continuous gradient into a contrast that no longer exists in the data.
- Context shaded on a **continuous sky-share ramp** — `sky_share_pct` from
  `data/attribution.json`, joined by BIN, normalised linearly on the maximum. One material
  driven by a per-object attribute; **never a hand-picked selection.** Buildings absent from
  the attribution set take a neutral material, because *not measured* is not *measured as
  zero*. Build per `blender/BLENDER_BUILD_STEPS.md` §6.2.
  ⚠️ The ramp will leave most of the site cold — the great majority of ranked buildings take a
  negligible share each, and a few dozen carry the enclosure. **That is the measurement, not a
  rendering failure.** Do not apply a non-linear ramp to spread the low end without deciding it
  explicitly and saying so in the caption; it would overstate small contributors.
  ⚠️ **This replaces the post-2009 tint**, which rendered the two largest culprits neutral
  because both were completed in 2006. The date remains a caption fact and an object tag, not a
  colour.
- The deepest cores left legible rather than hidden. Mark `stations[2].s_m`, because Image C
  is that station's section and the two plates should read as the same place seen twice.

**Caption block — generate, do not transcribe.** Population plate; resolves through
`houdini/sources.json` as plate `D_corridor`:

| Caption line | Source key |
|---|---|
| deck stations | `envelope_stations` |
| rib height vs stolen-sky deficit | `envelope_corr_r` |
| rib minimum (generator floor) | `envelope_rib_min_m` |
| family maximum height | `ribsched_t10_height_m` |
| openness gate | `envelope_open_svf` |
| median utilization, field-driven / uniform 7 m | `struct_median_util_field` · `struct_median_util_uniform_a` |

⚠️ The `r_is_self_check` caveat travels with the correlation: it is the generator's own check
that the form answers the measured field rather than the eye. **It is not a performance
result** and must not be presented as one.

**Done when:** a reader who never reads the caption can see that the form tracks the loss —
and that it does so by *varying material*, which is the claim.

---

## ☐ Stage 5b · Image C — the section through the worst core

The canopy at its most ambitious, failing. This is the plate that makes
`THE_ANSWERING_LINE.md`'s stated limit visible: *the worst cores are a massing problem a
canopy can't fix.*

**Station · camera · numbers:** `cameras.json` → `stations[2]` (`C_section_worst_core`).
**Orthographic**, `camera.position` → `camera.target`, set out perpendicular to the deck
tangent (`camera.section_normal_xz`, verified exactly perpendicular) and level at mid-rib
height so the view is horizontal and the canyon walls stay parallel. It stands on the side the
rib reaches away from, so the cantilever reads broadside instead of foreshortened.

⚠️ **Orthographic, not perspective.** A section that converges is not a section, and the
caption calls it one.

**Why this station:** `max deficit_svf` over all 232 stations.

⚠️ **The trap this rule avoids, and it is not hypothetical.** "Worst deep-canyon" is defined
on **stolen sky**, not on minimum `svf_deck`. The lowest-`svf_deck` stations on the line all
have `deficit_svf = 0.0` — they were *always* enclosed, lost nothing to the tower boom, and
carry ribs at the generator minimum. A section drawn there would illustrate enclosure this
project never claimed to have found the cause of. The rule and the rejected stations are in
`stations[2].selection_trap_avoided`.

**Caption block — generate, do not transcribe:**

| Caption line | Source key |
|---|---|
| station | `stations[2].s_m` |
| stolen sky (`deficit_svf`) | `stations[2].numbers.deficit_svf.value` |
| sky view today (`svf_deck`) | `stations[2].numbers.svf_deck.value` |
| winter sun recaptured | `stations[2].numbers.recaptured_winter_sun_frac.value` |
| rib height / reach | `stations[2].numbers.rib_height_m.value` · `.reach_m.value` — the tallest rib in the family |
| enclosure angle | `stations[2].numbers.enclosure_deg.value` |
| nearest wall | `stations[2].numbers.nearest_wall_m.value` |
| dominant occluder built | `stations[2].numbers.dom_occ_year.value` |

**Must carry:** the canyon walls at true height · a human figure on the deck for scale · the
rib reaching and still not clearing the wall.

⚠️ **Print the recaptured figure rather than omitting it.** It is the lowest on the line, and
hiding it would be the one dishonest move available on this plate.

**Done when:** the image says *"this one we could not fix"* without a caption, and the
recapture figure is printed rather than hidden.

---

## ☐ Stage 6 · Post-production and composition

- **One visual language for the page, and it is the Streetscape Biophilia one** — paper
  ground, exploded axo, restrained type.
- **One palette.** The board plan's colourblind-validated set (`#2a78d6`, `#9ec5f4`,
  `#008300`, `#e87ba4`, ink `#0b0b0b`, surface `#fcfcfb`).
- **Pages are paper; images are dark plates.** The distinction that matters: a *page* must not
  be all-dark, but a dark *plate* on a paper page is the system working. So `board1`/`board2`
  keep their dark ground — only their accent hues migrate to the palette above.
  `boards/README.md` § Conventions carries the decision, the proposed role mapping, and the
  15-value migration surface. **That migration is decided but not yet applied**, so the boards
  on disk still show terracotta/teal; don't compose a page assuming otherwise.
- Rebuilding the boards is **out of scope** (`../IMPLEMENTATION_PLAN.md`). Re-theming their
  accents is not the same thing as rebuilding them — do not let it become a re-layout.
- The ControlNet raw → mask → depth triptych appears as **method evidence only**, at process-
  thumbnail size. The canopy is the design proposal; the biophilic redesign is not.

---

## Optional, high value · on-deck photography

`data/ondeck/` holds a README and `manifest.csv` and **no photographs**, so
`validate_ondeck.py --ingest` has never had input. An afternoon on the deck returns two
things from one trip:

1. Real input closing the on-deck validation loop (SegFormer sky fraction vs `svf_deck`).
2. Real photographic base plates to composite the canopy into.

A canopy comped into your own photograph of the actual site outperforms a fully synthetic
render, and it is the cheapest materiality you will ever buy.

---

## Numbers this project may quote

All sourced in `Projects/README.md` §5 with a `sources.json` key, so `build.py` will typeset
them. **Never quote a key without reopening its source file** — both number errors caught
on 2026-08-03 were keys cited from memory.

**Diagnosis**

| Key | Value |
|---|---|
| `highline_svf` | SVF 0.808 vs The 606's 0.978 |
| `highline_enclosure_deg` | enclosure angle 17.8° vs 3.1° · 21% of deck enclosed vs 1% |
| `highline_neighbour` | tallest neighbour, mean 64.2 m vs 22.6 m |
| `svf_validation` | r 0.956 vs Ladybug, RMSE 0.132, n = 232 |
| `sun_validation` | winter sunlit hours r 0.993 |

**The answer, and the build** — resolved, not listed

These used to be a value table here. **They are now keys in `houdini/sources.json`**, which
holds the `(file, path)` for each, and they print with their caveats via:

```powershell
python houdini/pick_cameras.py --captions
```

| Group | Keys |
|---|---|
| corridor / form | `envelope_stations` · `envelope_corr_r` · `envelope_rib_min_m` · `envelope_open_svf` |
| rationalisation | `ribsched_n_ribs` · `ribsched_n_types` · `ribsched_n_standardized` · `ribsched_n_bespoke` · `ribsched_coverage_pct` |
| the family | `ribsched_t01_count` · `ribsched_t01_share_pct` · `ribsched_t01_height_m` · `ribsched_t10_height_m` · `ribsched_t10_reach_m` |
| material | `ribsched_member_length_m` · `steel_sized_field_t` · `steel_sized_uniform_a_t` · `steel_ratio_sized` · `steel_heavy_section_field` · `steel_heavy_section_uniform_a` |
| structure | `struct_median_util_field` · `struct_median_util_uniform_a` |
| deviations | `ribsched_tol_mean_mm` · `ribsched_tol_max_mm` |

Caveats live in `sources.json` → `caveats` and are attached per key, so
`tonnage_is_sized_not_assumed`, `recapture_nonsignificance`, `t01_dominance`,
`n_types_chosen`, `tolerance_is_geometric` and `r_is_self_check` are emitted automatically
with whichever numbers a plate actually prints. **Never retype one.**

**The recapture figures are deliberately NOT keyed here.** They belong to a station
(`cameras.json` → `stations[].numbers.recaptured_winter_sun_frac`) or to the portfolio-level
row in `Projects/README.md` §5, which remains the authority for the three-canopy comparison,
its non-significance flag and the instrument names. A plate quoting a recapture figure takes
it from the station block, with the three travelling caveats `--captions` emits.

**Diagnosis figures above are not yet keyed** — they come from `comparison.json`,
`svf_calibration.json` and `lbt_validation.json` and still resolve through §5 by hand. Adding
them to `sources.json` is the obvious next extension and would close the last transcription
surface in this document.

**Still unsourced — do not typeset:**

- The **post-2009 attribution share**. It appears on `board1.png` and in prose, but has no §5
  row. **Verified 2026-08-09 to exist** at `data/attribution.json` →
  `metadata.post2009_sky_share_pct`, with a companion `metadata.post2009_winter_deckhours`
  (board1 rounds the latter). Add both as a §5 row + a `sources.json` key before either
  reaches a page.
- Rib **height and reach ranges as a continuous claim.** The per-type endpoints are keyed
  (`ribsched_t01_height_m`, `ribsched_t10_height_m`, `ribsched_t10_reach_m`); a range claim
  spanning the whole population needs its own key off `envelope.json`.

## Size budget

`portfolio_master.pdf` is **11.4 MB of a 12 MB ceiling** before any render here exists.
Plan compression into Stage 6 rather than meeting it at the end.
