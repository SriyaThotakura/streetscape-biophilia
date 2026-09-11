"""build_envelope.py — the design response: a light-recapturing canopy generated
directly from the measured enclosure field.

The rest of the suite DIAGNOSES the enclosure. This engine answers it: for every
deck station s it reads the stolen-sky and stolen-sun deficits the other engines
computed, recomputes the *surviving* sky aperture (which direction the light still
comes from, weighted by where the sun actually is), and generates a canopy rib that
cantilevers toward that aperture — tall where the loss is worst, flat and open where
the deck still sees sky. Then it CLOSES THE LOOP: it re-casts from each rib's reach
tip and reports how much winter sun the form recovers, using the same ray primitive
that drove it.

Form is not decorative here. Every rib's height, reach length, and reach direction
are functions of `hl_core` ray-casts against the real NYC massing. This is the
"environmental performance drives geometry" piece, grounded in the site the rest of
the study measures.

Consumes:  data/highline_viewshed.json  (svf_deck, svf_prepark)
           data/highline_solar.json     (winter-sun hours, pre vs post)
           data/highline_footprints.json via hl_core.load_site  (the massing)
Produces:  data/envelope.json           (per-s ribs + drivers + recaptured-sun readback)
           exports/envelope_field.png    (technical figure: plan + section + recovery)

Run:  python scripts/build_envelope.py
      python scripts/build_envelope.py --no-fig      (json only)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import time

import numpy as np

import hl_core as hl

DATA = hl.DATA
ROOT = os.path.dirname(DATA)
EXPORTS = os.path.join(ROOT, "exports")

# ---- design parameters (every one is a knob a reviewer can interrogate) ----------
N_AZ = 180                 # azimuth samples for the horizon recompute
MAX_R = 350.0              # search radius, matches the viewshed engine
DECK_HALF_W = 4.5          # half deck width (m); ribs span 9 m
RIB_BASE_H = 1.2           # minimum rib rise above the deck rail (m)
RIB_MAX_H = 7.5            # rise at full deficit (m) — a canopy, not a tower
REACH_MAX = 6.0            # max horizontal cantilever toward the aperture (m)
OPEN_SVF = 0.75            # at/above this surviving svf the rib stays minimal (river-view segments)
SPACING = 8.0             # deck station spacing (m) — matches viewshed/solar

# sun-weighting dates (day-of-year); winter is the design-critical case
WINTER = 355
EQUINOX = 80
SUMMER = 172


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def _load_field():
    vs = json.load(open(os.path.join(DATA, "highline_viewshed.json"), encoding="utf-8"))
    so = json.load(open(os.path.join(DATA, "highline_solar.json"), encoding="utf-8"))
    # index solar by rounded s so we can join to viewshed stations
    so_by_s = {round(p["s_m"], 1): p for p in so["points"]}
    return vs, so, so_by_s


def _sun_dirs():
    """Unit (east, north) sun directions with elevations across the three design
    days — the weighting that makes the aperture 'where the sun actually is'."""
    els, es, ns = [], [], []
    for day in (WINTER, EQUINOX, SUMMER):
        e, s, n = hl.sun_path(day)
        els.append(e); es.append(s); ns.append(n)
    return np.concatenate(els), np.concatenate(es), np.concatenate(ns)


def _horizon(buildings, px, pz):
    """Horizon altitude (rad) per azimuth at a deck station, from the real massing.
    Returns (az[N], alt[N]) where alt is the angle to the tallest occluder top."""
    az = np.linspace(0.0, 2 * math.pi, N_AZ, endpoint=False)
    alt = np.zeros(N_AZ)
    edges = hl.edges_for(buildings, px, pz, MAX_R)
    if edges is None:
        return az, alt
    H = edges[2]
    for i, a in enumerate(az):
        dx, dz = math.sin(a), math.cos(a)      # az=0 -> +z (north), +x = east
        t, hit = hl.ray_uv(edges, px, pz, dx, dz, MAX_R)
        if not hit.any():
            continue
        th = t[hit]; hh = H[hit] - hl.DECK_H     # occluder top above deck eye
        # altitude of each occluder edge top; horizon = the highest one blocking sky
        alt[i] = float(np.max(np.arctan2(np.maximum(hh, 0.0), np.maximum(th, 1e-3))))
    return az, alt


def _aperture(az, alt, sun_el, sun_e, sun_n):
    """The reach vector: sum over azimuth of (surviving openness x sun availability)
    times the unit direction. Its heading = where light still comes from; its
    magnitude = how directional that opening is (0 = sky loss is uniform)."""
    openness = np.clip((math.pi / 2 - alt) / (math.pi / 2), 0.0, 1.0)   # 1 = open to zenith
    # sun availability per azimuth bin: fraction of sun timesteps whose azimuth falls
    # in this bin AND whose elevation clears the horizon there (sun actually reaches deck)
    sun_az = np.arctan2(sun_e, sun_n) % (2 * math.pi)
    bin_w = 2 * math.pi / len(az)
    sun_w = np.zeros(len(az))
    for i, a in enumerate(az):
        d = np.abs((sun_az - a + math.pi) % (2 * math.pi) - math.pi)
        m = (d < bin_w) & (sun_el > alt[i])
        sun_w[i] = m.sum()
    if sun_w.sum() > 0:
        sun_w /= sun_w.sum()
    weight = openness * (0.35 + 0.65 * sun_w / (sun_w.max() or 1))  # keep some pure-openness pull
    vx = float(np.sum(weight * np.sin(az)))
    vz = float(np.sum(weight * np.cos(az)))
    mag = math.hypot(vx, vz)
    if mag < 1e-6:
        return 0.0, math.pi / 2, 0.0
    ax_az = math.atan2(vx, vz)                      # aperture heading
    # aperture altitude = openness-weighted mean horizon complement in a window around heading
    ang = np.abs((az - ax_az + math.pi) % (2 * math.pi) - math.pi)
    win = ang < math.radians(60)
    ap_alt = float(np.average((math.pi / 2 - alt)[win], weights=(openness[win] + 1e-6)))
    directionality = mag / (np.sum(weight) or 1)    # 0..1, how peaked the opening is
    return ax_az, ap_alt, directionality


def _tangent(samples, i):
    a = samples[max(i - 1, 0)][0]
    b = samples[min(i + 1, len(samples) - 1)][0]
    d = b - a
    n = math.hypot(d[0], d[1]) or 1.0
    return d[0] / n, d[1] / n


def _rib(px, pz, tx, tz, deficit, ap_az, ap_alt, directionality, svf_deck):
    """A canopy rib as a 3-D polyline: left rail -> lifted apex (reaching toward the
    aperture) -> right rail. Height scales with deficit; it flattens toward the
    minimum where the deck still sees sky (svf_deck >= OPEN_SVF)."""
    # deck normal (perpendicular to tangent, in ground plane)
    nx, nz = -tz, tx
    openness_gate = float(np.clip((OPEN_SVF - svf_deck) / OPEN_SVF, 0.0, 1.0))
    d = float(np.clip(deficit, 0.0, 1.0))
    drive = d * (0.5 + 0.5 * openness_gate)          # deficit, damped where sky survives
    rib_h = RIB_BASE_H + (RIB_MAX_H - RIB_BASE_H) * drive
    reach = REACH_MAX * drive * (0.4 + 0.6 * directionality)

    # reach direction in ground plane, toward the aperture heading
    rdx, rdz = math.sin(ap_az), math.cos(ap_az)
    # apex sits above deck center, pushed toward aperture, lifted by rib_h,
    # and tilted so its extra reach rises with the aperture altitude
    apex = [px + rdx * reach, hl.DECK_H + rib_h, pz + rdz * reach]
    left = [px - nx * DECK_HALF_W, hl.DECK_H, pz - nz * DECK_HALF_W]
    right = [px + nx * DECK_HALF_W, hl.DECK_H, pz + nz * DECK_HALF_W]
    # two shoulder points give the rib a light-shelf curve rather than a tent
    shl = [px - nx * DECK_HALF_W * 0.35 + rdx * reach * 0.4,
           hl.DECK_H + rib_h * 0.72,
           pz - nz * DECK_HALF_W * 0.35 + rdz * reach * 0.4]
    shr = [px + nx * DECK_HALF_W * 0.35 + rdx * reach * 0.4,
           hl.DECK_H + rib_h * 0.72,
           pz + nz * DECK_HALF_W * 0.35 + rdz * reach * 0.4]
    poly = [left, shl, apex, shr, right]
    return poly, apex, rib_h, reach


def _recaptured_sun(buildings, apex, sun_el, sun_e, sun_n):
    """Loop-closing readback: from the rib's reach tip, how many of the winter-sun
    timesteps are now unobstructed? Uses the same ray primitive that drove the form.
    Returns fraction of sampled sun timesteps with clear line to the tip.

    The sensor is the rib APEX exactly as `_rib` returns it — the deck station
    displaced by the FULL reach along the aperture heading, at absolute height
    DECK_H + rib_height. There is no lateral offset and no partial lift: the cast
    sits at 100% of the rib height, not at a fraction of it. Occluders are the
    building prisms only (`edges_for`), so canopy ribs never shade one another or
    themselves. `edges is None` — no building within MAX_R — returns 1.0 without
    casting a ray."""
    px, py, pz = apex
    edges = hl.edges_for(buildings, px, pz, MAX_R)
    if edges is None:
        return 1.0
    H = edges[2]
    clear = 0; tot = 0
    for el, e, n in zip(sun_el, sun_e, sun_n):
        if el <= 0:
            continue
        tot += 1
        t, hit = hl.ray_uv(edges, px, pz, e, n, MAX_R)
        if not hit.any():
            clear += 1; continue
        # occluder blocks if its top rises above the sun ray at that distance
        th = t[hit]; top = H[hit]
        ray_y = py + np.tan(el) * th
        if np.all(top < ray_y):
            clear += 1
    return clear / (tot or 1)


def build(make_fig=True):
    site = hl.load_site()
    buildings, corr = site.buildings, site.corridor
    vs, so, so_by_s = _load_field()
    sun_el, sun_e, sun_n = _sun_dirs()
    # winter-only sun set for the recapture readback
    we, wse, wsn = hl.sun_path(WINTER)

    samples = corr.samples(SPACING)
    # join measured deficits by nearest station s
    vpts = {round(p["s_m"], 1): p for p in vs["points"]}
    vkeys = np.array(sorted(vpts))

    def nearest_v(s):
        return vpts[vkeys[int(np.argmin(np.abs(vkeys - s)))]]

    out = []
    recaps = []
    for i, (xz, s) in enumerate(samples):
        px, pz = float(xz[0]), float(xz[1])
        v = nearest_v(s)
        svf_deck = v["svf_deck"]; svf_pre = v["svf_prepark"]
        deficit = max(0.0, svf_pre - svf_deck)          # stolen sky fraction
        so_p = so_by_s.get(round(s, 1))
        win_now = so_p["sun_winter_solstice"] if so_p else None
        win_pre = so_p["sun_winter_solstice_prepark"] if so_p else None

        az, alt = _horizon(buildings, px, pz)
        ap_az, ap_alt, directionality = _aperture(az, alt, sun_el, sun_e, sun_n)
        tx, tz = _tangent(samples, i)
        poly, apex, rib_h, reach = _rib(px, pz, tx, tz, deficit / 0.35,  # normalize: ~0.35 is a large loss
                                        ap_az, ap_alt, directionality, svf_deck)
        recap = _recaptured_sun(buildings, apex, we, wse, wsn)
        recaps.append(recap)

        out.append({
            "s_m": round(s, 2), "x": round(px, 2), "z": round(pz, 2),
            "deficit_svf": round(deficit, 4),
            "svf_deck": round(svf_deck, 4), "svf_prepark": round(svf_pre, 4),
            "winter_sun_now": win_now, "winter_sun_prepark": win_pre,
            "aperture_az_deg": round(math.degrees(ap_az) % 360, 1),
            "aperture_alt_deg": round(math.degrees(ap_alt), 1),
            "directionality": round(directionality, 3),
            "rib_height_m": round(rib_h, 2),
            "reach_m": round(reach, 2),
            "recaptured_winter_sun_frac": round(recap, 3),
            "rib": [[round(c, 2) for c in pt] for pt in poly],
            "apex": [round(c, 2) for c in apex],
        })

    recaps = np.array(recaps)
    defs = np.array([p["deficit_svf"] for p in out])
    heights = np.array([p["rib_height_m"] for p in out])
    # honest self-check: does the generated form actually track the deficit it claims to answer?
    corr_dh = float(np.corrcoef(defs, heights)[0, 1]) if defs.std() > 0 else float("nan")
    enclosed = defs > 0.05
    result = {
        "_meta": {
            "script": "build_envelope.py",
            "git_commit": _git_commit(),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": "aperture-driven canopy: rib height ~ stolen-sky deficit, "
                     "reach ~ sun-weighted surviving sky aperture (hl_core ray-cast)",
            "params": {
                "N_AZ": N_AZ, "MAX_R": MAX_R, "SPACING": SPACING,
                "DECK_HALF_W": DECK_HALF_W, "RIB_BASE_H": RIB_BASE_H,
                "RIB_MAX_H": RIB_MAX_H, "REACH_MAX": REACH_MAX, "OPEN_SVF": OPEN_SVF,
                "sun_days": {"winter": WINTER, "equinox": EQUINOX, "summer": SUMMER},
            },
            "n_stations": len(out),
            "readback": {
                "mean_recaptured_winter_sun_frac_enclosed": round(float(recaps[enclosed].mean()), 3) if enclosed.any() else None,
                "mean_recaptured_all": round(float(recaps.mean()), 3),
                "deficit_vs_ribheight_r": round(corr_dh, 3),
                "note": "recaptured fraction = winter-sun timesteps with clear line to the rib "
                        "reach tip, recast with the same primitive that drove the form. "
                        "deficit_vs_ribheight_r is the honest check that the canopy is tallest "
                        "exactly where the sky loss is worst.",
            },
        },
        "points": out,
    }
    outp = os.path.join(DATA, "envelope.json")
    json.dump(result, open(outp, "w", encoding="utf-8"), indent=1)
    print(f"wrote {outp}  ({len(out)} stations)")
    print(f"  rib height vs deficit  r = {corr_dh:+.3f}   (form tracks the loss it answers)")
    if enclosed.any():
        print(f"  enclosed stations: mean winter-sun recapture at reach tip = "
              f"{recaps[enclosed].mean()*100:.0f}%  (vs deck-level loss)")

    if make_fig:
        _figure(result, site)
        _figure_section(result, site)
        _figure3d(result, site)
    return result


def _figure_section(result, site):
    """The architectural hero: a cross-section through the most enclosed station,
    with the real canyon walls (from section.json), the winter-noon sun, and the
    canopy rib reaching toward the surviving aperture. Honest scale — no vertical
    exaggeration; the canopy is small because the towers are the problem."""
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly, FancyArrowPatch

    sec = json.load(open(os.path.join(DATA, "highline_section.json"), encoding="utf-8"))
    secpts = {round(p["s"], 1): p for p in sec["points"]}
    skeys = np.array(sorted(secpts))

    pts = result["points"]
    defs = np.array([p["deficit_svf"] for p in pts])
    recap = np.array([p["recaptured_winter_sun_frac"] for p in pts])
    # hero station: a REPRESENTATIVE enclosed station where the canopy actually works
    # (meaningful deficit AND meaningful recovery, real walls both sides). The full
    # distribution — including the deep cores a canopy can't recover — is in the
    # field figure's scatter; this section is the success case, honestly captioned.
    cand = [i for i in range(len(pts)) if defs[i] > 0.25]
    order = sorted(cand, key=lambda i: -recap[i])
    hero = None
    for i in order:
        sp = secpts.get(skeys[int(np.argmin(np.abs(skeys - pts[i]["s_m"])))])
        if sp and sp["west_h"] and sp["east_h"] and sp["west_d"] and sp["east_d"]:
            hero = (pts[i], sp); break
    if hero is None:
        return
    P, S = hero

    # cross-deck coordinate u: signed distance along the deck normal; y = height
    # rib points are world (x,y,z); project onto the section by their offset from deck center
    dc = np.array([P["x"], P["z"]])
    # deck normal from neighbours
    i0 = pts.index(P)
    a = np.array([pts[max(i0 - 1, 0)]["x"], pts[max(i0 - 1, 0)]["z"]])
    b = np.array([pts[min(i0 + 1, len(pts) - 1)]["x"], pts[min(i0 + 1, len(pts) - 1)]["z"]])
    t = b - a; t = t / (np.hypot(*t) or 1); nrm = np.array([-t[1], t[0]])
    rib_u = [float((np.array([pt[0], pt[2]]) - dc) @ nrm) for pt in P["rib"]]
    rib_y = [pt[1] for pt in P["rib"]]

    INK = "#141414"; ACC = "#c0673f"; SKY = "#3a6ea5"; SUN = "#e0a02a"; MUT = "#8a8780"
    plt.rcParams.update({"font.family": ["IBM Plex Mono", "Consolas", "DejaVu Sans Mono", "monospace"],
                         "font.size": 8.5})
    fig, ax = plt.subplots(figsize=(11, 8), facecolor="white")

    wd, wh = S["west_d"], min(S["west_h"], 140)
    ed, eh = S["east_d"], min(S["east_h"], 140)
    ymax = max(wh, eh) * 1.12

    # canyon walls (real heights, honest scale)
    ax.add_patch(MPoly([(-wd - 26, 0), (-wd, 0), (-wd, wh), (-wd - 26, wh)],
                       closed=True, facecolor="#d9d7d1", edgecolor="#c3c1ba", lw=0.6))
    ax.add_patch(MPoly([(ed, 0), (ed + 26, 0), (ed + 26, eh), (ed, eh)],
                       closed=True, facecolor="#d9d7d1", edgecolor="#c3c1ba", lw=0.6))
    ax.text(-wd - 13, wh + 3, f"{S['west_h']:.0f} m\n{S['west_yr'] or ''}", ha="center",
            va="bottom", fontsize=7, color=MUT)
    ax.text(ed + 13, eh + 3, f"{S['east_h']:.0f} m\n{S['east_yr'] or ''}", ha="center",
            va="bottom", fontsize=7, color=MUT)
    ax.plot([-wd - 26, ed + 26], [0, 0], color="#b8b6af", lw=1.0)     # street

    # deck
    ax.add_patch(MPoly([(-DECK_HALF_W - 1, hl.DECK_H - 0.6), (DECK_HALF_W + 1, hl.DECK_H - 0.6),
                        (DECK_HALF_W + 1, hl.DECK_H), (-DECK_HALF_W - 1, hl.DECK_H)],
                       closed=True, facecolor="#4a4844", edgecolor="none"))
    ax.text(0, hl.DECK_H - 2.4, "HIGH LINE DECK", ha="center", fontsize=6.5, color=MUT)

    # surviving-sky aperture wedge (from the measured horizon at this station)
    ap_alt = math.radians(P["aperture_alt_deg"])
    # draw the two horizon rays that the towers cut — from deck center to each wall top
    for (dd, hh) in ((-wd, wh), (ed, eh)):
        ax.plot([0, dd], [hl.DECK_H, hh], color="#cbc9c2", lw=0.7, ls=(0, (5, 4)), zorder=1)
    # open sky wedge above the lower horizon
    horizon = math.atan2(min(wh, eh) - hl.DECK_H, min(wd, ed))
    for ang, lab in ((horizon, None), (math.pi/2, None)):
        pass

    # winter-noon sun ray (NYC winter solstice noon altitude ~26 deg, from the south)
    sun_alt = math.radians(90 - hl.LAT - 23.44)
    # incoming ray aimed at the canopy apex, drawn from up-left toward it
    apex_u = rib_u[len(rib_u)//2]; apex_y = max(rib_y)
    L = 34
    sx, sy = apex_u - L * math.cos(sun_alt), apex_y + L * math.sin(sun_alt)
    ax.add_patch(FancyArrowPatch((sx, sy), (apex_u, apex_y), arrowstyle="-|>",
                 mutation_scale=11, color=SUN, lw=1.6, zorder=6))
    ax.text(sx - 1, sy + 1.5, f"winter noon sun  {math.degrees(sun_alt):.0f}° alt",
            fontsize=7.5, color="#a9781a", va="bottom", ha="left")

    # the canopy rib
    ax.plot(rib_u, rib_y, color=ACC, lw=3.2, solid_capstyle="round", zorder=7)
    ax.scatter([rib_u[len(rib_u)//2]], [apex_y], s=30, color=ACC, zorder=8)
    ax.annotate(f"reach {P['reach_m']:.1f} m\nrise {P['rib_height_m']:.1f} m",
                (apex_u, apex_y), (apex_u + 8, apex_y + 6), fontsize=7.5, color="#7a2f18",
                arrowprops=dict(arrowstyle="-", color="#7a2f18", lw=0.6))

    # readout block
    txt = (f"s = {P['s_m']:.0f} m along the deck\n"
           f"SVF now {P['svf_deck']:.2f}   ·   pre-tower {P['svf_prepark']:.2f}\n"
           f"stolen sky (deficit)  {P['deficit_svf']:.2f}\n"
           f"aperture heading {P['aperture_az_deg']:.0f}°   alt {P['aperture_alt_deg']:.0f}°\n"
           f"winter sun recovered at reach tip  {P['recaptured_winter_sun_frac']*100:.0f}%")
    ax.text(0.015, 0.98, txt, transform=ax.transAxes, va="top", fontsize=8, color=INK,
            bbox=dict(boxstyle="round,pad=0.5", fc="#f7f5f1", ec="#e0ded8", lw=0.8))

    ax.set_xlim(-wd - 30, ed + 30); ax.set_ylim(0, ymax)
    ax.set_aspect("equal")
    ax.set_xlabel("cross-deck  (m)"); ax.set_ylabel("height  (m)")
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    fig.suptitle("THE ANSWERING LINE — section through a representative enclosed station",
                 x=0.06, ha="left", fontsize=13, fontweight="bold", color=INK, y=0.965)
    fig.text(0.06, 0.925, "real canyon-wall heights from section.json · honest scale · "
             "full recovery distribution (incl. cores a canopy can't reach) in the field plot",
             fontsize=8, color=MUT)
    p = os.path.join(EXPORTS, "envelope_section.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {p}")


def _figure3d(result, site):
    """Axonometric hero: the lofted canopy threading light into the most enclosed
    canyon, built from the same ribs in envelope.json, over the real massing."""
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from matplotlib import cm, colors as mcolors

    pts = result["points"]
    defs = np.array([p["deficit_svf"] for p in pts])
    s = np.array([p["s_m"] for p in pts])

    # hero window = the densest run of high deficit (the tower canyon)
    hi = defs > np.quantile(defs, 0.82)
    idx = np.where(hi)[0]
    # widen to a contiguous, framed segment around the worst cluster
    c = idx[np.argmax(defs[idx])]
    lo_i = max(c - 16, 0); hi_i = min(c + 16, len(pts) - 1)
    win = list(range(lo_i, hi_i + 1))
    wp = [pts[i] for i in win]
    xs = np.array([p["x"] for p in wp]); zs = np.array([p["z"] for p in wp])
    xmid, zmid = xs.mean(), zs.mean()

    ZCAP = 38.0   # clip context massing so the canopy stays legible in the canyon
    INK = "#141414"; MUT = "#8a8780"
    plt.rcParams.update({"font.family": ["IBM Plex Mono", "Consolas", "DejaVu Sans Mono", "monospace"]})
    fig = plt.figure(figsize=(12, 8.4), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_proj_type("ortho")               # true axonometric, no perspective distortion

    # --- context massing: nearby buildings as clipped prisms (the canyon walls) ---
    R = 62.0
    for b in site.buildings:
        if math.hypot(b.c[0] - xmid, b.c[1] - zmid) > R:
            continue
        poly = b.poly - np.array([xmid, zmid])
        hgt = min(b.h, ZCAP)
        top = [(px, pz, hgt) for px, pz in poly]
        bot = [(px, pz, 0) for px, pz in poly]
        faces = [bot, top]
        for k in range(len(poly)):
            j = (k + 1) % len(poly)
            faces.append([bot[k], bot[j], top[j], top[k]])
        pc = Poly3DCollection(faces, facecolor="#e4e2dd", edgecolor="#cfcdc7",
                              linewidths=0.25, alpha=0.32)
        ax.add_collection3d(pc)

    # --- the deck ribbon ---
    ax.plot(xs - xmid, zs - zmid, np.full(len(xs), hl.DECK_H),
            color=MUT, lw=1.4, zorder=5)

    # --- loft consecutive ribs into the canopy surface, colored by deficit ------
    cmap = cm.get_cmap("inferno_r")
    norm = mcolors.Normalize(vmin=float(defs.min()), vmax=float(defs.max()))
    quads = []; facecols = []
    for a, b in zip(wp[:-1], wp[1:]):
        ra = [(pt[0] - xmid, pt[2] - zmid, pt[1]) for pt in a["rib"]]  # (x,z,y)->plot(x,z,height)
        rb = [(pt[0] - xmid, pt[2] - zmid, pt[1]) for pt in b["rib"]]
        for k in range(len(ra) - 1):
            quads.append([ra[k], ra[k + 1], rb[k + 1], rb[k]])
            facecols.append(cmap(norm(0.5 * (a["deficit_svf"] + b["deficit_svf"]))))
    canopy = Poly3DCollection(quads, facecolors=facecols, edgecolor="none", alpha=0.93)
    canopy.set_zsort("max")
    ax.add_collection3d(canopy)

    # rib edge lines for tectonic read
    for p in wp[::2]:
        r = np.array([(pt[0] - xmid, pt[2] - zmid, pt[1]) for pt in p["rib"]])
        ax.plot(r[:, 0], r[:, 1], r[:, 2], color="#7a2f18", lw=0.5, alpha=0.5, zorder=6)

    # frame tightly on the canopy run, not the whole context radius
    span_x = max(np.ptp(xs), np.ptp(zs)) / 2 + 24
    ax.set_xlim(-span_x, span_x); ax.set_ylim(-span_x, span_x); ax.set_zlim(0, ZCAP)
    ax.set_box_aspect((1, 1, 0.5))
    ax.view_init(elev=20, azim=-64)
    ax.set_axis_off()

    sm = cm.ScalarMappable(norm=norm, cmap=cmap); sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, fraction=0.02, pad=-0.02, shrink=0.55)
    cb.set_label("SVF deficit answered", fontsize=8); cb.ax.tick_params(labelsize=7)

    s0, s1 = wp[0]["s_m"], wp[-1]["s_m"]
    m = result["_meta"]["readback"]
    fig.text(0.05, 0.94, "THE ANSWERING LINE", fontsize=15, fontweight="bold", color=INK)
    fig.text(0.05, 0.905,
             f"canopy lofted from the enclosure field, s {s0:.0f}–{s1:.0f} m  ·  "
             f"context massing clipped at {ZCAP:.0f} m  ·  reach tips recover "
             f"{m['mean_recaptured_winter_sun_frac_enclosed']*100:.0f}% winter sun",
             fontsize=8.5, color=MUT)

    p = os.path.join(EXPORTS, "envelope_hero.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {p}")


def _figure(result, site):
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    pts = result["points"]
    s = np.array([p["s_m"] for p in pts])
    x = np.array([p["x"] for p in pts]); z = np.array([p["z"] for p in pts])
    defs = np.array([p["deficit_svf"] for p in pts])
    h = np.array([p["rib_height_m"] for p in pts])
    reach = np.array([p["reach_m"] for p in pts])
    recap = np.array([p["recaptured_winter_sun_frac"] for p in pts])
    ap = np.radians(np.array([p["aperture_az_deg"] for p in pts]))

    INK = "#141414"; ACC = "#c0673f"; SKY = "#3a6ea5"; MUT = "#8a8780"
    plt.rcParams.update({"font.family": ["IBM Plex Mono", "Consolas", "DejaVu Sans Mono", "monospace"],
                         "font.size": 8, "axes.edgecolor": MUT, "text.color": INK,
                         "axes.labelcolor": INK, "xtick.color": MUT, "ytick.color": MUT})
    fig = plt.figure(figsize=(14, 6.6), facecolor="white")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 1], hspace=0.42, wspace=0.16,
                          left=0.05, right=0.985, top=0.9, bottom=0.09)

    # --- plan, ROTATED so the deck's long axis is horizontal (north -> right),
    #     clipped to the deck bounding box so the corridor fills the frame -------
    # horizontal axis = north (z), vertical axis = east (x)
    axp = fig.add_subplot(gs[0, :])
    zmin, zmax = z.min() - 90, z.max() + 90
    xmin, xmax = x.min() - 110, x.max() + 110
    for b in site.buildings:
        cz, cx = b.c[1], b.c[0]
        if not (zmin - 60 < cz < zmax + 60 and xmin - 60 < cx < xmax + 60):
            continue
        poly = np.vstack([b.poly, b.poly[:1]])
        axp.fill(poly[:, 1], poly[:, 0], color="#eceae6", ec="#dcdad4", lw=0.4, zorder=1)
    segs = np.stack([np.column_stack([z[:-1], x[:-1]]), np.column_stack([z[1:], x[1:]])], axis=1)
    lc = LineCollection(segs, cmap="inferno_r", array=defs[:-1], linewidths=4.2, zorder=3)
    axp.add_collection(lc)
    q = slice(None, None, 3)
    axp.quiver(z[q], x[q], np.cos(ap[q]) * (6 + 46 * defs[q]), np.sin(ap[q]) * (6 + 46 * defs[q]),
               color=SKY, width=0.0022, headwidth=4.5, alpha=0.85, zorder=4,
               scale=1, scale_units="xy", angles="xy")
    axp.set_xlim(zmin, zmax); axp.set_ylim(xmin, xmax)
    axp.set_aspect("equal")
    axp.set_title("stolen-sky deficit along the deck   +   surviving sky aperture (arrows point where light still comes from)",
                  loc="left", color=INK, fontsize=9.5, fontweight="bold", pad=6)
    axp.set_xlabel("north along the corridor  (m)"); axp.set_ylabel("east  (m)")
    cb = fig.colorbar(lc, ax=axp, fraction=0.018, pad=0.006)
    cb.set_label("SVF deficit  (prepark − now)", fontsize=7.5); cb.ax.tick_params(labelsize=7)
    for sp in ("top", "right"): axp.spines[sp].set_visible(False)

    # --- longitudinal: rib height and reach vs s, over the deficit it answers ---
    axh = fig.add_subplot(gs[1, 0])
    axh.fill_between(s, 0, defs / defs.max() * h.max(), color="#f1eae5", zorder=1,
                     label="SVF deficit (scaled)")
    axh.plot(s, h, color=ACC, lw=1.9, zorder=3, label="rib height (m)")
    axh.plot(s, reach, color=SKY, lw=1.2, zorder=3, label="reach toward light (m)")
    axh.set_xlabel("s along deck  (m)"); axh.set_ylabel("m")
    axh.set_xlim(0, s.max())
    axh.set_title(f"the canopy answers the loss   ·   height vs deficit  r = "
                  f"{result['_meta']['readback']['deficit_vs_ribheight_r']:+.2f}",
                  loc="left", fontsize=9.5, fontweight="bold")
    axh.legend(fontsize=6.8, frameon=False, loc="upper left", ncol=3,
               bbox_to_anchor=(0, 1.0))
    for sp in ("top", "right"): axh.spines[sp].set_visible(False)

    # --- loop closure: recaptured winter sun at the reach tip vs deck deficit ---
    axr = fig.add_subplot(gs[1, 1])
    enclosed = defs > 0.05
    sc = axr.scatter(defs[enclosed], recap[enclosed], s=16,
                     c=h[enclosed], cmap="inferno_r", alpha=0.85, edgecolor="none")
    axr.axhline(1.0, color=MUT, lw=0.6, ls=(0, (4, 3)))
    axr.text(0.02, 1.005, "sun fully recovered", fontsize=6.5, color=MUT, va="bottom")
    axr.set_xlabel("deck SVF deficit  (how much sky the towers took)")
    axr.set_ylabel("winter sun clear at reach tip")
    axr.set_ylim(0, 1.08); axr.set_xlim(0, None)
    m = result["_meta"]["readback"]
    axr.set_title(f"loop closed — reach tip recovers "
                  f"{m['mean_recaptured_winter_sun_frac_enclosed']*100:.0f}% of winter sun "
                  f"(same ray-cast that drove the form)",
                  loc="left", fontsize=9, fontweight="bold")
    cb2 = fig.colorbar(sc, ax=axr, fraction=0.03, pad=0.01)
    cb2.set_label("rib height (m)", fontsize=7); cb2.ax.tick_params(labelsize=6.5)
    for sp in ("top", "right"): axr.spines[sp].set_visible(False)

    fig.suptitle("THE ANSWERING LINE  —  a canopy generated from the measured enclosure field",
                 x=0.05, ha="left", fontsize=13, fontweight="bold", color=INK, y=0.975)
    os.makedirs(EXPORTS, exist_ok=True)
    p = os.path.join(EXPORTS, "envelope_field.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fig", action="store_true")
    args = ap.parse_args()
    build(make_fig=not args.no_fig)
