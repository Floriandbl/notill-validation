// ============================================================================
//  PROTOTYPE — paste into the GEE Code Editor (code.earthengine.google.com)
//  Purpose: eyeball the IMAGERY on one real field before the batch run. Tune
//  BANDS / VIS / dates until the 8 layers look right, then copy those exact
//  values into gee/build_from_gee.py and run the Python batch.
//
//  No parcel asset needed: the shapefile stays local, and the field delineation
//  + centroid dot are drawn locally by build_from_gee.py. This script is only
//  for judging the composite's look (band combo, stretch, cloudiness, dates).
// ============================================================================

// ---- a real sampled field (any lon/lat row from prep/fields_settat_500.csv) ----
var LON = -7.278611, LAT = 32.451724;    // settat_453, 1.31 ha
var SEASON_YEAR = 2025;

// ---- knobs to tune (mirror these into gee/build_from_gee.py) ----
var SEASON_START = ee.Date.fromYMD(SEASON_YEAR, 9, 1);    // 1 Sept
var N_STEPS = 8, STEP_DAYS = 14, BOX_M = 250;             // 250 x 250 m box
var BANDS = ['B11', 'B8', 'B2'];        // agriculture false colour: veg=green, soil=red/brown
// Per-band stretch measured from real Settat reflectance. min=0/max=3000 saturates
// B11+B8 (everything renders yellow); stretching BLUE to its own range makes soil
// magenta — so the blue ceiling is deliberately wide. Keep fixed across all dates.
var VIS   = {min: [2000, 2900, 250], max: [5200, 5100, 5000]};
var MAX_CLOUD = 60;

var centre = ee.Geometry.Point([LON, LAT]);
var region = centre.buffer(BOX_M / 2).bounds();
Map.centerObject(region, 16);
Map.addLayer(centre, {color: 'red'}, 'centroid');

function maskS2(img) {
  var scl = img.select('SCL');
  var bad = scl.eq(3).or(scl.eq(8)).or(scl.eq(9)).or(scl.eq(10)).or(scl.eq(11));
  return img.updateMask(bad.not());
}

// one layer per date — toggle them in the Layers panel to see the field change
for (var i = 0; i < N_STEPS; i++) {
  var s = SEASON_START.advance(i * STEP_DAYS, 'day');
  var e = s.advance(STEP_DAYS, 'day');
  var comp = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
      .filterBounds(region).filterDate(s, e)
      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', MAX_CLOUD))
      .map(maskS2).median();
  var shown = comp.visualize({bands: BANDS, min: VIS.min, max: VIS.max});
  Map.addLayer(shown.clip(region), {}, 'ABCDEFGH'.charAt(i));   // A..H, same as the montage
}
print('Fields here are small (median 0.75 ha ~ 9 Sentinel-2 pixels): judge the field by how');
print('its TONE changes across A..H, not by texture. Copy BANDS/VIS/dates into build_from_gee.py.');
