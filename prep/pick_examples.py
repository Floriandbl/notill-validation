#!/usr/bin/env python3
"""
pick_examples.py — choose two REAL montages to teach with, from the data itself.

The examples sheet must show what labelers actually see. This measures, inside each
field's own polygon, how "brown" (bare soil) vs "teal" (residue) it is on every one
of the 8 dates, then picks:

  * the clearest TILLED   example: starts teal, ends brown (residue buried)
  * the clearest NO-TILL  example: stays teal all season

"brownness" = mean(R) - mean(B) over the field interior, ignoring the magenta overlay.
NDTI ramp: brown #8c510a = (140,81,10) -> R-B = +130 ; teal #01665e = (1,102,94) -> R-B = -93.

    python prep/pick_examples.py
"""
import json
import os
import shutil

from PIL import Image
from pyproj import Transformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON = os.path.join(ROOT, "prep", "fields_settat_500.geojson")
IMAGES = os.path.join(ROOT, "images")
SOURCE = os.path.join(ROOT, "source")

# must match the montage that was actually generated
BOX_M, PANEL_PX, COLS, ROWS, PAD, CAP = 650, 320, 4, 2, 5, 20
UTM_CRS = "EPSG:32629"
TO_UTM = Transformer.from_crs("EPSG:4326", UTM_CRS, always_xy=True)


def panel_origin(i):
    c, r = i % COLS, i // COLS
    return PAD + c * (PANEL_PX + PAD), PAD + r * (PANEL_PX + CAP + PAD) + CAP


def is_overlay(px):
    r, g, b = px
    return r > 190 and g < 90 and b > 190          # magenta outline / centroid dot


def brownness(img, feat):
    """R-B inside the field polygon, per panel. Positive = brown/bare, negative = teal/residue."""
    lon, lat = feat["properties"]["lon"], feat["properties"]["lat"]
    cx, cy = TO_UTM.transform(lon, lat)
    half = BOX_M / 2.0
    xmin, ymax = cx - half, cy + half
    ring = [TO_UTM.transform(x, y) for x, y in feat["geometry"]["coordinates"][0]]
    # polygon -> panel-local pixels
    poly = [((X - xmin) / BOX_M * PANEL_PX, (ymax - Y) / BOX_M * PANEL_PX) for X, Y in ring]
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1 = max(0, int(min(xs)) + 2), min(PANEL_PX, int(max(xs)) - 1)
    y0, y1 = max(0, int(min(ys)) + 2), min(PANEL_PX, int(max(ys)) - 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    out = []
    for i in range(COLS * ROWS):
        ox, oy = panel_origin(i)
        vals = []
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                p = img.getpixel((ox + xx, oy + yy))
                if not is_overlay(p):
                    vals.append(p[0] - p[2])
        if vals:
            out.append(sum(vals) / len(vals))
    return out if len(out) == COLS * ROWS else None


def main():
    feats = json.load(open(GEOJSON, encoding="utf-8"))["features"]
    by_id = {f["properties"]["field_id"]: f for f in feats}
    import csv
    rows = list(csv.DictReader(open(os.path.join(ROOT, "pairs_metadata.csv"), encoding="utf-8")))

    scored = []
    for r in rows:
        f = by_id.get(r["pair_id"])
        p = os.path.join(IMAGES, r["image_a"].replace("/", os.sep))
        if not f or not os.path.exists(p):
            continue
        b = brownness(Image.open(p).convert("RGB"), f)
        if not b:
            continue
        start, end = sum(b[:2]) / 2, sum(b[-2:]) / 2      # A-B vs G-H
        scored.append({"id": r["pair_id"], "path": p, "rel": r["image_a"],
                       "start": start, "end": end, "shift": end - start, "trace": b})
    print(f"scored {len(scored)} montages\n")

    # TILLED: teal at the start, brown at the end -> biggest positive shift
    tilled = sorted([s for s in scored if s["start"] < 0 and s["end"] > 10],
                    key=lambda s: -s["shift"])
    # NO-TILL: teal throughout -> most negative maximum
    notill = sorted([s for s in scored if max(s["trace"]) < 0],
                    key=lambda s: max(s["trace"]))

    for name, lst in (("TILLED (teal -> brown)", tilled), ("NO-TILL (stays teal)", notill)):
        print(name)
        for s in lst[:3]:
            tr = " ".join(f"{v:+5.0f}" for v in s["trace"])
            print(f"  {s['id']:16s} A..H: {tr}   shift {s['shift']:+.0f}")
        if not lst:
            print("  none found")
        print()

    os.makedirs(SOURCE, exist_ok=True)
    picked = {}
    if tilled:
        shutil.copy(tilled[0]["path"], os.path.join(SOURCE, "example_till.jpg"))
        picked["till"] = tilled[0]["id"]
        print("wrote source/example_till.jpg  <-", tilled[0]["id"])
    if notill:
        shutil.copy(notill[0]["path"], os.path.join(SOURCE, "example_notill.jpg"))
        picked["no_till"] = notill[0]["id"]
        print("wrote source/example_notill.jpg <-", notill[0]["id"])
    json.dump(picked, open(os.path.join(SOURCE, "examples_picked.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
