#!/usr/bin/env python3
"""
build_from_gee.py — build the REAL labeling dataset from Sentinel-2 (Google Earth Engine).

Implements the pipeline:
  1. randomly pick N GPS locations (fields) inside the province, from YOUR parcel layer
  2. take each field's centroid — all 8 dates use that exact same location
  3. build 8 Sentinel-2 composites, one every 2 weeks from 1 September
  4. overlay the parcel delineation (boundary painted red) on each date
  5. stitch the 8 dates into ONE image (4x2 facets, dated)
  6. save as  {lat}_{lon}_{season}_{province}.jpg  under images/{province}/{season}/
  7. iterate over all fields
  8/9. write pairs_metadata.csv — ONE field = ONE row = one screen in the app
       (image_b stays empty: the app runs in single-image mode)

Run it in a GEE-authenticated Python environment (Colab is easiest):
    pip install earthengine-api pillow requests
    earthengine authenticate           # once
    python build_from_gee.py

Current run: Settat, one season, 500 fields -> 500 montages -> 500 screens.

NOTE ON SCALE: 500 fields x 8 dates = 4,000 thumbnail pulls (~20-40 min) and a few
hundred MB — fine for git/Pages. If you later go to many provinces/seasons, move
images/ to object storage (R2/S3); the app only needs the URLs in the pairs table.
"""
import csv
import io
import os
import time
from datetime import date, timedelta

import ee
import requests
from PIL import Image, ImageDraw

# ======================================================================
# CONFIG  —  edit these
# ======================================================================
EE_PROJECT      = "your-gcp-project-id"          # TODO: your Earth Engine / GCP project
PARCELS_ASSET   = "projects/your-project/assets/morocco_parcels"  # TODO: your parcel layer
PROVINCE_FIELD  = "province"                      # TODO: attribute holding the province name

PROVINCES = ["Settat"]         # current run: Settat only
SEASONS   = [2025]             # season named by its START year (Sep 2025 -> Dec 2025).
                               # TODO: confirm which season you want.

SEASON_START_MD = (9, 1)       # tillage season starts 1 September (month, day)
N_STEPS         = 8            # 8 dates -> an 8-facet montage
STEP_DAYS       = 14           # every 2 weeks -> 16 weeks (1 Sep .. ~22 Dec)
N_FIELDS        = 500          # GPS locations sampled in the province

BUFFER_M   = 250              # half-size -> 500 x 500 m footprint.
                              # Want a closer look? drop to 150 (300 m) or 100 (200 m).
PANEL_PX   = 320             # pixels per facet
BANDS      = ["B11", "B8", "B2"]   # Sentinel-2 "agriculture": veg=green, bare soil=red/brown
VIS        = {"min": 0, "max": 3000}
MAX_CLOUD  = 60              # drop scenes cloudier than this before compositing
SEED       = 42

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(ROOT, "images")
META_CSV   = os.path.join(ROOT, "pairs_metadata.csv")


# ======================================================================
# Earth Engine helpers
# ======================================================================
def init_ee():
    try:
        ee.Initialize(project=EE_PROJECT)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=EE_PROJECT)


def mask_s2_scl(img):
    """Mask clouds/shadows/snow using the Scene Classification (SCL) band."""
    scl = img.select("SCL")
    bad = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10)).Or(scl.eq(11))
    return img.updateMask(bad.Not())


def s2_composite(region, start, end):
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterBounds(region)
           .filterDate(start, end)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD))
           .map(mask_s2_scl))
    return col.median()


def visualize_with_boundary(img, field_geom):
    """Agriculture false-colour RGB with the field boundary painted red."""
    vis = img.visualize(bands=BANDS, min=VIS["min"], max=VIS["max"])
    fc = ee.FeatureCollection([ee.Feature(field_geom)])
    outline = ee.Image().byte().paint(fc, 1, 2)            # 2-px boundary
    red = ee.Image.constant([236, 58, 40]).visualize(min=0, max=255)
    return vis.where(outline, red)


def season_windows(year):
    """6 two-week windows: [(start_iso, end_iso, label), ...]."""
    start = date(year, SEASON_START_MD[0], SEASON_START_MD[1])
    out = []
    for i in range(N_STEPS):
        s = start + timedelta(days=i * STEP_DAYS)
        e = s + timedelta(days=STEP_DAYS)
        out.append((s.isoformat(), e.isoformat(), s.strftime("%d %b %Y")))
    return out


def download_thumb(img_vis, region, dim, tries=5):
    url = img_vis.getThumbURL({"region": region, "dimensions": dim, "format": "jpg"})
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=90)
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).convert("RGB")
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)          # backoff: respects thumbnail rate limits
    raise RuntimeError("thumbnail download failed after retries")


# ======================================================================
# Montage (Pillow) — 6 facets, 2 rows x 3 cols, dated
# ======================================================================
def make_montage(panels, labels):
    cols, rows, pad, cap = 4, 2, 5, 20      # 8 facets: 4 across x 2 down
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
# Per-field + main loop
# ======================================================================
def process_field(geom_dict, province, season):
    geom = ee.Geometry(geom_dict)
    centroid = geom.centroid(maxError=1)
    lon, lat = centroid.coordinates().getInfo()
    region = centroid.buffer(BUFFER_M).bounds()

    panels, labels = [], []
    for start, end, label in season_windows(season):
        comp = s2_composite(region, start, end)
        panels.append(download_thumb(visualize_with_boundary(comp, geom), region, PANEL_PX))
        labels.append(label)

    montage = make_montage(panels, labels)
    fname = f"{lat:.5f}_{lon:.5f}_{season}_{province}.jpg"
    rel = f"{province}/{season}/{fname}"
    out_path = os.path.join(IMAGES_DIR, province, str(season), fname)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    montage.save(out_path, quality=88)
    return {"rel": rel, "lat": round(lat, 6), "lon": round(lon, 6)}


def sample_fields(province, n):
    parcels = ee.FeatureCollection(PARCELS_ASSET).filter(
        ee.Filter.eq(PROVINCE_FIELD, province))
    sample = parcels.randomColumn("rnd", SEED).sort("rnd").limit(n)
    return [f["geometry"] for f in sample.toList(n).getInfo()]


def main():
    init_ee()
    os.makedirs(IMAGES_DIR, exist_ok=True)
    rows = []
    for province in PROVINCES:
        for season in SEASONS:
            print(f"== {province} {season}: sampling {N_FIELDS} fields ==")
            geoms = sample_fields(province, N_FIELDS)
            for i, g in enumerate(geoms, 1):
                try:
                    f = process_field(g, province, season)
                    # ONE field = one montage = one screen (image_b unused in
                    # single-image mode; kept empty for schema compatibility)
                    rows.append({
                        "pair_id": f"{province}_{season}_{i:04d}",
                        "province": province, "year": season,
                        "image_a": f["rel"], "image_b": "",
                        "lat_a": f["lat"], "lon_a": f["lon"],
                        "lat_b": "", "lon_b": "",
                    })
                    print(f"  [{i}/{len(geoms)}] {f['rel']}")
                except Exception as e:
                    print(f"  [{i}/{len(geoms)}] SKIPPED ({e})")

    cols = ["pair_id", "province", "year", "image_a", "image_b",
            "lat_a", "lon_a", "lat_b", "lon_b"]
    write_header = not os.path.exists(META_CSV)
    with open(META_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])

    print(f"\nDone. {len(rows)} fields (= {len(rows)} screens). Metadata -> {META_CSV}")
    print("Next: Rscript r/build_pairs.R  ->  load into Supabase  ->  it's live.")


if __name__ == "__main__":
    main()
