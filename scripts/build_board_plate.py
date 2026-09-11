"""build_board_plate.py — the counterfactual board, redrawn on paper.

    python scripts/build_board_plate.py            -> exports/plates/FIG10_counterfactual_board.png

WHY THIS EXISTS BESIDE compose_boards.py
    `boards/board1.png` is the 2026-07-10 board: a dark dashboard — near-black ground,
    teal and terracotta, IBM Plex Mono on `#0a0b0f` — assembled by `compose_boards.py`
    from Playwright captures of index.html. Two things are wrong with it now.

    1. Its numbers predate the 2026-08-15 footprint re-fetch. It prints SVF 0.73, a
       "53.7% share of 6 post-2009 towers" and "~340 winter deck-hours", all of which
       were measured against a footprint set that was 81.6% incomplete. The current
       figures are 0.424, 67.9% across 74 buildings and 1,166 hours. It also prints the
       linear calibration `svf = 1.18·svf − 0.23`, which IMPLEMENTATION_PLAN W2 retired.
    2. It is the one dark plate in a set of nine drawn on paper (`build_analysis_plates.py`
       and its siblings), and on the site it sits beside them.

    This script is the same board — title, headline, hero, scenario matrix, attribution
    leaderboard, Ladybug validation, three detail stations — drawn in the plate set's own
    language and from the CURRENT data. Every number is read from a `data/*.json` or the
    horizon field; nothing is retyped, and the retired calibration columns are not used.
    The 3D captures are replaced by drawings from the same data: the hero is the plan of
    every footprint with the attribution ranks painted on, and the three detail views are
    the measured horizon at each station — which is what the captures were illustrating.

WHAT IS DRAWN, AND FROM WHERE
    title / headline      data/comparison.json          SVF 0.424 vs The 606's 0.978
                          data/attribution.json         metadata.cuts.primary_2005_rezoning
    hero plan             data/highline_footprints.json every footprint + the deck centreline
                          data/attribution.json         leaderboard rank + sky_share_pct
                          data/building_labels.json     the display address per BIN
    scenario matrix       data/removals.json            16 cells: 3 anchors, KEY, 12 removals
                          hl_core.load_site()           counts recomputed — `meta` is stale
    leaderboard           data/attribution.json         top 12 rows
    validation            data/lbt_validation.json      r / R² / RMSE, published RAW
    detail stations       data/detail_points.json       s for worst / peak-congestion / best
                          exports/horizon_field.npz     beta[232, 360] — the measured horizon
                          data/highline_viewshed.json   svf_deck at each station
                          data/behavior_metrics.json    seeded density at the congestion peak
                          data/sun_vectors.json         winter sun path, if present
"""

import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402
import matplotlib.font_manager as fm                              # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402
from matplotlib.patches import Polygon, Rectangle                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import hl_core as hlc                    # noqa: E402
import build_viewshed as bv              # noqa: E402 — PARK_YEAR
from build_analysis_plates import (      # noqa: E402 — the plate set's own language
    PAPER, STEEL, SHADE, DETECTED, FLAGGED, RAMP, MONO, style, load, log,
)

OUT = os.path.join(PROJECT, "exports", "plates")
DATA = os.path.join(PROJECT, "data")
FONTS = os.path.join(PROJECT, "boards", "assets", "fonts")

for w in ("Regular", "Medium", "SemiBold"):
    p = os.path.join(FONTS, f"IBMPlexMono-{w}.ttf")
    if os.path.isfile(p):
        fm.fontManager.addfont(p)

# The plate set's diverging ramp for change-vs-baseline (FIG4), and a quiet
# sequential one for absolute sky view: paper at enclosed, the blue at open.
DIV = LinearSegmentedColormap.from_list("hl_div", [FLAGGED, PAPER, "#2c3e8f"])
SEQ = LinearSegmentedColormap.from_list("hl_seq", ["#d9d6cf", "#9fb6c9", "#2c3e8f"])
INK2 = "#5c5f5a"       # a mid tone between STEEL and SHADE for secondary values
RULE = "#dcd9d2"       # panel edges and hairlines


def display_name(labels, bid):
    """The geocoded street address for a BIN, or the BIN itself when Nominatim
    answered with the park rather than a building. Two of the current twelve
    resolve to "HIGH LINE" — they stand against the deck — and a label that
    names the park as the culprit would be wrong, so those print as a BIN
    until `data/building_labels.json` is hand-corrected, which its own note
    invites. The " · year" suffix the builder appends is dropped here: the
    year has its own column everywhere it appears."""
    d = labels.get(bid, {}).get("display", "")
    d = d.split(" · ")[0].strip()
    if not d or d.startswith("#") or d.upper().startswith("HIGH LINE"):
        return "BIN %s" % bid
    return d


def rule(fig, x0, x1, y, col=RULE, lw=0.6):
    fig.add_artist(plt.Line2D([x0, x1], [y, y], color=col, lw=lw, transform=fig.transFigure))


def label(fig, x, y, s, size=7.2, col=SHADE, ha="left", va="center", weight="normal"):
    fig.text(x, y, s, fontsize=size, color=col, ha=ha, va=va, fontweight=weight)


def panel_head(fig, x0, x1, y, title, note=None):
    """A section label on a hairline — the register every plate in the set uses."""
    label(fig, x0, y + 0.012, title, size=7.6, col=STEEL, weight="bold")
    if note:
        label(fig, x1, y + 0.012, note, size=6.6, col=SHADE, ha="right")
    rule(fig, x0, x1, y)


# ═════════════════════════════════════════════════════════════════════════════
def main():
    os.makedirs(OUT, exist_ok=True)
    style()

    cmp_ = load("comparison.json")["corridors"]
    hl_c = next(c for c in cmp_ if c["name"].startswith("High Line"))
    c606 = next(c for c in cmp_ if "606" in c["name"])
    att = load("attribution.json")
    cut = att["metadata"]["cuts"]["primary_2005_rezoning"]
    labels = load("building_labels.json")["labels"]
    rm = load("removals.json")
    lbt = load("lbt_validation.json")["metrics"]
    det = load("detail_points.json")
    vs = load("highline_viewshed.json")["points"]
    beh = load("behavior_metrics.json")
    fp = load("highline_footprints.json")
    hf = np.load(os.path.join(PROJECT, "exports", "horizon_field.npz"))

    site = hlc.load_site()
    bld = site.buildings
    n_all = len(bld)
    n_pre = sum(1 for b in bld if b.yr is not None and b.yr <= bv.PARK_YEAR)
    n_post = n_all - n_pre

    scen = rm["scenarios"]
    s_axis = np.array(rm["s_axis"], dtype=float)
    base = next(x for x in scen if x["key"] == "baseline")
    b0 = np.array(base["svf"], dtype=float)

    fig = plt.figure(figsize=(16.5, 10.6), dpi=200)

    # ── title block ─────────────────────────────────────────────────────────
    fig.text(0.045, 0.962, "THE PARK BUILT THE WALLS THAT NOW ENCLOSE IT", fontsize=19,
             fontweight="bold", color=STEEL)
    fig.text(0.045, 0.936,
             "board 1 / counterfactual matrix  ·  computed per building  ·  isovist + solar, "
             "Ladybug-validated and published raw  ·  %d footprints, %d stations, seed 42"
             % (n_all, len(s_axis)), fontsize=8.2, color=SHADE)

    # headline, right — three facts, each read from its file and none rounded past
    # what the file carries
    fig.text(0.955, 0.966, "SVF %.3f" % hl_c["mean_svf"], fontsize=19, fontweight="bold",
             color=FLAGGED, ha="right", va="center")
    fig.text(0.955, 0.943, "against %.3f on The 606  ·  %.0f%% of the deck enclosed"
             % (c606["mean_svf"], hl_c["pct_enclosed"]), fontsize=7.8, color=STEEL, ha="right")
    fig.text(0.955, 0.926,
             "%d of %d ranked buildings — built after the 2005 rezoning — own %.1f%% of the "
             "stolen sky, %s winter deck-hours"
             % (cut["n"], att["metadata"]["n_buildings_ranked"], cut["sky_share_pct"],
                format(round(cut["winter_deckhours_stolen"]), ",")),
             fontsize=7.2, color=SHADE, ha="right")
    rule(fig, 0.045, 0.955, 0.912, col=SHADE, lw=0.8)

    # ── column geometry ─────────────────────────────────────────────────────
    top, bot = 0.885, 0.315                # main band
    xh0, xh1 = 0.045, 0.285                # hero plan
    xm0, xm1 = 0.315, 0.700                # matrix
    xr0, xr1 = 0.730, 0.955                # leaderboard + validation

    # ── HERO — the plan, attribution painted on ─────────────────────────────
    panel_head(fig, xh0, xh1, top, "WHO TOOK THE SKY  ·  plan",
               "top 12 by share  ·  data/attribution.json")
    axh = fig.add_axes([xh0, bot, xh1 - xh0, top - bot - 0.02])
    axh.set_facecolor(PAPER)
    axh.set_aspect("equal")
    axh.set_axis_off()
    share = {r["id"]: r for r in att["leaderboard"]}
    top12 = {r["id"]: r for r in att["leaderboard"][:12]}
    vmax = max(r["sky_share_pct"] for r in att["leaderboard"][:12])
    for f in fp["features"]:
        pid = f["properties"]["id"]
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            ring = np.array(poly[0], dtype=float)
            if pid in top12:
                a = 0.35 + 0.65 * top12[pid]["sky_share_pct"] / vmax
                axh.add_patch(Polygon(ring, closed=True, facecolor=FLAGGED, alpha=a,
                                      edgecolor=FLAGGED, lw=0.5, zorder=3))
            elif pid in share and share[pid]["sky_share_pct"] > 0.5:
                axh.add_patch(Polygon(ring, closed=True, facecolor="#e9c9c4", edgecolor="none",
                                      zorder=2))
            else:
                axh.add_patch(Polygon(ring, closed=True, facecolor="#e4e1da", edgecolor="#d3d0c8",
                                      lw=0.25, zorder=1))
    cl = np.array(fp["high_line"]["centerline"], dtype=float)
    axh.plot(cl[:, 0], cl[:, 1], color=STEEL, lw=1.6, zorder=5, solid_capstyle="round")
    axh.plot(cl[:, 0], cl[:, 1], color=PAPER, lw=0.6, zorder=6, ls=(0, (2, 3)))
    # rank tags on the twelve, placed at each footprint's centroid
    for f in fp["features"]:
        pid = f["properties"]["id"]
        if pid not in top12:
            continue
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        ring = np.array(polys[0][0], dtype=float)
        cx, cy = ring[:, 0].mean(), ring[:, 1].mean()
        axh.text(cx, cy, str(top12[pid]["rank"]), fontsize=6.2, color=PAPER, ha="center",
                 va="center", fontweight="bold", zorder=7)
    # the three detail stations
    xs = np.array([p["x"] for p in vs]); zs = np.array([p["z"] for p in vs])
    ss = np.array([p["s_m"] for p in vs])
    for key, tag in (("worst_svf", "A"), ("peak_congestion", "B"), ("best_svf", "C")):
        i = int(np.argmin(np.abs(ss - det[key]["s"])))
        axh.plot(xs[i], zs[i], "o", ms=7, mfc=PAPER, mec=STEEL, mew=1.0, zorder=8)
        axh.text(xs[i] + 28, zs[i], tag, fontsize=7, color=STEEL, va="center", fontweight="bold",
                 zorder=9)
    pad = 60
    axh.set_xlim(xs.min() - 420, xs.max() + 420)
    axh.set_ylim(zs.min() - pad, zs.max() + pad)
    label(fig, xh0, bot - 0.004, "deck centreline  ·  red fill = share of stolen sky, "
          "numbered by rank  ·  pink = any share above 0.5%  ·  A B C = the detail stations below",
          size=6.2, va="top")

    # ── MATRIX — 4 × 4 cells ────────────────────────────────────────────────
    panel_head(fig, xm0, xm1, top, "SCENARIO MATRIX  ·  baseline + pre-2005 + forward + 12 single removals",
               "data/removals.json")
    order = ["baseline", "pre2009", "forward", "KEY"] + ["r%d" % i for i in range(1, 13)]
    strips = {x["key"]: (np.array(x["svf"], dtype=float) - b0) * 100.0
              for x in scen if x["key"].startswith("r")}
    lim = float(np.nanpercentile(np.abs(np.concatenate(list(strips.values()))), 99))
    dnorm = Normalize(vmin=-lim, vmax=lim)
    smin, smax = rm["metadata"]["svf_scale"]
    snorm = Normalize(vmin=smin, vmax=smax)
    dmax = max(abs(v) for v in rm["metadata"]["d_svf_scale"])

    cols, rows = 4, 4
    gx, gy = 0.010, 0.014
    cw = (xm1 - xm0 - (cols - 1) * gx) / cols
    ch = (top - 0.02 - bot - (rows - 1) * gy) / rows
    by_key = {x["key"]: x for x in scen}

    def cell_frame(x, y):
        fig.add_artist(Rectangle((x, y), cw, ch, transform=fig.transFigure, facecolor="#f7f5f1",
                                 edgecolor=RULE, lw=0.6, zorder=0))

    for i, key in enumerate(order):
        r, c = divmod(i, cols)
        x = xm0 + c * (cw + gx)
        y = top - 0.02 - (r + 1) * ch - r * gy
        cell_frame(x, y)
        if key == "KEY":
            label(fig, x + 0.008, y + ch - 0.015, "KEY", size=7.6, col=STEEL, weight="bold")
            label(fig, x + cw - 0.008, y + ch - 0.015, "shared scales", size=5.8, ha="right")
            label(fig, x + 0.008, y + ch - 0.030, "sky view  ·  the anchor strips", size=5.4)
            ax1 = fig.add_axes([x + 0.008, y + ch - 0.046, cw - 0.016, 0.010])
            ax1.imshow(np.linspace(0, 1, 256)[None, :], aspect="auto", cmap=SEQ)
            ax1.set_xticks([]); ax1.set_yticks([])
            for sp in ax1.spines.values(): sp.set_color(RULE)
            label(fig, x + 0.008, y + ch - 0.055, "%.2f enclosed" % smin, size=5.2)
            label(fig, x + cw - 0.008, y + ch - 0.055, "open %.2f" % smax, size=5.2, ha="right")
            label(fig, x + 0.008, y + ch - 0.073, "change  ·  the removal strips", size=5.4)
            ax2 = fig.add_axes([x + 0.008, y + ch - 0.089, cw - 0.016, 0.010])
            ax2.imshow(np.linspace(0, 1, 256)[None, :], aspect="auto", cmap=DIV)
            ax2.set_xticks([]); ax2.set_yticks([])
            for sp in ax2.spines.values(): sp.set_color(RULE)
            label(fig, x + 0.008, y + ch - 0.098, "−%.1f pts" % lim, size=5.2)
            label(fig, x + cw - 0.008, y + ch - 0.098, "+%.1f pts  (p99)" % lim, size=5.2, ha="right")
            label(fig, x + 0.008, y + 0.014, "bar 0–%.0f pts  ·  h: winter sun" % dmax, size=5.0)
            continue

        sc = by_key[key]
        is_diff = key.startswith("r")
        is_ref = key == "baseline"
        tone = {"restore": "#2c3e8f", "loss": FLAGGED, "neutral": STEEL}[sc["tone"]]
        if is_diff:
            name = display_name(labels, sc.get("id", ""))
            sub = "%s  ·  %.0f m" % (sc.get("year") or "undated", sc.get("height_m", 0))
        elif key == "pre2009":
            name = "PRE-REZONING"
            sub = "%d footprints removed" % n_post
        elif key == "forward":
            name = "FORWARD"
            sub = "soft sites built out"
        else:
            name = "BASELINE"
            sub = "as built"
        label(fig, x + 0.008, y + ch - 0.015, name, size=7.2, col=STEEL, weight="bold")
        head = ("SVF %.3f" % sc["mean_svf"]) if is_ref else ("%+.2f pts" % sc["d_svf_pct"])
        label(fig, x + 0.008, y + ch - 0.029, sub, size=5.4)
        label(fig, x + cw - 0.008, y + ch - 0.047, head, size=9, col=tone, ha="right", weight="bold")
        # strip
        axs = fig.add_axes([x + 0.008, y + 0.040, cw - 0.016, ch - 0.100])
        if is_diff:
            axs.imshow(strips[key][None, :], aspect="auto", cmap=DIV, norm=dnorm,
                       extent=[s_axis.min(), s_axis.max(), 0, 1], interpolation="nearest")
        else:
            svf = np.array(sc["svf"], dtype=float)
            axs.imshow(svf[None, :], aspect="auto", cmap=SEQ, norm=snorm,
                       extent=[s_axis.min(), s_axis.max(), 0, 1], interpolation="nearest")
            if not is_ref:
                axs.plot(s_axis, (b0 - smin) / (smax - smin), color=STEEL, lw=0.55, alpha=0.7)
        axs.set_yticks([])
        axs.set_xticks([0, 900, s_axis.max()])
        axs.set_xticklabels(["0 m", "900", "%.0f" % s_axis.max()], fontsize=5.2, color=SHADE)
        axs.tick_params(length=1.5, pad=1.5, color=SHADE)
        for sp in axs.spines.values():
            sp.set_color(RULE); sp.set_linewidth(0.5)
        # bottom band: the headline bar on the shared scale, and the winter-sun delta
        if is_ref:
            label(fig, x + 0.008, y + 0.017, "winter sun, mean", size=5.6)
            label(fig, x + cw - 0.008, y + 0.017, "%.2f h" % sc["mean_winter_sun_h"], size=8,
                  col=STEEL, ha="right", weight="bold")
        else:
            axb = fig.add_axes([x + 0.008, y + 0.012, (cw - 0.016) * 0.52, 0.011])
            axb.set_xlim(0, dmax); axb.set_ylim(0, 1); axb.set_axis_off()
            axb.add_patch(Rectangle((0, 0), dmax, 1, facecolor="#ebe8e1", edgecolor=RULE, lw=0.5))
            axb.add_patch(Rectangle((0, 0), abs(sc["d_svf_pct"]), 1, facecolor=tone))
            dh = sc["d_winter_sun_h"]
            txt = "<0.01 h" if (dh != 0 and abs(dh) < 0.01) else "%+.2f h" % dh
            label(fig, x + cw - 0.008, y + 0.017, txt, size=8, col=tone, ha="right", weight="bold")

    # ── LEADERBOARD ─────────────────────────────────────────────────────────
    ytab_top = top
    panel_head(fig, xr0, xr1, ytab_top, "ATTRIBUTION LEADERBOARD",
               "data/attribution.json  ·  top 12 of %d" % att["metadata"]["n_buildings_ranked"])
    colx = [xr0 + 0.000, xr0 + 0.018, xr0 + 0.118, xr0 + 0.150, xr0 + 0.190, xr0 + 0.225]
    heads = ["#", "ADDRESS", "YR", "HT m", "SKY %", "WIN h"]
    has = ["left", "left", "right", "right", "right", "right"]
    y = ytab_top - 0.018
    for cx, h, ha in zip(colx, heads, has):
        label(fig, cx, y, h, size=6.2, ha=ha, weight="bold")
    rule(fig, xr0, xr1, y - 0.009)
    for r in att["leaderboard"][:12]:
        y -= 0.0225
        post = r["era"] == "post"
        col = FLAGGED if post else STEEL
        vals = [str(r["rank"]),
                display_name(labels, r["id"]),
                str(r["year"]) if r["year"] else "—",
                "%.0f" % r["height_m"],
                "%.1f" % r["sky_share_pct"],
                "%.0f" % r["winter_deckhours_stolen"]]
        for cx, v, ha in zip(colx, vals, has):
            label(fig, cx, y, v, size=6.6, col=col, ha=ha)
    y -= 0.014
    rule(fig, xr0, xr1, y)
    label(fig, xr0, y - 0.014, "red = built after the 2005 West Chelsea rezoning,", size=6)
    label(fig, xr0, y - 0.026, "the event that moved the development rights. %d such buildings"
          % cut["n"], size=6)
    label(fig, xr0, y - 0.038, "(%.1f%% of those ranked) own %.1f%% of the lost sky: %.2fx over-represented."
          % (cut["pct_of_ranked"], cut["sky_share_pct"], cut["over_representation"]), size=6)

    # ── VALIDATION ──────────────────────────────────────────────────────────
    yv = y - 0.072
    panel_head(fig, xr0, xr1, yv, "TWO INSTRUMENTS, NEITHER ADJUSTED", "data/lbt_validation.json")
    label(fig, xr0, yv - 0.018, "hl_core against an independent Ladybug recompute, 232 stations",
          size=6.2)
    yy = yv - 0.034
    for cx, h, ha in zip([xr0, xr0 + 0.120, xr0 + 0.165, xr0 + 0.225], ["", "r", "R²", "RMSE"],
                         ["left", "right", "right", "right"]):
        label(fig, cx, yy, h, size=6.2, ha=ha, weight="bold")
    rule(fig, xr0, xr1, yy - 0.009)
    for k, name, unit in (("svf_deck", "sky view factor", ""), ("sun_winter", "winter sun hours", " h"),
                          ("sun_summer", "summer sun hours", " h")):
        m = lbt[k]
        yy -= 0.021
        label(fig, xr0, yy, name, size=6.6, col=STEEL)
        label(fig, xr0 + 0.120, yy, "%+.3f" % m["r"], size=6.6, col=DETECTED, ha="right", weight="bold")
        label(fig, xr0 + 0.165, yy, "%.3f" % m["r2"], size=6.6, col=STEEL, ha="right")
        label(fig, xr0 + 0.225, yy, "%.3f%s" % (m["rmse"], unit), size=6.6, col=STEEL, ha="right")
    yy -= 0.018
    rule(fig, xr0, xr1, yy)
    m = lbt["svf_deck"]
    label(fig, xr0, yy - 0.014, "means: hl_core %.3f · Ladybug %.3f — both published raw."
          % (m["mean_mine"], m["mean_lbt"]), size=6, col=STEEL)
    label(fig, xr0, yy - 0.026, "The linear calibration between them is RETIRED and no column",
          size=6)
    label(fig, xr0, yy - 0.038, "on this board is adjusted toward the other instrument.", size=6)

    # ── DETAIL STATIONS — the measured horizon at three s ───────────────────
    ydet = bot - 0.030
    panel_head(fig, 0.045, 0.955, ydet,
               "DETAIL STATIONS  ·  the measured horizon, selected by the data",
               "data/detail_points.json  ·  exports/horizon_field.npz  ·  data/behavior_metrics.json")
    hs, hang, hbeta = hf["s"], hf["ang"], hf["beta"]
    seg_len = beh["length_m"] / beh["n_segments"]
    cases = [("A", "worst_svf", "WORST SKY VIEW"),
             ("B", "peak_congestion", "PEAK CONGESTION"),
             ("C", "best_svf", "BEST SKY VIEW")]
    dw = (0.955 - 0.045 - 2 * 0.030) / 3
    for j, (tag, key, title) in enumerate(cases):
        s_at = det[key]["s"]
        i = int(np.argmin(np.abs(hs - s_at)))
        iv = int(np.argmin(np.abs(ss - s_at)))
        x0 = 0.045 + j * (dw + 0.030)
        axp = fig.add_axes([x0 + 0.012, 0.058, 0.135, ydet - 0.118], projection="polar")
        axp.set_facecolor(PAPER)
        th = np.asarray(hang, dtype=float)   # stored in radians, 0..2π
        beta = np.degrees(np.clip(hbeta[i], 0, np.pi / 2))   # the field is stored in radians
        # radius = zenith distance of the horizon: 90 at open sky, 0 fully walled.
        # Filled from the rim inward, so what is painted red is the sky that is gone.
        rr = 90 - beta
        axp.fill_between(th, rr, 90, color=FLAGGED, alpha=0.55, lw=0)
        axp.plot(th, rr, color=STEEL, lw=0.8)
        axp.set_theta_zero_location("N"); axp.set_theta_direction(-1)
        axp.set_rlim(0, 90); axp.set_rticks([30, 60])
        axp.set_yticklabels(["60°", "30°"], fontsize=5, color=SHADE)
        axp.set_xticks(np.deg2rad([0, 90, 180, 270]))
        axp.set_xticklabels(["N", "E", "S", "W"], fontsize=5.6, color=SHADE)
        axp.tick_params(pad=1)
        axp.grid(color="#e2dfd8", lw=0.5)
        axp.spines["polar"].set_color(SHADE); axp.spines["polar"].set_linewidth(0.6)
        # text column
        tx = x0 + 0.175
        label(fig, x0, ydet - 0.024, "%s  ·  %s" % (tag, title), size=8, col=STEEL, weight="bold")
        label(fig, tx, ydet - 0.052, "s = %.1f m" % s_at, size=7, col=STEEL)
        p = vs[iv]
        label(fig, tx, ydet - 0.068, "sky view factor  %.3f" % p["svf_deck"], size=6.6, col=STEEL)
        label(fig, tx, ydet - 0.082, "pre-park at this station  %.3f" % p["svf_prepark"], size=6.2)
        label(fig, tx, ydet - 0.096, "enclosure  %.1f°  ·  openings  %d"
              % (p["enclosure_deg"], p["openings"]), size=6.2)
        label(fig, tx, ydet - 0.110, "nearest wall  %.1f m" % p["nearest_wall_m"], size=6.2)
        if key == "peak_congestion":
            k = min(int(s_at // seg_len), beh["n_segments"] - 1)
            label(fig, tx, ydet - 0.128, "seeded footfall, segment %d:  %d agents"
                  % (k, beh["ped_density"][k]), size=6.2, col=STEEL)
            label(fig, tx, ydet - 0.142, "comfort  %.2f  ·  seed %d, step %d"
                  % (beh["ped_comfort"][k], beh["seed"], beh["sim_step"]), size=6.2)
        else:
            label(fig, tx, ydet - 0.128, "horizon drawn from the cast itself —", size=6.2)
            label(fig, tx, ydet - 0.142, "red is the sky the walls take", size=6.2)

    # ── footer ──────────────────────────────────────────────────────────────
    rule(fig, 0.045, 0.955, 0.036, col=SHADE, lw=0.6)
    label(fig, 0.045, 0.026,
          "seed 42  ·  2.5-D isovist + solar geometry through hl_core, %d azimuths, %.0f m reach  ·  "
          "difference strips clipped at p99 = %.2f" % (att["metadata"]["n_azimuth"],
                                                       rm["metadata"]["max_radius_m"],
                                                       rm["metadata"]["diff_p99"]), size=6.4)
    label(fig, 0.045, 0.013,
          "every figure on this board is read from data/*.json or exports/horizon_field.npz  ·  "
          "the retired calibration columns are not used  ·  both instruments published raw", size=6.4)
    label(fig, 0.955, 0.026, "5.CV_Highline  ·  FIG 10", size=6.4, ha="right")

    p = os.path.join(OUT, "FIG10_counterfactual_board.png")
    fig.savefig(p)
    plt.close(fig)
    log("[fig10] %s" % p)
    return p


if __name__ == "__main__":
    main()
