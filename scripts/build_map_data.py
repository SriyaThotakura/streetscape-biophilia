"""build_map_data.py — georeference all engine outputs for the Mapbox deck map.

Inverts the footprint projection (local metres -> lat/lon via origin_latlon) and
emits data/map_data.js (window.MAP_DATA) containing:
  - buildings : GeoJSON FeatureCollection (lat/lon, props height + year + era)
  - deck      : elevated ribbon as GeoJSON polygons, one per sample, carrying
                every metric (svf, sky_lost, sun_w, enc, char) for data-driven paint
  - path      : centerline lat/lon per sample (smooth camera track) + bearings
  - access    : access points lat/lon + names
  - stats     : headline numbers + bbox/center

Run after the four engines + build_strip_data, from project root:
    python scripts/build_map_data.py
"""
import json, math, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
M_PER_DEG_LAT = 110_574.0
DECK_H = 9.0            # deck elevation (m)
HALFW = 5.0            # deck ribbon half-width (m)
# ── era threshold ────────────────────────────────────────────────────────────
# PRIMARY is the 2005 West Chelsea rezoning, not the 2009 park opening. The
# rezoning is the causal event: it is what moved the development rights and made
# the tower boom legal. The opening is when the gates opened. Cutting at 2009
# splits the cohort the rezoning created — the three largest single culprits are
# 2008, 2006 and 2006 — and hands them to the "pre" side, which understates the
# self-enclosure the project is about. Measured: the 2005 cut puts 27.1% of ranked
# buildings on 67.9% of the stolen sky (2.50x); the 2009 cut, 19.4% on 43.0%
# (2.22x), and the 2005-2008 band alone runs at 3.23x.
REZONING_YEAR = 2005          # primary
OPENING_YEAR = 2009           # secondary, retained for reporting
PARK_YEAR = REZONING_YEAR


def main():
    fp = json.load(open(os.path.join(D, "highline_footprints.json")))
    lat0, lon0 = fp["metadata"]["origin_latlon"]
    mlon = 111_320.0 * math.cos(math.radians(lat0))
    inv = lambda x, z: [lon0 + x / mlon, lat0 + z / M_PER_DEG_LAT]   # -> [lng,lat]

    # ── buildings -> GeoJSON ──
    feats = []
    for f in fp["features"]:
        p = f["properties"]; h = p.get("height")
        if not h:
            continue
        try:
            yr = int(str(p.get("construction_year"))[:4])
        except (TypeError, ValueError):
            yr = None
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = [[[inv(c[0], c[1]) for c in ring] for ring in poly] for poly in polys]
        feats.append({"type": "Feature",
                      "geometry": {"type": "MultiPolygon", "coordinates": rings},
                      "properties": {"h": round(float(h), 1), "yr": yr,
                                     "era": "post" if (yr and yr > PARK_YEAR) else "pre"}})
    buildings = {"type": "FeatureCollection", "features": feats}

    # ── engine points (shared s grid: viewshed/solar/section) ──
    view = json.load(open(os.path.join(D, "highline_viewshed.json")))["points"]
    solar = json.load(open(os.path.join(D, "highline_solar.json")))["points"]
    sect = json.load(open(os.path.join(D, "highline_section.json")))["points"]
    rec = json.load(open(os.path.join(D, "highline_reconciled.json")))["bins"]

    def char_at(s):
        for b in rec:
            if b["s0_m"] <= s < b["s1_m"]:
                return b["opening_character"]
        return rec[-1]["opening_character"]

    xs = np.array([p["x"] for p in view]); zs = np.array([p["z"] for p in view])
    path, ribbon = [], []
    for i, v in enumerate(view):
        x, z, s = v["x"], v["z"], v["s_m"]
        # tangent from neighbours -> bearing + perpendicular
        a = i - 1 if i > 0 else 0; b = i + 1 if i < len(view) - 1 else i
        tx, tz = xs[b] - xs[a], zs[b] - zs[a]
        tl = math.hypot(tx, tz) or 1.0; tx, tz = tx / tl, tz / tl
        nx, nz = -tz, tx
        bearing = (math.degrees(math.atan2(tx, tz))) % 360   # +x east,+z north -> compass
        lng, lat = inv(x, z)
        path.append({"lng": round(lng, 6), "lat": round(lat, 6), "s": s,
                     "bearing": round(bearing, 1)})
        sky_lost = round(v["svf_prepark"] - v["svf_deck"], 4)
        props = {"s": s, "svf": v["svf_deck"], "sky_lost": sky_lost,
                 "enc": v["enclosure_deg"], "sun_w": solar[i]["sun_winter_solstice"],
                 "sun_s": solar[i]["sun_summer_solstice"],
                 "wh": sect[i]["west_h"], "eh": sect[i]["east_h"], "char": char_at(s)}
        # ribbon quad between i and i+1
        if i < len(view) - 1:
            x2, z2 = view[i + 1]["x"], view[i + 1]["z"]
            quad = [inv(x + nx * HALFW, z + nz * HALFW),
                    inv(x2 + nx * HALFW, z2 + nz * HALFW),
                    inv(x2 - nx * HALFW, z2 - nz * HALFW),
                    inv(x - nx * HALFW, z - nz * HALFW),
                    inv(x + nx * HALFW, z + nz * HALFW)]
            ribbon.append({"type": "Feature",
                           "geometry": {"type": "Polygon", "coordinates": [quad]},
                           "properties": props})
    deck = {"type": "FeatureCollection", "features": ribbon}

    # ── access points ──
    hl = fp["high_line"]
    cl = np.asarray(hl["centerline"], dtype=float)
    seglen = np.hypot(*np.diff(cl, axis=0).T); cum = np.concatenate([[0], np.cumsum(seglen)])
    access = [{"name": a["name"], "lng": round(inv(a["x"], a["z"])[0], 6),
               "lat": round(inv(a["x"], a["z"])[1], 6),
               "s": round(float(cum[i]), 1) if i < len(cum) else 0}
              for i, a in enumerate(hl["access_points"])]

    # ── stats + framing ──
    svf_d = np.array([p["svf_deck"] for p in view])
    svf_p = np.array([p["svf_prepark"] for p in view])
    lost = svf_p - svf_d
    lat_all = [pt["lat"] for pt in path]; lng_all = [pt["lng"] for pt in path]
    stats = {
        "length_m": hl["length_m"], "n_points": len(path), "deck_h": DECK_H,
        "svf_deck_mean": round(float(svf_d.mean()), 3),
        "sky_lost_mean": round(float(100 * lost.mean()), 1),
        "sky_lost_max": round(float(100 * lost.max()), 1),
        "choke_s": path[int(lost.argmax())]["s"],
        "n_post": sum(1 for f in feats if f["properties"]["era"] == "post"),
        "center": [round((min(lng_all) + max(lng_all)) / 2, 6),
                   round((min(lat_all) + max(lat_all)) / 2, 6)],
        "bbox": [min(lng_all), min(lat_all), max(lng_all), max(lat_all)],
    }

    payload = {"stats": stats, "buildings": buildings, "deck": deck,
               "path": path, "access": access}
    out = os.path.join(D, "map_data.js")
    with open(out, "w") as f:
        f.write("window.MAP_DATA = "); json.dump(payload, f, separators=(",", ":")); f.write(";\n")
    print(f"wrote {os.path.relpath(out, ROOT)}: {len(feats)} buildings, {len(ribbon)} ribbon segs, "
          f"{len(path)} path pts, {len(access)} access")
    print(f"center {stats['center']}  choke s={stats['choke_s']}  post-2009 towers={stats['n_post']}")


if __name__ == "__main__":
    main()
