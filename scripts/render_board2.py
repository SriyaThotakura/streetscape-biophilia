"""render_board2.py — the data-driven panels for Board 2 (BEHAVIORAL CONSEQUENCE):
5 stacked comfort-field states + 4 process panels (centerline extraction, ray-cast
diagram, calibration scatter, dwell-gap). All numbers from data/*.json. IBM Plex Mono.
Writes boards/captures/panels/*.png. Run from project root:
    python scripts/render_board2.py
"""
import json, os, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "boards", "captures", "panels")
os.makedirs(OUT, exist_ok=True)
FONTS = os.path.join(ROOT, "boards", "assets", "fonts")
for w in ("Regular", "Medium", "SemiBold"):
    fm.fontManager.addfont(os.path.join(FONTS, f"IBMPlexMono-{w}.ttf"))
plt.rcParams["font.family"] = "IBM Plex Mono"
BG, CELL, INK, DIM = "#0a0b0f", "#0d0e14", "#cdd5c6", "#5b6b78"
TEAL, TERRA, EDGE, AMBER = "#00ddaa", "#c0673f", "#1a1d2a", "#c9a24a"
CMAP = LinearSegmentedColormap.from_list("cf", ["#c0673f", "#c9a24a", "#00ddaa"])
def L(n): return json.load(open(os.path.join(D, n), encoding="utf-8"))


def comfort_states():
    v = L("highline_viewshed.json")["points"]; s = L("highline_solar.json")["points"]
    fw = L("forward_scenario.json")["points"]
    s_ax = [p["s_m"] for p in v]
    cf = lambda svf, sun, dl: 0.6 * np.clip(np.array(svf), 0, 1) + 0.4 * np.clip(np.array(sun) / dl, 0, 1)
    svf = [p["svf_deck"] for p in v]; svfp = [p["svf_prepark"] for p in v]
    svff = [p["svf_future"] for p in fw]
    states = [
        ("WINTER", cf(svf, [p["sun_winter_solstice"] for p in s], 8.8)),
        ("SUMMER", cf(svf, [p["sun_summer_solstice"] for p in s], 14.8)),
        ("EQUINOX", cf(svf, [p["sun_equinox"] for p in s], 11.8)),
        ("PRE-2009", cf(svfp, [p["sun_winter_solstice_prepark"] for p in s], 8.8)),
        ("FORWARD", cf(svff, [p["sun_future"] for p in fw], 8.8)),
    ]
    fig = plt.figure(figsize=(3.1, 6.9), dpi=300); fig.patch.set_facecolor(BG)
    fig.text(0.06, 0.965, "COMFORT FIELD = 0.6·SVF + 0.4·sun", fontsize=8, color=DIM, fontweight="medium")
    n = len(states); top = 0.76; band = 0.13; gap = 0.025
    for i, (name, c) in enumerate(states):
        y = top - i * (band + gap)
        fig.text(0.06, y + band + 0.006, name, fontsize=8.5, color=INK, fontweight="semibold")
        fig.text(0.94, y + band + 0.006, f"mean {c.mean():.2f}", fontsize=7, color=DIM, ha="right")
        ax = fig.add_axes([0.06, y, 0.88, band])
        ax.imshow(c.reshape(1, -1), aspect="auto", cmap=CMAP, vmin=0, vmax=1, extent=[0, s_ax[-1], 0, 1])
        ax.set_yticks([]); ax.set_xticks([0, s_ax[-1]]); ax.set_xticklabels([], fontsize=5)
        for sp in ax.spines.values(): sp.set_color(EDGE)
    fig.text(0.06, 0.03, "terracotta = enclosed/shadowed   →   teal = open/sunlit", fontsize=6.5, color=DIM)
    fig.savefig(os.path.join(OUT, "comfort_states.png"), dpi=300, facecolor=BG); plt.close(fig)


def _fig(w=3.8, h=2.05):
    fig = plt.figure(figsize=(w, h), dpi=300); fig.patch.set_facecolor(CELL)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.add_patch(plt.Rectangle((0.008, 0.008), 0.984, 0.984, facecolor=CELL, edgecolor=EDGE, lw=1.2))
    return fig, ax


def proc_centerline():
    hl = L("highline_footprints.json")["high_line"]; cl = np.array(hl["centerline"])
    fig, ax = _fig()
    a2 = fig.add_axes([0.08, 0.14, 0.86, 0.62]); a2.set_facecolor(CELL)
    a2.plot(cl[:, 0], cl[:, 1], color=TEAL, lw=2)
    for ap in hl["access_points"]:
        a2.plot(ap["x"], ap["z"], "o", ms=4, mfc="none", mec=AMBER, mew=1.2)
    a2.set_aspect("equal"); a2.axis("off")
    ax.text(0.05, 0.90, "1 · CENTERLINE EXTRACTION", fontsize=9, color=INK, fontweight="semibold")
    ax.text(0.05, 0.06, f"{hl['length_m']:.0f} m · {len(hl['access_points'])} access points · local metres",
            fontsize=7, color=DIM)
    fig.savefig(os.path.join(OUT, "proc_centerline.png"), dpi=300, facecolor=CELL); plt.close(fig)


def proc_raycast():
    fig, ax = _fig()
    ax.text(0.05, 0.90, "2 · ISOVIST RAY-CAST", fontsize=9, color=INK, fontweight="semibold")
    a2 = fig.add_axes([0.05, 0.12, 0.9, 0.66]); a2.set_xlim(-1.1, 1.1); a2.set_ylim(-0.15, 1.05); a2.axis("off")
    # buildings as blocks
    blocks = [(-0.9, 0.2, 0.25, 0.55), (0.55, 0.25, 0.3, 0.6), (-0.2, 0.55, 0.2, 0.4), (0.15, 0.35, 0.18, 0.3)]
    for bx, by, bw, bh in blocks:
        a2.add_patch(plt.Rectangle((bx, by), bw, bh, facecolor="#2a333b", edgecolor="#3b4650", lw=0.6))
    # deck point + rays
    ox, oy = 0, 0.05
    import random; random.seed(1)
    for k in range(24):
        ang = math.pi * (k + 0.5) / 24
        dx, dy = math.cos(ang), math.sin(ang)
        t = 1.4
        for bx, by, bw, bh in blocks:  # crude nearest hit
            for tt in np.linspace(0.02, 1.4, 90):
                px, py = ox + dx * tt, oy + dy * tt
                if bx <= px <= bx + bw and by <= py <= by + bh: t = min(t, tt); break
        col = TERRA if t < 1.3 else TEAL
        a2.plot([ox, ox + dx * t], [oy, oy + dy * t], color=col, lw=0.7, alpha=0.85)
    a2.plot(ox, oy, "o", ms=5, mfc="#eef0e6", mec=TEAL, mew=1.5)
    ax.text(0.05, 0.06, "green ray = sky · terracotta = blocked by a building", fontsize=7, color=DIM)
    fig.savefig(os.path.join(OUT, "proc_raycast.png"), dpi=300, facecolor=CELL); plt.close(fig)


def proc_calibration():
    mine = [p["svf_deck"] for p in L("highline_viewshed.json")["points"]]
    lbt = [p["svf_deck"] for p in L("highline_viewshed_lbt.json")["points"]]
    cal = L("svf_calibration.json")["svf"]
    fig, ax = _fig()
    ax.text(0.05, 0.90, "3 · CALIBRATION", fontsize=9, color=INK, fontweight="semibold")
    a2 = fig.add_axes([0.13, 0.18, 0.8, 0.58]); a2.set_facecolor("#0b0c11")
    a2.scatter(mine, lbt, s=3, c=TEAL, alpha=0.5, edgecolors="none")
    xs = np.array([0, 1]); a2.plot(xs, cal["a"] * xs + cal["b"], color=TERRA, lw=1.4)
    a2.plot([0, 1], [0, 1], color=DIM, lw=0.6, ls="--")
    a2.set_xlim(0, 1); a2.set_ylim(0, 1); a2.set_xticks([0, 1]); a2.set_yticks([0, 1])
    a2.tick_params(colors=DIM, labelsize=6)
    for sp in a2.spines.values(): sp.set_color(EDGE)
    a2.set_xlabel("hl_core SVF", fontsize=6.5, color=DIM); a2.set_ylabel("Ladybug SVF", fontsize=6.5, color=DIM)
    ax.text(0.95, 0.90, f"r={cal['r']:+.2f}  R²={cal['r2']:.2f}", fontsize=9, color=TEAL, ha="right", fontweight="medium")
    ax.text(0.05, 0.06, f"hl_core vs Ladybug · fit svf = {cal['a']:.2f}·svf {cal['b']:+.2f}", fontsize=7, color=DIM)
    fig.savefig(os.path.join(OUT, "proc_calibration.png"), dpi=300, facecolor=CELL); plt.close(fig)


def proc_dwell():
    bm = L("behavior_metrics.json"); gap = bm["dwell_gap_pct"]
    fig, ax = _fig()
    ax.text(0.05, 0.90, "4 · DWELL GAP  (de-parking)", fontsize=9, color=INK, fontweight="semibold")
    ax.text(0.5, 0.56, f"{gap:.0f}%", fontsize=54, color=TEAL, ha="center", va="center", fontweight="semibold")
    ax.text(0.5, 0.30, "slower (lingering) in open vs shadowed segments", fontsize=7.5, color=INK, ha="center")
    ax.text(0.5, 0.14, f"seed=42 · peak congestion s={bm['peak_congestion_s']:.0f} m · the towers turn park into corridor",
            fontsize=6.5, color=DIM, ha="center")
    fig.savefig(os.path.join(OUT, "proc_dwell.png"), dpi=300, facecolor=CELL); plt.close(fig)


if __name__ == "__main__":
    comfort_states(); proc_centerline(); proc_raycast(); proc_calibration(); proc_dwell()
    print("wrote 5 comfort states + 4 process panels ->", os.path.relpath(OUT, ROOT))
