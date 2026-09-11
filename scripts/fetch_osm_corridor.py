"""fetch_osm_corridor.py — pull a comparison elevated-park corridor from
OpenStreetMap into the SAME schema as data/highline_footprints.json, so the
hl_core engines run on it unchanged. This is what turns the project from a case
study into a method with a demonstrated second instance.

Buildings come from Overpass (way["building"]); height = height tag, else
building:levels × 3.2 m, else a context default. The centerline + access points
are configured per corridor below (OSM's park ways are patchy; a hand-set
centerline is more reliable and is all the engines need).

Usage:  python scripts/fetch_osm_corridor.py the606
Writes data/<name>_footprints.json.
"""
import json, math, os, sys, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LEVEL_M = 3.2
DEFAULT_LEVELS = 2

# ── corridor configs (a comparison instance for the method) ──
CORRIDORS = {
    "the606": {
        "name": "The 606 / Bloomingdale Trail (Chicago)",
        # eastern ~1.9 km, Ashland → Humboldt Blvd, through low-rise Wicker Park/Bucktown
        "bbox": (41.9108, -87.6918, 41.9168, -87.6685),   # (S, W, N, E)
        "centerline_ll": [[41.9138, -87.6685], [41.9139, -87.6800], [41.9140, -87.6918]],
        "access_ll": [["Ashland Ave", 41.9138, -87.6685, 1.0],
                      ["Damen Ave", 41.9139, -87.6773, 0.8],
                      ["Western Ave", 41.9140, -87.6865, 0.7],
                      ["Humboldt Blvd", 41.9140, -87.6918, 0.6]],
        "default_levels": 2,
    },
}


def overpass_buildings(bbox):
    s, w, n, e = bbox
    q = f'[out:json][timeout:90];way["building"]({s},{w},{n},{e});out geom;'
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                 data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": "highline-method-compare/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r).get("elements", [])


def height_of(tags, default_levels):
    h = tags.get("height")
    if h:
        try: return float(str(h).split()[0].replace("m", ""))
        except ValueError: pass
    lv = tags.get("building:levels") or tags.get("building:levels:aboveground")
    if lv:
        try: return float(lv) * LEVEL_M
        except ValueError: pass
    return default_levels * LEVEL_M


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "the606"
    cfg = CORRIDORS[which]
    lats = [c[0] for c in cfg["centerline_ll"]]; lons = [c[1] for c in cfg["centerline_ll"]]
    lat0 = (cfg["bbox"][0] + cfg["bbox"][2]) / 2
    lon0 = (cfg["bbox"][1] + cfg["bbox"][3]) / 2
    mlon = 111_320.0 * math.cos(math.radians(lat0)); mlat = 110_574.0
    proj = lambda lat, lon: [round((lon - lon0) * mlon, 2), round((lat - lat0) * mlat, 2)]

    print(f"fetching buildings for {cfg['name']} …")
    els = overpass_buildings(cfg["bbox"])
    feats = []; n_h = 0
    for el in els:
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        ring = [[g["lon"], g["lat"]] for g in el["geometry"]]
        if len(ring) < 4:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        tags = el.get("tags", {})
        h = height_of(tags, cfg["default_levels"])
        if tags.get("height") or tags.get("building:levels"):
            n_h += 1
        coords = [[proj(la_lo[1], la_lo[0]) for la_lo in ring]]
        feats.append({"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [coords]},
                      "properties": {"id": str(el["id"]), "name": str(el["id"]),
                                     "height": round(h, 2), "type": "building",
                                     "construction_year": None}})

    # centerline + length + access in local metres
    cl = [proj(la, lo) for la, lo in cfg["centerline_ll"]]
    length_m = sum(math.hypot(cl[i + 1][0] - cl[i][0], cl[i + 1][1] - cl[i][1]) for i in range(len(cl) - 1))
    access = [{"name": a[0], "x": proj(a[1], a[2])[0], "z": proj(a[1], a[2])[1], "weight": a[3]}
              for a in cfg["access_ll"]]

    out = {"type": "FeatureCollection",
           "metadata": {"source": "OpenStreetMap via Overpass (ODbL)", "corridor": cfg["name"],
                        "bbox_latlon": list(cfg["bbox"]), "origin_latlon": [lat0, lon0],
                        "units": "local metres [x,z], +x east +z north, centred (0,0)",
                        "count": len(feats), "height_note": f"{n_h}/{len(feats)} from OSM tags; "
                        f"rest = {cfg['default_levels']} levels × {LEVEL_M} m default"},
           "features": feats,
           "high_line": {"length_m": round(length_m, 1), "centerline": cl,
                         "access_points": access}}
    path = os.path.join(DATA, f"{which}_footprints.json")
    json.dump(out, open(path, "w"))
    print(f"wrote {os.path.relpath(path, ROOT)}: {len(feats)} buildings "
          f"({n_h} with OSM height/levels, {len(feats)-n_h} defaulted), "
          f"corridor {length_m:.0f} m")


if __name__ == "__main__":
    main()
