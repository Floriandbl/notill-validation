# Building the real dataset from Sentinel-2 (Google Earth Engine)

`build_from_gee.py` turns your parcel layer into the labeling dataset: for each
sampled field it makes a **6-facet, bi-weekly Sentinel-2 montage** (agriculture
false-colour, field boundary painted red), named `{lat}_{lon}_{season}_{province}.jpg`,
and writes `pairs_metadata.csv` so the app + `r/build_pairs.R` pick it up unchanged.

## Setup
```bash
pip install earthengine-api pillow requests
earthengine authenticate      # once
```

## Fill in 3 things (top of the script)
- `EE_PROJECT` — your Earth Engine / GCP project id
- `PARCELS_ASSET` — your uploaded parcel layer (GEE asset id)
- `PROVINCE_FIELD` — the attribute on that layer holding the province name

## Run the pilot, then scale
Defaults do **1 province × 1 season × 100 fields = 50 pairs**:
```bash
python gee/build_from_gee.py
```
Eyeball `images/Settat/2020/*.jpg`. When happy, scale by editing two lines:
```python
PROVINCES = ["Settat", "Berrechid", ...]   # your 20
SEASONS   = [2015, 2016, ..., 2025]        # 11 seasons
```
Then: `Rscript r/build_pairs.R` → load the pairs into Supabase → it's live.

## Tunables
- `SEASON_START_MD`, `N_STEPS`, `STEP_DAYS` — the 6 dates (default: every 2 weeks from 1 Oct)
- `BUFFER_M`, `PANEL_PX` — footprint + resolution per facet
- `BANDS`, `VIS` — the false-colour look. Default `B11/B8/B2` (veg green, soil red-brown).
  If your reference tiles used a different combo/stretch, set it here so it matches.
- `MAX_CLOUD` — scenes cloudier than this are dropped before compositing.

## Two things to know
1. **Scale / storage.** Full scale = 22,000 montages ≈ 132,000 thumbnail pulls and
   several GB — hours of downloading, and **too big for git/GitHub Pages**. At that
   size host `images/` in object storage (Cloudflare R2 / S3) and set
   `host_mode`/URLs in `build_pairs.R` accordingly. The app itself needs no change.
2. **App display tweak (montages are landscape).** The current cards are square
   (`object-fit: cover`) because the placeholder tiles are square. A 6-facet montage
   is ~3:2 wide, so switch `.imgcard img` in `static/style.css` to
   `object-fit: contain` (and drop the forced square) when you go live with montages —
   otherwise the outer facets get cropped. Ping me and I'll flip it.

## Rate limits
`getThumbURL` is throttled (a few hundred/min). The script already retries with
backoff; for full scale add a small thread pool and expect a few hours.
