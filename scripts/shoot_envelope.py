"""Headless screenshot + console-error check for envelope.html. Verification only."""
import sys, time
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8011/envelope.html"
OUT = sys.argv[2] if len(sys.argv) > 2 else "exports/envelope_web.png"

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader",
                                "--enable-webgl", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    errs, logs = [], []
    pg.on("console", lambda m: (logs.append(m.text), errs.append(m.text) if m.type == "error" else None))
    pg.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)))
    pg.goto(URL, wait_until="networkidle", timeout=30000)
    # wait for the loader to hide (build finished) or timeout
    try:
        pg.wait_for_selector("#loading.hide", timeout=15000)
        status = "loaded"
    except Exception:
        status = "loader-did-not-hide"
    time.sleep(2.0)  # let a few frames render

    mode = sys.argv[3] if len(sys.argv) > 3 else "orbit"
    if mode == "walk":
        pg.click("#btn-walk")
        time.sleep(0.4)
        # scrub into the enclosed midsection (s ~ 1250 m of ~1856) and pause
        pos = sys.argv[4] if len(sys.argv) > 4 else "430"
        pg.eval_on_selector("#scrub",
            f"el => {{ el.value = {pos}; el.dispatchEvent(new Event('input', {{bubbles:true}})); }}")
        time.sleep(1.6)

    pg.screenshot(path=OUT)
    b.close()

print("status:", status)
print("screenshot:", OUT)
if errs:
    print("CONSOLE ERRORS:")
    for e in errs[:15]:
        print("  ", e[:200])
else:
    print("no console errors")
