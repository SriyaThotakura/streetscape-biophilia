"""build_exploded_plate.py — the exploded axo: the site taken apart into its strata.

    blender --background blender/answering_line.blend --python blender/render_massing.py -- --layers
    python scripts/build_exploded_plate.py

THE GRAMMAR THIS FOLLOWS
    `CV_exploded streetscape.pdf` — this project's own earlier board — and the reference
    sheet's radiation-analysis plate both do the same thing: one site, pulled apart into
    horizontal strata, stacked with air between them, thin leader lines tying the layers
    together, each stratum labelled. It is the clearest way to say "these are different
    readings of ONE place".

WHERE EACH STRATUM COMES FROM
    THE CITY      Blender, E_layer_massing.png    ranked context ramped by sky share
    THE LINE      Blender, E_layer_corridor.png   the deck and the canopy
    THE FOOTPRINT drawn here, from the footprints  every outline at Z = 0, in ink

    The third layer is drawn in Python rather than rendered, using the projection the
    render itself wrote to E_massing_cam.json. An orthographic camera is a pure affine
    map, so a layer Blender never rendered still lands in exact register — no eyeballing,
    no re-projection guesswork.

Nothing under data/ is written.
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
BL = os.path.join(PROJECT, "exports", "blender")
OUT_DIR = os.path.join(PROJECT, "exports", "plates")

STEEL, SHADE, FLAGGED = (43, 43, 40), (154, 164, 174), (224, 72, 61)
RAMP_LO = (224, 221, 216)
INK = (120, 118, 112)

W, H = 3400, 4350
M = 150
# The strata are in REGISTER, so each layer image is the full frame and mostly
# transparent. The gap therefore has to exceed the rendered CONTENT height or the
# corridor draws on top of the city instead of below it — which is what the first
# attempt did at 620. Derived from the content box at build time; this is the floor.
GAP_MIN = 980
MONO = r"C:\Windows\Fonts\consola.ttf"
MONO_B = r"C:\Windows\Fonts\consolab.ttf"

STRATA = [
    ("massing",  "THE CITY",
     "2,083 extruded footprints; the %d in the attribution set carry the measured share"),
    ("corridor", "THE LINE",
     "the deck lofted between the 232 rib rails, and the canopy that answers the loss"),
    ("plan",     "THE FOOTPRINT",
     "every outline at ground level, drawn from the same projection the render used"),
]


def log(*a):
    print(*a)
    sys.stdout.flush()


def f(p, px):
    return ImageFont.truetype(p, px)


def tw(d, t, fo):
    b = d.textbbox((0, 0), t, font=fo)
    return b[2] - b[0], b[3] - b[1]


def ramp_rgb(t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(RAMP_LO[i] + (FLAGGED[i] - RAMP_LO[i]) * t)) for i in range(3))


class Proj:
    """The render's own camera, reused. See dump_camera() in blender/render_massing.py."""

    def __init__(self, doc):
        self.M = np.array(doc["world_to_cam"], dtype=float)
        self.k = float(doc["px_per_m"])
        self.res = doc["res"]

    def __call__(self, x, y, z):
        v = self.M @ np.array([x, y, z, 1.0])
        return (self.res[0] / 2.0 + v[0] * self.k,
                self.res[1] / 2.0 - v[1] * self.k)


def content_box(im):
    a = np.asarray(im)[:, :, 3]
    ys, xs = np.nonzero(a > 4)
    if not len(ys):
        return None
    return xs.min(), ys.min(), xs.max(), ys.max()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    campath = os.path.join(BL, "E_massing_cam.json")
    for p in (campath, os.path.join(BL, "E_layer_massing.png"),
              os.path.join(BL, "E_layer_corridor.png")):
        if not os.path.exists(p):
            raise SystemExit("missing %s — run render_massing.py -- --layers first" % p)
    proj = Proj(json.load(open(campath, encoding="utf-8")))
    fc = json.load(open(os.path.join(PROJECT, "data", "highline_footprints.json"),
                        encoding="utf-8"))
    att = json.load(open(os.path.join(PROJECT, "data", "attribution.json"),
                         encoding="utf-8"))
    lead = att["leaderboard"]
    mx = float(lead[0]["sky_share_pct"])

    layers = {}
    for key in ("massing", "corridor"):
        layers[key] = Image.open(os.path.join(BL, "E_layer_%s.png" % key)).convert("RGBA")

    # ── the drawn stratum: every footprint outline, in the render's own projection ─────
    plan = Image.new("RGBA", tuple(proj.res), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plan)
    share = {str(r["id"]): r["sky_share_pct"] for r in lead}
    n_drawn = 0
    for feat in fc["features"]:
        bid = str(feat["properties"].get("id", ""))
        ring = feat["geometry"]["coordinates"][0][0]
        pts = [proj(float(c[0]), float(c[1]), 0.0) for c in ring]
        if len(pts) < 3:
            continue
        sh = share.get(bid)
        if sh is not None and sh >= 0.5:
            pd.polygon(pts, fill=(*ramp_rgb(sh / mx), 150), outline=STEEL)
        else:
            pd.line(pts + [pts[0]], fill=INK, width=2)
        n_drawn += 1
    log("[plan] %d footprint outlines drawn in the render's projection" % n_drawn)
    layers["plan"] = plan

    # ── crop all strata to the union of their content, so they stay in register ────────
    boxes = [content_box(im) for im in layers.values()]
    boxes = [b for b in boxes if b]
    ux0 = min(b[0] for b in boxes)
    uy0 = min(b[1] for b in boxes)
    ux1 = max(b[2] for b in boxes)
    uy1 = max(b[3] for b in boxes)
    cw, chh = ux1 - ux0, uy1 - uy0
    avail_w = W - 2 * M - 820          # leave a column for the stratum labels
    sc = min(1.0, avail_w / cw)
    log("[reg] common content box %dx%d, scaled %.3f" % (cw, chh, sc))

    ground = (250, 247, 239)
    plate = Image.new("RGB", (W, H), ground)
    d = ImageDraw.Draw(plate)
    f_title, f_sub = f(MONO_B, 64), f(MONO, 30)
    f_lab, f_micro, f_tiny = f(MONO_B, 34), f(MONO, 22), f(MONO, 18)

    x0, x1 = M, W - M
    d.text((x0, M), "ONE SITE, THREE READINGS", font=f_title, fill=STEEL)
    d.text((x0, M + 88),
           "the same orthographic projection, pulled apart  ·  every stratum is the same "
           "%d footprints seen a different way" % len(fc["features"]),
           font=f_sub, fill=STEEL)
    d.line([(x0, M + 142), (x1, M + 142)], fill=STEEL, width=3)

    lay_h = int(chh * sc)
    gap = max(GAP_MIN, int(lay_h * 0.62))
    log("[stack] layer content %d px tall, gap %d px" % (lay_h, gap))
    top = M + 250
    placed = []
    for i, (key, title, sub) in enumerate(STRATA):
        im = layers[key].crop((ux0, uy0, ux1, uy1))
        if sc < 1.0:
            im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
        yy = top + i * gap
        plate.paste(im, (x0, yy), im)
        placed.append((yy, im.height))
        lx = x0 + avail_w + 60
        d.text((lx, yy + 40), title, font=f_lab, fill=STEEL)
        txt = sub % len(lead) if "%d" in sub else sub
        yline = yy + 84
        words, cur = txt.split(), ""
        for w in words:
            t = (cur + " " + w).strip()
            if tw(d, t, f_micro)[0] <= (x1 - lx) or not cur:
                cur = t
            else:
                d.text((lx, yline), cur, font=f_micro, fill=SHADE)
                yline += 28
                cur = w
        if cur:
            d.text((lx, yline), cur, font=f_micro, fill=SHADE)

    # ── leader lines: the same world point, tied through every stratum ────────────────
    anchors = []
    for r in lead[:4]:
        for feat in fc["features"]:
            if str(feat["properties"].get("id", "")) != str(r["id"]):
                continue
            ring = np.array(feat["geometry"]["coordinates"][0][0], dtype=float)
            cxw, czw = ring[:, 0].mean(), ring[:, 1].mean()
            px, _ = proj(cxw, czw, 0.0)
            anchors.append((px, r))
            break
    ytop = placed[0][0]
    ybot = placed[-1][0] + placed[-1][1]
    for px, r in anchors:
        sx = x0 + (px - ux0) * sc
        if not (x0 < sx < x0 + avail_w):
            continue
        for yv in range(int(ytop), int(ybot), 16):
            d.line([(sx, yv), (sx, yv + 7)], fill=SHADE, width=1)
        d.ellipse([sx - 5, ytop - 5, sx + 5, ytop + 5], fill=ramp_rgb(r["sky_share_pct"] / mx),
                  outline=STEEL)
        lab = "BIN %s  %.2f%%" % (r["id"], r["sky_share_pct"])
        d.text((sx + 12, ytop - 44), lab, font=f_tiny, fill=STEEL)
    log("[leader] %d culprits tied through the strata" % len(anchors))

    # ── the bar ───────────────────────────────────────────────────────────────────────
    # horizontal, in the header band, clear of the stratum labels down the right
    bw2, bh2 = 620, 34
    bx, by = x1 - bw2, M + 24
    for i in range(bw2):
        d.line([(bx + i, by), (bx + i, by + bh2)], fill=ramp_rgb(i / float(bw2 - 1)))
    d.rectangle([bx, by, bx + bw2, by + bh2], outline=SHADE, width=2)
    d.text((bx, by - 30), "Sky taken from the deck  ·  share of measured loss, %",
           font=f_tiny, fill=STEEL)
    d.text((bx, by + bh2 + 8), "0.00 %", font=f_tiny, fill=STEEL)
    lab = "%.2f %%  BIN %s" % (mx, lead[0]["id"])
    lw, _ = tw(d, lab, f_tiny)
    d.text((bx + bw2 - lw, by + bh2 + 8), lab, font=f_tiny, fill=STEEL)

    fy = H - M - 78
    d.line([(x0, fy), (x1, fy)], fill=SHADE, width=2)
    fy += 18
    for t in [
        "THE STRATA ARE NOT SEPARATE MODELS. All three are the same site in the same "
        "orthographic camera, offset vertically on the page only — the footprint layer is "
        "drawn in Python from the projection the render wrote out, so it lands in register "
        "by construction rather than by eye.",
        "Outlines are drawn for every footprint; the fill appears only where a building "
        "carries at least 0.5%% of the measured loss. Absent from the attribution set means "
        "not measured, never measured-as-zero.",
    ]:
        d.text((x0, fy), t, font=f_tiny, fill=SHADE)
        fy += 24
    d.text((x0, H - M + 12),
           "data/highline_footprints.json · data/attribution.json · "
           "exports/blender/E_layer_*.png · exports/blender/E_massing_cam.json",
           font=f_tiny, fill=SHADE)

    p = os.path.join(OUT_DIR, "FIG9_exploded_axo.png")
    plate.save(p)
    log("[plate] %s  %dx%d  ·  %d strata" % (p, W, H, len(STRATA)))


if __name__ == "__main__":
    main()
