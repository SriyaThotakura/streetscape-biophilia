"""build_rib_schedule.py — rationalize the canopy into a buildable kit of parts.

The envelope generates 232 unique performance-driven ribs. You cannot economically
fabricate 232 one-off bent members. This engine does the fabrication move: it reduces the
continuous rib family to a small set of **standard types**, schedules them, and quantifies
the buildability tradeoff — how much each installed rib deviates from its standard part as
a function of how many types you allow.

Two fabrication insights make the rationalization honest:
  1. A rib's fabricated member is defined by its cross-deck **section profile** (segment
     lengths + bend angles). The aperture heading only rotates the rib about vertical at
     install — same part, different orientation — so heading is NOT a fabrication variable.
     Ribs are therefore clustered on their intrinsic geometry (height, reach) only.
  2. Rationalizing to N types snaps each rib to its type's standard profile. The resulting
     nodal displacement (in mm) is the install tolerance you must absorb with slotted
     connections. Fewer types = cheaper kit, larger tolerance. We report the whole curve
     and pick a defensible N.

Consumes:  data/envelope.json
Produces:  data/rib_schedule.json       (types, per-station assignment, totals, provenance)
           exports/rib_schedule.csv      (one row per rib — the fabricator's cut list)
           exports/rib_schedule.png      (the schedule sheet: typed profiles + tradeoff)

Run:  python scripts/build_rib_schedule.py [--types 10]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import time

import numpy as np

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
ROOT = os.path.dirname(DATA)
EXPORTS = os.path.join(ROOT, "exports")

N_TYPES = 10             # standard rib types in the kit
KG_PER_M = 24.0         # nominal steel: ~168x6 CHS / small box section
TOL_OK_MM = 200.0       # a member within this of its standard cut is "standardized"
                         # (absorbed by a slotted connection); beyond it -> bespoke
SEED = 42


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def _deck_normal(pts, i):
    a = pts[max(i - 1, 0)]; b = pts[min(i + 1, len(pts) - 1)]
    tx, tz = b["x"] - a["x"], b["z"] - a["z"]
    n = math.hypot(tx, tz) or 1.0
    return -tz / n, tx / n               # unit normal in ground plane


def _section_profile(p, nx, nz):
    """Project the 3-D rib onto its cross-deck vertical plane -> [(u, y)] profile.
    u = signed distance along the deck normal; y = height. This is the fabricated
    member's true elevation; the small along-deck component is the install twist."""
    cx, cz = p["x"], p["z"]
    prof = []
    for (x, y, z) in p["rib"]:
        u = (x - cx) * nx + (z - cz) * nz
        prof.append((u, y))
    return np.array(prof)


def _member3d(rib):
    """True fabricated member geometry from the 3-D rib points: segment lengths and
    bend angles. Heading-invariant (rotation preserves both), so these are the real
    cut lengths and bends — NOT the flattened projection, which loses the along-deck
    component of the reach."""
    p = np.asarray(rib, float)
    d = np.diff(p, axis=0)
    seg = np.linalg.norm(d, axis=1)                  # 4 member lengths (m)
    bends = []
    for k in range(1, len(p) - 1):
        v0 = p[k] - p[k - 1]; v1 = p[k + 1] - p[k]
        c = np.dot(v0, v1) / ((np.linalg.norm(v0) * np.linalg.norm(v1)) or 1)
        bends.append(math.degrees(math.acos(max(-1.0, min(1.0, c)))))
    return seg, np.array(bends)


def _profile_metrics(prof):
    """2-D metrics of the projected (u,y) elevation — for drawing only."""
    d = np.diff(prof, axis=0)
    return np.hypot(d[:, 0], d[:, 1])


def _rationalize(feats, k):
    """KMeans on standardized [height, reach]; return labels + medoid index per cluster."""
    from sklearn.cluster import KMeans
    mu, sd = feats.mean(0), feats.std(0) + 1e-9
    z = (feats - mu) / sd
    km = KMeans(n_clusters=k, random_state=SEED, n_init=10).fit(z)
    labels = km.labels_
    medoids = []
    for c in range(k):
        members = np.where(labels == c)[0]
        d = np.linalg.norm(z[members] - km.cluster_centers_[c], axis=1)
        medoids.append(int(members[np.argmin(d)]))
    return labels, medoids


def build(n_types=N_TYPES, make_fig=True):
    env = json.load(open(os.path.join(DATA, "envelope.json"), encoding="utf-8"))
    pts = env["points"]

    # per-rib fabrication geometry — segs/bends from the TRUE 3-D member;
    # profiles (u,y) are the projected elevation, kept only for drawing
    profiles, segs, bends, feats = [], [], [], []
    for i, p in enumerate(pts):
        nx, nz = _deck_normal(pts, i)
        profiles.append(_section_profile(p, nx, nz))
        s, b = _member3d(p["rib"])
        segs.append(s); bends.append(b)
        feats.append([p["rib_height_m"], p["reach_m"]])
    feats = np.array(feats)
    segs = np.array(segs)                              # (n, 4) true member lengths
    mem_len = segs.sum(1)

    # rationalize to N standard types
    labels, medoids = _rationalize(feats, n_types)

    # order types shortest -> tallest for a legible schedule
    type_h = [feats[medoids[c]][0] for c in range(n_types)]
    order = np.argsort(type_h)
    remap = {old: new for new, old in enumerate(order)}
    labels = np.array([remap[l] for l in labels])
    medoids = [medoids[old] for old in order]

    # install tolerance (heading-invariant): worst mismatch, in mm, between a rib's
    # true member segments and its type's standard cut lengths — what a slotted
    # connection must absorb. Comparing segment lengths (not projected node positions)
    # is what makes mirrored/rotated ribs count as the same part.
    tol_mm = np.array([np.max(np.abs(segs[i] - segs[medoids[labels[i]]])) * 1000.0
                       for i in range(len(pts))])
    bespoke = tol_mm > TOL_OK_MM                       # exceeds slotted tolerance -> bespoke
    coverage = 100.0 * (~bespoke).mean()

    types = []
    for t in range(n_types):
        idx = np.where(labels == t)[0]
        med = medoids[t]
        mseg, mbend = segs[med], bends[med]
        std_idx = idx[~bespoke[idx]]
        types.append({
            "type": f"T{t+1:02d}",
            "count": int(len(idx)),
            "count_standardized": int(len(std_idx)),
            "count_bespoke": int(len(idx) - len(std_idx)),
            "height_m": round(float(feats[med][0]), 3),
            "reach_m": round(float(feats[med][1]), 3),
            "member_length_m": round(float(mseg.sum()), 3),
            "segments_m": [round(float(v), 3) for v in mseg],
            "bend_angles_deg": [round(float(v), 1) for v in mbend],
            "profile_uy": [[round(float(u), 3), round(float(y), 3)] for u, y in profiles[med]],
            "std_tol_mm": round(float(tol_mm[std_idx].max()), 1) if len(std_idx) else 0.0,
            "std_tol_pct": round(float(tol_mm[std_idx].max() / (mseg.sum()*1000) * 100), 2) if len(std_idx) else 0.0,
            "stations_s": [round(pts[i]["s_m"], 1) for i in idx],
        })

    # rationalization tradeoff: % of ribs standardized within TOL_OK vs number of types
    tradeoff = []
    for k in range(3, min(20, len(pts)) + 1):
        lab, med = _rationalize(feats, k)
        tmm = np.array([np.max(np.abs(segs[i] - segs[med[lab[i]]])) * 1000.0 for i in range(len(pts))])
        tradeoff.append([k, round(100.0 * (tmm <= TOL_OK_MM).mean(), 1)])

    total_len = float(mem_len.sum())
    result = {
        "_meta": {
            "script": "build_rib_schedule.py",
            "git_commit": _git_commit(),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "data/envelope.json",
            "model": "rib family rationalized to N standard types by KMeans on "
                     "[height, reach]; aperture heading is an install rotation, not a "
                     "fabrication variable. Tolerance = max nodal snap displacement (mm).",
            "params": {"n_types": n_types, "kg_per_m": KG_PER_M,
                       "tol_ok_mm": TOL_OK_MM, "seed": SEED},
            "totals": {
                "n_ribs": len(pts),
                "n_types": n_types,
                "n_standardized": int((~bespoke).sum()),
                "n_bespoke": int(bespoke.sum()),
                "standardization_coverage_pct": round(coverage, 1),
                "total_member_length_m": round(total_len, 1),
                "est_steel_tonnes": round(total_len * KG_PER_M / 1000.0, 2),
                "mean_install_tol_mm": round(float(tol_mm.mean()), 1),
                "max_standardized_tol_mm": round(float(tol_mm[~bespoke].max()), 1),
                "dominant_type_share_pct": round(100.0 * max(t["count"] for t in [{"count": int((labels==c).sum())} for c in range(n_types)]) / len(pts), 1),
                "parts_reduction": f"{len(pts)} unique ribs -> {n_types} standard types + "
                                   f"{int(bespoke.sum())} bespoke",
            },
        },
        "types": types,
        "tradeoff_types_vs_maxtol_mm": tradeoff,
        "assignments": [
            {"s_m": round(p["s_m"], 1), "type": f"T{labels[i]+1:02d}",
             "install_heading_deg": p["aperture_az_deg"],
             "install_tol_mm": round(float(tol_mm[i]), 1)}
            for i, p in enumerate(pts)
        ],
    }

    outp = os.path.join(DATA, "rib_schedule.json")
    json.dump(result, open(outp, "w", encoding="utf-8"), indent=1)
    print(f"wrote {outp}")
    tt = result["_meta"]["totals"]
    print(f"  {tt['parts_reduction']}")
    print(f"  {tt['standardization_coverage_pct']:.0f}% of ribs standardized within "
          f"±{TOL_OK_MM:.0f} mm  ·  dominant type covers {tt['dominant_type_share_pct']:.0f}%  "
          f"·  {tt['n_bespoke']} bespoke signature ribs")
    print(f"  {tt['total_member_length_m']:.0f} m member (~{tt['est_steel_tonnes']:.1f} t) · "
          f"standardized fit within ±{tt['max_standardized_tol_mm']:.0f} mm")

    # CSV cut list
    os.makedirs(EXPORTS, exist_ok=True)
    csvp = os.path.join(EXPORTS, "rib_schedule.csv")
    with open(csvp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rib_id", "s_m", "type", "fabrication", "height_m", "reach_m",
                    "install_heading_deg", "member_length_m", "seg1_m", "seg2_m",
                    "seg3_m", "seg4_m", "bend1_deg", "bend2_deg", "bend3_deg", "install_tol_mm"])
        for i, p in enumerate(pts):
            s = segs[i]; b = bends[i]
            w.writerow([f"R{i+1:03d}", round(p["s_m"], 1), f"T{labels[i]+1:02d}",
                        "bespoke" if bespoke[i] else "standard",
                        round(p["rib_height_m"], 3), round(p["reach_m"], 3),
                        p["aperture_az_deg"], round(float(s.sum()), 3),
                        *[round(float(v), 3) for v in s], *[round(float(v), 1) for v in b],
                        round(float(tol_mm[i]), 1)])
    print(f"wrote {csvp}  ({len(pts)} ribs)")

    if make_fig:
        _figure(result, labels, np.array([p["s_m"] for p in pts]))
    return result


def _figure(result, labels, s):
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    from matplotlib import cm, colors as mcolors

    types = result["types"]
    n = len(types)
    INK = "#141414"; ACC = "#c0673f"; MUT = "#8a8780"; SKY = "#3a6ea5"
    plt.rcParams.update({"font.family": ["IBM Plex Mono", "Consolas", "DejaVu Sans Mono", "monospace"],
                         "font.size": 8, "axes.edgecolor": MUT})

    fig = plt.figure(figsize=(14, 9), facecolor="white")
    gs = fig.add_gridspec(3, 1, height_ratios=[3.1, 0.5, 1.15], hspace=0.42,
                          left=0.045, right=0.98, top=0.9, bottom=0.07)

    # --- typed rib profiles, dimensioned, drawn to a common scale ---------------
    cols = 5; rows = math.ceil(n / cols)
    gtop = gs[0].subgridspec(rows, cols, hspace=0.55, wspace=0.28)
    ymax = max(max(y for _, y in t["profile_uy"]) for t in types)
    umax = max(max(abs(u) for u, _ in t["profile_uy"]) for t in types)
    cmap = cm.get_cmap("inferno_r")
    norm = mcolors.Normalize(0, n - 1)
    for ti, t in enumerate(types):
        ax = fig.add_subplot(gtop[ti // cols, ti % cols])
        prof = np.array(t["profile_uy"])
        col = cmap(norm(ti))
        ax.plot(prof[:, 0], prof[:, 1], color=col, lw=2.4, solid_capstyle="round", zorder=3)
        ax.scatter(prof[:, 0], prof[:, 1], s=9, color=INK, zorder=4)
        # deck line
        ax.plot([prof[0, 0], prof[-1, 0]], [9, 9], color=MUT, lw=0.8, ls=(0, (4, 3)))
        bespoke_tag = f"  ({t['count_bespoke']} bespoke)" if t['count_bespoke'] else ""
        ax.set_title(f"{t['type']}  ×{t['count']}{bespoke_tag}", fontsize=9, fontweight="bold",
                     color=(ACC if t['count_bespoke'] else INK), loc="left", pad=2)
        ax.text(0.5, -0.02, f"h {t['height_m']:.1f}  reach {t['reach_m']:.1f}\n"
                f"L {t['member_length_m']:.1f} m · ±{t['std_tol_mm']:.0f} mm ({t['std_tol_pct']:.1f}%)",
                transform=ax.transAxes, ha="center", va="top", fontsize=6.6, color=MUT)
        ax.set_xlim(-umax - 1, umax + 1); ax.set_ylim(8, ymax + 1.5)
        ax.set_aspect("equal"); ax.axis("off")

    # --- distribution: type along the deck (s) ----------------------------------
    axd = fig.add_subplot(gs[1])
    seg = np.stack([np.column_stack([s[:-1], np.zeros(len(s)-1)]),
                    np.column_stack([s[1:], np.zeros(len(s)-1)])], axis=1)
    from matplotlib.collections import LineCollection
    lc = LineCollection(seg, cmap=cmap, norm=norm, array=labels[:-1], linewidths=13)
    axd.add_collection(lc)
    axd.set_xlim(0, s.max()); axd.set_ylim(-1, 1)
    axd.set_yticks([]); axd.set_xlabel("standard type deployed along the deck   (s, m)", fontsize=8)
    axd.set_title("which type goes where", loc="left", fontsize=9, fontweight="bold", color=INK)
    for sp in ("top", "right", "left"): axd.spines[sp].set_visible(False)

    # --- rationalization tradeoff: coverage vs number of types ------------------
    axt = fig.add_subplot(gs[2])
    tr = np.array(result["tradeoff_types_vs_maxtol_mm"])
    tol_ok = result["_meta"]["params"]["tol_ok_mm"]
    axt.plot(tr[:, 0], tr[:, 1], color=SKY, lw=1.8, marker="o", ms=3.5, zorder=3)
    nT = result["_meta"]["params"]["n_types"]
    hit = tr[tr[:, 0] == nT]
    if len(hit):
        axt.scatter([nT], [hit[0, 1]], s=70, facecolor=ACC, edgecolor="white",
                    zorder=5, linewidths=1.2)
        axt.annotate(f"chosen: {nT} types\n{hit[0,1]:.0f}% standardized",
                     (nT, hit[0, 1]), (nT + 1.0, hit[0, 1] - 16),
                     fontsize=8, color=ACC, fontweight="bold",
                     arrowprops=dict(arrowstyle="-", color=ACC, lw=0.8))
    axt.set_xlabel("number of standard rib types")
    axt.set_ylabel(f"% ribs within\n±{tol_ok:.0f} mm")
    axt.set_ylim(0, 101)
    axt.set_title("rationalization coverage — how many ribs a standard kit fits",
                  loc="left", fontsize=9, fontweight="bold", color=INK)
    axt.set_xticks(tr[::2, 0].astype(int))
    for sp in ("top", "right"): axt.spines[sp].set_visible(False)

    tt = result["_meta"]["totals"]
    fig.suptitle("THE ANSWERING LINE — canopy rib schedule", x=0.045, ha="left",
                 fontsize=13, fontweight="bold", color=INK, y=0.965)
    fig.text(0.045, 0.925,
             f"{tt['n_ribs']} ribs → {tt['n_types']} standard types + {tt['n_bespoke']} bespoke  ·  "
             f"{tt['standardization_coverage_pct']:.0f}% standardized within ±{tol_ok:.0f} mm  ·  "
             f"{tt['total_member_length_m']:.0f} m member (~{tt['est_steel_tonnes']:.1f} t)  ·  "
             f"heading = install rotation (same part)", fontsize=8.5, color=MUT)
    p = os.path.join(EXPORTS, "rib_schedule.png")
    fig.savefig(p, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", type=int, default=N_TYPES)
    ap.add_argument("--no-fig", action="store_true")
    args = ap.parse_args()
    build(n_types=args.types, make_fig=not args.no_fig)
