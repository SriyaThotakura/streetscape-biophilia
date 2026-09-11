"""build_strip_data.py — merge the three engine outputs into one arc-length-aligned
payload for the section-strip visual. Emits data/strip_data.js (window.STRIP_DATA)
so index_strip.html works from file:// with no fetch.

Run after build_viewshed / build_solar / reconcile_exposure, from project root:
    python scripts/build_strip_data.py
"""
import json, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")


def main():
    view = json.load(open(os.path.join(D, "highline_viewshed.json")))["points"]
    solar = json.load(open(os.path.join(D, "highline_solar.json")))["points"]
    sect = json.load(open(os.path.join(D, "highline_section.json")))["points"]
    rec = json.load(open(os.path.join(D, "highline_reconciled.json")))
    fp = json.load(open(os.path.join(D, "highline_footprints.json")))
    hl = fp["high_line"]

    # viewshed / solar / section share the same resampled s grid
    assert len(view) == len(solar) == len(sect), "engine point-count mismatch"
    pts = []
    for v, s, sec in zip(view, solar, sect):
        pts.append({
            "s": v["s_m"],
            "svf_deck": v["svf_deck"], "svf_prepark": v["svf_prepark"],
            "svf_street": v["svf_street"], "enc": v["enclosure_deg"],
            "river": 1 if v["river_view"] else 0,
            "wall": v["nearest_wall_m"], "occyr": v["dom_occ_year"],
            "sun_s": s["sun_summer_solstice"], "sun_e": s["sun_equinox"],
            "sun_w": s["sun_winter_solstice"],
            "sun_s_pre": s["sun_summer_solstice_prepark"],
            "sun_e_pre": s["sun_equinox_prepark"],
            "sun_w_pre": s["sun_winter_solstice_prepark"],
            "wh": sec["west_h"], "eh": sec["east_h"],
            "wyr": sec["west_yr"], "eyr": sec["east_yr"],
        })

    bins = [{"s0": b["s0_m"], "s1": b["s1_m"], "char": b["opening_character"],
             "sky": b["cv_sky"], "gvi": b["cv_gvi"]} for b in rec["bins"]]

    # access points ARE the centerline vertices -> cumulative s along centerline
    cl = np.asarray(hl["centerline"], dtype=float)
    seglen = np.hypot(*np.diff(cl, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seglen)])
    access = [{"name": a["name"], "s": round(float(cum[i]), 1)}
              for i, a in enumerate(hl["access_points"]) if i < len(cum)]

    # headline stats
    svf_d = np.array([p["svf_deck"] for p in pts])
    svf_s = np.array([p["svf_street"] for p in pts])
    svf_p = np.array([p["svf_prepark"] for p in pts])
    river = np.array([p["river"] for p in pts])
    lost = svf_p - svf_d
    sun_w = np.array([p["sun_w"] for p in pts]); sun_w_pre = np.array([p["sun_w_pre"] for p in pts])
    choke = int(lost.argmax())
    stats = {
        "length_m": hl["length_m"], "n_points": len(pts),
        "svf_deck_mean": round(float(svf_d.mean()), 3),
        "deck_lift": round(float(100 * (svf_d.mean() - svf_s.mean())), 1),
        "river_pct": int(round(100 * river.mean())),
        "sky_lost_mean": round(float(100 * lost.mean()), 1),
        "sky_lost_max": round(float(100 * lost.max()), 1),
        "sun_stolen_winter": round(float((sun_w_pre - sun_w).mean()), 2),
        "choke_s": pts[choke]["s"],
        "daylight": rec["metadata"].get("_") or {"summer": 14.8, "equinox": 11.8, "winter": 8.8},
    }

    payload = {"stats": stats, "access": access, "bins": bins, "points": pts}
    out = os.path.join(D, "strip_data.js")
    with open(out, "w") as f:
        f.write("window.STRIP_DATA = ")
        json.dump(payload, f, separators=(",", ":"))
        f.write(";\n")
    print(f"wrote {os.path.relpath(out, ROOT)}  ({len(pts)} points, {len(bins)} bins, "
          f"{len(access)} access pts)")
    print(f"chokepoint s={stats['choke_s']} m  |  deck SVF {stats['svf_deck_mean']}  "
          f"|  river {stats['river_pct']}%  |  winter sun stolen {stats['sun_stolen_winter']} h")


if __name__ == "__main__":
    main()
