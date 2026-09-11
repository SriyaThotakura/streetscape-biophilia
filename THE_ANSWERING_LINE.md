# The Answering Line — the design response

The rest of the suite **diagnoses** the enclosure: it measures, per deck station `s`,
how much sky and winter sun the towers took. This engine **answers** it. It generates a
light-recapturing canopy directly from that measured field — and then re-casts to check
how much of the loss the form actually recovers.

This supersedes `Option1/2/3_*.md`. Those briefs proposed generative geometry (DLA
aggregation, Physarum networks, iridescent ribbons) extracted from an abstract seed in a
black void — the "motion-graphics" trap. This one keeps the same generative instinct
(gradient → curvature → ridge → ribbon) but drives it from the **real enclosure field the
study already computed**, on the real site. The form is not decorative: every rib's height,
reach, and heading is a function of `hl_core` ray-casts against the actual NYC massing.

## Why this is the piece the study was missing

The engine suite is a brilliant **diagnosis with no prescription**. For an urban-analysis
reviewer that's complete; for a **design-technology** portfolio (Gensler dxLab weights
design + visuals) a diagnosis-only project reads as analytics, not architecture. This closes
the arc: *measure the wound → design the response → validate the response with an **independent**
instrument.* The loop was closed with the same ray-caster that drove the form, and then
**re-opened and re-measured with Ladybug** — which is where the most interesting result came from.

## The method (`scripts/build_envelope.py`)

Imports `hl_core`, keys off arc-length `s`, writes provenance-stamped JSON — same discipline
as every other engine. For each of the 232 deck stations:

1. **Read the loss.** `deficit = svf_prepark − svf_deck` (stolen sky) from
   `highline_viewshed.json`; winter-sun hours pre/post from `highline_solar.json`.
2. **Find the surviving aperture.** Recompute the full azimuthal horizon at the station via
   `edges_for` + `ray_uv`, then weight each direction by **where the sun actually is**
   (`sun_path` across winter/equinox/summer). The result is a *reach vector*: heading =
   where light still comes from, magnitude = how directional the opening is.
3. **Generate the rib.** A canopy cross-section that cantilevers toward the aperture —
   **taller where the deficit is worse, flatter where the deck still sees sky**
   (`svf_deck ≥ 0.75` stays minimal, so river-view segments aren't shaded). Height,
   reach, and heading are all functions of the measured field.
4. **Close the loop.** Re-cast from each rib's reach tip through the winter sun path with the
   **same ray primitive** that drove the form, and report the fraction of winter-sun
   timesteps it recovers.

Lofting consecutive ribs along `s` gives the continuous envelope.

## Honest results (deterministic; re-run to reproduce)

- **rib height vs deficit  r = +0.95** — the canopy is tallest exactly where the sky loss is
  worst. That correlation is the self-check that the form answers the field, not the eye.
- **All three canopies, one instrument** (Ladybug `lb_sunpath`, **159** enclosed stations,
  `scripts/validate_envelope.py` → `data/envelope_validation.json`): **field-driven 17.39% ·
  uniform 7 m (a) 18.95% · equal-material (b) 16.21%.** Confirmed on the second sun model
  (17.66% / 19.47% / 16.52%). The hand-rolled figures are 18.56% / 20.73% / 17.27%.
- **Both comparisons ARE significant at n = 159, and they point opposite ways.** Field-vs-(b) is
  **+1.18 pts, 95% CI [+0.26, +2.30]** — the shaping genuinely beats the same steel spread flat.
  Field-vs-(a) is **−1.56 pts, 95% CI [−3.08, −0.03]** — the uniform 7 m canopy genuinely recovers
  more, because it is 2.27× the steel. **Neither sentence travels without the other.**
  ⚠️ The significance arrived with the sample (n 56 → 159 after the footprint re-fetch), not with a
  better design — the effect sizes *shrank* — and it does not survive a 2005 pre-park baseline. Say
  so when you quote it.
- **What does separate them is steel — and that is the finding.** The field-driven canopy performs
  significantly better than equal material on **44% of what a uniform 7 m canopy needs: 83.2 t against
  188.6 t** (`data/structure.json`, `data/structure_counterfactual.json`; same solver, same combos,
  same section ladder). **The form does not buy sun. It buys material.**
- **Three independent layers say it.** The enclosure field (rib height vs deficit **r = +0.949**),
  the fabrication kit (**114 of 232 ribs bespoke**, 50.9% standardized), and the structural pass
  (**median utilization 0.36, 40 ribs needing the heavy section against (a)'s 199**) share no code
  path and all report the same thing: the canyon is irregular, the form tracks it, and the material
  concentrates where it must.
- **The instrument was biased toward the form it generated, and the bias model then predicted a
  configuration it had never seen.** Against Ladybug the hand-rolled caster's per-station error is
  **RMSE 0.056 on the field-driven canopy, 0.051 on the flat control, and 0.073 on the tallest
  canopy (a)** — it is systematically more generous to taller, further-reaching geometry. A
  falsifiable prediction registered in `validate_envelope.py` **before (a) was measured** said (a)
  must therefore deflate most; it did, monotonically, on both sun models: **(a) −1.78 · field-driven
  −1.17 · control (b) −1.06 pts.** Out-of-sample confirmation, not curve-fitting — and a real test,
  because under a 2005 pre-park baseline the same prediction **failed**.
  ⚠️ This also means the linear `svf_calibration` (`a·svf_mine + b`) **cannot be extended to the
  design layer** — the error is shape-dependent, scaling with rib height and reach, not a constant
  offset a two-parameter global fit can absorb.
- **⚠️ The sensor is the structure, not the visitor.** Recapture is measured at the **rib apex**,
  which stands **1.20–7.23 m above the deck** (a flat 7.00 m for (a)). Every figure here describes
  winter sun reaching the *canopy*, not winter sun reaching a *person standing under it*.
  **Deck-level recapture is unmeasured** and is the obvious next study. It likely cuts against the
  tall canopy: an apex reaches light a deck-level sensor would not see, so (a) would probably fare
  worse under that measurement than it does here.
  **The recapture measurement assumes nothing about how light at the rib apex reaches the deck.** An
  opaque canopy would reduce deck-level direct sun; a reflective or redirecting surface would not.
  The study measures sun arriving at the structure and **does not model delivery to the deck** — the
  material and section of the canopy are unspecified, and a deck-level study would need both.
- **The deepest cores recover ~0%** — a 7 m canopy cannot reach winter sun at the bottom of
  a 24 m+ canyon (see the field-plot scatter). Stated plainly rather than hidden: the canopy
  answers the mid-range enclosure; the worst cores are a massing problem a canopy can't fix.
  **Under Ladybug that is 53 of the 159 enclosed stations recovering nothing under either canopy**,
  which is why the 159-station mean sits at 17.4%: recovery concentrates in the other 106 and
  divided across a denominator half of which is inert by design. **159 stays the denominator** — the
  decomposition is the honest way to explain the figure, not a re-based one.

No vertical exaggeration anywhere. The canopy is small because the towers are the problem —
that honesty is the argument.

## Outputs

| File | What |
|---|---|
| `data/envelope.json` | per-station ribs (3-D polylines), drivers (deficit, aperture, reach), recaptured-sun readback, `_meta` provenance |
| `exports/envelope_section.png` | **architectural hero** — section through a representative enclosed station: real canyon walls from `section.json`, winter-noon sun, the rib reaching for the aperture |
| `exports/envelope_field.png` | **technical proof** — plan (deficit + aperture arrows), longitudinal (height/reach vs the deficit, r=+0.95), loop-closed recovery scatter |
| `exports/envelope_hero.png` | 3-D system axo — the lofted canopy varying along the corridor, threading the tower canyon |
| **`envelope.html`** | **interactive WebGL hero** — the canopy lofted over the real NYC massing (Three.js 0.164.1), post-2009 culprit towers distinguished, sun-shadowed, deficit-graded. Controls: season toggle (winter/equinox/summer sun), frame-enclosure, canopy on/off, and a **deck-eye walk** — first-person camera flown along the centerline at eye level *under* the canopy, with a scrubber + play/pause. |
| **`exports/rib_schedule.png`** | **fabrication schedule** — the 10 standard rib types dimensioned (and the 114 bespoke), "which type goes where" along the deck, and the rationalization-coverage curve |
| **`exports/rib_schedule.csv`** | fabricator cut list — one row per rib: type, standard/bespoke, member length, 4 segment cuts, 3 bend angles, install heading, tolerance |
| `data/rib_schedule.json` | typed kit + per-station assignment + tradeoff + provenance |
| **`exports/structure.png`** | **structural utilization pass** — utilization along the deck, the worst-rib frame + bending-moment diagram, and utilization-vs-reach |
| `data/structure.json` | per-rib utilization, governing combo, base moment, sized section + solver-validation report |
| `data/structure_counterfactual.json` | the same pass over the uniform 7 m counterfactual — the sized 188.6 t that the 2.27× ratio rests on |
| `data/envelope_validation.json` | **W3.1 independent Ladybug recheck** — both configurations re-measured, paired delta + bootstrap, and the instrument-bias finding |

## Fabrication — the buildable kit (`scripts/build_rib_schedule.py`)

A performance-driven surface is only a *design* until it can be built. This engine
rationalizes the 232 unique ribs into a standard kit and quantifies the tradeoff — the
Thornton Tomasetti "is-it-buildable" layer.

Two fabrication insights make it honest:
1. **Heading is an install rotation, not a fabrication variable.** A rib's fabricated member
   is its segment lengths + bend angles (heading-invariant); two ribs of equal height/reach
   at different aperture headings are the *same part* installed rotated. So ribs cluster on
   intrinsic geometry (height, reach) only — measured on the true 3-D member, not a
   projection (an earlier projected-profile metric wrongly read mirrored parts as 6 m apart).
2. **Standardize the common, bespoke the exceptional.** KMeans → 10 standard types. A member
   within **±200 mm** of its type's standard cut is standardized (slotted connection absorbs
   it); beyond that it's flagged bespoke.

**Result (deterministic, seed 42):** 232 ribs → **10 standard types + 114 bespoke**;
**50.9% standardized within ±200 mm**; the dominant type covers only **31.5%** of the deck; mean
install deviation **425.7 mm**; **2,869.1 m of member, which sizes to 83.2 t**
(`data/structure.json`, 192 × CHS 168x6.3 + 40 × CHS 219x8). **One tonnage basis governs this
document and it is the sized one** — the older assumed-linear-density figures are retired.

⚠️ **Read the standardization number as a finding about the site, not a failure of the kit.** Before
the 2026-08-15 footprint re-fetch this read 29 bespoke at 87.5% coverage — measuring a canyon that
was 81.6% absent. The real West Chelsea canyon (2,083 buildings, walls from 3.5 m to 386 m) is
*genuinely irregular*, and a form that answers it faithfully **cannot be built from ten parts**.
The honest version of the fabrication story is that rationalization has limits and this site exceeds
them; that is a more useful sentence to a fabricator than a high coverage number would have been.
The
coverage curve still shows diminishing returns past ten types, which is what justifies the type
count — but the curve now tops out far lower, and that is the point: **the 114 bespoke ribs are the
deep-canyon signature pieces**, and there are simply a lot of them, because the canyon is not
regular.

```powershell
python scripts/build_rib_schedule.py [--types 10]
```

## Structure — the utilization pass (`scripts/build_structure.py`)

Is the kit strong enough? This engine answers with a **from-scratch 2-D frame direct-
stiffness solver** (no Grasshopper/Karamba binary — the solver *is* the tool), analysing
every rib under LRFD combinations.

- **The solver is validated every run** against closed-form cantilever results (tip
  deflection and base moment, UDL) — errors ~1e-16; the build aborts if it drifts. (It
  already caught one real sign bug in the equivalent-nodal-load convention.)
- Each rib is analysed in its **own best-fit plane**, so the aperture reach becomes true
  in-plane bending (a cross-deck plane would miss it). Both rails are moment-fixed to the
  deck — the ribs are efficient **leaning arches**, not cantilevers.
- Loads: 1.2D + 1.6S (NYC snow 1.2 kPa on 8 m tributary) and 0.9D + 1.0W (net uplift),
  S355, φ = 0.9. Utilization = N/φNc + M/φMc.

**Result:** median utilization is **0.36**, rising to **0.82** where the ribs reach furthest into
the canyon — the material is worked hardest exactly where the design reaches, which is efficient,
not marginal. All ribs are within capacity; a sized kit (**192 × CHS 168x6.3, 40 × CHS 219x8,
83.2 t**) keeps every rib ≤ 1.0. The structural
cost, the fabrication bespoke-flags, and the enclosure-field worst cases all point at the
same handful of deep-canyon ribs.

**The same pass, run on the naive counterfactual, is what earns the project its headline.**
`--source counterfactual_a` → `data/structure_counterfactual.json` sizes the uniform 7 m canopy on
the identical solver, combos and section ladder: **188.6 t**, because **199 of its 232 ribs (86%)
need CHS 219x8 against 40 of ours (17%)**. **2.27× the steel — for 1.6 more points of winter sun.** Because both tonnages come from one sizing run,
that ratio is like-for-like in a way the earlier assumed-density comparison was not, and because it
contains no instrument at all, it is the one number here that no re-measurement can move.

**The utilization spread is the structural half of the same argument.** This canopy's median
utilization is **0.36** with a long tail to 0.82 — hard-worked in the deep-canyon ribs,
idling elsewhere. (a)'s is **0.53 with a tight spread (sd 0.053)** — uniformly mid-worked, because a
uniform form has no cheap stations. The fabrication kit says it a third way: **114 of 232 ribs are
bespoke**, because the field they answer is irregular. Field, fabrication and structure share no code path and agree.

**Limitation, stated specifically rather than generically.** This is in-plane frame analysis;
connection detailing is not claimed. But the sharper limitation is in the load model: **factored
snow and factored wind scale on the same horizontal projection and the same plane-tilt factor**, and
factored snow (1.6 × 1.2 = 1.92 kPa, *added* to dead load) is more than twice factored uplift
(1.0 × 0.9 = 0.9 kPa, *opposed* by dead load). So the combo ratio is near-constant by construction —
**~2.3–2.5 across the field-driven canopy, 2.40–2.43 across the uniform one** — and **1.2D + 1.6S
governs all 232 ribs in both. Uplift cannot govern at any geometry under this model.** A 5.5 m
cantilever with a 7 m rib is exactly where a real uplift case should bite, and **this engine cannot
surface it**: that would need a wind model with pressure coefficients and out-of-plane action, which
it does not have. Read the snow-governed result as a property of the load model, not as a finding
that wind is unimportant here.

```powershell
python scripts/build_structure.py
```

## Run

```powershell
python scripts/build_envelope.py            # json + 3 figures
python scripts/build_envelope.py --no-fig   # json only

python -m http.server 8000                  # then open http://localhost:8000/envelope.html
```

`envelope.html` fetches `data/envelope.json` + `data/highline_footprints.json` (same raw
local-meter frame — no rescaling), so it must be **served over http**, like `index.html`.
Verify a headless render any time with `python scripts/shoot_envelope.py` (Playwright →
`exports/envelope_web.png`, prints any console errors).

## Where it could go next

- **Out-of-plane + connections** — the structural pass is in-plane; a 3-D frame with
  out-of-plane wind and rib-to-deck connection design would complete the engineering.
- **Structured captures** — `scripts/shoot_envelope.py <url> <out> [orbit|walk] [scrub]`
  headlessly renders any view (orbit hero, or the walk at any station) and reports console
  errors; drive it to mint board-ready stills from the WebGL scene.
