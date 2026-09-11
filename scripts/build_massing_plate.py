"""build_massing_plate.py — the ramped-massing plate: render + bar + distribution.

    blender --background blender/answering_line.blend --python blender/render_massing.py
    python scripts/build_massing_plate.py

The render is S03's fill and S06's ink. This adds the third thing the reference image has
and a render cannot carry: **the bar with the unit**, which S03 calls "the whole claim".

IT ALSO ADDS THE ONE THING THE REFERENCE DOES NOT NEED
    a distribution strip under the bar. The reference ramps a displacement field, which is
    smooth. This ramps `sky_share_pct`, which is violently skewed — most ranked buildings
    take almost nothing and a handful take the rest. A bare linear bar would let a reader
    assume the colours are evenly spread. The strip shows where the mass actually sits, so
    the skew is stated instead of hidden. The ramp itself stays LINEAR: §6.2 refuses a
    gamma on the Fac input, and the honest fix for a skewed ramp is to show the skew.

Every number is read from data/attribution.json at build time.
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
OUT_DIR = os.path.join(PROJECT, "exports", "plates")
RENDER = os.path.join(PROJECT, "exports", "blender", "E_massing_ramp.png")
ATTR = os.path.join(PROJECT, "data", "attribution.json")

PAPER, STEEL, SHADE = (242, 240, 236), (43, 43, 40), (154, 164, 174)
FLAGGED = (224, 72, 61)
RAMP_LO = (224, 221, 216)          # the ramp's own floor, from build_lookdev.RAMP
W, H = 3600, 2400
M = 150

MONO = r"C:\Windows\Fonts\consola.ttf"
MONO_B = r"C:\Windows\Fonts\consolab.ttf"


def log(*a):
    print(*a)
    sys.stdout.flush()


def f(path, px):
    return ImageFont.truetype(path, px)


def tw(d, t, fo):
    b = d.textbbox((0, 0), t, font=fo)
    return b[2] - b[0], b[3] - b[1]


def autocrop(im, pad=24):
    """Trim the paper margin the fitted camera leaves, keeping a little air."""
    a = np.asarray(im.convert("RGB")).astype(int)
    bg = np.array(a[4, 4])
    diff = np.abs(a - bg).sum(axis=2)
    mask = diff > 14
    if not mask.any():
        return im
    ys, xs = np.nonzero(mask)
    box = (max(0, xs.min() - pad), max(0, ys.min() - pad),
           min(im.width, xs.max() + pad), min(im.height, ys.max() + pad))
    log("[crop] %s -> %s" % (im.size, (box[2] - box[0], box[3] - box[1])))
    return im.crop(box)


def ramp_rgb(t):
    """The same two-stop linear ramp the material uses, in sRGB for drawing."""
    t = max(0.0, min(1.0, t))
    return tuple(int(round(RAMP_LO[i] + (FLAGGED[i] - RAMP_LO[i]) * t)) for i in range(3))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if not os.path.exists(RENDER):
        raise SystemExit("missing %s — run blender/render_massing.py first" % RENDER)
    att = json.load(open(ATTR, encoding="utf-8"))
    lead = att["leaderboard"]
    shares = np.array([r["sky_share_pct"] for r in lead], dtype=float)
    mx = float(shares.max())
    n_small = int((shares < 0.1).sum())

    # Take the plate's ground from the RENDER's own background rather than from the palette
    # constant. They differ by a few levels after the view transform, and at plate scale
    # that shows up as a visible rectangle around the image — the seam the paper sweep
    # exists to avoid. Sampling makes the join invisible by construction.
    _probe = Image.open(RENDER).convert("RGB")
    ground = _probe.getpixel((4, 4))
    log("[ground] plate paper taken from the render itself: %s (palette says %s)"
        % (ground, PAPER))
    plate = Image.new("RGB", (W, H), ground)
    d = ImageDraw.Draw(plate)
    f_title, f_sub = f(MONO_B, 66), f(MONO, 30)
    f_lab, f_num, f_micro, f_tiny = f(MONO_B, 26), f(MONO, 26), f(MONO, 21), f(MONO, 18)

    x0, x1 = M, W - M
    d.text((x0, M), "WHO TOOK THE SKY", font=f_title, fill=STEEL)
    d.text((x0, M + 92),
           "measured share of the deck's lost sky, painted on the massing that took it  ·  "
           "%d ranked buildings of %d footprints" % (len(lead), att.get("n_footprints", 2083)),
           font=f_sub, fill=STEEL)
    d.line([(x0, M + 148), (x1, M + 148)], fill=STEEL, width=3)

    # ── the render ────────────────────────────────────────────────────────────────────
    img = autocrop(Image.open(RENDER).convert("RGB"))
    box_w, box_h = 2560, 1720
    sc = min(box_w / img.width, box_h / img.height)
    img = img.resize((int(img.width * sc), int(img.height * sc)), Image.LANCZOS)
    iy = M + 200
    plate.paste(img, (x0, iy))

    # ── the bar ───────────────────────────────────────────────────────────────────────
    bx = x0 + box_w + 150
    by, bh, bw = iy + 40, 900, 54
    for i in range(bh):
        t = 1.0 - i / float(bh - 1)
        d.line([(bx, by + i), (bx + bw, by + i)], fill=ramp_rgb(t))
    d.rectangle([bx, by, bx + bw, by + bh], outline=SHADE, width=2)

    d.text((bx, by - 108), "Sky taken from the deck", font=f_lab, fill=STEEL)
    d.text((bx, by - 74), "share of total measured loss, %", font=f_micro, fill=SHADE)
    d.text((bx + bw + 20, by - 4), "%.2f %%" % mx, font=f_num, fill=STEEL)
    d.text((bx + bw + 20, by + 30), "BIN %s" % lead[0]["id"], font=f_micro, fill=SHADE)
    d.text((bx + bw + 20, by + bh - 28), "0.00 %", font=f_num, fill=STEEL)

    # distribution of the ranked set against that same axis
    # LOG-SCALED WIDTHS, and the label says so. On a linear width the first bin holds 213
    # of 273 and every other bin is one or two buildings, so the strip renders as a single
    # bar and a reader concludes it is broken. The point of the strip is that the rest of
    # the distribution EXISTS but is thin; log is the only scaling that shows both.
    nb = 40
    hist, edges = np.histogram(shares, bins=nb, range=(0.0, mx))
    hmax = float(np.log1p(hist.max())) or 1.0
    hx, hw = bx - 30, 150
    for k in range(nb):
        if not hist[k]:
            continue
        t0, t1 = edges[k] / mx, edges[k + 1] / mx
        y_a = by + int(bh * (1.0 - t1))
        y_b = by + int(bh * (1.0 - t0))
        wpx = max(3, int(round(hw * np.log1p(hist[k]) / hmax)))
        d.rectangle([hx - wpx, y_a, hx, max(y_a + 2, y_b - 1)], fill=(206, 201, 192))
        if hist[k] >= 5:
            lab = str(int(hist[k]))
            lw, _ = tw(d, lab, f_tiny)
            d.text((hx - wpx - lw - 8, y_a - 2), lab, font=f_tiny, fill=STEEL)
    d.text((hx - hw, by + bh + 16), "count per bin, LOG width", font=f_tiny, fill=SHADE)
    d.text((hx - hw, by + bh + 40), "%d of %d take under 0.1%%" % (n_small, len(lead)),
           font=f_tiny, fill=STEEL)

    # ── the leaderboard ───────────────────────────────────────────────────────────────
    ly = by + bh + 110
    d.text((bx - 122, ly), "TOP TEN", font=f_lab, fill=STEEL)
    ly += 44
    for r in lead[:10]:
        yr = r.get("construction_year") or r.get("year")
        d.rectangle([bx - 122, ly + 4, bx - 100, ly + 24],
                    fill=ramp_rgb(r["sky_share_pct"] / mx))
        d.text((bx - 88, ly), "BIN %s" % r["id"], font=f_micro, fill=STEEL)
        d.text((bx + 132, ly), str(yr) if yr else "year n/k", font=f_micro, fill=SHADE)
        s = "%.2f%%" % r["sky_share_pct"]
        wpx, _ = tw(d, s, f_micro)
        d.text((x1 - wpx, ly), s, font=f_micro, fill=STEEL)
        ly += 34

    # ── footer ────────────────────────────────────────────────────────────────────────
    fy = H - M - 96
    d.line([(x0, fy), (x1, fy)], fill=SHADE, width=2)
    fy += 18
    notes = [
        "The ramp is LINEAR in share and deliberately carries no gamma: a building that "
        "takes twice the sky reads twice as hot. The distribution strip beside the bar is "
        "there because that ramp is skewed —",
        "%d of the %d ranked buildings take under 0.1%% each, so most of the city sits at "
        "the floor of the scale. That is the measurement, not a rendering failure."
        % (n_small, len(lead)),
        "Buildings absent from the attribution set are shaded neutral, NOT at the ramp's "
        "zero: absent means not measured, not measured-as-zero.  ·  edges drawn by "
        "Freestyle; no vertex was moved and no height was changed.",
    ]
    for t in notes:
        d.text((x0, fy), t, font=f_tiny, fill=SHADE)
        fy += 24
    d.text((x0, H - M + 14),
           "data/attribution.json  ·  render blender/render_massing.py  ·  ramp material "
           "MAT_Context_Share driven by the per-object sky_share_norm the ingest wrote",
           font=f_tiny, fill=SHADE)

    p = os.path.join(OUT_DIR, "FIG8_massing_ramp.png")
    plate.save(p)
    log("[plate] %s  %dx%d  ·  max share %.2f%% (BIN %s)  ·  %d of %d under 0.1%%"
        % (p, W, H, mx, lead[0]["id"], n_small, len(lead)))


if __name__ == "__main__":
    main()
