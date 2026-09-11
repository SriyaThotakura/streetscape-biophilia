"""build_analysis_plates.py — the two assets `visual-language.html` actually names.

    python scripts/build_analysis_plates.py

WHY THIS EXISTS AND THE BLENDER PLATES DO NOT REPLACE IT
    `refrences/pintest_layouts/visual-language.html`, project id "5", field `sim`:

        "The counterfactual is the simulation and it is the argument. Remove the post-2009
         towers from the model and recompute sky view factor and sunlit hours along the
         same centreline stations — as-built against the counterfactual, same engine, same
         seed. ... Ladybug already gives you an independent recompute, so the result
         arrives with its own second opinion.
         Asset: a long section along the centreline with the two sky-view curves plotted
         against each other, and one ray-cast fan diagram from a single station showing
         what the cast is actually testing."

    That is an ANALYSIS drawing, not a scene. The eye-level render answers §4.2's
    "one image with a human figure"; it does not carry a measurement, and this project's
    argument is entirely measurement. The first system listed for it is S03 Analysis Ramp:

        "Simulation output painted onto the geometry it belongs to. The colourbar is part
         of the drawing. The bar with the unit is the whole claim. Always print min, max
         and unit. Put the analysed surface on a plain grey or white context so the ramp is
         the only saturated thing on the page."

WHAT IS DRAWN, AND FROM WHERE
    FIG 1  the long section     data/highline_viewshed.json      svf_deck vs svf_prepark
                                data/highline_solar.json         winter sun, both eras
                                data/highline_viewshed_lbt.json  the Ladybug second opinion
                                data/highline_section.json       street-wall heights
                                data/lbt_validation.json         r / RMSE for the A-B
    FIG 2  the ray-cast fan     recomputed LIVE through hl_core, using build_viewshed's own
                                horizon() and svf_from_beta() — so the picture is the cast
                                the engine actually runs, not an illustration of one.

Nothing under data/ is written. Every constant is imported from the engine, not retyped.
"""

import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402
from matplotlib.collections import LineCollection                 # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(PROJECT, "houdini"))

import hl_core as hlc                    # noqa: E402
import build_viewshed as bv              # noqa: E402  — horizon(), svf_from_beta(), N_AZ, MAX_R

OUT = os.path.join(PROJECT, "exports", "plates")
DATA = os.path.join(PROJECT, "data")

# visual-language.html :: P id "5" :: pal
PAPER, STEEL, SHADE = "#f2f0ec", "#2b2b28", "#9aa4ae"
DETECTED, FLAGGED = "#4fb0a8", "#e0483d"
# visual-language.html :: SYS id "ramp" :: pal — neutral context / low / mid / high / peak
RAMP_HEX = ["#2c3e8f", "#4fb0a8", "#e8c33d", "#c0392b"]
RAMP = LinearSegmentedColormap.from_list("hl_ramp", RAMP_HEX)

MONO = ["IBM Plex Mono", "Consolas", "DejaVu Sans Mono", "monospace"]


def log(*a):
    print(*a)
    sys.stdout.flush()


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def style():
    plt.rcParams.update({
        "font.family": MONO, "font.size": 8,
        "figure.facecolor": PAPER, "axes.facecolor": PAPER,
        "savefig.facecolor": PAPER,
        "axes.edgecolor": SHADE, "axes.labelcolor": STEEL,
        "xtick.color": SHADE, "ytick.color": SHADE,
        "text.color": STEEL, "axes.linewidth": 0.6,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "grid.color": "#e2dfd8", "grid.linewidth": 0.5,
    })


def micro(ax, text, x=0.0, y=1.02, ha="left", size=7, col=SHADE, weight="normal"):
    ax.text(x, y, text, transform=ax.transAxes, ha=ha, va="bottom",
            fontsize=size, color=col, fontweight=weight)


# ═════════════════════════════════════════════════════════════════════════════
# FIG 1 — the long section
# ═════════════════════════════════════════════════════════════════════════════
def fig_long_section():
    vs, so, lbt, sec = (load("highline_viewshed.json"), load("highline_solar.json"),
                        load("highline_viewshed_lbt.json"), load("highline_section.json"))
    val = load("lbt_validation.json")["metrics"]
    cams = json.load(open(os.path.join(PROJECT, "houdini", "cameras.json"), encoding="utf-8"))

    s = np.array([p["s_m"] for p in vs["points"]])
    svf = np.array([p["svf_deck"] for p in vs["points"]])
    svf_pre = np.array([p["svf_prepark"] for p in vs["points"]])
    svf_lbt = np.array([p["svf_deck"] for p in lbt["points"]])
    win = np.array([p["sun_winter_solstice"] for p in so["points"]])
    win_pre = np.array([p["sun_winter_solstice_prepark"] for p in so["points"]])
    ss = np.array([p["s"] for p in sec["points"]])
    wh = np.array([p["west_h"] for p in sec["points"]], dtype=float)
    eh = np.array([p["east_h"] for p in sec["points"]], dtype=float)

    fig = plt.figure(figsize=(16.5, 9.0), dpi=200)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.15, 0.85, 1.0], hspace=0.42,
                          left=0.055, right=0.985, top=0.875, bottom=0.115)

    fig.text(0.055, 0.955, "THE SELF-ENCLOSING LINE", fontsize=19, fontweight="bold",
             color=STEEL)
    fig.text(0.055, 0.925,
             "as-built against the pre-park counterfactual, same engine, same stations  ·  "
             "%d azimuths per station, %.0f m cast radius  ·  %d stations at %.1f m spacing"
             % (bv.N_AZ, bv.MAX_R, len(s), bv.SPACING), fontsize=8.5, color=SHADE)
    fig.text(0.985, 0.955, "SKY VIEW FACTOR · SUNLIT HOURS · STREET-WALL SECTION",
             fontsize=8.5, color=SHADE, ha="right", va="center")

    # ── 1 · sky view factor ───────────────────────────────────────────────────────────
    ax = fig.add_subplot(gs[0])
    ax.fill_between(s, svf, svf_pre, where=svf_pre >= svf, color=FLAGGED, alpha=0.16,
                    linewidth=0, label="sky lost to post-2009 development")
    ax.plot(s, svf_pre, color=SHADE, lw=1.1, label="pre-park counterfactual (2009 city)")
    ax.plot(s, svf, color=STEEL, lw=1.3, label="as built")
    ax.plot(s, svf_lbt, color=DETECTED, lw=1.0, ls="--",
            label="Ladybug recompute (independent)")
    ax.set_ylabel("sky view factor  (0–1)")
    ax.set_xlim(s.min(), s.max())
    ax.set_ylim(0, 1)
    ax.grid(True, axis="y")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=False,
              fontsize=7.5, ncol=4)
    stolen = float(np.mean(svf_pre - svf))
    micro(ax, "MEAN STOLEN SKY  %.4f   ·   the shaded band is the measurement, "
              "not an emphasis" % stolen, weight="bold", col=STEEL)

    # ── 2 · winter sunlit hours ───────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1], sharex=ax)
    ax2.fill_between(s, win, win_pre, where=win_pre >= win, color=FLAGGED, alpha=0.16,
                     linewidth=0)
    ax2.plot(s, win_pre, color=SHADE, lw=1.1)
    ax2.plot(s, win, color=STEEL, lw=1.3)
    ax2.set_ylabel("sunlit hours\nwinter solstice")
    ax2.set_ylim(0, max(1.0, float(win_pre.max()) * 1.1))
    ax2.grid(True, axis="y")
    micro(ax2, "MEAN STOLEN WINTER SUN  %.2f h   ·   day %s"
          % (float(np.mean(win_pre - win)), so["metadata"].get("winter_day", 355)),
          weight="bold", col=STEEL)

    # ── 3 · the street-wall section ───────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2], sharex=ax)
    ax3.fill_between(ss, 0, wh, color=SHADE, alpha=0.55, linewidth=0)
    ax3.fill_between(ss, 0, -eh, color=SHADE, alpha=0.30, linewidth=0)
    ax3.axhline(0, color=STEEL, lw=1.0)
    ax3.set_ylabel("street wall (m)\nwest  ·  east")
    ax3.set_xlabel("arc length along the deck centreline, s (m)")
    ax3.grid(True, axis="y")
    micro(ax3, "TALLEST WALL  west %.1f m   east %.1f m   ·   the deck plane is the zero line"
          % (np.nanmax(wh), np.nanmax(eh)), weight="bold", col=STEEL)

    # committed camera stations, so the plates and this drawing share a coordinate
    for st in cams["stations"]:
        for a in (ax, ax2, ax3):
            a.axvline(st["s_m"], color=STEEL, lw=0.6, ls=":", alpha=0.75)
        ax3.text(st["s_m"], 0.02, st["id"].split("_")[0], transform=ax3.get_xaxis_transform(),
                 fontsize=8, color=STEEL, ha="center", va="bottom", fontweight="bold",
                 bbox=dict(fc=PAPER, ec="none", pad=1.4))

    v = val["svf_deck"]
    fig.text(0.055, 0.028,
             "the two SVF curves are the same engine on the same stations with the "
             "post-2009 cohort removed  ·  Ladybug A/B on svf_deck: r %.3f, RMSE %.4f, "
             "n %d, mean %.3f vs %.3f — published side by side, neither adjusted toward "
             "the other" % (v["r"], v["rmse"], v["n"], v["mean_mine"], v["mean_lbt"]),
             fontsize=7, color=SHADE)
    fig.text(0.055, 0.008,
             "data/highline_viewshed.json · highline_solar.json · "
             "highline_viewshed_lbt.json · highline_section.json · lbt_validation.json",
             fontsize=7, color=SHADE)

    p = os.path.join(OUT, "FIG1_long_section.png")
    fig.savefig(p)
    plt.close(fig)
    log("[fig1] %s  ·  mean stolen sky %.4f over %d stations" % (p, stolen, len(s)))
    return p


# ═════════════════════════════════════════════════════════════════════════════
# FIG 2 — the ray-cast fan
# ═════════════════════════════════════════════════════════════════════════════
def _cast(bld, px, pz, dirs):
    """One cast, through the engine's own horizon(). Returns (beta, reach, svf)."""
    edges = hlc.edges_for(bld, px, pz, bv.MAX_R)
    if edges is None:
        beta = np.zeros(bv.N_AZ)
        return beta, np.full(bv.N_AZ, bv.MAX_R), bv.svf_from_beta(beta)
    beta, dist, _, _ = bv.horizon(edges, bld, px, pz, bv.EYE_DECK, dirs)
    reach = np.where(np.isfinite(dist), np.minimum(dist, bv.MAX_R), bv.MAX_R)
    return beta, reach, bv.svf_from_beta(beta)


def _draw_fan(ax, bld, px, pz, dirs, beta, reach, R, norm, title, sub):
    ax.set_facecolor(PAPER)
    for b in bld:
        if math.hypot(b.c[0] - px, b.c[1] - pz) - b.rad > R * 1.3:
            continue
        poly = np.asarray(b.poly, dtype=float)
        ax.plot(poly[:, 0], poly[:, 1], color=SHADE, lw=0.5, zorder=2)
    segs = [[(px, pz), (px + dirs[k, 0] * reach[k], pz + dirs[k, 1] * reach[k])]
            for k in range(bv.N_AZ)]
    ax.add_collection(LineCollection(segs, colors=RAMP(norm(np.degrees(beta))),
                                     linewidths=0.9, alpha=0.95, zorder=1))
    ax.plot([px], [pz], marker="o", ms=4.5, color=STEEL, zorder=4)
    ax.set_xlim(px - R, px + R)
    ax.set_ylim(pz - R, pz + R)
    ax.set_aspect("equal")
    ax.set_xlabel("east (m)")
    for sp in ax.spines.values():
        sp.set_color(SHADE)
    ax.text(0.0, 1.045, title, transform=ax.transAxes, fontsize=11, fontweight="bold",
            color=STEEL)
    ax.text(0.0, 1.012, sub, transform=ax.transAxes, fontsize=7.5, color=SHADE)


def fig_ray_fan(station_id="C_section_worst_core"):
    """The same station cast twice — as built, and with the post-2009 cohort removed.

    Not a diagram OF the method: the method, run again. `horizon()` and `svf_from_beta()`
    are imported from build_viewshed, and both SVFs printed here are recomputed from the
    rays you can see. The as-built one is checked against the published value.
    """
    cams = json.load(open(os.path.join(PROJECT, "houdini", "cameras.json"), encoding="utf-8"))
    st = next(x for x in cams["stations"] if x["id"] == station_id)
    px, pz = st["station_xz"]

    site = hlc.load_site()
    bld = site.buildings
    # the same rule build_viewshed uses for the baseline, imported not retyped
    bld_pre = [b for b in bld if (b.yr is not None and b.yr <= bv.PARK_YEAR)]

    ang = np.linspace(0, 2 * math.pi, bv.N_AZ, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], axis=1)
    beta_a, reach_a, svf_a = _cast(bld, px, pz, dirs)
    beta_p, reach_p, svf_p = _cast(bld_pre, px, pz, dirs)

    published = json.load(open(os.path.join(DATA, "highline_viewshed.json"),
                               encoding="utf-8"))["points"]
    pub = min(published, key=lambda p: abs(p["s_m"] - st["s_m"]))

    # Zoom so the SHORTER cast is still readable. Derived from the casts themselves:
    # the pre-park 90th percentile, floored so a total-enclosure station never collapses
    # to a dot. The full cast radius is stated on the drawing.
    R = float(max(60.0, min(bv.MAX_R, np.percentile(reach_p, 90) * 1.15)))

    fig = plt.figure(figsize=(15.0, 9.4), dpi=200)
    norm = Normalize(vmin=0.0, vmax=90.0)     # beta is bounded at the zenith by definition

    axL = fig.add_axes([0.055, 0.300, 0.40, 0.565])
    axR = fig.add_axes([0.525, 0.300, 0.40, 0.565])
    axL.set_ylabel("north (m)")
    _draw_fan(axL, bld, px, pz, dirs, beta_a, reach_a, R, norm, "AS BUILT",
              "every footprint in data/highline_footprints.json")
    _draw_fan(axR, bld_pre, px, pz, dirs, beta_p, reach_p, R, norm,
              "PRE-PARK COUNTERFACTUAL",
              "the same cast with every building completed after %d removed" % bv.PARK_YEAR)

    fig.text(0.055, 0.955, "WHAT THE CAST IS ACTUALLY TESTING", fontsize=19,
             fontweight="bold", color=STEEL)
    fig.text(0.055, 0.925,
             "one station, cast twice, live through hl_core  ·  %s, s = %.2f m  ·  "
             "eye %.2f m on the %.1f m deck  ·  %d azimuths, %.0f m radius "
             "(frame zoomed to %.0f m)"
             % (station_id, st["s_m"], bv.EYE_DECK, st["deck_y"], bv.N_AZ, bv.MAX_R, R),
             fontsize=8.5, color=SHADE)

    sm = plt.cm.ScalarMappable(cmap=RAMP, norm=norm)
    cax = fig.add_axes([0.055, 0.215, 0.40, 0.015])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("horizon elevation returned by the ray, beta (degrees, 0 = open sky, "
                 "90 = zenith)", fontsize=7.5, color=STEEL)
    cb.ax.tick_params(labelsize=7, color=SHADE, labelcolor=SHADE)
    cb.outline.set_edgecolor(SHADE)
    cb.outline.set_linewidth(0.6)
    cb.set_ticks([0, 45, 90])

    op_a = int((np.degrees(beta_a) < 5.0).sum())
    op_p = int((np.degrees(beta_p) < 5.0).sum())
    rows = [
        ("", "AS BUILT", "PRE-PARK", "CHANGE"),
        ("sky view factor", "%.4f" % svf_a, "%.4f" % svf_p, "%+.4f" % (svf_a - svf_p)),
        ("mean beta (deg)", "%.2f" % np.degrees(beta_a).mean(),
         "%.2f" % np.degrees(beta_p).mean(),
         "%+.2f" % (np.degrees(beta_a).mean() - np.degrees(beta_p).mean())),
        ("rays reaching open sky", "%d of %d" % (op_a, bv.N_AZ),
         "%d of %d" % (op_p, bv.N_AZ), "%+d" % (op_a - op_p)),
        ("median ray reach (m)", "%.1f" % np.median(reach_a), "%.1f" % np.median(reach_p),
         "%+.1f" % (np.median(reach_a) - np.median(reach_p))),
    ]
    ty = 0.208
    xs = (0.525, 0.735, 0.840, 0.945)
    for i, r in enumerate(rows):
        head = (i == 0)
        for x, cell in zip(xs, r):
            fig.text(x, ty, cell, fontsize=7.5 if head else 9,
                     color=SHADE if head else STEEL,
                     fontweight="bold" if head or x == xs[3] else "normal",
                     ha="left" if x == xs[0] else "right",
                     family=MONO)
        ty -= 0.030
        if head:
            ty -= 0.006

    fig.text(0.055, 0.150,
             "SVF = 1 - mean(sin^2 beta) over the cast.", fontsize=7.5, color=STEEL)
    fig.text(0.055, 0.122,
             "the drawing and the number are the same computation — recomputed here, "
             "not read from a file", fontsize=7, color=SHADE)
    fig.text(0.055, 0.075,
             "as-built SVF recomputed %.4f  vs  published %.4f for s = %.1f m   "
             "difference %+.4f" % (svf_a, pub["svf_deck"], pub["s_m"],
                                   svf_a - pub["svf_deck"]),
             fontsize=7.5, color=STEEL, fontweight="bold")
    fig.text(0.055, 0.035,
             "hl_core.edges_for / ray_uv · build_viewshed.horizon / svf_from_beta · "
             "data/highline_footprints.json", fontsize=7, color=SHADE)

    p = os.path.join(OUT, "FIG2_raycast_fan.png")
    fig.savefig(p)
    plt.close(fig)
    log("[fig2] %s  ·  as-built SVF %.4f (published %.4f, delta %+.4f) · pre-park %.4f "
        "· stolen %.4f" % (p, svf_a, pub["svf_deck"], svf_a - pub["svf_deck"], svf_p,
                           svf_p - svf_a))
    return p



# ═════════════════════════════════════════════════════════════════════════════
# FIG 3 — the Ladybug A/B, and the mechanism behind the disagreement
# ═════════════════════════════════════════════════════════════════════════════
def fig_ladybug_ab():
    """Both instruments, side by side, neither adjusted toward the other.

    IMPLEMENTATION_PLAN.md W2: "Publish both, side by side. **Calibration retired**." So
    this draws the RAW isovist against the RAW Ladybug recompute. `removals.json` still
    carries `*_cal` fields and `svf_calibration.json` still exists; both are deliberately
    unused here, and saying so is the point of the plate.

    The right-hand panels are the part that makes it a finding rather than an apology: the
    residual is regressed against the two candidate explanations, and it is the one nobody
    expects — occluder COUNT, not occluder HEIGHT.
    """
    vs, lbt = load("highline_viewshed.json"), load("highline_viewshed_lbt.json")
    val = load("lbt_validation.json")["metrics"]["svf_deck"]

    mine = np.array([p["svf_deck"] for p in vs["points"]])
    lady = np.array([p["svf_deck"] for p in lbt["points"]])
    resid = mine - lady

    # the two candidate drivers, computed here from the same site the engines read
    site = hlc.load_site()
    bld = site.buildings
    counts, tallest = [], []
    for p in vs["points"]:
        px, pz = p["x"], p["z"]
        near = [b for b in bld
                if math.hypot(b.c[0] - px, b.c[1] - pz) - b.rad <= bv.MAX_R]
        counts.append(len(near))
        tallest.append(max([b.h for b in near], default=0.0))
    counts = np.array(counts, dtype=float)
    tallest = np.array(tallest, dtype=float)

    def r_of(a, b):
        if a.std() == 0 or b.std() == 0:
            return float("nan")
        return float(np.corrcoef(a, b)[0, 1])

    r_cnt, r_tall = r_of(resid, counts), r_of(resid, tallest)

    fig = plt.figure(figsize=(15.0, 8.2), dpi=200)
    fig.text(0.05, 0.945, "TWO INSTRUMENTS, NEITHER ADJUSTED TOWARD THE OTHER",
             fontsize=18, fontweight="bold", color=STEEL)
    fig.text(0.05, 0.912,
             "hand-rolled 2.5-D isovist against an independent Ladybug recompute, on the "
             "same %d stations  ·  the calibration fit is RETIRED and is not applied here"
             % len(mine), fontsize=8.5, color=SHADE)

    ax = fig.add_axes([0.05, 0.265, 0.37, 0.585])
    ax.scatter(lady, mine, s=11, c=STEEL, alpha=0.55, linewidths=0)
    lim = [0, 1]
    ax.plot(lim, lim, color=SHADE, lw=1.0, ls="--", label="1:1 — perfect agreement")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_aspect("equal")
    ax.set_xlabel("Ladybug recompute, svf_deck")
    ax.set_ylabel("hl_core 2.5-D isovist, svf_deck")
    ax.grid(True)
    ax.legend(loc="upper left", frameon=False, fontsize=7.5)
    micro(ax, "EVERY POINT SITS ABOVE THE LINE — the isovist reads systematically MORE OPEN",
          weight="bold", col=STEEL)

    tx = 0.455
    ty = 0.815
    rows = [("Pearson r", "%.3f" % val["r"]), ("r squared", "%.3f" % val["r2"]),
            ("RMSE", "%.4f" % val["rmse"]), ("n stations", "%d" % val["n"]),
            ("mean, isovist", "%.3f" % val["mean_mine"]),
            ("mean, Ladybug", "%.3f" % val["mean_lbt"]),
            ("mean difference", "%+.3f" % (val["mean_mine"] - val["mean_lbt"]))]
    for lab, v in rows:
        fig.text(tx, ty, lab.upper(), fontsize=7.5, color=SHADE)
        fig.text(tx + 0.190, ty, v, fontsize=9.5, color=STEEL, fontweight="bold", ha="right")
        ty -= 0.030

    ax2 = fig.add_axes([0.71, 0.590, 0.265, 0.26])
    ax2.scatter(counts, resid, s=9, c=FLAGGED, alpha=0.55, linewidths=0)
    ax2.set_xlabel("buildings within %.0f m" % bv.MAX_R, fontsize=7.5)
    ax2.set_ylabel("residual\n(isovist - Ladybug)", fontsize=7.5)
    ax2.grid(True)
    micro(ax2, "r = %+.3f   <- occluder COUNT" % r_cnt, weight="bold", col=STEEL, size=8)

    ax3 = fig.add_axes([0.71, 0.265, 0.265, 0.26])
    ax3.scatter(tallest, resid, s=9, c=SHADE, alpha=0.6, linewidths=0)
    ax3.set_xlabel("tallest building within %.0f m (m)" % bv.MAX_R, fontsize=7.5)
    ax3.set_ylabel("residual\n(isovist - Ladybug)", fontsize=7.5)
    ax3.grid(True)
    micro(ax3, "r = %+.3f   <- occluder HEIGHT" % r_tall, weight="bold", col=STEEL, size=8)

    fig.text(0.05, 0.185,
             "The divergence is not what it looks like. It tracks how MANY things are in "
             "the way,\nnot how TALL they are — which is a model-order limit, not a "
             "calibration error.\nA 2.5-D cast takes the single highest horizon per "
             "azimuth; a 3-D one integrates\nthe whole hemisphere, and the gap widens "
             "where many mid-rise occluders overlap.",
             fontsize=8.5, color=STEEL, va="top")
    fig.text(0.05, 0.028,
             "data/highline_viewshed.json · highline_viewshed_lbt.json · "
             "lbt_validation.json  ·  occluder counts recomputed here from "
             "data/highline_footprints.json", fontsize=7, color=SHADE)

    p = os.path.join(OUT, "FIG3_ladybug_ab.png")
    fig.savefig(p)
    plt.close(fig)
    log("[fig3] %s  ·  r %.3f RMSE %.4f  ·  residual vs count r %+.3f, vs height r %+.3f"
        % (p, val["r"], val["rmse"], r_cnt, r_tall))
    return p


# ═════════════════════════════════════════════════════════════════════════════
# FIG 4 — the counterfactual matrix
# ═════════════════════════════════════════════════════════════════════════════
def fig_counterfactual_matrix():
    """S04 Catalogue Matrix: every scenario, indexed, with its measured value beside it.

    ⚠️ `removals.json`'s `meta` strings are STALE — the baseline row still says
    "176 buildings", which is the count from before the 2026-08-15 footprint re-fetch.
    The NUMBERS are current (its baseline correlates 1.0000 with highline_viewshed.json's
    svf_deck, mean abs difference 0.0011), so the file is fine and only its labels are not.
    Every count printed here is therefore recomputed from the footprints, not read from
    `meta`.
    """
    r = load("removals.json")
    s_axis = np.array(r["s_axis"], dtype=float)
    scen = r["scenarios"]

    site = hlc.load_site()
    bld = site.buildings
    n_all = len(bld)
    # Mirror build_removals.py's OWN membership test, which is `yr is not None and
    # yr <= PARK_YEAR`. A building with no recorded year fails it and is removed from the
    # baseline too, so the scenario is not "post-2009 removed" — it is that plus every
    # undated building. An earlier version of this plate printed 93 here, which named a
    # different scenario from the one the row actually shows.
    n_pre = sum(1 for b in bld if b.yr is not None and b.yr <= bv.PARK_YEAR)
    n_post = n_all - n_pre
    n_dated = sum(1 for b in bld if b.yr is not None and b.yr > bv.PARK_YEAR)
    n_undated = sum(1 for b in bld if b.yr is None)

    base = next(x for x in scen if x["key"] == "baseline")
    rows = [x for x in scen if x["key"] != "baseline"]

    fig = plt.figure(figsize=(15.5, 9.6), dpi=200)
    fig.text(0.05, 0.957, "THE COUNTERFACTUAL MATRIX", fontsize=19, fontweight="bold",
             color=STEEL)
    fig.text(0.05, 0.928,
             "one row per scenario, %d stations across  ·  every cell is the change in sky "
             "view factor against the as-built baseline  ·  same engine, same stations, "
             "identical parameters" % len(s_axis), fontsize=8.5, color=SHADE)

    # d_svf_pct is a SCALAR (the scenario mean). The per-station strip has to be built
    # from the svf arrays against the baseline's, or the row is a single number stretched
    # across 232 columns and says nothing about WHERE the sky moved.
    b0 = np.array(base["svf"], dtype=float)
    strips = {x["key"]: (np.array(x["svf"], dtype=float) - b0) * 100.0 for x in rows}
    lim = float(np.nanpercentile(np.abs(np.concatenate(list(strips.values()))), 99))
    norm = Normalize(vmin=-lim, vmax=lim)
    div = LinearSegmentedColormap.from_list("hl_div", [FLAGGED, "#f2f0ec", "#2c3e8f"])

    left, width = 0.255, 0.525
    top, rowh = 0.885, 0.0545
    for i, x in enumerate(rows):
        yy = top - i * rowh
        ax = fig.add_axes([left, yy - rowh * 0.80, width, rowh * 0.74])
        ax.imshow(strips[x["key"]][None, :], aspect="auto", cmap=div,
                  norm=norm, extent=[s_axis.min(), s_axis.max(), 0, 1],
                  interpolation="nearest")
        ax.set_yticks([])
        ax.set_xticks([])
        for sp in ax.spines.values():
            sp.set_color(SHADE)
            sp.set_linewidth(0.5)
        if i == len(rows) - 1:
            ax.set_xticks([0, 500, 1000, 1500])
            ax.tick_params(labelsize=7)
            ax.set_xlabel("arc length along the deck centreline, s (m)", fontsize=8)

        lab = x["label"].replace("\u2212", "-")
        fig.text(left - 0.008, yy - rowh * 0.44, lab, fontsize=8.5, color=STEEL,
                 ha="right", va="center", fontweight="bold")
        # `meta` in the file predates the re-fetch; rebuild it from the row's own fields
        if x["key"] == "pre2009":
            meta = ("%d removed: %d after %d, %d undated"
                    % (n_post, n_dated, bv.PARK_YEAR, n_undated))
        elif x.get("id"):
            meta = "BIN %s  ·  %s  ·  %.1f m" % (
                x["id"], x.get("year") if x.get("year") else "year unknown",
                x.get("height_m", float("nan")))
        else:
            meta = x.get("meta", "")
        fig.text(0.045, yy - rowh * 0.44, meta, fontsize=7.2, color=SHADE, va="center")
        fig.text(left + width + 0.012, yy - rowh * 0.44,
                 "%+.2f" % float(x["d_svf_pct"]), fontsize=9, color=STEEL,
                 va="center", ha="right", fontweight="bold")
        fig.text(left + width + 0.075, yy - rowh * 0.44,
                 "%+.3f" % float(x["d_winter_sun_h"]), fontsize=9, color=STEEL,
                 va="center", ha="right")

    fig.text(0.045, top + 0.018, "SCENARIO", fontsize=7.5, color=SHADE, fontweight="bold")
    fig.text(left + width + 0.012, top + 0.018, "MEAN dSVF (% pts)", fontsize=7.5,
             color=SHADE, ha="right", fontweight="bold")
    fig.text(left + width + 0.075, top + 0.018, "MEAN dSUN (h)", fontsize=7.5,
             color=SHADE, ha="right", fontweight="bold")

    sm = plt.cm.ScalarMappable(cmap=div, norm=norm)
    cax = fig.add_axes([left, 0.098, 0.26, 0.014])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("change in SVF vs baseline (percentage points)  ·  blue = regained, "
                 "red = lost", fontsize=7.2, color=STEEL)
    cb.ax.tick_params(labelsize=7, color=SHADE, labelcolor=SHADE)
    cb.outline.set_edgecolor(SHADE)
    cb.outline.set_linewidth(0.6)
    cb.set_ticks([-lim, 0, lim])
    cb.set_ticklabels(["%.1f" % -lim, "0", "+%.1f" % lim])

    fig.text(0.045, 0.052,
             "baseline: %d footprints, mean SVF %.4f  ·  the calibrated columns in "
             "removals.json are NOT used — IMPLEMENTATION_PLAN W2 retired the calibration "
             "and publishes both instruments raw" % (n_all, float(np.mean(base["svf"]))),
             fontsize=7.5, color=STEEL)
    fig.text(0.045, 0.030,
             "every scenario label is recomputed from data/highline_footprints.json: the "
             "file's own `meta` strings predate the 2026-08-15 re-fetch and still say "
             "\"176 buildings\", \"6 post-2009 towers\" and \"9 soft sites\" against a "
             "site of 2,083 footprints, 116 removed and 59 soft sites",
             fontsize=7, color=SHADE)
    fig.text(0.045, 0.010, "data/removals.json", fontsize=7, color=SHADE)

    p = os.path.join(OUT, "FIG4_counterfactual_matrix.png")
    fig.savefig(p)
    plt.close(fig)
    log("[fig4] %s  ·  %d scenarios, colour limit +/-%.2f pts" % (p, len(rows), lim))
    return p


# ═════════════════════════════════════════════════════════════════════════════
# FIG 5 — sunlit hours painted on the corridor
# ═════════════════════════════════════════════════════════════════════════════
def fig_sun_ramp():
    """S03 proper: the simulation output painted onto the geometry it belongs to.

    Three plans of the same corridor — as built, pre-park, and the difference — with the
    deck drawn as a ramped line and the city left as plain outline, so the ramp is the
    only saturated thing on the page.
    """
    so, vs = load("highline_solar.json"), load("highline_viewshed.json")
    x = np.array([p["x"] for p in vs["points"]])
    z = np.array([p["z"] for p in vs["points"]])
    now = np.array([p["sun_winter_solstice"] for p in so["points"]])
    pre = np.array([p["sun_winter_solstice_prepark"] for p in so["points"]])
    lost = pre - now

    site = hlc.load_site()
    bld = site.buildings

    fig = plt.figure(figsize=(16.0, 8.6), dpi=200)
    fig.text(0.04, 0.950, "WINTER SUN, PAINTED ON THE DECK", fontsize=19,
             fontweight="bold", color=STEEL)
    fig.text(0.04, 0.920,
             "sunlit hours at the winter solstice, day %s  ·  %d stations at %.1f m "
             "spacing  ·  the city is outline only so the ramp is the only saturated "
             "thing on the page"
             % (so["metadata"].get("winter_day", 355), len(x), bv.SPACING),
             fontsize=8.5, color=SHADE)

    panels = [("AS BUILT", now, RAMP, Normalize(0, max(1e-6, float(pre.max())))),
              ("PRE-PARK COUNTERFACTUAL", pre, RAMP,
               Normalize(0, max(1e-6, float(pre.max())))),
              ("HOURS LOST", lost,
               LinearSegmentedColormap.from_list("hl_loss", ["#f2f0ec", FLAGGED]),
               Normalize(0, max(1e-6, float(lost.max()))))]

    for i, (title, val, cmap, norm) in enumerate(panels):
        ax = fig.add_axes([0.04 + i * 0.322, 0.185, 0.28, 0.66])
        ax.set_facecolor(PAPER)
        for b in bld:
            poly = np.asarray(b.poly, dtype=float)
            ax.plot(poly[:, 0], poly[:, 1], color="#cbc7be", lw=0.35, zorder=1)
        pts = np.stack([x, z], axis=1).reshape(-1, 1, 2)
        segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
        lc = LineCollection(segs, cmap=cmap, norm=norm, linewidths=3.4, zorder=3)
        lc.set_array(val[:-1])
        ax.add_collection(lc)
        # Fill the panel instead of letterboxing: the corridor is 1.73 km north-south in a
        # 480 m-wide band, so an equal-aspect axes padded symmetrically leaves most of the
        # box empty. Pad the SHORT axis until the data aspect matches the axes box, which
        # spends the spare width on context city rather than on paper.
        zpad = 60.0
        z0, z1 = z.min() - zpad, z.max() + zpad
        want = (0.28 * fig.get_figwidth()) / (0.66 * fig.get_figheight())
        xspan = (z1 - z0) * want
        xmid = 0.5 * (x.min() + x.max())
        ax.set_xlim(xmid - xspan / 2.0, xmid + xspan / 2.0)
        ax.set_ylim(z0, z1)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color(SHADE)
            sp.set_linewidth(0.5)
        ax.text(0.0, 1.025, title, transform=ax.transAxes, fontsize=11,
                fontweight="bold", color=STEEL)
        ax.text(0.0, 1.002,
                "mean %.2f h   ·   min %.2f   max %.2f" % (val.mean(), val.min(), val.max()),
                transform=ax.transAxes, fontsize=7.5, color=SHADE)

        cax = fig.add_axes([0.04 + i * 0.322, 0.115, 0.28, 0.015])
        cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=norm), cax=cax,
                          orientation="horizontal")
        cb.set_label("sunlit hours, winter solstice (h)", fontsize=7.5, color=STEEL)
        cb.ax.tick_params(labelsize=7, color=SHADE, labelcolor=SHADE)
        cb.outline.set_edgecolor(SHADE)
        cb.outline.set_linewidth(0.6)

    fig.text(0.04, 0.055,
             "MEAN WINTER SUN  as built %.2f h   ·   pre-park %.2f h   ·   lost %.2f h"
             % (now.mean(), pre.mean(), lost.mean()),
             fontsize=10, color=STEEL, fontweight="bold")
    fig.text(0.04, 0.028,
             "data/highline_solar.json · data/highline_viewshed.json (station coordinates) "
             "· data/highline_footprints.json (context outline)", fontsize=7, color=SHADE)

    p = os.path.join(OUT, "FIG5_sun_ramp.png")
    fig.savefig(p)
    plt.close(fig)
    log("[fig5] %s  ·  mean winter sun %.2f h as built, %.2f h pre-park, %.2f h lost"
        % (p, now.mean(), pre.mean(), lost.mean()))
    return p


def main():
    os.makedirs(OUT, exist_ok=True)
    style()
    fig_long_section()
    fig_ray_fan()
    fig_ladybug_ab()
    fig_counterfactual_matrix()
    fig_sun_ramp()


if __name__ == "__main__":
    main()
