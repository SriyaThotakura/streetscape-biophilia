"""render_cell.py — render ONE matrix cell at final pixel size for the legibility
gate (before generating all 16). Reused by the compositor later.

A cell = scenario label + SVF strip along s (shared colormap) with the baseline
ghosted for reference + a ΔSVF bar on the SHARED scale + the winter-sun delta.
All numbers from data/removals.json. IBM Plex Mono, dark theme, terracotta accent.
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
FONTS = os.path.join(ROOT, "boards", "assets", "fonts")

# palette: TYPE_COLOR + terracotta accent, on the app dark
BG = "#0a0b0f"; CELL = "#0d0e14"; INK = "#99aabb"; DIM = "#556677"
TEAL = "#00ddaa"; TERRA = "#c0673f"; EDGE = "#1a1d2a"
SVF_CMAP = LinearSegmentedColormap.from_list("svf", ["#7a2f18", "#c0673f", "#33414a", "#00ddaa"])
# difference colormap: 0 = cell background (quiet, no change) → teal (sky restored).
# zero is neutral, never a hot color, so small-effect cells read as quiet.
DIFF_CMAP = LinearSegmentedColormap.from_list("diff", ["#0d0e14", "#123c33", "#00ddaa"])

for w in ("Regular", "Medium", "SemiBold"):
    fm.fontManager.addfont(os.path.join(FONTS, f"IBMPlexMono-{w}.ttf"))
plt.rcParams["font.family"] = "IBM Plex Mono"

try:
    LABELS = json.load(open(os.path.join(D, "building_labels.json")))["labels"]
except Exception:
    LABELS = {}


def render_cell(scen, s_axis, meta, size_px=(640, 500), out=None, diff_scale=None):
    W, H = size_px
    dpi = 300
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG)
    svf = np.array(scen["svf"])
    is_diff = scen["key"].startswith("r")     # the 12 single-removal cells only
    smin, smax = meta["svf_scale"]
    dmax = max(abs(meta["d_svf_scale"][0]), abs(meta["d_svf_scale"][1]))
    tone = {"restore": TEAL, "loss": TERRA, "neutral": INK}[scen["tone"]]

    # cell background panel
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.add_patch(plt.Rectangle((0.012, 0.012), 0.976, 0.976, facecolor=CELL,
                 edgecolor=EDGE, lw=1.2, transform=ax.transAxes))

    is_ref = scen["key"] == "baseline"
    # ── header: address (removals) / name (anchors) left · headline right ──
    label = LABELS.get(scen.get("id", ""), {}).get("display", scen["label"]) if is_diff else scen["label"]
    ax.text(0.055, 0.915, label, fontsize=11, fontweight="semibold",
            color="#e6ecf0", transform=ax.transAxes, va="center")
    headline = f"SVF {scen['mean_svf_cal']:.2f}" if is_ref else f"{scen['d_svf_pct']:+.1f}%"
    ax.text(0.945, 0.915, headline, fontsize=14, fontweight="semibold",
            color=tone, transform=ax.transAxes, va="center", ha="right")
    sub = f"{scen['dir']}  ·  {scen['year']}" if is_diff else scen["dir"]
    ax.text(0.055, 0.835, sub, fontsize=8, color=DIM, transform=ax.transAxes, va="center")
    ax.plot([0.055, 0.945], [0.785, 0.785], color=EDGE, lw=0.8, transform=ax.transAxes)

    # ── SVF strip: absolute (anchors) or difference vs baseline (removals) ──
    cap = ("SVF RESTORED vs baseline" if is_diff
           else "SKY-VIEW FACTOR  ·  ghost = baseline")
    ax.text(0.055, 0.735, cap, fontsize=6, color=DIM, transform=ax.transAxes, va="center")
    axs = fig.add_axes([0.055, 0.40, 0.89, 0.28])
    if is_diff:
        diff = svf - np.array(BASE_SVF)          # ≥0: removing a building only opens sky
        axs.imshow(diff.reshape(1, -1), aspect="auto", cmap=DIFF_CMAP,
                   vmin=0, vmax=(diff_scale or diff.max() or 1e-6), extent=[0, s_axis[-1], 0, 1])
    else:
        axs.imshow(svf.reshape(1, -1), aspect="auto", cmap=SVF_CMAP, vmin=smin, vmax=smax,
                   extent=[0, s_axis[-1], 0, 1])
        axs.plot(s_axis, (np.array(BASE_SVF) - smin) / (smax - smin), color="#dfe4e8", lw=0.8, alpha=0.6)
    axs.set_ylim(0, 1); axs.set_yticks([])
    axs.set_xlim(0, s_axis[-1]); axs.set_xticks([0, 900, s_axis[-1]])
    axs.set_xticklabels(["0 m", "900", "1857"], fontsize=6, color=DIM)
    for sp in axs.spines.values(): sp.set_color(EDGE)
    axs.tick_params(colors=DIM, length=2, pad=2)

    # ── bottom band ──
    ax.text(0.70, 0.245, "winter sun", fontsize=6, color=DIM, transform=ax.transAxes, va="center")
    if is_ref:
        # reference: absolute state, no delta bar
        ax.text(0.055, 0.245, "REFERENCE STATE", fontsize=6, color=DIM,
                transform=ax.transAxes, va="center")
        ax.text(0.055, 0.135, "deltas vs this", fontsize=9, color=DIM,
                transform=ax.transAxes, va="center")
        ax.text(0.945, 0.135, f"{scen['mean_winter_sun_h']:.1f} h", fontsize=12, fontweight="medium",
                color=INK, transform=ax.transAxes, va="center", ha="right")
    else:
        ax.text(0.055, 0.245, f"SKY-VIEW CHANGE  0–{dmax:.0f}%", fontsize=6,
                color=DIM, transform=ax.transAxes, va="center")
        axb = fig.add_axes([0.055, 0.10, 0.50, 0.075])
        axb.set_xlim(0, dmax); axb.set_ylim(0, 1); axb.set_axis_off()
        axb.add_patch(plt.Rectangle((0, 0), dmax, 1, facecolor="#12141b", edgecolor=EDGE, lw=0.8))
        axb.add_patch(plt.Rectangle((0, 0), abs(scen["d_svf_pct"]), 1, facecolor=tone))
        dh = scen["d_winter_sun_h"]
        sun_txt = "<0.01 h" if (dh != 0 and abs(dh) < 0.01) else f"{dh:+.2f} h"
        ax.text(0.945, 0.135, sun_txt, fontsize=12, fontweight="medium",
                color=tone, transform=ax.transAxes, va="center", ha="right")

    if out:
        fig.savefig(out, dpi=dpi, facecolor=BG)
        plt.close(fig)
    return out


def render_key(meta, size_px=(640, 500), out=None, diff_scale=None):
    """KEY: both colormaps (absolute SVF for anchors, difference for removals),
    shared Δ scale, tone legend, decomposition note."""
    W, H = size_px; dpi = 300
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi); fig.patch.set_facecolor(BG)
    smin, smax = meta["svf_scale"]
    dmax = max(abs(meta["d_svf_scale"][0]), abs(meta["d_svf_scale"][1]))
    ds = diff_scale or 0.3
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.add_patch(plt.Rectangle((0.012, 0.012), 0.976, 0.976, facecolor=CELL, edgecolor=TERRA, lw=1.4,
                 transform=ax.transAxes))
    ax.text(0.055, 0.925, "KEY", fontsize=11, fontweight="semibold", color="#e6ecf0",
            transform=ax.transAxes, va="center")
    ax.text(0.945, 0.925, "shared scale", fontsize=9, color=DIM, transform=ax.transAxes,
            va="center", ha="right")
    ax.plot([0.055, 0.945], [0.875, 0.875], color=EDGE, lw=0.8, transform=ax.transAxes)

    def swatch(y, cmap, title, left, right):
        ax.text(0.055, y + 0.075, title, fontsize=6.5, color=DIM, transform=ax.transAxes)
        axc = fig.add_axes([0.055, y, 0.89, 0.055])
        axc.imshow(np.linspace(0, 1, 256).reshape(1, -1), aspect="auto", cmap=cmap)
        axc.set_xticks([]); axc.set_yticks([])
        for sp in axc.spines.values(): sp.set_color(EDGE)
        ax.text(0.055, y - 0.045, left, fontsize=6.5, color=DIM, transform=ax.transAxes, ha="left")
        ax.text(0.945, y - 0.045, right, fontsize=6.5, color=DIM, transform=ax.transAxes, ha="right")

    swatch(0.735, SVF_CMAP, "SKY-VIEW FACTOR (anchor strips)", "enclosed", "open sky")
    swatch(0.535, DIFF_CMAP, "SVF RESTORED (removal strips)", "no change",
           f"regained 0-{ds*100:.0f}%")

    # Δ shared scale (headline number bar)
    ax.text(0.055, 0.40, f"SKY-VIEW CHANGE headline   0-{dmax:.0f}%", fontsize=6.5, color=DIM,
            transform=ax.transAxes)
    axd = fig.add_axes([0.055, 0.315, 0.89, 0.05]); axd.set_xlim(0, dmax); axd.set_ylim(0, 1)
    axd.set_axis_off()
    axd.add_patch(plt.Rectangle((0, 0), dmax, 1, facecolor="#12141b", edgecolor=EDGE, lw=0.8))
    for gx in range(0, int(dmax) + 1, 2):
        axd.plot([gx, gx], [0, 1], color=EDGE, lw=0.6)
        axd.text(gx, -0.6, f"{gx}", fontsize=5.5, color=DIM, ha="center")

    for i, (c, lab) in enumerate([(TEAL, "restore (sky regained)"), (TERRA, "loss (built out)"),
                                   (INK, "reference / baseline")]):
        y = 0.215 - i * 0.058
        ax.add_patch(plt.Rectangle((0.055, y - 0.016), 0.028, 0.032, facecolor=c, transform=ax.transAxes))
        ax.text(0.10, y, lab, fontsize=6.5, color=INK, transform=ax.transAxes, va="center")
    ax.text(0.5, 0.065, "pre-2009 = sum of 12 removals", fontsize=6.5, color=TERRA,
            transform=ax.transAxes, va="center", ha="center", style="italic")
    if out:
        fig.savefig(out, dpi=dpi, facecolor=BG); plt.close(fig)


if __name__ == "__main__":
    data = json.load(open(os.path.join(D, "removals.json")))
    meta, s_axis, scen = data["metadata"], data["s_axis"], data["scenarios"]
    BASE_SVF = next(s["svf"] for s in scen if s["key"] == "baseline")
    pick = sys.argv[1] if len(sys.argv) > 1 else "r1"
    sc = next(s for s in scen if s["key"] == pick)
    outp = os.path.join(ROOT, "boards", "captures", f"_cell_preview_{pick}.png")
    render_cell(sc, s_axis, meta, out=outp)
    print(f"rendered {pick} ({sc['label']}, {sc['d_svf_pct']:+.1f}% / {sc['d_winter_sun_h']:+.2f}h) -> {outp}")
