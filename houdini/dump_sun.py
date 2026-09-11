"""dump_sun.py — export the study's own sun positions for the Houdini render.

The canopy's form was driven by `hl_core.sun_path`. If the render is lit by a sun placed
by eye, the image is decoration. If it is lit by THIS sun, the light raking under the
canopy is the same winter sun the 36.8% recapture figure counts — the image and the
number describe one event.

Run from the project root with the project's own Python:

    python houdini/dump_sun.py

Writes data/sun_vectors.json. Vectors point FROM the site TOWARD the sun, unit length,
in the project's world frame: +x east, +y up, +z north — the same frame as
envelope.json and highline_footprints.json, and the same as Houdini's.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import hl_core  # noqa: E402

# the three dates the study uses throughout (envelope.json _meta.params.sun_days)
SUN_DAYS = {"winter": 355, "equinox": 80, "summer": 172}


def vectors_for(day):
    """[(hour_index, elev_deg, azim_deg, [x, y, z]), ...] for daylight timesteps."""
    els, es, ns = hl_core.sun_path(day)
    out = []
    for i in range(len(els)):
        el = float(els[i])
        ce = math.cos(el)
        # es = sin(az), ns = cos(az) — already unit horizontal components
        v = [ce * float(es[i]), math.sin(el), ce * float(ns[i])]
        az = math.degrees(math.atan2(float(es[i]), float(ns[i]))) % 360.0
        out.append(
            {
                "i": i,
                "elev_deg": round(math.degrees(el), 4),
                "azim_deg": round(az, 4),
                "dir": [round(c, 6) for c in v],
            }
        )
    return out


def main():
    data = {
        "_meta": {
            "script": "houdini/dump_sun.py",
            "source": "scripts/hl_core.py :: sun_path",
            "lat": getattr(hl_core, "LAT", None),
            "dt_h": 1.0 / 6.0,
            "frame": "+x east, +y up, +z north; unit vector site -> sun",
            "note": "same primitive that drove the canopy form and the recapture readback",
        },
        "days": {},
    }
    for name, day in SUN_DAYS.items():
        v = vectors_for(day)
        peak = max(v, key=lambda r: r["elev_deg"]) if v else None
        data["days"][name] = {
            "day_of_year": day,
            "n_timesteps": len(v),
            "peak": peak,
            "vectors": v,
        }
        print(
            "%-8s day %3d  %3d daylight steps  peak elev %5.1f deg  azim %5.1f"
            % (name, day, len(v), peak["elev_deg"], peak["azim_deg"])
        )

    out = os.path.join(ROOT, "data", "sun_vectors.json")
    with open(out, "w") as fh:
        json.dump(data, fh, indent=1)
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
