#!/usr/bin/env python3
"""
build_register_assets.py — Assemble the real artifacts behind the perception
register (Prompt 4, View 1).

For each selected survey point this script gathers:
  frame_<id>.jpg    the ORIGINAL Mapillary thumbnail, copied unchanged from
                    ComputerVision/highline_images_mapillary/<id>.jpg
  overlay_<id>.jpg  the SegFormer inference-overlay panel for that point,
                    CROPPED (never regenerated) from a notebook board that
                    saved it: expanded_audit_grid.png (12 pts) or
                    digital_eye_analysis_grid.png (P16/35/45)

No segmentation is synthesized. If a point had no saved overlay panel, this
script must fail loudly rather than approximate one.

Output: data/register/manifest.json + the image files above.
Requires Pillow (crop only — no inference of any kind).

Run:  python scripts/build_register_assets.py
"""

import json
import math
import os
import shutil
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CV_DIR = os.path.join(ROOT, "ComputerVision")
IMG_DIR = os.path.join(CV_DIR, "highline_images_mapillary")
EXPOSURE = os.path.join(ROOT, "data", "highline_exposure.json")
FOOTPRINTS = os.path.join(ROOT, "data", "highline_footprints.json")
OUT_DIR = os.path.join(ROOT, "data", "register")

# Selected register points, south -> north. Board column layouts were read
# off the boards themselves (titles are baked into the images).
EXPANDED_BOARD = os.path.join(CV_DIR, "expanded_audit_grid.png")
EXPANDED_ORDER = [8, 11, 14, 17, 20, 23, 26, 29, 32, 36, 39, 42]
DIGITAL_BOARD = os.path.join(CV_DIR, "digital_eye_analysis_grid.png")
DIGITAL_ORDER = [8, 16, 35, 45]

SELECTED = [
    (8,  "expanded"),
    (17, "expanded"),   # the underpass — sky measured at 0
    (23, "expanded"),
    (32, "expanded"),
    (42, "expanded"),
    (45, "digital"),    # extends the register toward the north measured edge
]


def content_runs(profile, min_len):
    """Contiguous True runs of at least min_len along a boolean profile."""
    runs, start = [], None
    for i, v in enumerate(profile):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(profile) - start >= min_len:
        runs.append((start, len(profile)))
    return runs


def panel_grid(board_path, n_cols, n_rows):
    """Locate subplot panels on a matplotlib board by contrast with the
    modal background color. Rows are detected first; the column profile is
    then computed within the panel rows only, so centered titles/labels
    can't bridge the gaps between panels. Returns (im, col_runs, row_runs)."""
    im = Image.open(board_path).convert("RGB")
    w, h = im.size
    px = im.load()
    # modal background from the corners
    from collections import Counter
    corners = [px[3, 3], px[w - 4, 3], px[3, h - 4], px[w - 4, h - 4]]
    bg = Counter(corners).most_common(1)[0][0]

    step = 4  # sample every 4px for speed
    def is_content(x, y):
        r, g, b = px[x, y]
        return abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > 90

    rows = [False] * (h // step)
    for yi in range(h // step):
        y = yi * step
        for xi in range(w // step):
            if is_content(xi * step, y):
                rows[yi] = True
                break
    # panel rows are tall; text bands are thin
    row_runs = [(a * step, b * step) for a, b in content_runs(rows, 150 // step)]
    row_runs = sorted(row_runs, key=lambda r: r[1] - r[0], reverse=True)[:n_rows]
    row_runs = sorted(row_runs)

    cols = [False] * (w // step)
    for xi in range(w // step):
        x = xi * step
        for y0, y1 in row_runs:
            if any(is_content(x, y) for y in range(y0, y1, step * 8)):
                cols[xi] = True
                break
    col_runs = [(a * step, b * step) for a, b in content_runs(cols, 100 // step)]
    col_runs = [r for r in col_runs if r[1] - r[0] >= 500]   # drop label bands

    if len(col_runs) != n_cols or len(row_runs) != n_rows:
        sys.exit(f"[fail] {os.path.basename(board_path)}: found "
                 f"{len(col_runs)} cols / {len(row_runs)} rows, "
                 f"expected {n_cols}x{n_rows}")
    return im, sorted(col_runs), row_runs, bg


def project_access(footprints):
    """Access-point arc lengths in meters along the centerline (raw local
    meters — same space the exposure build used)."""
    hl = footprints["high_line"]
    pts, s, prev = [], 0.0, None
    for x, z in hl["centerline"]:
        if prev is not None:
            s += math.hypot(x - prev[0], z - prev[1])
        pts.append((x, z, s))
        prev = (x, z)
    total = s

    def arclen(x, z):
        best_d2, best_s = float("inf"), 0.0
        for k in range(len(pts) - 1):
            ax, az, as_ = pts[k]
            bx, bz, bs_ = pts[k + 1]
            dx, dz = bx - ax, bz - az
            seg2 = dx * dx + dz * dz or 1e-9
            t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / seg2))
            d2 = (x - (ax + dx * t)) ** 2 + (z - (az + dz * t)) ** 2
            if d2 < best_d2:
                best_d2, best_s = d2, as_ + t * (bs_ - as_)
        return best_s

    acc = [{"name": a["name"], "s_m": round(arclen(a["x"], a["z"]), 1)}
           for a in hl["access_points"]]
    return sorted(acc, key=lambda a: a["s_m"]), total


def main():
    with open(EXPOSURE) as f:
        expo = json.load(f)
    with open(FOOTPRINTS) as f:
        foot = json.load(f)
    by_id = {p["id"]: p for p in expo["points"]}
    access, _ = project_access(foot)

    grids = {
        "expanded": panel_grid(EXPANDED_BOARD, len(EXPANDED_ORDER), 3),
        "digital": panel_grid(DIGITAL_BOARD, len(DIGITAL_ORDER), 3),
    }
    boards = {k: v[:3] for k, v in grids.items()}
    boards_bg = {k: v[3] for k, v in grids.items()}
    orders = {"expanded": EXPANDED_ORDER, "digital": DIGITAL_ORDER}
    board_names = {"expanded": "expanded_audit_grid.png",
                   "digital": "digital_eye_analysis_grid.png"}

    os.makedirs(OUT_DIR, exist_ok=True)
    records = []
    for pid, board_key in SELECTED:
        rec = by_id.get(pid)
        if rec is None:
            sys.exit(f"[fail] point {pid} not in exposure points[]")
        src_frame = os.path.join(IMG_DIR, f"{pid}.jpg")
        if not os.path.isfile(src_frame):
            sys.exit(f"[fail] point {pid}: no Mapillary frame on disk")
        shutil.copyfile(src_frame, os.path.join(OUT_DIR, f"frame_{pid}.jpg"))

        im, col_runs, row_runs = boards[board_key]
        col = orders[board_key].index(pid)
        x0, x1 = col_runs[col]
        y0, y1 = row_runs[2]          # bottom row = inference overlay
        crop = im.crop((x0, y0, x1, y1))
        # trim residual board-background letterbox inside the panel
        bg_img = Image.new("RGB", crop.size, boards_bg[board_key])
        bbox = ImageChops.difference(crop, bg_img).convert("L").point(
            lambda v: 255 if v > 24 else 0).getbbox()
        if bbox:
            crop = crop.crop(bbox)
        crop.save(os.path.join(OUT_DIR, f"overlay_{pid}.jpg"), quality=88)

        stretch = min(access, key=lambda a: abs(a["s_m"] - rec["s_m"]))
        records.append({
            "id": pid,
            "s_m": rec["s_m"],
            "bin": rec["bin"],
            "stretch": stretch["name"],
            "frame": f"frame_{pid}.jpg",
            "overlay": f"overlay_{pid}.jpg",
            "overlay_source": board_names[board_key],
            "metrics": rec["metrics"],
        })
        print(f"[ok] P{pid}: frame + overlay (col {col} of "
              f"{board_names[board_key]}), s={rec['s_m']} m, bin {rec['bin']}, "
              f"near {stretch['name']}")

    records.sort(key=lambda r: r["s_m"])   # south -> north, like the cartography
    manifest = {
        "caveat": "street-level context exposure, not on-deck view",
        "note": ("overlay panels are excerpts of notebook-saved boards, "
                 "not regenerated segmentation"),
        "points": records,
        "access": access,
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    print(f"[done] wrote {os.path.join(OUT_DIR, 'manifest.json')} "
          f"({len(records)} points)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
