# Boards — programmatic simulation-board pipeline

Two 11×17 landscape boards @ 300 dpi (5100×3300 px), dark theme matching
`index.html`, in the style of research-lab sim boards. **Every number on a board
comes from a JSON in `data/`** — nothing is hand-placed or hardcoded.

- **`board1.png` — COUNTERFACTUAL MATRIX**: hero axon (towers by attribution
  rank) · 4×4 scenario matrix (baseline + pre-2009 + forward + 12 single-building
  removals, difference-strips) · attribution leaderboard · Ladybug validation card
  · 3 algorithmically-selected detail extremes · callout.
- **`board2.png` — BEHAVIORAL CONSEQUENCE**: 5 stacked comfort-field states · a
  composited deck-perspective hero (4 render passes) · 4 process panels
  (centerline extraction, ray-cast diagram, calibration scatter, dwell-gap) ·
  the de-parking annotation.

## One-command rebuild

```bash
bash scripts/build_boards.sh          # → boards/board1.png + board2.png
```

Deterministic: the agent sim is seeded (`seed=42`), so trails/dwell reproduce
identically. The script owns the **board layer** — it (1) drives `index.html`
capture mode with Playwright for the 8 3D captures, (2) dumps behavioural metrics,
(3) renders the matrix cells + Board-2 panels, (4) screen-blends the hero passes,
(5) composites both boards.

## Pipeline

```
data/*.json (engines, upstream) ─┐
                                 ├─ build_boards.sh ─→ board1.png / board2.png
index.html?capture=… (Playwright)┘
```

**Upstream (produce `data/*.json`)** — run once, or after the model changes:
`fetch_nyc_data.py` → `build_viewshed/solar/section/attribution/forward.py` →
`reconcile_exposure.py` → `build_lbt.py` (Ladybug) → `calibrate_svf.py` →
`build_removals.py` → `build_building_labels.py`. See root `CLAUDE.md`.

**Board layer (this folder)**:
- `scripts/capture.py` — Playwright driver (2× device scale, waits on `window.CAPTURE_READY`).
- `scripts/capture_metrics.py` → `data/behavior_metrics.json` (seeded dwell-gap + per-segment congestion).
- `scripts/render_cell.py` — the 16 matrix cells + KEY (matplotlib).
- `scripts/render_board2.py` — the 5 comfort states + 4 process panels (matplotlib).
- `scripts/compose_boards.py` — the PIL assembler, reads `board{1,2}_spec.json`.
- `board1_spec.json` / `board2_spec.json` — panel rects, labels, sources, callouts.

`index.html` capture mode (URL params): `?capture=1&cam=<preset>&s=<m>&pass=<context|heatmap|trails|access>&colorby=attribution&layers=<csv>&bg=<dark|black>&seed=42&ticks=<n>`.
Camera presets live in `data/capture_presets.json`.

## Conventions

- **Palette — migrating to the portfolio system. Decided 2026-08-09; NOT yet applied in code.**

  **Target** is the colourblind-validated set in `../../PORTFOLIO_ARCH_BOARD_PLAN.md` §"Global
  visual standard", so these boards read as the same document as every other spread:
  blue `#2a78d6` · pale blue `#9ec5f4` · green `#008300` · magenta `#e87ba4` ·
  ink `#0b0b0b` · surface `#fcfcfb`.

  **The dark ground stays.** `docs/PDF_COMPOSITION_GUIDE.md` is *"pages are paper, images are
  dark plates"* — a dark board sitting on a paper page is the system working, not a violation.
  What has to change is only the **accent hues**, which currently belong to no other spread.
  Do not invert these boards to white: that would mean redesigning every colormap and
  re-capturing the eight 3D passes, and `../IMPLEMENTATION_PLAN.md` lists rebuilding the boards
  as explicitly out of scope.

  **Proposed mapping** (keeps the diverging structure, colourblind-safe pair):

  | Role | Now | Target |
  |---|---|---|
  | loss / enclosure | terracotta `#c0673f` | magenta `#e87ba4` |
  | restored / open sky | teal `#00ddaa` | pale blue `#9ec5f4` |
  | emphasis, headline figures | teal | blue `#2a78d6` |
  | validation / pass state | amber `#c9a24a` | green `#008300` |

  **Migration surface — 15 hex values in 4 files**, plus the captures:

  | File | What |
  |---|---|
  | `board1_spec.json`, `board2_spec.json` | `accent`, `teal` keys (2 each) |
  | `scripts/render_cell.py:22-26` | `TEAL`/`TERRA`/`EDGE` + `SVF_CMAP` + `DIFF_CMAP` |
  | `scripts/render_board2.py:24-25` | `TEAL`/`TERRA`/`EDGE`/`AMBER` + `CMAP` |
  | `index.html` `TYPE_COLOR` | feeds the 8 Playwright 3D captures — **re-capture after changing**, or the board mixes palettes |

  ⚠️ **Until that migration lands, `board1.png` and `board2.png` on disk still carry the
  terracotta/teal accents.** This section records the decision, not the current output.
- **Font**: IBM Plex Mono (the app font), in `assets/fonts/` (from google/fonts).
- **Difference strips** (matrix removal cells): 0 = background (quiet, no change) →
  teal (sky restored); clipped at the 99th-percentile (`diff_p99` in
  `removals.json`); the true peak is documented in the Board 1 footer.
- **Calibration**: SVF figures are shown raw in the strips but the headline is
  Ladybug-calibrated (`svf_calibration.json`).
- **Provenance**: `seed=42` and the clip/peak are printed in the Board 1 footer;
  every panel names its source JSON.

## Requirements

Python: `playwright` (+ `playwright install chromium`), `matplotlib`, `pillow`,
`numpy`. A local static server (the script uses `python -m http.server`).
