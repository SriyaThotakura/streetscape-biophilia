"""build_hero_plate.py — assemble the W1 hero plate.

    python scripts/build_hero_plate.py

THE SPEC THIS BUILDS, VERBATIM
    `refrences/pintest_layouts/visual-language.html`, project id "5", field `plate`:

        "The eye-level hero with figures, and directly under it a strip of three
         capture-and-overlay pairs showing what the pipeline extracted from each."

    and the four `lang` rules it has to obey:
        - "Detection needs a before and after. Same frame twice: the plate as captured,
           then the plate with the extracted geometry drawn over it in one accent."
        - "Eye level with people in it."
        - "Efficiency reads as a ratio. Put the number on the drawing."
        - "Keep the render honest. Neutral light, no lens flare, no volumetrics."

    and its `clarity` note, which is why nothing below is typed:
        "Do not retype numbers that a caption file already carries — quote them from their
         source so they cannot drift."

EVERY NUMBER ON THIS PLATE IS RESOLVED AT BUILD TIME
    the hero's figures      <- houdini/cameras.json, through pick_cameras.resolve()
    the strip's figures     <- exports/cv_overlays/strip.json, which quotes
                               data/highline_exposure.json
    the recapture caveats   <- the station's own
                               caveats_that_must_travel_with_it
    Not one of them is written in this file. If a value changes upstream, re-run.

INPUTS
    exports/blender/A_hero_eye_level.png     blender/render_all.py
    exports/cv_overlays/*.png + strip.json   scripts/build_cv_overlays.py

OUTPUT
    exports/plates/HERO_A_answering_line.png
"""

import json
import os
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJECT, "houdini"))
import pick_cameras as pc                     # noqa: E402  — resolve(), the caption source

OUT_DIR = os.path.join(PROJECT, "exports", "plates")
HERO = os.path.join(PROJECT, "exports", "blender", "A_hero_eye_level.png")
STRIP = os.path.join(PROJECT, "exports", "cv_overlays", "strip.json")

# visual-language.html :: P id "5" :: pal
PAPER, STEEL, SHADE = "#f2f0ec", "#2b2b28", "#9aa4ae"
DETECTED, FLAGGED = "#4fb0a8", "#e0483d"

W, H = 3508, 2480                              # A4 landscape @ 300 dpi, as §11.3 uses
M = 170                                        # margin
GUT = 34                                       # gutter

MONO = r"C:\Windows\Fonts\consola.ttf"
MONO_B = r"C:\Windows\Fonts\consolab.ttf"


def font(path, px):
    return ImageFont.truetype(path, px)


def log(*a):
    print(*a)
    sys.stdout.flush()


def tw(d, text, f):
    b = d.textbbox((0, 0), text, font=f)
    return b[2] - b[0], b[3] - b[1]


def rule(d, x0, y, x1, col=SHADE, wpx=2):
    d.line([(x0, y), (x1, y)], fill=col, width=wpx)


def fit(im, box_w, box_h, ybias=0.5):
    """Cover-crop to the box — never letterbox onto the paper.

    `ybias` is where the kept window sits vertically: 0.5 centres it, lower keeps more of
    the top. The hero is cropped high because the canopy is at the top of the frame and the
    deck at the bottom is the least informative part of it; the same convention the
    reference contact sheet uses on its own cards.
    """
    sc = max(box_w / im.width, box_h / im.height)
    r = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
    x = (r.width - box_w) // 2
    y = int((r.height - box_h) * ybias)
    return r.crop((x, y, x + box_w, y + box_h))


def wrap_px(d, text, f, px):
    """Wrap on measured pixel width, not on a guessed character count."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tw(d, t, f)[0] <= px or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def station_numbers():
    """The hero's caption lines, resolved from cameras.json — never transcribed."""
    doc = json.load(open(os.path.join(PROJECT, "houdini", "cameras.json"), encoding="utf-8"))
    st = doc["stations"][0]
    out = []
    for line in st["caption"]["lines"]:
        val, found = pc.resolve(st, line["key"])
        if not found or val is None:
            continue
        try:
            shown = line["format"].format(val)
        except (ValueError, TypeError):
            shown = str(val)
        out.append((line["label"], shown))
    caveats, _ = pc.resolve(st, st["caption"]["caveats_key"])
    prints_recapture = any("recaptured" in ln["key"] for ln in st["caption"]["lines"])
    return st, out, (caveats if (prints_recapture and caveats) else []), doc["key_light"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for p in (HERO, STRIP):
        if not os.path.exists(p):
            raise SystemExit("missing input: %s" % p)
    strip = json.load(open(STRIP, encoding="utf-8"))
    st, lines, caveats, key_light = station_numbers()

    plate = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(plate)
    f_title = font(MONO_B, 62)
    f_sub = font(MONO, 30)
    f_lab = font(MONO_B, 26)
    f_num = font(MONO, 26)
    f_micro = font(MONO, 21)
    f_tiny = font(MONO, 18)

    x0, x1 = M, W - M
    y = M

    # ── header ────────────────────────────────────────────────────────────────────────
    d.text((x0, y), "THE ANSWERING LINE", font=f_title, fill=STEEL)
    right = "STATION A · EYE LEVEL · %s" % st["id"]
    wpx, _ = tw(d, right, f_sub)
    d.text((x1 - wpx, y + 24), right, font=f_sub, fill=SHADE)
    y += 92
    sub = ("the canopy at the worst enclosure where it still works  ·  "
           "winter solstice day %s, %.2f deg elevation at %.1f deg azimuth"
           % (key_light["day_of_year"], key_light["elev_deg"], key_light["azim_deg"]))
    d.text((x0, y), sub, font=f_sub, fill=STEEL)
    y += 52
    rule(d, x0, y, x1, STEEL, 3)
    y += 30

    # ── vertical budget ───────────────────────────────────────────────────────────────
    # Everything below the hero has a known height, so the hero takes what is left. Laying
    # it out the other way round is what pushed the caveats off the bottom of the first
    # draft — and a caveat that falls off the page is a caveat that did not travel.
    strip_card_h = 400
    h_strip = 46 + strip_card_h + 78
    h_foot = 22 + 5 * 26 + 40
    hero_h = (H - M) - y - (h_strip + h_foot + 40)

    # SHOWN WHOLE, NOT CROPPED TO A BAND. The render is 1.41:1 and a full-width band here
    # is 2.9:1, so cover-cropping it cut the figures' feet off — and the figures are the
    # one thing §4.2 and `visual-language.html` both require this plate to carry. The image
    # is contained instead, and because the world is a paper sweep of the same value as the
    # plate its edges dissolve into the page rather than sitting in a letterbox.
    src = Image.open(HERO).convert("RGB")
    hero_w = int(round(hero_h * src.width / src.height))
    hero = src.resize((hero_w, hero_h), Image.LANCZOS)
    plate.paste(hero, (x0, y))
    d.rectangle([x0, y, x0 + hero_w - 1, y + hero_h - 1], outline=SHADE, width=2)
    log("[plate] hero shown whole at %d x %d px — no crop, so the figures survive"
        % (hero_w, hero_h))

    # measured values, beside the drawing (the "efficiency reads as a ratio" rule)
    kx = x0 + hero_w + 64
    ky = y + 4
    d.text((kx, ky), "MEASURED AT THIS STATION", font=f_lab, fill=STEEL)
    ky += 44
    rule(d, kx, ky, x1, SHADE, 2)
    ky += 22
    for lab, val in lines:
        d.text((kx, ky), lab.upper(), font=f_micro, fill=SHADE)
        wpx, _ = tw(d, val, f_num)
        d.text((x1 - wpx, ky - 3), val, font=f_num, fill=STEEL)
        ky += 30
        rule(d, kx, ky, x1, "#e2dfd8", 1)
        ky += 18
    ky += 8
    for ln in wrap_px(d, st["why_this_station"], f_tiny, x1 - kx)[:8]:
        d.text((kx, ky), ln, font=f_tiny, fill=SHADE)
        ky += 24

    y += hero_h + 30
    rule(d, x0, y, x1, SHADE, 2)
    y += 28

    # ── the strip ─────────────────────────────────────────────────────────────────────
    d.text((x0, y), "SEMANTIC COMPUTER VISION AUDIT", font=f_lab, fill=STEEL)
    note = ("capture, then the same frame with the extracted sky class in one accent  ·  "
            "%s" % strip["_meta"]["model_actually_used"])
    wpx, _ = tw(d, note, f_micro)
    d.text((x1 - wpx, y + 4), note, font=f_micro, fill=SHADE)
    y += 46

    # Six cards across, grouped as three pairs: a tight gap INSIDE a pair, a wide one
    # between pairs, so "same frame twice" is read from the spacing without a label having
    # to say it. Three full-width columns letterboxed the street photographs to 4:1.
    pairs = strip["pairs"]
    n = len(pairs)
    inner, outer = 10, 64
    cw = (x1 - x0 - outer * (n - 1) - inner * n) // (n * 2)
    ch = strip_card_h
    for i, pr in enumerate(pairs):
        px = x0 + i * (cw * 2 + inner + outer)
        cap = fit(Image.open(os.path.join(PROJECT, pr["capture"])).convert("RGB"), cw, ch)
        ov = fit(Image.open(os.path.join(PROJECT, pr["overlay"])).convert("RGB"), cw, ch)
        plate.paste(cap, (px, y))
        plate.paste(ov, (px + cw + inner, y))
        d.rectangle([px, y, px + cw - 1, y + ch - 1], outline=SHADE, width=2)
        d.rectangle([px + cw + inner, y, px + cw * 2 + inner - 1, y + ch - 1],
                    outline=SHADE, width=2)
        d.text((px + 10, y + 8), "CAPTURE", font=f_tiny, fill="#ffffff")
        d.text((px + cw + inner + 10, y + 8), "EXTRACTED", font=f_tiny, fill="#ffffff")

        ty = y + ch + 14
        d.text((px, ty), "POINT %s · %s" % (pr["id"], pr["role"].upper()),
               font=f_micro, fill=STEEL)
        sky = "sky %.1f%%" % (pr["sky_measured"] * 100.0)
        gvi = ("gvi %.1f%%" % (pr["gvi"] * 100.0)) if pr.get("gvi") is not None else "gvi n/a"
        d.text((px, ty + 26), "%s   %s   s = %.0f m" % (sky, gvi, pr["s_m"]),
               font=f_micro, fill=SHADE)
        d.rectangle([px + cw * 2 + inner - 22, ty + 4, px + cw * 2 + inner - 2, ty + 24],
                    fill=DETECTED)
    y += ch + 78

    # ── footer: the caveats that must travel, and the sources ─────────────────────────
    rule(d, x0, y, x1, SHADE, 2)
    y += 22
    foot = []
    for c in caveats:
        foot.append("· %s" % (c if isinstance(c, str) else json.dumps(c)))
    foot.append("· %s" % strip["_meta"]["caveat"])
    foot.append("· %s" % strip["_meta"]["coverage_note"])
    if not strip["_meta"]["model_matches_the_published_metrics"]:
        foot.append("· OVERLAY MODEL DIFFERS from the one the published metrics name.")
    text = "   ".join(foot)
    wrapped = wrap_px(d, text, f_tiny, x1 - x0)
    if len(wrapped) > 4:
        wrapped = wrapped[:4]
        wrapped[-1] = wrapped[-1].rstrip(" .") + " …"
        log("[plate] WARNING: the caveat block was truncated to 4 lines. The full text is "
            "in exports/blender/captions.txt — check nothing load-bearing was cut.")
    for ln in wrapped:
        d.text((x0, y), ln, font=f_tiny, fill=SHADE)
        y += 26

    src = ("sources — houdini/cameras.json · data/highline_exposure.json · "
           "exports/cv_overlays/strip.json · every figure resolved at build time, "
           "none transcribed")
    d.text((x0, H - M + 14), src, font=f_tiny, fill=SHADE)

    out = os.path.join(OUT_DIR, "HERO_A_answering_line.png")
    plate.save(out)
    log("[plate] %s  %dx%d" % (out, W, H))
    log("[plate] %d measured values on the drawing, %d caveats carried, %d capture/overlay "
        "pairs" % (len(lines), len(foot), len(pairs)))


if __name__ == "__main__":
    main()
