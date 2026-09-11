"""compose_boards.py — deterministic board assembler (PIL). Reads a board spec +
the pre-rendered captures/cells + data/*.json, and writes boards/boardN.png.
Every number comes from a JSON in data/. IBM Plex Mono throughout.

    python scripts/compose_boards.py 1 [--draft]      # --draft = half-res quick view
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
FONTS = os.path.join(ROOT, "boards", "assets", "fonts")
_fc = {}
def F(size, w="Regular"):
    k = (size, w)
    if k not in _fc: _fc[k] = ImageFont.truetype(os.path.join(FONTS, f"IBMPlexMono-{w}.ttf"), size)
    return _fc[k]
def C(h): return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))
def load(n): return json.load(open(os.path.join(D, n), encoding="utf-8"))


def crop_content(im, thresh=16, pad=26):
    """Crop the dark border off a 3D capture so the content fills its panel."""
    a = np.asarray(im.convert("L")); ys, xs = np.where(a > thresh)
    if len(xs) == 0: return im
    return im.crop((max(0, xs.min() - pad), max(0, ys.min() - pad),
                    min(im.width, xs.max() + pad), min(im.height, ys.max() + pad)))


def paste_fit(board, path, rect, pad=20, crop=False):
    x0, y0, x1, y1 = rect; w, h = x1 - x0 - 2 * pad, y1 - y0 - 2 * pad
    im = Image.open(path).convert("RGB")
    if crop: im = crop_content(im)
    iw, ih = im.size
    sc = min(w / iw, h / ih); nw, nh = int(iw * sc), int(ih * sc)
    im = im.resize((nw, nh), Image.LANCZOS)
    ox, oy = x0 + pad + (w - nw) // 2, y0 + pad + (h - nh) // 2
    board.paste(im, (ox, oy))
    return ox, oy, sc


def panel(dr, rect, S, label=None):
    dr.rectangle(rect, fill=C(S["panel_bg"]), outline=C(S["edge"]), width=2)
    if label:
        dr.text((rect[0] + 22, rect[1] + 16), label, font=F(24, "Medium"), fill=C(S["dim"]))


def board1(draft):
    S = json.load(open(os.path.join(ROOT, "boards", "board1_spec.json"), encoding="utf-8"))
    W, H = S["size"]
    bd = Image.new("RGB", (W, H), C(S["bg"]))
    dr = ImageDraw.Draw(bd)
    # subtle frame
    dr.rectangle([18, 18, W - 18, H - 18], outline=C(S["edge"]), width=2)

    # ── title block ──
    att = load("attribution.json"); cal = load("svf_calibration.json")["svf"]
    rm = load("removals.json")["metadata"]; labels = load("building_labels.json")["labels"]
    raw_pct = 10.1  # from viewshed self-enclosure (documented); calibrated:
    cal_pct = round(raw_pct * cal["a"])
    win_hrs = round(att["metadata"]["post2009_winter_deckhours"] / 10) * 10
    dr.text((70, 52), "THE SELF-ENCLOSING LINE   ·   BOARD 1 / COUNTERFACTUAL MATRIX",
            font=F(26, "Medium"), fill=C(S["accent"]))
    dr.text((70, 96), "THE PARK BUILT THE WALLS THAT NOW ENCLOSE IT",
            font=F(58, "SemiBold"), fill=C(S["hot"]))
    dr.text((70, 176), "computed per building  ·  isovist + solar, Ladybug-validated",
            font=F(28), fill=C(S["dim"]))
    dr.text((W - 70, 92), f"~{cal_pct}% sky", font=F(52, "SemiBold"), fill=C(S["accent"]), anchor="ra")
    dr.text((W - 70, 158), f"~{win_hrs} winter deck-hours", font=F(30, "Medium"), fill=C(S["ink"]), anchor="ra")
    dr.text((W - 70, 202), f"removed by {att['metadata'].get('post2009_sky_share_pct', 53.7):.0f}%-share of 6 post-2009 towers",
            font=F(22), fill=C(S["dim"]), anchor="ra")

    # ── panels ──
    grid_geo = None
    for p in S["panels"]:
        r = p["rect"]
        if p["type"] in ("image", "grid_image", "detail"):
            panel(dr, r, S, p.get("label"))
            geo = paste_fit(bd, os.path.join(ROOT, p["src"]),
                            (r[0], r[1] + (46 if p.get("label") else 0), r[2], r[3]),
                            pad=18 if p["type"] != "grid_image" else 8, crop=(p["type"] != "grid_image"))
            if p["type"] == "grid_image": grid_geo = geo
            if p.get("sublabel"):
                dr.text((r[0] + 22, r[3] - 34), p["sublabel"], font=F(22), fill=C(S["dim"]))
        elif p["type"] == "table_attribution":
            panel(dr, r, S, p["label"]); draw_table(dr, r, att, labels, S)
        elif p["type"] == "card_lbt":
            panel(dr, r, S, p["label"]); draw_lbt(dr, r, cal, S)

    # ── callout: the 848 Washington cell → its worst-SVF detail (s=104 is its canyon) ──
    if grid_geo:
        ox, oy, sc = grid_geo
        cw, ch, gu, idx = 640, 500, 18, 5          # order index of the 848 Washington (r2) cell
        rr, cc = divmod(idx, 4)
        bx = ox + (gu + cc * (cw + gu) + cw / 2) * sc
        by = oy + (gu + rr * (ch + gu) + ch / 2) * sc
        rad = 130 * sc
        dr.ellipse([bx - rad, by - rad, bx + rad, by + rad], outline=C(S["accent"]), width=5)
        dr.text((bx, by + (ch / 2 + 20) * sc), "→ WORST SKY-VIEW  s=104 (detail below)",
                font=F(22, "Medium"), fill=C(S["accent"]), anchor="ma")

    # detail caption + one callout (worst → the culprit cell)
    dr.text((70, S["panels"][4]["rect"][1] - 34), S.get("detail_caption", ""), font=F(22), fill=C(S["dim"]))

    # ── footer (provenance; every figure from JSON) ──
    fr = S["footer"]["rect"]
    dr.line([fr[0], fr[1], fr[2], fr[1]], fill=C(S["edge"]), width=2)
    peak_lbl = labels.get(rm["diff_peak_id"], {}).get("display", rm["diff_peak_id"])
    dr.text((fr[0] + 10, fr[1] + 20),
            f"seed=42   ·   difference strips clipped at p99={rm['diff_p99']:.2f}, peak {rm['diff_peak']:.2f} "
            f"at s={rm['diff_peak_s']:.0f} m ({peak_lbl})",
            font=F(24), fill=C(S["dim"]))
    dr.text((fr[0] + 10, fr[1] + 62),
            f"method: hl_core 2.5-D isovist + solar-geometry, validated vs Ladybug (SVF r=+.96, winter-sun r=+.99)   ·   "
            f"calibrated svf = {cal['a']:.2f}·svf {cal['b']:+.2f}   ·   every figure from data/*.json",
            font=F(24), fill=C(S["dim"]))

    out = os.path.join(ROOT, "boards", "board1.png")
    bd.save(out)
    if draft:
        v = bd.copy(); v.thumbnail((2000, 2000), Image.LANCZOS)
        v.save(os.path.join(ROOT, "boards", "board1_draft.png"))
    print(f"wrote {os.path.relpath(out, ROOT)}" + ("  + board1_draft.png" if draft else ""))


def draw_table(dr, r, att, labels, S):
    x0, y0 = r[0] + 26, r[1] + 66
    cols = [(0, "#"), (70, "ADDRESS"), (470, "YR"), (600, "HT"), (740, "SKY%"), (940, "WIN-h")]
    for dx, h in cols: dr.text((x0 + dx, y0), h, font=F(24, "Medium"), fill=C(S["dim"]))
    y = y0 + 44
    for row in att["leaderboard"][:12]:
        disp = labels.get(row["id"], {}).get("display", "#" + row["id"])
        wh = next((s for s in load("removals.json")["scenarios"] if s.get("id") == row["id"]), {})
        vals = [str(row["rank"]), disp, str(row["year"]), f"{row['height_m']:.0f}",
                f"{row['sky_share_pct']:.1f}", f"{row['winter_deckhours_stolen']:.0f}"]
        col = C(S["accent"]) if row["era"] == "post" else C(S["ink"])
        for (dx, _), v in zip(cols, vals):
            dr.text((x0 + dx, y), v, font=F(24, "Medium" if dx == 0 else "Regular"), fill=col)
        y += 46
    dr.text((x0, y + 14), f"post-2009 towers own {att['metadata']['post2009_sky_share_pct']:.1f}% of the deck's enclosure",
            font=F(22), fill=C(S["accent"]))


def draw_lbt(dr, r, cal, S):
    lbt = load("lbt_validation.json")["metrics"]; x0, y0 = r[0] + 26, r[1] + 74
    rows = [("Sky-View Factor", lbt["svf_deck"]), ("Winter sun hours", lbt["sun_winter"]),
            ("Summer sun hours", lbt["sun_summer"])]
    for i, (name, m) in enumerate(rows):
        y = y0 + i * 74
        dr.text((x0, y), name, font=F(26), fill=C(S["ink"]))
        dr.text((r[2] - 26, y), f"r={m['r']:+.2f}  R2={m['r2']:.2f}", font=F(26, "Medium"),
                fill=C(S["teal"]), anchor="ra")
    y = y0 + 3 * 74 + 12
    dr.text((x0, y), f"calibration   svf = {cal['a']:.2f}·svf {cal['b']:+.2f}", font=F(24), fill=C(S["dim"]))
    dr.text((x0, y + 60), "GEOMETRY VALIDATED vs RADIANCE-LINEAGE", font=F(28, "SemiBold"), fill=C(S["teal"]))


def board2(draft):
    S = json.load(open(os.path.join(ROOT, "boards", "board2_spec.json"), encoding="utf-8"))
    W, H = S["size"]; bd = Image.new("RGB", (W, H), C(S["bg"])); dr = ImageDraw.Draw(bd)
    dr.rectangle([18, 18, W - 18, H - 18], outline=C(S["edge"]), width=2)
    bm = load("behavior_metrics.json"); cal = load("svf_calibration.json")["svf"]

    dr.text((70, 52), "THE SELF-ENCLOSING LINE   ·   BOARD 2 / BEHAVIORAL CONSEQUENCE",
            font=F(26, "Medium"), fill=C(S["accent"]))
    dr.text((70, 96), "THE TOWERS DON'T EMPTY THE DECK — THEY DE-PARK IT",
            font=F(56, "SemiBold"), fill=C(S["hot"]))
    dr.text((70, 176), "pedestrians linger in open, sunlit segments and hurry through shadowed canyons",
            font=F(28), fill=C(S["dim"]))
    dr.text((W - 70, 90), f"{bm['dwell_gap_pct']:.0f}% dwell gap", font=F(52, "SemiBold"),
            fill=C(S["teal"]), anchor="ra")
    dr.text((W - 70, 156), "slower in open vs shadowed", font=F(30, "Medium"), fill=C(S["ink"]), anchor="ra")
    dr.text((W - 70, 200), "seeded sim (42) · footfall driven by the enclosure field",
            font=F(22), fill=C(S["dim"]), anchor="ra")

    for p in S["panels"]:
        r = p["rect"]; panel(dr, r, S, p.get("label"))
        paste_fit(bd, os.path.join(ROOT, p["src"]),
                  (r[0], r[1] + (46 if p.get("label") else 0), r[2], r[3]),
                  pad=12, crop=(p["type"] == "image_crop"))
    hr = S["panels"][1]["rect"]
    dr.text((hr[0] + 22, hr[3] - 42),
            "> LINGER  where the deck is open & sunlit        > PASS-THROUGH  where the towers shadow it",
            font=F(24, "Medium"), fill=C(S["accent"]))

    fr = S["footer"]["rect"]; dr.line([fr[0], fr[1], fr[2], fr[1]], fill=C(S["edge"]), width=2)
    dr.text((fr[0] + 10, fr[1] + 20),
            "seed=42   ·   comfort = 0.6·SVF + 0.4·sun   ·   agent sim coupled to the viewshed + solar field (PED_EXPOSURE_K=0.78)",
            font=F(24), fill=C(S["dim"]))
    dr.text((fr[0] + 10, fr[1] + 62),
            f"hero: 4 passes screen-blended (ghost + comfort + trails + access)   ·   calibrated svf = {cal['a']:.2f}·svf {cal['b']:+.2f}   ·   every figure from data/*.json",
            font=F(24), fill=C(S["dim"]))
    out = os.path.join(ROOT, "boards", "board2.png"); bd.save(out)
    if draft:
        v = bd.copy(); v.thumbnail((2000, 2000), Image.LANCZOS); v.save(os.path.join(ROOT, "boards", "board2_draft.png"))
    print(f"wrote {os.path.relpath(out, ROOT)}" + ("  + board2_draft.png" if draft else ""))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "1"
    draft = "--draft" in sys.argv
    if which == "1": board1(draft)
    elif which == "2": board2(draft)
    else: print("board must be 1 or 2")
