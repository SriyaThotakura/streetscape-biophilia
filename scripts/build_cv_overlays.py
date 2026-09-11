"""build_cv_overlays.py — the capture-and-overlay pairs for the hero plate's strip.

    python scripts/build_cv_overlays.py

`refrences/pintest_layouts/visual-language.html`, project id "5", says the plate is:

    "The eye-level hero with figures, and directly under it a strip of three
     capture-and-overlay pairs showing what the pipeline extracted from each."

and the language rule behind it:

    "Detection needs a before and after. Same frame twice: the plate as captured, then
     the plate with the extracted geometry drawn over it in one accent. The overlay is
     the entire claim."

So this writes, per chosen point, two files at identical size: `<id>_capture.png` and
`<id>_overlay.png`, plus `strip.json` carrying the measured numbers each pair is allowed
to print — read from `data/highline_exposure.json`, never retyped.

WHICH THREE POINTS, AND WHY IT IS NOT AN EYE PICK
    minimum, median and maximum measured `sky`, over the points that have one. That spans
    the instrument's own range and puts a true zero at one end: P17's sky view is genuinely
    0.0, which the project documents as a real measured value rather than a missing one.

WHICH MODEL
    `data/highline_exposure.json` names the model that produced the published metrics:
    nvidia/segformer-b5-finetuned-cityscapes-1024-1024. This script uses THAT model, so
    the overlay shows what the numbers came from. If it cannot be fetched, the script
    falls back and says so in `strip.json` and on stdout — it does not quietly substitute
    a different network behind the same caption.

WHAT IS OVERLAID
    the Cityscapes `sky` class, in the project's `detected` accent. That is the class the
    `sky` metric counts, so the overlay and the number are the same measurement.

data/ is read-only here. Nothing under data/ is written.
"""

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
DATA = os.path.join(PROJECT, "data")
IMAGES = os.path.join(PROJECT, "ComputerVision", "highline_images_mapillary")
OUT = os.path.join(PROJECT, "exports", "cv_overlays")

# visual-language.html :: P id "5" :: pal — the project's own five, by name.
PAL = {"paper": "#f2f0ec", "steel": "#2b2b28", "shade": "#9aa4ae",
       "detected": "#4fb0a8", "flagged": "#e0483d"}

CITYSCAPES_SKY = 10          # the class the `sky` metric counts
OVERLAY_ALPHA = 0.62         # accent over capture; the capture must stay readable beneath
CARD_W = 900                 # px, before plate layout scales it


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def log(*a):
    print(*a)
    sys.stdout.flush()


def pick_points():
    with open(os.path.join(DATA, "highline_exposure.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    pts = [p for p in doc["points"] if p["metrics"].get("sky") is not None]
    pts.sort(key=lambda p: p["metrics"]["sky"])
    chosen = [("minimum", pts[0]), ("median", pts[len(pts) // 2]), ("maximum", pts[-1])]
    log("[pick] %d points carry a measured sky value; taking min / median / max"
        % len(pts))
    for role, p in chosen:
        log("    %-8s %-7s s = %8.2f m   sky %.4f   gvi %.4f"
            % (role, p["image"], p["s_m"], p["metrics"]["sky"],
               p["metrics"].get("gvi") if p["metrics"].get("gvi") is not None else float("nan")))
    return doc, chosen


def load_model(named):
    """The model the metrics name, or a declared fallback — never a silent substitution."""
    from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor
    tried = []
    for repo in (named, "nvidia/segformer-b0-finetuned-cityscapes-1024-1024"):
        try:
            proc = SegformerImageProcessor.from_pretrained(repo)
            model = SegformerForSemanticSegmentation.from_pretrained(repo)
            model.eval()
            exact = (repo == named)
            log("[model] %s%s" % (repo, "" if exact else "   <-- FALLBACK, NOT the model "
                                                          "the published metrics name"))
            return proc, model, repo, exact
        except Exception as exc:                     # noqa: BLE001 — report, then try next
            tried.append("%s: %s" % (repo, exc))
            log("[model] could not load %s (%s)" % (repo, type(exc).__name__))
    raise SystemExit("no SegFormer checkpoint available.\n  " + "\n  ".join(tried))


def segment(proc, model, path):
    import torch
    img = Image.open(path).convert("RGB")
    inputs = proc(images=img, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    up = torch.nn.functional.interpolate(
        logits, size=img.size[::-1], mode="bilinear", align_corners=False)
    return img, up.argmax(dim=1)[0].cpu().numpy()


def main():
    os.makedirs(OUT, exist_ok=True)
    doc, chosen = pick_points()
    named = doc["metadata"]["model"]
    proc, model, repo, exact = load_model(named)

    accent = np.array(hexrgb(PAL["detected"]), dtype=np.float32)
    rows = []
    for role, p in chosen:
        src = os.path.join(IMAGES, p["image"])
        if not os.path.exists(src):
            raise SystemExit("missing capture %s" % src)
        img, seg = segment(proc, model, src)
        arr = np.asarray(img, dtype=np.float32)
        mask = (seg == CITYSCAPES_SKY)
        over = arr.copy()
        over[mask] = arr[mask] * (1.0 - OVERLAY_ALPHA) + accent * OVERLAY_ALPHA

        h = int(round(CARD_W * img.size[1] / img.size[0]))
        cap_p = os.path.join(OUT, "%s_capture.png" % p["id"])
        ov_p = os.path.join(OUT, "%s_overlay.png" % p["id"])
        img.resize((CARD_W, h), Image.LANCZOS).save(cap_p)
        Image.fromarray(over.astype(np.uint8)).resize((CARD_W, h), Image.LANCZOS).save(ov_p)

        measured = float(p["metrics"]["sky"])
        recomputed = float(mask.mean())
        rows.append({
            "id": p["id"], "role": role, "image": p["image"],
            "s_m": p["s_m"],
            "capture": os.path.relpath(cap_p, PROJECT).replace("\\", "/"),
            "overlay": os.path.relpath(ov_p, PROJECT).replace("\\", "/"),
            "sky_measured": measured,
            "sky_recomputed_here": round(recomputed, 4),
            "gvi": p["metrics"].get("gvi"),
            "typology": p["metrics"].get("typology"),
            "source": "data/highline_exposure.json :: points[].metrics",
        })
        log("[seg] %-7s %-8s sky measured %.4f · recomputed from this mask %.4f · "
            "delta %+.4f" % (p["image"], role, measured, recomputed, recomputed - measured))

    strip = {
        "_meta": {
            "purpose": "the three capture-and-overlay pairs for the hero plate strip, per "
                       "refrences/pintest_layouts/visual-language.html :: P id 5 :: plate",
            "selection_rule": "minimum, median and maximum measured `sky` over the points "
                              "that carry one — the instrument's own range, not an eye pick",
            "model_named_by_the_metrics": named,
            "model_actually_used": repo,
            "model_matches_the_published_metrics": exact,
            "overlaid_class": "Cityscapes `sky` — the class the `sky` metric counts, so the "
                              "overlay and the number are the same measurement",
            "accent": PAL["detected"],
            "caveat": doc["metadata"]["caveat"],
            "coverage_note": doc["metadata"]["coverage_note"],
            "numbers_are_not_stored_twice": "sky_measured is copied from "
                                            "data/highline_exposure.json for the caption; "
                                            "sky_recomputed_here is this run's own mask "
                                            "fraction, kept separate so the two can be "
                                            "compared rather than conflated",
        },
        "pairs": rows,
    }
    with open(os.path.join(OUT, "strip.json"), "w", encoding="utf-8") as fh:
        json.dump(strip, fh, indent=1)
    log("[out] %s" % os.path.join(OUT, "strip.json"))
    if not exact:
        log("[WARN] the overlay was produced by a DIFFERENT model from the one the metrics "
            "name. Say so on the plate, or re-run with network access.")


if __name__ == "__main__":
    main()
