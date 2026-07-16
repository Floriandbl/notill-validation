#!/usr/bin/env python3
"""
sample_fields.py — pick the fields to validate, from the Settat delineation shapefile.

  1. stream every polygon (the file is ~600k fields / 132 MB)
  2. compute each field's area + centroid (local equirectangular metres — <1% error
     at field scale, and the file is already WGS84 so centroids come out as GPS)
  3. DROP the extremes of the size distribution (default: keep P10..P90 by area)
  4. randomly sample N fields (seeded, reproducible)
  5. write:
       fields_settat_<N>.csv      field_id, lon, lat, area_ha   <- the GPS list
       fields_settat_<N>.geojson  the 500 polygons + centroid    <- for the overlay step

Only the exterior ring of each polygon is used.

    pip install pyshp
    python prep/sample_fields.py
"""
import csv
import json
import math
import os
import random

import shapefile   # pyshp

SHP = r"C:\Users\fdebundel\Documents\Dropbox\Github\CA_Morocco\data\raw\Delineation_Settat\Delineation_settat_2021_polys.shp"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

N_FIELDS  = 500
PCT_LOW   = 10      # drop the smallest 10% ...
PCT_HIGH  = 90      # ... and the largest 10% (the "extremes")
SEED      = 42
MIN_PTS   = 4       # ignore degenerate rings


def exterior_ring(shp):
    """Points of the first (exterior) ring only."""
    if len(shp.parts) > 1:
        return shp.points[: shp.parts[1]]
    return shp.points


def area_centroid(pts):
    """Shoelace area (m^2) + centroid (lon, lat), via a local equirectangular projection."""
    lat0 = sum(p[1] for p in pts) / len(pts)
    k = math.cos(math.radians(lat0))
    xs = [p[0] * 111320.0 * k for p in pts]
    ys = [p[1] * 110540.0 for p in pts]
    a = cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        cr = xs[i] * ys[j] - xs[j] * ys[i]
        a += cr
        cx += (xs[i] + xs[j]) * cr
        cy += (ys[i] + ys[j]) * cr
    a *= 0.5
    if abs(a) < 1e-6:
        return 0.0, (pts[0][0], pts[0][1])
    cx /= (6 * a)
    cy /= (6 * a)
    return abs(a), (cx / (111320.0 * k), cy / 110540.0)


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def main():
    print(f"Reading {SHP}")
    sf = shapefile.Reader(SHP)
    total = len(sf)
    print(f"  {total:,} polygons")

    recs = []          # (index, area_m2, lon, lat)
    for i, shp in enumerate(sf.iterShapes()):
        pts = exterior_ring(shp)
        if len(pts) < MIN_PTS:
            continue
        a, (lon, lat) = area_centroid(pts)
        if a > 0:
            recs.append((i, a, lon, lat))
        if (i + 1) % 100000 == 0:
            print(f"  ...{i + 1:,} / {total:,}")
    print(f"  usable: {len(recs):,}")

    areas = sorted(r[1] for r in recs)
    lo = percentile(areas, PCT_LOW)
    hi = percentile(areas, PCT_HIGH)
    print("\nField size distribution (ha):")
    for p in (0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100):
        print(f"  P{p:<3} {percentile(areas, p) / 10000:8.2f}")
    print(f"\nKeeping P{PCT_LOW}..P{PCT_HIGH}  ->  {lo/10000:.2f} .. {hi/10000:.2f} ha")

    pool = [r for r in recs if lo <= r[1] <= hi]
    print(f"  fields in range: {len(pool):,}")
    if len(pool) < N_FIELDS:
        raise SystemExit(f"only {len(pool)} fields in range; need {N_FIELDS}")

    rng = random.Random(SEED)
    picked = rng.sample(pool, N_FIELDS)
    picked.sort(key=lambda r: r[0])

    csv_path = os.path.join(OUT_DIR, f"fields_settat_{N_FIELDS}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["field_id", "lon", "lat", "area_ha"])
        for idx, a, lon, lat in picked:
            w.writerow([f"settat_{idx}", f"{lon:.6f}", f"{lat:.6f}", f"{a/10000:.3f}"])
    print(f"\nWrote {csv_path}")

    # geometry of the picked fields, for the local delineation overlay
    feats = []
    for idx, a, lon, lat in picked:
        pts = exterior_ring(sf.shape(idx))
        feats.append({
            "type": "Feature",
            "properties": {"field_id": f"settat_{idx}", "area_ha": round(a / 10000, 3),
                           "lon": round(lon, 6), "lat": round(lat, 6)},
            "geometry": {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in pts]]},
        })
    gj_path = os.path.join(OUT_DIR, f"fields_settat_{N_FIELDS}.geojson")
    with open(gj_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    print(f"Wrote {gj_path}")

    sel = sorted(r[1] / 10000 for r in picked)
    print(f"\nSelected {len(picked)} fields: {sel[0]:.2f} .. {sel[-1]:.2f} ha "
          f"(median {percentile(sel, 50):.2f} ha)")


if __name__ == "__main__":
    main()
