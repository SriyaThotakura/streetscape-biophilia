"""validate_ondeck.py — validate the geometric deck model against real imagery.

THE PROBLEM. Every CV metric in this project is street-level (survey points sit
~30 m off the deck centerline), so it cannot validate the on-deck Sky-View-Factor
that build_viewshed.py computes. The reconciliation proved the two are
uncorrelated precisely because of that vantage gap. The honest fix is imagery
captured ON the elevated deck. Mapillary has it — the trick is isolating it.

WHAT THIS DOES.
  on-deck mode (needs a Mapillary token):
    1. invert the footprint projection -> centerline lat/lon
    2. query Mapillary Graph API for images along the corridor
    3. keep only ON-DECK frames: within DECK_CORRIDOR_M of the centerline AND
       elevated (computed_altitude above the local street cluster ~ +9 m deck)
    4. segment sky with SegFormer (Cityscapes) -> measured on-deck sky fraction
    5. regress measured sky vs geometric svf_deck at the matched arc-length
       -> r, R^2, RMSE. This is the validation the caveat has always needed.

  --local mode (no token; runs now): segment images already on disk (default:
    the 6 register frames) and compare the measured sky to (a) the project's
    recorded sky and (b) geometric svf_street at the same s — a proof that the
    segment->correlate pipeline works and a robustness check on the street model.

USAGE
    python scripts/validate_ondeck.py --local                 # runs offline
    MAPILLARY_TOKEN=MLY|... python scripts/validate_ondeck.py # full on-deck run
    python scripts/validate_ondeck.py --token MLY|... --model <hf-id>

Deps: transformers, torch, pillow, requests, numpy (all present in this repo).
Default model is segformer-b0 (fast, CPU-friendly). Pass --model
nvidia/segformer-b5-finetuned-cityscapes-1024-1024 to match the project exactly.
"""
import os, sys, json, math, argparse, csv
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
SKY_CLASS = 10                    # Cityscapes 'sky' train-id
M_PER_DEG_LAT = 110_574.0
DEFAULT_MODEL = "nvidia/segformer-b0-finetuned-cityscapes-1024-1024"
PROJECT_MODEL = "nvidia/segformer-b5-finetuned-cityscapes-1024-1024"
# on-deck extraction knobs
STEP_M = 25.0                     # centerline query spacing
RADIUS_M = 22.0                   # per-query search radius
DECK_CORRIDOR_M = 7.0            # on-deck frames sit over the ~10 m deck
DECK_RISE_M = 4.0                # min altitude above the local street cluster


# ── geometry ────────────────────────────────────────────────────────────────
def load_geo():
    fp = json.load(open(os.path.join(D, "highline_footprints.json")))
    lat0, lon0 = fp["metadata"]["origin_latlon"]
    mlon = 111_320.0 * math.cos(math.radians(lat0))
    cl = np.asarray(fp["high_line"]["centerline"], dtype=float)     # local metres
    seg = np.diff(cl, axis=0)
    s = np.concatenate([[0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))])
    vs = json.load(open(os.path.join(D, "highline_viewshed.json")))["points"]
    V = {"s": np.array([p["s_m"] for p in vs]),
         "svf_deck": np.array([p["svf_deck"] for p in vs]),
         "svf_street": np.array([p["svf_street"] for p in vs])}
    return dict(lat0=lat0, lon0=lon0, mlon=mlon, cl=cl, cls=s, V=V, lengthM=fp["high_line"]["length_m"])


def to_local(g, lat, lon):
    return (lon - g["lon0"]) * g["mlon"], (lat - g["lat0"]) * M_PER_DEG_LAT


def to_latlon(g, x, z):
    return g["lat0"] + z / M_PER_DEG_LAT, g["lon0"] + x / g["mlon"]


def nearest_s(g, x, z):
    """arc-length s (m) and perpendicular offset (m) of point (x,z) on centerline."""
    cl, cls = g["cl"], g["cls"]
    best_d, best_s = 1e18, 0.0
    for k in range(len(cl) - 1):
        a, b = cl[k], cl[k + 1]
        d = b - a
        seg2 = float(d @ d) or 1e-9
        t = max(0.0, min(1.0, float((np.array([x, z]) - a) @ d) / seg2))
        proj = a + t * d
        dd = (x - proj[0]) ** 2 + (z - proj[1]) ** 2
        if dd < best_d:
            best_d, best_s = dd, cls[k] + t * (cls[k + 1] - cls[k])
    return best_s, math.sqrt(best_d)


def geom_at(g, key, s):
    return float(np.interp(s, g["V"]["s"], g["V"][key]))


# ── segmentation ──────────────────────────────────────────────────────────────
def build_segmenter(model_name):
    from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation
    import torch
    print(f"loading {model_name} …")
    proc = SegformerImageProcessor.from_pretrained(model_name)
    model = SegformerForSemanticSegmentation.from_pretrained(model_name).eval()

    def sky_fraction(pil):
        pil = pil.convert("RGB")
        inp = proc(images=pil, return_tensors="pt")
        with torch.no_grad():
            logits = model(**inp).logits
        up = torch.nn.functional.interpolate(logits, size=pil.size[::-1],
                                             mode="bilinear", align_corners=False)
        seg = up.argmax(1)[0]
        return float((seg == SKY_CLASS).float().mean())
    return sky_fraction


def stats(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3:
        return dict(n=len(x), r=None, r2=None, rmse=None)
    r = float(np.corrcoef(x, y)[0, 1])
    a, b = np.polyfit(x, y, 1)
    pred = a * x + b
    ss_res = float(np.sum((y - pred) ** 2)); ss_tot = float(np.sum((y - y.mean()) ** 2))
    return dict(n=len(x), r=round(r, 3), r2=round(1 - ss_res / ss_tot, 3) if ss_tot else None,
                rmse=round(float(np.sqrt(np.mean((y - pred) ** 2))), 4), slope=round(float(a), 3))


# ── local proof mode ─────────────────────────────────────────────────────────
def cmd_local(args, g):
    from PIL import Image
    reg = json.load(open(os.path.join(D, "register", "manifest.json")))
    items = []
    for p in reg["points"]:
        fpath = os.path.join(D, "register", p["frame"])
        if os.path.exists(fpath):
            items.append((fpath, p["s_m"], p["metrics"].get("sky")))
    if args.images:
        items = [(im, None, None) for im in args.images]
    if not items:
        print("no local images found"); return
    sky = build_segmenter(args.model)
    rows = []
    print(f"\n{'frame':<16}{'s_m':>8}{'meas_sky':>10}{'proj_sky':>10}{'geom_svf_street':>18}")
    for fpath, s, proj_sky in items:
        f = round(sky(Image.open(fpath)), 4)
        gs = geom_at(g, "svf_street", s) if s is not None else None
        rows.append((f, proj_sky, gs, s, os.path.basename(fpath)))
        print(f"{os.path.basename(fpath):<16}{('' if s is None else round(s,1)):>8}"
              f"{f:>10}{('' if proj_sky is None else round(proj_sky,3)):>10}"
              f"{('' if gs is None else round(gs,3)):>18}")
    meas = [r[0] for r in rows if r[1] is not None]
    proj = [r[1] for r in rows if r[1] is not None]
    gsvf = [r[2] for r in rows if r[2] is not None]
    print("\n-- pipeline validation --")
    if len(meas) >= 3:
        st = stats(meas, proj)
        print(f"our SegFormer sky vs project's recorded sky : r={st['r']}  (segmentation consistency)")
    if len(gsvf) >= 3:
        st2 = stats([r[0] for r in rows if r[2] is not None], gsvf)
        print(f"measured street sky vs geometric svf_street : r={st2['r']}  n={st2['n']}")
        print("(street imagery; confirms the vantage gap the on-deck run will close)")
    json.dump({"mode": "local", "model": args.model, "rows": [
        {"frame": r[4], "s_m": r[3], "meas_sky": r[0], "project_sky": r[1], "geom_svf_street": r[2]}
        for r in rows]}, open(os.path.join(D, "ondeck_validation_local.json"), "w"), indent=1)
    print(f"\nwrote data/ondeck_validation_local.json")


# ── on-deck mode ─────────────────────────────────────────────────────────────
def mapillary_query(token, bbox):
    import requests
    url = "https://graph.mapillary.com/images"
    params = {"fields": "id,computed_geometry,computed_altitude,captured_at,thumb_2048_url",
              "bbox": ",".join(f"{v:.6f}" for v in bbox), "limit": 200, "access_token": token}
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Mapillary {r.status_code}: {r.text[:180]}")
    return r.json().get("data", [])


def cmd_ondeck(args, g):
    from PIL import Image
    import requests, io
    token = args.token or os.environ.get("MAPILLARY_TOKEN")
    if not token:
        print("NO TOKEN. Set MAPILLARY_TOKEN or pass --token MLY|...  "
              "(get one free at mapillary.com/dashboard/developers).")
        print("Everything else is ready: georeferencing verified, segmentation works "
              "(run --local), geometric svf_deck computed. This run needs only the token.")
        return
    # sample centerline -> lat/lon queries
    total = g["cls"][-1]
    cand = {}
    print("querying Mapillary along the corridor …")
    for s in np.arange(0, total, STEP_M):
        k = int(np.searchsorted(g["cls"], s)) - 1; k = max(0, min(k, len(g["cl"]) - 2))
        f = (s - g["cls"][k]) / ((g["cls"][k + 1] - g["cls"][k]) or 1)
        x, z = g["cl"][k] + f * (g["cl"][k + 1] - g["cl"][k])
        lat, lon = to_latlon(g, x, z)
        dlat = RADIUS_M / M_PER_DEG_LAT; dlon = RADIUS_M / g["mlon"]
        try:
            for im in mapillary_query(token, (lon - dlon, lat - dlat, lon + dlon, lat + dlat)):
                cand[im["id"]] = im
        except RuntimeError as e:
            print(" ", e); return
    print(f"collected {len(cand)} candidate frames")
    if not cand:
        print("no imagery returned for this corridor / token."); return
    # classify on-deck: corridor distance + altitude
    recs = []
    for im in cand.values():
        gc = im.get("computed_geometry");
        if not gc: continue
        lon, lat = gc["coordinates"]
        x, z = to_local(g, lat, lon)
        s, off = nearest_s(g, x, z)
        recs.append(dict(id=im["id"], s=s, off=off, alt=im.get("computed_altitude"),
                         url=im.get("thumb_2048_url")))
    alts = [r["alt"] for r in recs if r["alt"] is not None]
    floor = (np.median(alts) + DECK_RISE_M) if alts else -1e9
    deck = [r for r in recs if r["off"] <= DECK_CORRIDOR_M and (r["alt"] is None or r["alt"] >= floor)]
    print(f"on-deck frames (<= {DECK_CORRIDOR_M} m off centerline, alt >= {floor:.1f} m): {len(deck)}")
    if len(deck) < 3:
        print("too few on-deck frames to validate; try widening DECK_CORRIDOR_M or a denser token area.")
    sky = build_segmenter(args.model)
    out = []
    for i, r in enumerate(sorted(deck, key=lambda r: r["s"])):
        if not r["url"]:
            continue
        try:
            img = Image.open(io.BytesIO(requests.get(r["url"], timeout=30).content))
        except Exception as e:
            print("  dl fail", r["id"], e); continue
        m = round(sky(img), 4); gsvf = geom_at(g, "svf_deck", r["s"])
        out.append(dict(id=r["id"], s_m=round(r["s"], 1), off_m=round(r["off"], 1),
                        alt=r["alt"], meas_sky=m, geom_svf_deck=round(gsvf, 4)))
        print(f"  [{i}] s={r['s']:.0f}m off={r['off']:.1f}m alt={r['alt']}  meas_sky={m}  svf_deck={gsvf:.3f}")
    st = stats([o["meas_sky"] for o in out], [o["geom_svf_deck"] for o in out])
    print("\n=== ON-DECK VALIDATION ===")
    print(f"matched on-deck frames : {st['n']}")
    print(f"measured on-deck sky vs geometric svf_deck : r={st['r']}  R^2={st['r2']}  RMSE={st['rmse']}")
    json.dump({"mode": "ondeck", "model": args.model, "stats": st, "frames": out},
              open(os.path.join(D, "ondeck_validation.json"), "w"), indent=1)
    print("wrote data/ondeck_validation.json")


# ── ingest mode: validate against YOUR captured on-deck imagery ───────────────
def _exif_latlon(path):
    """Best-effort GPS from a photo's EXIF; None if absent/unreadable."""
    try:
        from PIL import Image
        from PIL.ExifTags import GPSTAGS, TAGS
        ex = Image.open(path)._getexif() or {}
        gps = {}
        for t, v in ex.items():
            if TAGS.get(t) == "GPSInfo":
                for gt, gv in v.items():
                    gps[GPSTAGS.get(gt, gt)] = gv
        if "GPSLatitude" not in gps:
            return None
        dms = lambda x: float(x[0]) + float(x[1]) / 60 + float(x[2]) / 3600
        lat, lon = dms(gps["GPSLatitude"]), dms(gps["GPSLongitude"])
        if gps.get("GPSLatitudeRef") == "S": lat = -lat
        if gps.get("GPSLongitudeRef") == "W": lon = -lon
        return lat, lon
    except Exception:
        return None


def _s_for_row(g, r, path):
    """Resolve arc-length s for a manifest row: s_m > lat/lng > EXIF GPS."""
    if r.get("s_m"):
        try: return float(r["s_m"])
        except ValueError: pass
    lat = r.get("lat"); lon = r.get("lng") or r.get("lon")
    if lat and lon:
        x, z = to_local(g, float(lat), float(lon)); return nearest_s(g, x, z)[0]
    ll = _exif_latlon(path)
    if ll:
        x, z = to_local(g, *ll); return nearest_s(g, x, z)[0]
    return None


def cmd_ingest(args, g):
    from PIL import Image
    d = args.ingest
    if not os.path.isdir(d):
        print(f"not a directory: {d}"); return
    man = os.path.join(d, "manifest.csv")
    entries = []
    if os.path.exists(man):
        with open(man, newline="") as f:
            for raw in csv.DictReader(f):
                r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
                img = r.get("image") or r.get("file") or r.get("filename")
                if not img or img.startswith("#"):
                    continue
                p = os.path.join(d, img)
                if not os.path.exists(p):
                    print("  missing:", img); continue
                s = _s_for_row(g, r, p)
                if s is None:
                    print("  no position for", img, "— add s_m or lat/lng"); continue
                entries.append((p, s))
    else:
        print(f"no manifest.csv in {d}; trying EXIF GPS on all images…")
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                p = os.path.join(d, fn); ll = _exif_latlon(p)
                if ll:
                    x, z = to_local(g, *ll); entries.append((p, nearest_s(g, x, z)[0]))
                else:
                    print("  no GPS EXIF:", fn)
    if len(entries) < 3:
        print(f"\nonly {len(entries)} usable on-deck frames; need ≥3.")
        print("Fill data/ondeck/manifest.csv (image,s_m) and drop your photos in data/ondeck/.")
        return
    sky = build_segmenter(args.model)
    out = []
    print(f"\n{'frame':<24}{'s_m':>8}{'meas_sky':>10}{'geom_svf_deck':>15}")
    for p, s in sorted(entries, key=lambda e: e[1]):
        f = round(sky(Image.open(p)), 4); gd = geom_at(g, "svf_deck", s)
        out.append({"frame": os.path.basename(p), "s_m": round(s, 1),
                    "meas_sky": f, "geom_svf_deck": round(gd, 4)})
        print(f"{os.path.basename(p):<24}{s:>8.1f}{f:>10}{gd:>15.3f}")
    st = stats([o["meas_sky"] for o in out], [o["geom_svf_deck"] for o in out])
    print("\n=== ON-DECK VALIDATION — your imagery ===")
    print(f"frames: {st['n']}   measured on-deck sky vs geometric svf_deck : "
          f"r={st['r']}  R²={st['r2']}  RMSE={st['rmse']}")
    if st["r2"] is not None:
        if st["r2"] >= 0.5:
            print("→ geometry PREDICTS on-deck perception — the deck model is validated.")
        elif st["r2"] >= 0.25:
            print("→ partial — geometry explains some on-deck sky; vegetation / deck structure the rest.")
        else:
            print("→ weak — on-deck sky isn't mainly building-geometric (a real finding; see which frames diverge).")
    json.dump({"mode": "ingest", "model": args.model, "stats": st, "frames": out},
              open(os.path.join(D, "ondeck_validation.json"), "w"), indent=1)
    print("wrote data/ondeck_validation.json")


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")   # Windows console is cp1252
    except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="offline proof on local images")
    ap.add_argument("--images", nargs="*", help="explicit image paths for --local")
    ap.add_argument("--ingest", metavar="DIR", help="validate YOUR captured on-deck photos in DIR "
                    "(reads DIR/manifest.csv: image,s_m [or lat,lng]; falls back to EXIF GPS)")
    ap.add_argument("--token", help="Mapillary access token (or MAPILLARY_TOKEN env)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"HF model id (project uses {PROJECT_MODEL})")
    args = ap.parse_args()
    g = load_geo()
    if args.ingest: cmd_ingest(args, g)
    elif args.local: cmd_local(args, g)
    else: cmd_ondeck(args, g)


if __name__ == "__main__":
    main()
