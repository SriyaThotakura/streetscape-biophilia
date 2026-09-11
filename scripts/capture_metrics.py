"""capture_metrics.py — dump the SEEDED sim's behavioural metrics to JSON so the
board reads them (dwell-gap, per-segment congestion) from data/, not from a
pasted earlier readout. Runs index.html in capture mode (seed=42), waits for the
settle, and evaluates window.getCaptureMetrics().

Also derives the peak-congestion arc-length (max pedDensity segment) — one of the
three algorithmically-selected detail s-coords for Board 1.

Needs a local server for index.html. Usage:
    python scripts/capture_metrics.py http://localhost:PORT/index.html
"""
import json, os, sys
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8160/index.html"
    url = base + "?capture=1&cam=deck-hero&pass=trails&bg=black&ticks=1200&seed=42"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport={"width": 1400, "height": 900}).new_page()
        pg.goto(url, wait_until="networkidle")
        try:
            pg.wait_for_function("() => window.CAPTURE_READY === true", timeout=45000)
        except Exception as e:
            print("  ready-wait timed out:", str(e)[:80])
        m = pg.evaluate("window.getCaptureMetrics()")
        b.close()

    ped = m.get("pedDensity") or []
    L = m.get("length_m") or 1856.7
    segs = len(ped) or 48
    peak_seg = max(range(len(ped)), key=lambda i: ped[i]) if ped else 0
    out = {
        "seed": m.get("seed"), "sim_step": m.get("simStep"),
        "dwell_gap_pct": round(m["dwellGap"], 1) if m.get("dwellGap") is not None else None,
        "n_segments": segs, "length_m": L,
        "ped_density": ped, "ped_comfort": m.get("pedComfort"),
        "peak_congestion_seg": peak_seg,
        "peak_congestion_s": round((peak_seg + 0.5) / segs * L, 1),
        "peak_congestion_density": ped[peak_seg] if ped else None,
        "note": "seeded (42) capture-mode readout; dwell_gap = % slower in open vs shadowed segments",
    }
    json.dump(out, open(os.path.join(D, "behavior_metrics.json"), "w"), indent=1)
    print(f"dwell_gap={out['dwell_gap_pct']}%  peak_congestion s={out['peak_congestion_s']} m "
          f"(seg {peak_seg}, density {out['peak_congestion_density']})  simStep={out['sim_step']}")
    print("wrote data/behavior_metrics.json")


if __name__ == "__main__":
    main()
