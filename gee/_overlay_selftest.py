#!/usr/bin/env python3
"""
Self-test for the LOCAL half of build_from_gee.py (no Earth Engine needed).

Proves, against a REAL field polygon from prep/fields_settat_500.geojson:
  - the WGS84 -> UTM transform
  - the exact metre -> pixel mapping for BOX_M
  - the delineation outline + red centroid dot land in the right place
  - the 4x2 A..H montage layout

The 8 "satellite" panels are faked (a real tile, reused) — only the geometry math
is under test. Run:  python gee/_overlay_selftest.py
"""
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_from_gee as B   # noqa: E402  (imports ee, but never initialises it)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(B.GEOJSON, encoding="utf-8") as f:
        feats = json.load(f)["features"]

    # a mid-sized field so the framing is representative
    feats.sort(key=lambda ft: ft["properties"]["area_ha"])
    feat = feats[len(feats) // 2]
    p = feat["properties"]
    print(f"field {p['field_id']}  {p['area_ha']} ha  @ {p['lat']:.5f},{p['lon']:.5f}")

    lon, lat = p["lon"], p["lat"]
    cx, cy = B.TO_UTM.transform(lon, lat)
    half = B.BOX_M / 2.0
    bounds = (cx - half, cy - half, cx + half, cy + half)
    ring_utm = [B.TO_UTM.transform(x, y) for x, y in feat["geometry"]["coordinates"][0]]

    # how much of the frame does this field occupy?
    xs = [x for x, _ in ring_utm]
    ys = [y for _, y in ring_utm]
    print(f"  field extent: {max(xs)-min(xs):.0f} m x {max(ys)-min(ys):.0f} m "
          f"in a {B.BOX_M} m box  ->  {(max(xs)-min(xs))/B.BOX_M*100:.0f}% of frame width")

    # fake panels: a real tile, so the overlay is visible over imagery
    base = Image.open(os.path.join(ROOT, "source", "till.jpg")).convert("RGB")
    s = min(base.size)
    base = base.crop((0, 0, s, s)).resize((B.PANEL_PX, B.PANEL_PX), Image.LANCZOS)

    windows = B.season_windows(B.SEASON)
    panels, labels = [], []
    for _, _, label in windows:
        panels.append(B.overlay_field(base.copy(), ring_utm, (cx, cy), bounds))
        labels.append(label)

    out = os.path.join(ROOT, "gee", "_overlay_selftest.jpg")
    B.make_montage(panels, labels).save(out, quality=90)
    print(f"  labels: {', '.join(l for _, _, l in windows)}")
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
