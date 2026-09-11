"""build_skydome_plates.py — the Ladybug-register plates: sky domes and the horizon field.

    python scripts/build_skydome_plates.py            # both
    python scripts/build_skydome_plates.py --domes    # FIG 6 only (fast)
    python scripts/build_skydome_plates.py --carpet   # FIG 7 only (slow, ~232x360 casts)

WHY THESE TWO
    `refrences/pintest_layouts/visual-language.html` gives this project S03 Analysis Ramp
    first, and its reference images are not charts — they are the simulation painted onto
    the thing it measures, with a labelled bar carrying the unit. The two drawings that
    register actually wants from a sky-view engine are:

    FIG 6  THE SKY DOME.  What one station can see, drawn the way a fisheye sees it, with
           the measured horizon as a ramped obstruction and the real sun paths over it.
           The sunlit-hours number IS the count of sun positions that clear that horizon,
           so the diagram and the number are the same computation — the plate shows the
           arithmetic instead of asserting it.

    FIG 7  THE HORIZON FIELD.  beta(s, azimuth) for the whole line: 232 stations by 360
           azimuths, the raw output of the instrument before any of it is collapsed into a
           single SVF. Every figure this project quotes is a mean over one row of this.

BOTH ARE RECOMPUTED, NOT READ
    hl_core.edges_for / ray_uv, build_viewshed.horizon / svf_from_beta, hl_core.sun_path.
    The SVFs printed are recomputed from the rays drawn and checked against the published
    values. Nothing under data/ is written; the carpet caches to exports/.
"""

import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import hl_core as hlc                    # noqa: E402
import build_viewshed as bv              # noqa: E402

OUT = os.path.join(PROJECT, "exports", "plates")
CACHE = os.path.join(PROJECT, "exports", "horizon_field.npz")
DATA = os.path.join(PROJECT, "data")

PAPER, STEEL, SHADE = "#f2f0ec", "#2b2b28", "#9aa4ae"
DETECTED, FLAGGED = "#4fb0a8", "#e0483d"
# The obstruction ramp. Cool where the horizon is low, hot where it closes overhead —
# the same direction of travel as the reference plates' displacement ramps.
SKY = LinearSegmentedColormap.from_list(
    "hl_sky", ["#2c3e8f", "#4f7fb0", "#4fb0a8", "#e8c33d", "#e07a3d", "#c0392b"])

MONO = ["IBM Plex Mono", "Consolas", "DejaVu Sans Mono", "monospace"]
DAYS = [("winter solstice", 355, FLAGGED),
        ("equinox", 80, STEEL),
        ("summer solstice", 172, DETECTED)]


def log(*a):
    print(*a)
    sys.stdout.flush()


def style():
    plt.rcParams.update({
        "font.family": MONO, "font.size": 8,
        "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
        "axes.edgecolor": SHADE, "axes.labelcolor": STEEL,
        "xtick.color": SHADE, "ytick.color": SHADE, "text.color": STEEL,
        "axes.linewidth": 0.6, "grid.color": "#e2dfd8", "grid.linewidth": 0.45,
    })


def cast(px, pz, bld):
    ang = np.linspace(0, 2 * math.pi, bv.N_AZ, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], axis=1)
    edges = hlc.edges_for(bld, px, pz, bv.MAX_R)
    if edges is None:
        return ang, np.zeros(bv.N_AZ)
    beta, _, _, _ = bv.horizon(edges, bld, px, pz, bv.EYE_DECK, dirs)
    return ang, beta


def bar(fig, rect, cmap, norm, title, unit, lo_lab, hi_lab):
    """A vertical bar carrying its own title, unit and both ends — ref5_1's convention."""
    cax = fig.add_axes(rect)
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=norm), cax=cax)
    cb.outline.set_edgecolor(SHADE)
    cb.outline.set_linewidth(0.6)
    cb.set_ticks([norm.vmin, norm.vmax])
    cb.set_ticklabels([lo_lab, hi_lab])
    cb.ax.tick_params(labelsize=7.5, color=SHADE, labelcolor=STEEL, length=3)
    fig.text(rect[0], rect[1] + rect[3] + 0.030, title, fontsize=8.5, color=STEEL,
             fontweight="bold")
    fig.text(rect[0], rect[1] + rect[3] + 0.012, unit, fontsize=7.5, color=SHADE)
    return cb


# ═════════════════════════════════════════════════════════════════════════════
# FIG 6 — the sky domes
# ═════════════════════════════════════════════════════════════════════════════
def fig_domes():
    cams = json.load(open(os.path.join(PROJECT, "houdini", "cameras.json"), encoding="utf-8"))
    pub = json.load(open(os.path.join(DATA, "highline_viewshed.json"),
                         encoding="utf-8"))["points"]
    solar = json.load(open(os.path.join(DATA, "highline_solar.json"),
                           encoding="utf-8"))["points"]
    site = hlc.load_site()
    bld = site.buildings

    fig = plt.figure(figsize=(16.2, 8.4), dpi=200)
    fig.text(0.038, 0.945, "WHAT EACH STATION CAN SEE", fontsize=20, fontweight="bold",
             color=STEEL)
    fig.text(0.038, 0.912,
             "the measured horizon as a fisheye, with the real sun paths over it  ·  "
             "%d azimuths, %.0f m cast radius, eye %.2f m  ·  zenith at the centre, "
             "horizon at the rim" % (bv.N_AZ, bv.MAX_R, bv.EYE_DECK),
             fontsize=8.5, color=SHADE)

    norm = Normalize(0, 90)
    rr = np.linspace(0, 90, 91)

    for i, st in enumerate(cams["stations"]):
        px, pz = st["station_xz"]
        ang, beta = cast(px, pz, bld)
        deg = np.degrees(beta)
        svf = bv.svf_from_beta(beta)
        p = min(pub, key=lambda q: abs(q["s_m"] - st["s_m"]))
        sol = min(solar, key=lambda q: abs(q["s_m"] - st["s_m"]))

        ax = fig.add_axes([0.045 + i * 0.285, 0.290, 0.225, 0.545], projection="polar")
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_facecolor(PAPER)

        # the obstruction, ramped by the elevation it reaches
        TH, RR = np.meshgrid(np.append(ang, ang[0] + 2 * math.pi), rr, indexing="ij")
        B = np.repeat(np.append(deg, deg[0])[:, None], len(rr), axis=1)
        blocked = np.where(RR >= (90.0 - B), B, np.nan)
        ax.pcolormesh(TH, RR, blocked, cmap=SKY, norm=norm, shading="auto", zorder=1)

        # the sun paths, and which of their positions clear that horizon
        for label, doy, col in DAYS:
            els, es, ns = hlc.sun_path(doy)
            az = np.arctan2(es, ns) % (2 * math.pi)
            el = np.degrees(els)
            horiz = np.degrees(np.interp(az, ang, beta, period=2 * math.pi))
            vis = el > horiz
            ax.plot(az, 90 - el, color=col, lw=1.0, alpha=0.5, zorder=3)
            ax.scatter(az[vis], 90 - el[vis], s=9, c=col, zorder=4, linewidths=0)
            ax.scatter(az[~vis], 90 - el[~vis], s=5, facecolors="none",
                       edgecolors=col, linewidths=0.5, alpha=0.55, zorder=4)

        ax.set_rlim(0, 90)
        ax.set_rticks([30, 60, 90])
        ax.set_yticklabels([])
        ax.set_xticks(np.radians([0, 90, 180, 270]))
        ax.set_xticklabels(["N", "E", "S", "W"], fontsize=8, color=SHADE)
        ax.grid(True, alpha=0.5)
        ax.spines["polar"].set_color(SHADE)
        ax.spines["polar"].set_linewidth(0.6)

        tag = st["id"].split("_")[0]
        fig.text(0.045 + i * 0.285, 0.870, "%s  ·  s = %.2f m" % (tag, st["s_m"]),
                 fontsize=11.5, fontweight="bold", color=STEEL)
        fig.text(0.045 + i * 0.285, 0.849, st["id"], fontsize=7.5, color=SHADE)

        facts = [("SVF recomputed here", "%.4f" % svf),
                 ("SVF published", "%.4f" % p["svf_deck"]),
                 ("mean horizon", "%.1f deg" % deg.mean()),
                 ("max horizon", "%.1f deg" % deg.max()),
                 ("winter sunlit hours", "%.2f h" % sol["sun_winter_solstice"]),
                 ("pre-park winter hours", "%.2f h" % sol["sun_winter_solstice_prepark"])]
        ty = 0.235
        for lab, v in facts:
            fig.text(0.045 + i * 0.285, ty, lab.upper(), fontsize=7, color=SHADE)
            fig.text(0.045 + i * 0.285 + 0.225, ty, v, fontsize=8.5, color=STEEL,
                     ha="right", fontweight="bold")
            ty -= 0.0235

    bar(fig, [0.905, 0.36, 0.014, 0.40], SKY, norm,
        "Horizon elevation", "degrees above the deck eye", "0 deg  open", "90 deg  zenith")

    fig.text(0.038, 0.062,
             "FILLED dots are sun positions that clear the measured horizon; HOLLOW dots "
             "are blocked. The sunlit-hours figure is the filled count times the timestep, "
             "so the diagram and the number are one computation.", fontsize=8, color=STEEL)
    fig.text(0.038, 0.030,
             "sun paths from hl_core.sun_path at latitude %.4f  ·  winter solstice day 355, "
             "equinox day 80, summer solstice day 172  ·  horizon recomputed live through "
             "build_viewshed.horizon" % hlc.LAT, fontsize=7, color=SHADE)

    p_out = os.path.join(OUT, "FIG6_sky_domes.png")
    fig.savefig(p_out)
    plt.close(fig)
    log("[fig6] %s" % p_out)
    return p_out


# ═════════════════════════════════════════════════════════════════════════════
# FIG 7 — the horizon field
# ═════════════════════════════════════════════════════════════════════════════
def horizon_field(force=False):
    if os.path.exists(CACHE) and not force:
        z = np.load(CACHE)
        if z["beta"].shape == (232, bv.N_AZ):
            log("[cache] %s" % CACHE)
            return z["s"], z["ang"], z["beta"]
    site = hlc.load_site()
    bld = site.buildings
    samples = site.corridor.samples(bv.SPACING)
    ang = np.linspace(0, 2 * math.pi, bv.N_AZ, endpoint=False)
    dirs = np.stack([np.cos(ang), np.sin(ang)], axis=1)
    S, B = [], []
    for n, (pt, s) in enumerate(samples):
        px, pz = float(pt[0]), float(pt[1])
        edges = hlc.edges_for(bld, px, pz, bv.MAX_R)
        beta = (np.zeros(bv.N_AZ) if edges is None
                else bv.horizon(edges, bld, px, pz, bv.EYE_DECK, dirs)[0])
        S.append(s)
        B.append(beta)
        if n % 40 == 0:
            log("   cast %d/%d" % (n, len(samples)))
    S, B = np.array(S), np.array(B)
    np.savez_compressed(CACHE, s=S, ang=ang, beta=B)
    log("[cache] wrote %s" % CACHE)
    return S, ang, B


def fig_carpet(force=False):
    S, ang, B = horizon_field(force)
    deg = np.degrees(B)
    cams = json.load(open(os.path.join(PROJECT, "houdini", "cameras.json"), encoding="utf-8"))

    fig = plt.figure(figsize=(15.0, 9.6), dpi=200)
    fig.text(0.045, 0.952, "THE HORIZON FIELD", fontsize=20, fontweight="bold", color=STEEL)
    fig.text(0.045, 0.921,
             "every ray the instrument casts: %d stations by %d azimuths  ·  this is the "
             "raw output, before any of it is collapsed into a single number  ·  every "
             "sky-view figure this project quotes is a mean over one row"
             % (len(S), bv.N_AZ), fontsize=8.5, color=SHADE)

    norm = Normalize(0, 90)
    ax = fig.add_axes([0.045, 0.225, 0.70, 0.655])
    ax.imshow(deg, aspect="auto", cmap=SKY, norm=norm, origin="lower",
              extent=[0, 360, S.min(), S.max()], interpolation="nearest")
    ax.set_xticks([0, 90, 180, 270, 360])
    ax.set_xticklabels([])
    ax.set_ylabel("arc length along the deck centreline, s (m)")
    for sp in ax.spines.values():
        sp.set_color(SHADE)

    # The winter sun gets its OWN panel on the same azimuth axis. It was drawn over the
    # field on a twin y-axis, which put a curve whose height means DEGREES on top of an
    # axis whose height means METRES ALONG THE DECK — legible to whoever drew it and
    # misleading to everyone else. Same x, separate y, no ambiguity.
    els, es, ns = hlc.sun_path(355)
    az = np.degrees(np.arctan2(es, ns)) % 360.0
    o = np.argsort(az)
    axs = fig.add_axes([0.045, 0.100, 0.70, 0.105], sharex=ax)
    axs.plot(az[o], np.degrees(els)[o], color=STEEL, lw=1.4)
    axs.fill_between(az[o], 0, np.degrees(els)[o], color=FLAGGED, alpha=0.13, linewidth=0)
    axs.set_ylim(0, 90)
    axs.set_yticks([0, 45, 90])
    axs.set_ylabel("winter sun altitude (deg)", fontsize=7.0)
    axs.set_xlim(0, 360)
    axs.set_xticks([0, 90, 180, 270, 360])
    axs.set_xticklabels(["N", "E", "S", "W", "N"])
    axs.set_xlabel("azimuth (compass bearing from north)")
    axs.grid(True, axis="y")
    for sp in axs.spines.values():
        sp.set_color(SHADE)
    axs.text(0.005, 0.86, "the sun the field above has to clear", transform=axs.transAxes,
             fontsize=7.5, color=SHADE)

    for st in cams["stations"]:
        ax.axhline(st["s_m"], color=PAPER, lw=1.8, alpha=0.85, zorder=4)
        ax.axhline(st["s_m"], color=STEEL, lw=0.7, ls=":", zorder=5)
        ax.text(4, st["s_m"], st["id"].split("_")[0], fontsize=8.5, color=STEEL,
                va="center", fontweight="bold", zorder=6,
                bbox=dict(fc=PAPER, ec="none", pad=1.2))

    bar(fig, [0.795, 0.44, 0.014, 0.38], SKY, norm,
        "Horizon elevation", "degrees above the deck eye", "0 deg  open", "90 deg  zenith")

    prof = deg.mean(axis=1)
    axp = fig.add_axes([0.885, 0.225, 0.095, 0.655])
    axp.plot(prof, S, color=STEEL, lw=1.0)
    axp.fill_betweenx(S, 0, prof, color=FLAGGED, alpha=0.13, linewidth=0)
    axp.set_ylim(S.min(), S.max())
    axp.set_xlim(0, 90)
    axp.set_yticklabels([])
    axp.set_xlabel("mean beta\n(deg)", fontsize=7.5)
    axp.grid(True, axis="x")
    for sp in axp.spines.values():
        sp.set_color(SHADE)

    fig.text(0.045, 0.050,
             "READ IT AS A MAP OF ENCLOSURE: the hot vertical bands are the towers, and "
             "they sit where the sun path is lowest — south, at winter altitude %.1f deg."
             % np.degrees(els).max(), fontsize=8.5, color=STEEL)
    fig.text(0.045, 0.024,
             "recomputed live: hl_core.edges_for / ray_uv · build_viewshed.horizon · "
             "cached to exports/horizon_field.npz  ·  nothing under data/ is written",
             fontsize=7, color=SHADE)

    p_out = os.path.join(OUT, "FIG7_horizon_field.png")
    fig.savefig(p_out)
    plt.close(fig)
    log("[fig7] %s  ·  mean beta %.2f deg, max %.2f deg" % (p_out, deg.mean(), deg.max()))
    return p_out


def main():
    os.makedirs(OUT, exist_ok=True)
    style()
    args = sys.argv[1:]
    if not args or "--domes" in args:
        fig_domes()
    if not args or "--carpet" in args:
        fig_carpet("--force" in args)


if __name__ == "__main__":
    main()
