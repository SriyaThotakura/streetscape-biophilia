# The Self-Enclosing Line

**Did the High Line’s success build the towers that now shadow it?**

Sriya Thotakura · 2026 · Research · [case study on the portfolio site](https://sriyathotakura.com/#streetscape-biophilia)

"The Self-Enclosing Line" — a computational study of whether the High Line's own success built the towers that now enclose and shadow it.

## The problem

That the High Line is enclosed is easy to assert and hard to attribute. The usual move is qualitative — read the park as a growth machine and describe what followed — which cannot say how much sky was lost, to which buildings, or whether the enclosure is a property of the typology or of one rezoning. Without a counterfactual the claim stays arguable in both directions, and without an instrument the counterfactual cannot be built at all.

## How it works

Every later number is a ray cast against building footprints, so the corridor is only ever as complete as one fetch — which is why that fetch now aborts on a completeness mismatch.

A 2.5-D ray-segment isovist at each deck station answers how much sky is left and how many hours of sun reach it, and the same geometry pipeline runs the counterfactual: the towers built after the 2005 rezoning, removed. A second park the tower boom never found is measured as a control. The stolen sky is then apportioned building by building, which turns a condition into an attribution a reader can argue with.

An independent Ladybug recompute is written alongside the hand-rolled engines, so the geometry is checked by something that did not produce it — and the two are published unadjusted rather than calibrated toward each other.

The prescription half inverts the same field. Each station reads the sky it lost, recomputes which direction light still arrives from, and grows a rib that cantilevers toward it — tall where the loss is worst, flat where the deck still sees sky. Those one-off ribs are then clustered into a buildable family and written out as a real per-rib cut list, and the whole canopy is sized under a direct-stiffness pass against a uniform-height counterfactual.

## Stack

Python, Ladybug Tools, Socrata API, Three.js / WebGL, SegFormer, Playwright

## Measured

The enclosure figures are unambiguous and the design figures point two ways at once, which is why both sentences always travel together. The field-driven canopy beats the same steel spread flat, and it loses to a uniform canopy that costs 2.27× the material — so the form buys material, not sun. Two independent sun models and a hand-rolled third agree on the direction. The instrument favoured the form it generated, and that bias was predicted out-of-sample: a falsifiable claim registered in the validation script before the tall counterfactual was ever measured held monotonically on both sun models. That is a result rather than a caveat. Every recapture number is measured at the rib apex, not at deck level.

| Claim | Value | Source |
|---|---|---|
| High Line enclosure | SVF 0.424 vs The 606's 0.978 — a 0.554 gap. Was 0.808 before the 2026-08-15 re-fetch recovered 1,907 missing buildings | `5.CV_Highline/data/comparison.json` |
| High Line enclosure angle | 49.9° vs The 606's 3.1°; 85% of deck enclosed vs 1% | `5.CV_Highline/data/comparison.json` |
| Tallest neighbour, mean | 212.8 m vs The 606's 22.6 m | `5.CV_Highline/data/comparison.json` |
| SVF method validation — ⚠️ publish BOTH, unadjusted | Isovist 0.424 vs Ladybug 0.269; r 0.871, RMSE 0.201; winter sun r 0.927. The divergence tracks occluder density (r +0.384 with building count), NOT height (r −0.332 with the tallest occluder) — a model-order limit: one horizon angle per azimuth cannot represent a punctured hemisphere. The linear calibration is RETIRED (U-shaped bias, 5× heteroscedasticity, 16% of predictions outside [0,1], quadratic gains 4.7%). Neither figure is adjusted toward the other | `5.CV_Highline/data/lbt_validation.json; retirement evidence in svf_calibration.json` |
| Answering Line — deck stations | 232 | `5.CV_Highline/data/envelope.json` |
| Answering Line — winter sun recaptured, all three canopies under one instrument | Under Ladybug lb_sunpath at the 159 enclosed stations: field-driven 17.39% · uniform 7 m (a) 18.95% · equal-material (b) 16.21%. Second sun model hl_core_vectors: 17.66% / 19.47% / 16.52%. Hand-rolled hl_core: 18.56% / 20.73% / 17.27%. Always name the instrument; never mix two in one comparison. The sun models are never averaged or blended | `5.CV_Highline/data/envelope_validation.json (results.lb_sunpath.*, results.hl_core_vectors.*, handrolled.*)` |
| Answering Line — both recapture comparisons ARE significant, and point opposite ways | At n = 159: field-vs-(b) +1.18 pts, 95% CI [+0.26, +2.30], P(δ ≤ 0) = 0.0038 — the shaping beats the same steel spread flat. Field-vs-(a) −1.56 pts, 95% CI [−3.08, −0.03] — the uniform 7 m canopy recovers more, on 2.27× the steel. Confirmed on hl_core_vectors (+1.14 [+0.24, +2.24]; −1.82 [−3.35, −0.27]) and hand-rolled (+1.29 [+0.27, +2.49]). 20,000 paired resamples, default_rng(42). Neither sentence travels without the other. Significance arrived with the sample (n 56 → 159 after the re-fetch), not a better design — effect sizes shrank — and it does not survive a 2005 pre-park baseline (+0.90 [−0.23, +2.29]) | `5.CV_Highline/data/envelope_validation.json (results.*.bootstrap, .bootstrap_field_vs_a)` |
| Answering Line — the headline: the form buys material, not sun | The field-driven canopy recovers significantly more than equal material (+1.18 pts) on 44% of what a uniform 7 m canopy needs — 83.2 t against 188.6 t. Spend 2.27× the steel and you buy 1.6 more points of sun. Three layers with no shared code path agree: enclosure field (r 0.949), fabrication (114 of 232 ribs bespoke), structure (median utilization 0.36, 40 heavy ribs vs (a)'s 199) | `5.CV_Highline/data/structure.json + structure_counterfactual.json; envelope_validation.json; envelope.json; rib_schedule.json` |
| Answering Line — the instrument favoured the form it generated, and the bias model predicted out-of-sample | Hand-rolled-vs-Ladybug per-station error rises with height and reach: RMSE 0.091 flat control (b) · 0.130 field-driven · 0.165 uniform 7 m (a). A falsifiable prediction registered in validate_envelope.py before (a) was ever measured said the tallest canopy must deflate most; it held monotonically on both sun models — (a) −4.91 · field-driven −3.98 · (b) −2.69 pts. Out-of-sample confirmation, not curve-fitting. This is a result, not a caveat — lead with it. It also makes the linear svf_calibration (a·svf_mine + b) inapplicable to the design layer: the error is shape-dependent, not a constant offset | `5.CV_Highline/data/envelope_validation.json (_meta.prediction_configuration_a, results.*.field_driven.vs_handrolled_rmse, .uniform_equal_max_height_a.*, .uniform_equal_member_b.*)` |
| Answering Line — ⚠️ the sensor is the structure, not the visitor | Recapture is measured at the rib apex, standing 1.20–7.04 m above the deck for the field-driven canopy and a flat 7.00 m for (a). Every recapture figure describes sun reaching the canopy, not sun reaching a person under it. Deck-level recapture is unmeasured, and is named as the obvious next study. State this whenever a recapture number appears | `5.CV_Highline/data/envelope.json (points[].rib_height_m); envelope_validation.json (_meta.mirrored_from_build_envelope.sensor)` |
| Answering Line — the deep cores are inert | 53 of the 159 enclosed stations recover nothing under either canopy under Ladybug. This is why the mean is 17.4% — recovery concentrates in the other 106, divided across a denominator a third of which is inert by design. 159 is the denominator. envelope_validation.json carries a secondary_serviceable_population block; it is the full delta rescaled by n_full/n_serviceable, adds no information, and is JSON-only — never quote its delta or CI | `5.CV_Highline/data/envelope_validation.json (results.lb_sunpath.win_tie_loss.n_both_zero_recapture)` |
| Answering Line — form tracks the loss | r 0.949, stolen-sky deficit vs rib height | `5.CV_Highline/data/envelope.json` |
| Answering Line — rib rationalization ⚠️ a finding, not a failure | 232 unique ribs → 10 standard types + 114 bespoke; 50.9% standardized within ±200 mm; dominant type covers only 31.5%; mean install deviation 425.7 mm. Before the 2026-08-15 re-fetch this read 29 bespoke / 87.5% — measuring a canyon 81.6% absent. Report it as a property of the site: a canyon this irregular (2,083 buildings, 3.5–386 m) cannot be answered with ten parts. Rationalization has limits and this site exceeds them | `5.CV_Highline/data/rib_schedule.json (_meta.totals)` |
| Answering Line — ⚠️ RETIRED: 'the canopy is mostly minimal' | Dead phrasing. It rested on T01 covering 74.6% of ribs, which was an artefact of the 81.6%-incomplete footprint set. The dominant type now covers 31.5% and 114 ribs are bespoke. Do not quote the old framing | `5.CV_Highline/data/rib_schedule.json (types)` |
| Answering Line — material quantity | 2,869.1 m total member length, which sizes to 83.2 t (192 × CHS 168x6.3 + 40 × CHS 219x8) under the direct-stiffness pass. The assumed-24 kg/m figures and the pre-re-fetch 63.8 t are both retired. One tonnage basis governs: the solver-derived one | `5.CV_Highline/data/rib_schedule.json (_meta.totals.total_member_length_m); 5.CV_Highline/data/structure.json` |
| Answering Line — sized steel vs the naive canopy | 83.2 t field-driven against 188.6 t for the uniform 7 m counterfactual (a) = 2.27× (the field-driven kit is 44% of (a)'s). Mechanism: 199 of (a)'s 232 ribs (86%) need CHS 219x8 against 40 of ours (17%). Both tonnages come from the same solver, combos and section ladder — like-for-like, and instrument-free, so no re-measurement can move it. The retired pairs are 57.8/115.3 → 2.00× and 63.8/188.6 → 2.96× | `5.CV_Highline/data/structure.json + structure_counterfactual.json` |
| Answering Line — governing load combination | 1.2D + 1.6S governs all 232 ribs in both canopies; snow/uplift utilization ratio 2.33–2.47 field-driven, 2.40–2.43 uniform. Uplift cannot govern at any geometry under this load model — factored snow (1.92 kPa, added to dead) and factored uplift (0.9 kPa, opposed by dead) scale on the same horizontal projection and plane-tilt factor, so the ratio is near-constant by construction. A 5.5 m cantilever is where a real uplift case should bite and this engine cannot surface it. Report as a property of the load model, never as evidence wind is unimportant | `5.CV_Highline/data/structure_counterfactual.json (_meta.totals.combo_margin, .governing_combo_counts_nominal)` |
| Answering Line — install deviation | mean 425.7 mm, max standardized 199.3 mm, against a 200 mm acceptance threshold — the mean is 2.1× the threshold. 'Tolerance' here is the max nodal snap displacement when a bespoke rib is replaced by its standard type — a geometric deviation, not a fabrication tolerance in the engineering sense | `5.CV_Highline/data/rib_schedule.json (_meta.model, _meta.totals)` |
| Answering Line — standardization curve | The curve still flattens past ~10 types, which is what justifies the count — but it now tops out far lower (50.9% at 10). Quote the coverage with the bespoke count beside it; a curve alone reads as success | `5.CV_Highline/data/rib_schedule.json (tradeoff_types_vs_maxtol_mm)` |
| High Line — who caused the enclosure (2005 rezoning, primary) | 74 of 273 ranked buildings (27.1%) own 67.9% of the stolen sky — 2.50× over-representation, 1,166 winter deck-hours. Bands: pre-2005 0.39× · 2005–2008 3.23× (21 buildings, 24.8%) · 2009+ 2.22×. Ranks 1–3 are 2008, 2006, 2006. The threshold is the 2005 West Chelsea rezoning, not the 2009 opening — the rezoning moved the development rights and is the causal event; the 2009 cut splits the cohort it created and hands the three largest culprits to the 'pre' side | `5.CV_Highline/data/attribution.json (metadata.cuts, .bands)` |
| High Line — the 2009 opening cut (secondary) | 52 of 273 (19.0%) own 43.0%, 2.26×. Retained for reporting. The old 53.7% figure is dead — it came from a footprint set 81.6% incomplete | `5.CV_Highline/data/attribution.json (metadata.cuts.secondary_2009_opening)` |
| High Line — ⚠️ era thresholds are TWO constants | REZONING_YEAR = 2005 is causal (who caused it — attribution, map colouring). OPENING_YEAR = 2009 is the baseline (what the deck lost as a park — svf_prepark, the deficit field, everything generated from it). A baseline predating the park would count loss no visitor experienced. The 2009 baseline also restores a significance the 2005 baseline removes — that was not the reason for the choice, and both runs exist so the claim is checkable | `5.CV_Highline/data/highline_viewshed.json (_meta.era_thresholds)` |
| High Line — ⚠️ the data-loss incident (disclose it) | On 2026-06-28 fetch_nyc_data.py took a silent partial API response: 176 rows against a true 955 (81.6% lost) and the project analysed 18.4% of its own site for six weeks. Not a wrong dataset, not a parser bug, not a filter — every returned row was valid. Found because built coverage was 4.5%; Manhattan cannot be 8.6× less built than Wicker Park. Cost: svf_deck read 0.808 instead of 0.424; tallest building recorded 83 m with a 386 m tower in the bbox. A completeness count(1) assertion now aborts the fetch on mismatch. Report this — the guard is the credential | `5.CV_Highline/scripts/fetch_nyc_data.py; data/highline_footprints.json (metadata.completeness_verified)` |

Every figure above is traced to the file it was measured from. Nothing is quoted from memory.

## Limitations

The sky measure is 2.5-D — one horizon angle per azimuth cannot represent a punctured hemisphere, and the disagreement with Ladybug tracks how many things are in the way rather than how tall they are. That is a model-order limit, which is why the calibration fit was retired and both numbers are published raw. Recapture is measured at the canopy, not at a person under it. The pedestrian model is not validated against counts, and this repository holds no rent, tenure or displacement data at all: it measures sky, on the deck.

- **There is no eye-level architectural hero with human figures and site context.** It is the one asset this project's own notes name as blocking, and the study is otherwise finished. A single rendered eye-level view under the enclosed section would carry the argument to an audience that reads drawings before it reads plots.
- **The piece has drifted from the plan it was scoped against.** The plan describes a ribbon-envelope study; the code is now an enclosure study. Both are defensible — the plan is what needs rewriting to match, not the code.
- **The map layer runs untokenised.** The token is git-ignored, so the application runs in non-georeferenced mode for anyone else. A documented environment variable would make the georeferenced view reproducible off this machine.

## References and prior art

- **To take hold of space: isovists and isovist fields** — Benedikt, M. L., 1979 · Environment and Planning B, 6(1), 47–65 · doi:10.1068/b060047  
  The ancestor of hl_core. The isovist — everything visible from a vantage point — and the measures that turn it from a drawing into a quantity. Benedikt’s is planar; this cast keeps the highest horizon angle per azimuth instead, which returns sky access above the deck rather than floor area along it. That 2.5-D simplification is also where the project’s measured limit comes from.
- **Canyon geometry and the nocturnal urban heat island** — Oke, T. R., 1981 · Journal of Climatology, 1(3), 237–254 · doi:10.1002/joc.3370010304  
  Establishes sky view factor as the canyon-geometry variable governing long-wave loss — so SVF is a quantity with a literature, not an index invented here. ⚠ Oke’s SVF governs nocturnal heat; this project uses the same geometry for daylight and sky access on a public deck. Same measure, different claim: no temperature was measured and no heat island is asserted.
- **Sky view factor by hemispherical ray casting** — hl_core, five engines, seeded at 42  
  The standard formulation, implemented here rather than imported, so the counterfactual runs could share one geometry pipeline with the sunlit-hours pass.
- **Ladybug Tools — independent recompute of SVF and sunlit hours** — Sadeghipour Roudsari, M. & Pak, M., 2013 · Proceedings of BS2013, 13th IBPSA Conference, Chambéry · a second implementation, run against the same geometry  
  Used as a validation layer, not as the engine. The engines are this project's; Ladybug exists here to disagree with them, and it agrees at r = 0.871. The earlier calibration fit built on that agreement is retired.
- **Characteristics of pattern formation in approximations of Physarum transport networks** — Jones, J., 2010 · Artificial Life, 16(2), 127–153  
  The sense–turn–move–deposit agent model the pedestrian simulation runs on, reused on a 1-D corridor and driven by the measured enclosure field. ⚠ It is not validated against pedestrian counts: it shows where the sim says people linger given the measured sky, not where people actually go.
- **SegFormer — simple and efficient design for semantic segmentation with Transformers** — Xie et al., 2021 · NeurIPS 34 · checkpoint nvidia/segformer-b5-finetuned-cityscapes-1024-1024  
  The checkpoint behind data/highline_exposure.json, re-run to build the capture-and-overlay strip — reproducing the published sky fractions to four decimals. ⚠ Street-level context exposure, not the on-deck view, and the southern corridor only; uncovered bins are null, never 0.
- **Parks for profit: the High Line, growth machines, and the uneven development of urban public spaces** — Loughran, K., 2014 · City & Community, 13(1), 49–68 · doi:10.1111/cico.12050  
  THE ARGUMENT THIS PROJECT TESTS. Reads the High Line as an archetypal neoliberal space and traces the growth-machine dynamics behind its redevelopment — qualitatively. The counterfactual sizes it: removing the post-park cohort restores 23.06 SVF points across the line, and at the worst core 0 of 360 rays reach open sky where 92 did before the boom.
- **Green gentrification — greening that displaces the residents it was nominally for** — Gould, K. A. & Lewis, T. L. · Green Gentrification, Routledge · ⚠ year appears as both 2016 and 2017 across sources; confirm against the copy consulted  
  The wider frame the finding sits inside. ⚠ Cite as the frame, never as a High Line study — its cases are Brooklyn. And this repository holds no rent, tenure or displacement data at all: it measures sky, on the deck. The attribution leaderboard names buildings, not owners or beneficiaries.

## What is in this repository

- `.gitignore` — 1 file
- `cityBlock.json` — 1 file
- `CV_exploded streetscape.pdf` — 1 file
- `CV_isoview.pdf` — 1 file
- `deck_map.html` — 1 file
- `envelope.html` — 1 file
- `highline_workstream_dependency_flow.png` — 1 file
- `I want to know where exactly did i.txt` — 1 file
- `index.html` — 1 file
- `index_strip.html` — 1 file
- `ingest_log.txt` — 1 file
- `LITERATURE.md` — 1 file
- `mapbox_token.example.js` — 1 file
- `mapbox_token.js` — 1 file
- `meshWarp.js` — 1 file
- `prompt1_continue.txt` — 1 file
- `README.md` — 1 file
- `Screenshot 2026-08-09 124032.png` — 1 file
- `Screenshot 2026-08-09 124054.png` — 1 file
- `THE_ANSWERING_LINE.md` — 1 file
- `blender` — 6 files
- `boards` — 53 files
- `ComputerVision` — 80 files
- `data` — 81 files
- `exports` — 38 files
- `houdini` — 6 files
- `scripts` — 41 files

Large data, media and binaries are not committed. `DATA.md` lists what was left out and where it comes from.

---

Narrative, figures and numbers on this page are synced from the same source the portfolio site is built from. Site: https://sriyathotakura.com
