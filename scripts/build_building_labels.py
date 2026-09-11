"""build_building_labels.py — map the 12 attribution BINs to human-readable
"ADDRESS · YEAR" labels for the board cells (label change only; data/sort untouched).

Reverse-geocodes each building's centroid (from the footprint geometry, inverted
to lat/lon via hl_core) with OSM Nominatim, then formats "500 W 21ST · 2013".
Writes data/building_labels.json keyed by BIN, carrying lat/lng + raw address so
any auto-label can be hand-corrected. BIN stays in removals.json for provenance.

    python scripts/build_building_labels.py
Nominatim policy: 1 req/sec, descriptive User-Agent.
"""
import json, os, sys, time, urllib.request, urllib.parse
import hl_core as hlc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
ABBR = [("West ", "W "), ("East ", "E "), ("North ", "N "), ("South ", "S "),
        (" Street", " ST"), (" Avenue", " AVE"), (" Boulevard", " BLVD"), (" Place", " PL")]


def shorten(road):
    r = road
    for a, b in ABBR:
        r = r.replace(a, b)
    return r.upper()


def reverse(lat, lon):
    q = urllib.parse.urlencode({"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
                                "zoom": "18", "addressdetails": "1"})
    req = urllib.request.Request("https://nominatim.openstreetmap.org/reverse?" + q,
                                 headers={"User-Agent": "highline-selfenclosing-boards/1.0 (research)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    site = hlc.load_site()
    by_id = {b.id: b for b in site.buildings}
    ids = [s["id"] for s in json.load(open(os.path.join(D, "removals.json")))["scenarios"]
           if s["key"].startswith("r")]
    out = {}
    print(f"{'BIN':>10} {'year':>5} {'lat,lng':>20}  address")
    for bid in ids:
        b = by_id.get(bid)
        if not b:
            print(f"{bid:>10}  (not found)"); continue
        lng, lat = site.corridor.to_latlon(b.c[0], b.c[1])
        addr, disp = "", f"#{bid}"
        try:
            j = reverse(lat, lon=lng); a = j.get("address", {})
            hn = a.get("house_number", ""); road = a.get("road", "")
            addr = (hn + " " + road).strip()
            short = (hn + " " + shorten(road)).strip() if road else f"#{bid}"
            disp = f"{short} · {b.yr}" if b.yr else short
        except Exception as e:
            print(f"  geocode failed for {bid}: {str(e)[:60]}")
        out[bid] = {"bin": bid, "year": b.yr, "height_m": round(b.h, 1),
                    "lat": round(lat, 6), "lng": round(lng, 6),
                    "osm_address": addr, "display": disp}
        print(f"{bid:>10} {str(b.yr):>5} {lat:.5f},{lng:.5f}  {disp}")
        time.sleep(1.1)
    json.dump({"note": "auto-geocoded via Nominatim; edit 'display' to hand-correct. "
               "BIN + lat/lng kept for verification.", "labels": out},
              open(os.path.join(D, "building_labels.json"), "w"), indent=1)
    print(f"\nwrote data/building_labels.json  ({len(out)} labels — verify/correct 'display' fields)")


if __name__ == "__main__":
    main()
