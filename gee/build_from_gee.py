#!/usr/bin/env python3
"""
build_from_gee.py — download Sentinel-2 for the sampled fields, overlay the
delineation locally, and build the 8-facet montages the app serves.

Pipeline (per field, from prep/fields_settat_500.geojson):
  1. centroid -> UTM 29N, take an exact 500 x 500 m square around it
  2. pull 8 PLAIN Sentinel-2 composites (one every 2 weeks from 1 Sept) for that
     exact square (crs=EPSG:32629 + fixed pixel size => the image maps linearly
     to metres, so the overlay lands precisely)
  3. LOCALLY draw the field delineation (red outline) + a red dot on the centroid
  4. stitch the 8 dates into one 4x2 montage, captioned A..H with their dates
  5. save images/Settat/<season>/{lat}_{lon}_{season}_Settat.jpg
  6. append to pairs_metadata.csv (one field = one row = one screen)

No GEE asset upload needed — the shapefile stays local.

    pip install earthengine-api pillow requests pyproj
    earthengine authenticate
    python prep/sample_fields.py        # once: produces the geojson
    python gee/build_from_gee.py
"""
import csv
import io
import json
import os
import shutil
import time
from datetime import date, timedelta

import ee
import requests
from PIL import Image, ImageDraw
from pyproj import Transformer

# ======================================================================
# CONFIG
# ======================================================================
EE_PROJECT = "ca-morocco"       # picked from your `gcloud projects list`. It must be a
                                # Cloud project with the Earth Engine API enabled.
                                # Check/adjust: gcloud projects list

PROVINCE = "Settat"
SEASON   = 2025                 # season START year: 1 Sep 2025 -> ~22 Dec 2025. TODO confirm.

SEASON_START_MD = (9, 1)        # 1 September
N_STEPS   = 8                   # 8 dates -> 8 facets (A..H)
STEP_DAYS = 14                  # every 2 weeks
BOX_M     = 750                 # footprint per facet. Settat fields are small (median
                                # 0.75 ha ~= 87 m across), so the field fills ~12% of the
                                # frame at 750 m, ~35% at 250 m, ~43% at 200 m.
                                # 750 m = more surrounding context, smaller field.
PANEL_PX  = 320                 # pixels per facet

CLEAN_FIRST = True              # wipe images/ + pairs_metadata.csv before generating.
                                # The repo still holds the OLD placeholder dataset; without
                                # this you'd append 500 real rows onto 11,000 dead ones.

BANDS = ["B11", "B8", "B2"]     # agriculture false colour: veg green, bare soil red/brown
# Per-band stretch, measured from real Settat reflectance (2-98th percentiles,
# Sep 2025):  B11 2120..5159 | B8 2967..5029 | B2 297..1527.
#   - min=0/max=3000 for everything saturated B11+B8 -> every field rendered YELLOW.
#   - stretching BLUE to its own 2-98% is the obvious fix and it's WRONG: bare soil is
#     genuinely bright in blue, so it renders MAGENTA. The blue ceiling is kept wide on
#     purpose, which keeps soil low-blue => red, and vegetation => green.
# Predicted: bare soil ~RGB(220,61,55), vegetation ~RGB(32,232,5).
#
# KEEP THIS FIXED ACROSS ALL 8 DATES. A per-date auto-stretch would make colour change
# meaningless — the whole point is that a change from A..H is a change on the ground.
VIS   = {"min": [2000, 2900, 250], "max": [5200, 5100, 5000]}
MAX_CLOUD = 60
UTM_CRS = "EPSG:32629"          # UTM 29N — correct for Settat

PANEL_LETTERS = "ABCDEFGHIJKL"
ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON   = os.path.join(ROOT, "prep", "fields_settat_500.geojson")
IMAGES_DIR = os.path.join(ROOT, "images")
META_CSV  = os.path.join(ROOT, "pairs_metadata.csv")

TO_UTM = Transformer.from_crs("EPSG:4326", UTM_CRS, always_xy=True)


# ======================================================================
# Earth Engine
# ======================================================================
def init_ee():
    try:
        ee.Initialize(project=EE_PROJECT)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=EE_PROJECT)


def mask_s2_scl(img):
    scl = img.select("SCL")
    bad = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10)).Or(scl.eq(11))
    return img.updateMask(bad.Not())


def season_windows(year):
    """[(start_iso, end_iso, 'A · 1 Sep'), ...] — labels match config.js q_when."""
    start = date(year, *SEASON_START_MD)
    out = []
    for i in range(N_STEPS):
        s = start + timedelta(days=i * STEP_DAYS)
        e = s + timedelta(days=STEP_DAYS)
        out.append((s.isoformat(), e.isoformat(),
                    f"{PANEL_LETTERS[i]} · {s.strftime('%d %b').lstrip('0')}"))
    return out


def fetch_panel(rect, start, end, tries=5):
    """One PLAIN false-colour thumbnail of the exact UTM square."""
    comp = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(rect).filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD))
            .map(mask_s2_scl).median())
    vis = comp.visualize(bands=BANDS, min=VIS["min"], max=VIS["max"])
    url = vis.getThumbURL({
        "region": rect,
        "dimensions": f"{PANEL_PX}x{PANEL_PX}",   # exact size => exact metre->pixel mapping
        "crs": UTM_CRS,
        "format": "jpg",
    })
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=90)
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).convert("RGB")
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    raise RuntimeError("thumbnail download failed")


# ======================================================================
# Local overlay: delineation + centroid dot
# ======================================================================
# The overlay must contrast with the IMAGERY. Soil renders red and vegetation green,
# so a red outline vanishes on soil (and green would vanish on crops). Cyan is the one
# colour that is far from both.
OUTLINE = (0, 255, 255)
RED = OUTLINE          # kept as an alias: older code referred to RED


def overlay_field(img, ring_utm, cxy, bounds):
    """Draw the field outline + a red dot on the centroid, in pixel space."""
    xmin, ymin, xmax, ymax = bounds
    W, H = img.size

    def to_px(X, Y):
        return ((X - xmin) / (xmax - xmin) * W,
                (ymax - Y) / (ymax - ymin) * H)      # y flips: north is up

    d = ImageDraw.Draw(img)
    pts = [to_px(X, Y) for X, Y in ring_utm]
    if len(pts) > 1:
        d.line(pts + [pts[0]], fill=RED, width=2)    # closed delineation
    cx, cy = to_px(*cxy)
    r = 3.5
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=RED, outline=(255, 255, 255))
    return img


def make_montage(panels, labels):
    cols, rows, pad, cap = 4, 2, 5, 20               # 8 facets: 4 across x 2 down
    w, h = panels[0].size
    W = cols * w + (cols + 1) * pad
    H = rows * (h + cap) + (rows + 1) * pad
    canvas = Image.new("RGB", (W, H), (245, 243, 237))
    draw = ImageDraw.Draw(canvas)
    for i, (im, lab) in enumerate(zip(panels, labels)):
        c, r = i % cols, i // cols
        x = pad + c * (w + pad)
        y = pad + r * (h + cap + pad)
        draw.text((x + 2, y + 4), lab, fill=(70, 70, 70))
        canvas.paste(im, (x, y + cap))
    return canvas


# ======================================================================
# Main
# ======================================================================
def process(feature, windows):
    lon = feature["properties"]["lon"]
    lat = feature["properties"]["lat"]
    ring_ll = feature["geometry"]["coordinates"][0]

    cx, cy = TO_UTM.transform(lon, lat)
    half = BOX_M / 2.0
    bounds = (cx - half, cy - half, cx + half, cy + half)
    rect = ee.Geometry.Rectangle(list(bounds), UTM_CRS, False)   # geodesic=False
    ring_utm = [TO_UTM.transform(x, y) for x, y in ring_ll]

    panels, labels = [], []
    for start, end, label in windows:
        img = fetch_panel(rect, start, end)
        panels.append(overlay_field(img, ring_utm, (cx, cy), bounds))
        labels.append(label)

    montage = make_montage(panels, labels)
    fname = f"{lat:.5f}_{lon:.5f}_{SEASON}_{PROVINCE}.jpg"
    rel = f"{PROVINCE}/{SEASON}/{fname}"
    out = os.path.join(IMAGES_DIR, PROVINCE, str(SEASON), fname)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    montage.save(out, quality=88)
    return rel, lon, lat


def main():
    init_ee()
    if CLEAN_FIRST:
        if os.path.isdir(IMAGES_DIR):
            shutil.rmtree(IMAGES_DIR)
        if os.path.exists(META_CSV):
            os.remove(META_CSV)
        print("Cleared images/ and pairs_metadata.csv — starting from the real dataset only.")
    with open(GEOJSON, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    windows = season_windows(SEASON)
    print(f"{len(feats)} fields x {N_STEPS} dates = {len(feats) * N_STEPS} thumbnails")

    rows = []
    for i, feat in enumerate(feats, 1):
        try:
            rel, lon, lat = process(feat, windows)
            rows.append({
                "pair_id": feat["properties"]["field_id"],
                "province": PROVINCE, "year": SEASON,
                "image_a": rel, "image_b": "",       # single-image mode
                "lat_a": lat, "lon_a": lon, "lat_b": "", "lon_b": "",
            })
            print(f"  [{i}/{len(feats)}] {rel}")
        except Exception as e:
            print(f"  [{i}/{len(feats)}] SKIPPED ({e})")

    cols = ["pair_id", "province", "year", "image_a", "image_b",
            "lat_a", "lon_a", "lat_b", "lon_b"]
    new = not os.path.exists(META_CSV)
    with open(META_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])

    print(f"\nDone. {len(rows)} fields -> {IMAGES_DIR}")
    print("Next: Rscript r/build_pairs.R  ->  load pairs into Supabase  ->  live.")


if __name__ == "__main__":
    main()
