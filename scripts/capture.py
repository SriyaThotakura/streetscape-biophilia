"""capture.py — Playwright capture driver (headless Chromium, 2x device scale).

Reusable for both the board contact-sheet QA and the index.html 3D captures.
Reads a job JSON:
  { "url": "...", "viewport": [w,h], "scale": 2,
    "ready": "window.CAPTURE_READY" | null,   # JS predicate to await before shooting
    "shots": [ {"name":"foo","selector":"#el"}, {"name":"full"} ] }
selector -> element screenshot (transparent where the element is transparent);
no selector -> full-page screenshot.

    python scripts/capture.py <job.json> [outdir]
"""
import sys, json, os
from playwright.sync_api import sync_playwright


def run(job, outdir):
    os.makedirs(outdir, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(device_scale_factor=job.get("scale", 2),
                                  viewport={"width": job["viewport"][0], "height": job["viewport"][1]})
        page = ctx.new_page()
        page.goto(job["url"], wait_until="networkidle")
        ready = job.get("ready")
        if ready:
            try:
                page.wait_for_function(f"() => {ready} === true", timeout=25000)
            except Exception as e:
                print("  ready-wait timed out (continuing):", str(e)[:80])
        for shot in job["shots"]:
            path = os.path.join(outdir, shot["name"] + ".png")
            if shot.get("selector"):
                el = page.query_selector(shot["selector"])
                if el is None:
                    print("  MISSING selector", shot["selector"]); continue
                el.screenshot(path=path, omit_background=shot.get("transparent", False))
            else:
                page.screenshot(path=path, full_page=shot.get("full_page", True),
                                omit_background=shot.get("transparent", False))
            print("  captured", os.path.relpath(path))
        browser.close()


if __name__ == "__main__":
    job = json.load(open(sys.argv[1]))
    run(job, sys.argv[2] if len(sys.argv) > 2 else "boards/captures/browser")
