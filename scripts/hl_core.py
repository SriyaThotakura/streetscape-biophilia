"""hl_core — shared geometry + ray-cast primitives for the High Line engines.

Every engine (viewshed, solar, section, attribution, forward) keys off the same
things: the building prisms, the deck centerline, arc-length s along it, and a
2.5-D ray–segment intersection. Those lived copy-pasted in each script; they live
here now, so `s` is the API contract and the engines only express what they
compute from the rays.

Public surface
--------------
constants   DECK_H, EYE, EYE_DECK, LAT, M_PER_DEG_LAT
load_site() -> Site(buildings, corridor, length_m, meta)
Building     .id .yr .h .poly(Nx2) .c .rad ; era(park_year)
Corridor     .samples(spacing) -> [(xz, s)] ; .nearest_s(x,z) ; .tangents(spacing)
             .to_latlon(x,z) ; .to_local(lat,lon)
edges_for(buildings, px, pz, r, hkey='h') -> (A,B,H,BID) | None
ray_uv(edges, px, pz, dx, dz, max_r)      -> (t, hit)      # the intersection
sun_path(day, lat=LAT, dt_h=1/6)          -> (elev, east, north)
"""
import json, math, os
import numpy as np

DECK_H, EYE = 9.0, 1.6
EYE_DECK = DECK_H + EYE
LAT = 40.7409
M_PER_DEG_LAT = 110_574.0

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(_ROOT, "data")


class Building:
    __slots__ = ("id", "yr", "h", "poly", "c", "rad")

    def __init__(self, id, yr, h, poly):
        self.id, self.yr, self.h, self.poly = id, yr, h, poly
        cx, cz = poly[:, 0].mean(), poly[:, 1].mean()
        self.c = (float(cx), float(cz))
        self.rad = float(np.max(np.hypot(poly[:, 0] - cx, poly[:, 1] - cz)))

    def era(self, park_year):
        return "post" if (self.yr and self.yr > park_year) else "pre"


class Corridor:
    def __init__(self, centerline, length_m, origin_latlon, access=None):
        self.cl = np.asarray(centerline, float)
        self.length_m = length_m
        seg = np.diff(self.cl, axis=0)
        self._seglen = np.hypot(seg[:, 0], seg[:, 1])
        self._cum = np.concatenate([[0], np.cumsum(self._seglen)])
        self.world_len = float(self._cum[-1]) or 1.0
        self.lat0, self.lon0 = origin_latlon
        self.mlon = 111_320.0 * math.cos(math.radians(self.lat0))
        self.access = access or []

    def samples(self, spacing):
        """[(np[x,z], s_metres)] evenly along the centerline."""
        n = max(2, int(self._cum[-1] // spacing))
        out = []
        for t in np.linspace(0, self._cum[-1], n):
            i = min(max(np.searchsorted(self._cum, t) - 1, 0), len(self.cl) - 2)
            f = (t - self._cum[i]) / (self._seglen[i] if self._seglen[i] else 1.0)
            out.append((self.cl[i] + f * (self.cl[i + 1] - self.cl[i]), float(t)))
        return out

    def nearest_s(self, x, z):
        """(s, perpendicular_offset) of world point (x,z) projected on the line."""
        best_d, best_s = 1e18, 0.0
        for k in range(len(self.cl) - 1):
            a, b = self.cl[k], self.cl[k + 1]
            d = b - a; seg2 = float(d @ d) or 1e-9
            t = max(0.0, min(1.0, float((np.array([x, z]) - a) @ d) / seg2))
            p = a + t * d; dd = (x - p[0]) ** 2 + (z - p[1]) ** 2
            if dd < best_d:
                best_d, best_s = dd, self._cum[k] + t * self._seglen[k]
        return best_s, math.sqrt(best_d)

    def to_latlon(self, x, z):
        return [self.lon0 + x / self.mlon, self.lat0 + z / M_PER_DEG_LAT]  # [lng, lat]

    def to_local(self, lat, lon):
        return (lon - self.lon0) * self.mlon, (lat - self.lat0) * M_PER_DEG_LAT


class Site:
    def __init__(self, buildings, corridor, length_m, meta):
        self.buildings, self.corridor, self.length_m, self.meta = \
            buildings, corridor, length_m, meta


def load_site(path=None):
    d = json.load(open(path or os.path.join(DATA, "highline_footprints.json"), encoding="utf-8"))
    blds = []
    for f in d["features"]:
        p = f["properties"]; h = p.get("height")
        if not h:
            continue
        try:
            yr = int(str(p.get("construction_year"))[:4])
        except (TypeError, ValueError):
            yr = None
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            pts = np.asarray(poly[0], float)
            if len(pts) >= 3:
                blds.append(Building(str(p.get("id") or len(blds)), yr, float(h), pts))
    hl = d["high_line"]
    corr = Corridor(hl["centerline"], hl["length_m"],
                    d["metadata"]["origin_latlon"], hl.get("access_points"))
    return Site(blds, corr, hl["length_m"], d.get("metadata", {}))


def edges_for(buildings, px, pz, r, heights=None):
    """Stacked edge arrays (A,B,H,BID) for buildings whose disc meets radius r.
    `heights[bi]` overrides each building's height (for scenario buildout);
    default uses b.h. BID indexes into `buildings`."""
    A, B, H, BID = [], [], [], []
    for bi, b in enumerate(buildings):
        if math.hypot(b.c[0] - px, b.c[1] - pz) - b.rad > r:
            continue
        pts = b.poly
        A.append(pts[:-1]); B.append(pts[1:])
        hv = b.h if heights is None else heights[bi]
        H.append(np.full(len(pts) - 1, hv))
        BID.append(np.full(len(pts) - 1, bi))
    if not A:
        return None
    return np.vstack(A), np.vstack(B), np.concatenate(H), np.concatenate(BID)


def ray_uv(edges, px, pz, dx, dz, max_r):
    """Vectorised ray–segment intersection for one direction.
    Returns (t, hit): t = distance along the ray per edge, hit = valid-hit mask."""
    A, B = edges[0], edges[1]
    ax, az = A[:, 0], A[:, 1]
    ex, ez = B[:, 0] - ax, B[:, 1] - az
    oax, oaz = ax - px, az - pz
    denom = dx * ez - dz * ex
    ok = np.abs(denom) > 1e-9
    t = np.where(ok, (oax * ez - oaz * ex) / np.where(ok, denom, 1), -1.0)
    u = np.where(ok, (oax * dz - oaz * dx) / np.where(ok, denom, 1), -1.0)
    hit = ok & (t > 1e-6) & (t <= max_r) & (u >= 0) & (u <= 1)
    return t, hit


def sun_path(day, lat=LAT, dt_h=1.0 / 6.0):
    """(elev_rad, east, north) for daylight timesteps of a day-of-year."""
    decl = math.radians(-23.44) * math.cos(math.radians(360.0 / 365.0 * (day + 10)))
    phi = math.radians(lat); els, es, ns = [], [], []
    t = 0.0
    while t < 24.0:
        h = math.radians(15.0 * (t - 12.0))
        sel = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(h)
        el = math.asin(max(-1.0, min(1.0, sel)))
        if el > math.radians(0.5):
            cel = math.cos(el)
            az = math.atan2(-math.cos(decl) * math.sin(h) / cel,
                            (math.sin(decl) - math.sin(phi) * sel) / (math.cos(phi) * cel))
            els.append(el); es.append(math.sin(az)); ns.append(math.cos(az))
        t += dt_h
    return np.array(els), np.array(es), np.array(ns)
