# Literature — where this project sits, and where it departs

**What this file is for.** Every method in this project is an implementation of something with a
literature behind it, and the counterfactual finding lands inside an argument urban sociology has
been making about the High Line for a decade. Naming both is what turns "I built a ray caster"
into "I supplied a measured quantity to a live debate."

> ### ⚠️ VERIFICATION STATUS — read before quoting any of this
> Every citation below was checked on **2026-09-05** against the publisher's own record: title,
> authors, venue, volume, pages and DOI all resolve. **The full texts were not read for this
> file.** So the *bibliographic* details are verified; the one-line characterisation of each
> argument is a summary and should be confirmed against the paper before it is said out loud in
> an interview or printed on a board.
>
> That distinction is the same one this project applies to its own numbers, and it is deliberate:
> a citation whose details are right and whose claim is misremembered is exactly the failure that
> is hardest for a reader to catch.

---

## 1 · The method — visibility as a measurable field

**Benedikt, M. L. (1979). "To take hold of space: isovists and isovist fields."**
*Environment and Planning B: Planning and Design*, 6(1), 47–65. DOI `10.1068/b060047`.

The isovist — the set of all points visible from a vantage point — and the numerical measures that
turn it from a drawing into a quantity. This is the ancestor of `hl_core`: `edges_for` + `ray_uv`
computing an isovist at each of 232 deck stations is Benedikt's construction, cast rather than
drawn.

**Where this project departs.** Benedikt's isovist is planar. `hl_core` casts 360 azimuths and
keeps, per azimuth, the **highest horizon angle β** — a 2.5-D construction that returns a horizon
profile rather than a polygon, because the quantity wanted is sky access above the deck, not floor
area visible along it. `FIG 7` is that field drawn raw, 232 × 360, before it collapses to a number.

**⚠️ And this is exactly where the project's own honesty gap lives.** A 2.5-D cast takes one
horizon per azimuth; a 3-D one integrates the hemisphere. `FIG 3` measures the consequence against
Ladybug and finds the divergence tracks occluder **count** (r = +0.384), not occluder **height**
(r = −0.332) — which is a model-order limit inherited from the 2.5-D simplification, not a
calibration error. Cite Benedikt for the method and that figure for its limit in the same breath.

---

## 2 · The quantity — sky view factor as an established climatic variable

**Oke, T. R. (1981). "Canyon geometry and the nocturnal urban heat island: comparison of scale
model and field observations."** *Journal of Climatology*, 1(3), 237–254. DOI
`10.1002/joc.3370010304`.

Establishes sky view factor as the canyon-geometry variable governing long-wave radiative loss, and
therefore as a real physical quantity with a literature — not an index invented for this project.
When a board says "SVF 0.424", this is what makes the number mean something to a reviewer who has
never seen `hl_core`.

**⚠️ Where this project departs, and it matters.** Oke's SVF governs **nocturnal heat loss**. This
project uses the same geometric quantity to describe **daylight and sky access on a public deck**.
The measure is identical; the claim is not. **Do not let Oke's citation drift into implying this
project measured an urban heat island** — it did not, it has no temperature data, and
`data/HEAT_ISLAND_RISK_MAP.png` in `ComputerVision/` is a separate CV-era artefact, not an output
of these engines.

---

## 3 · The second opinion — an independent implementation

**Sadeghipour Roudsari, M., & Pak, M. (2013). "Ladybug: a parametric environmental plugin for
Grasshopper to help designers create an environmentally-conscious design."** *Proceedings of
BS2013: 13th Conference of the International Building Performance Simulation Association*,
Chambéry, France, 25–28 August 2013.

The validation layer. `build_lbt.py` recomputes deck SVF and sunlit hours through Ladybug's own
`Sunpath` and `ladybug_geometry` ray casting, and the two are published side by side at
r = 0.871, RMSE 0.2013 — **neither adjusted toward the other**, the calibration fit having been
retired (`IMPLEMENTATION_PLAN.md` W2). See `FIG 3`.

---

## 4 · The movement model — stigmergy and trail formation

**Jones, J. (2010). "Characteristics of pattern formation and evolution in approximations of
Physarum transport networks."** *Artificial Life*, 16(2), 127–153.

The particle-and-pheromone agent model — sense, turn, move, deposit — that `index.html`'s
`physarumStep()` implements, and which the High Line pedestrian mode reuses on a 1-D corridor.
`FIG` — the space-time volume and the Marey diagram — are two readings of one seeded run.

**⚠️ What this citation does not license.** Jones's networks are an *emergent pattern* result. The
High Line mode is a **corridor occupancy model driven by the measured enclosure field**, and it is
not validated against pedestrian counts. It shows where the sim says people linger given the
measured sky; it does not show where people actually go. Say so.

---

## 5 · The visual audit — semantic segmentation

**Xie, E., Wang, W., Yu, Z., Anandkumar, A., Álvarez, J. M., & Luo, P. (2021). "SegFormer: simple
and efficient design for semantic segmentation with Transformers."** *Advances in Neural
Information Processing Systems (NeurIPS) 34*.

`nvidia/segformer-b5-finetuned-cityscapes-1024-1024` is the checkpoint that produced
`data/highline_exposure.json`'s sky, greenery and public-realm fractions, and the same checkpoint
regenerates the capture-and-overlay strip in `scripts/build_cv_overlays.py` — reproducing the
published sky fractions to four decimal places.

**⚠️ Carry the pilot caveat.** This is **street-level context exposure, not the on-deck view**, and
it covers the southern corridor only — imagery exists for transect points 8–47. Uncovered bins are
`null`, never `0`; **P17's 0.0 is a real measured value**, which is why its overlay shows no accent
at all.

---

## 6 · The relevance — what the measurement is *for*

This is the half that makes the project an argument rather than an exercise. The claim that the
High Line's success drove the development that now encloses it has been made, forcefully, in urban
sociology. **It has been made qualitatively.** This project supplies a number to it.

**Loughran, K. (2014). "Parks for profit: the High Line, growth machines, and the uneven
development of urban public spaces."** *City & Community*, 13(1), 49–68. DOI `10.1111/cico.12050`.

Reads the High Line as an archetypal neoliberal space and traces its redevelopment from decaying
viaduct to celebrated park, arguing contemporary public spaces sit on a continuum of privilege
produced by growth-machine dynamics. **This is the argument the counterfactual matrix tests.**
`FIG 4`'s pre-2009 row restores **+23.06 SVF points**; `FIG 2` shows a station where **0 of 360
rays** reach open sky as built against **92 of 360** before the boom. Loughran names the mechanism;
these figures size it.

**Gould, K. A., & Lewis, T. L. *Green Gentrification: Urban Sustainability and the Struggle for
Environmental Justice*.** Routledge, Equity, Justice and the Sustainable City series.

The wider frame: greening initiatives that improve environmental conditions while displacing the
residents they were nominally for.

⚠️ **Two precision notes.** Its cases are **Brooklyn**, not the High Line — cite it as the frame,
never as a High Line study. And the publication year is **inconsistent across sources** (2016 and
2017 both appear, hardback vs. Routledge listing); confirm against the copy you actually consult
before printing a year.

---

## What the literature does **not** cover, and this project must not imply it does

- **No displacement or demographic data is in this repository.** The green-gentrification
  literature is about who gets pushed out. This project measures **sky**, and it measures it on
  the deck. It cannot speak to rents, tenure or displacement, and the attribution leaderboard
  names buildings, not owners or beneficiaries.
- **Causality is apportioned geometrically, not economically.** `build_attribution.py` asks which
  massing blocks which ray. That a building takes 7.52% of the lost sky is a statement about
  geometry; whether the park *caused* that building is the rezoning question, and the project
  handles it by naming the **2005 West Chelsea rezoning** as the causal cut and the **2009
  opening** as the baseline cut, and keeping the two apart.
- **The design response is a proposal, not a validated intervention.** The canopy's recapture
  figures are computed by the same ray primitive that generated the canopy —
  `IMPLEMENTATION_PLAN.md` W3 — and that circularity is disclosed rather than resolved.
