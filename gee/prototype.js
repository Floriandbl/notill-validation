// ============================================================================
//  PROTOTYPE — paste into the GEE Code Editor (code.earthengine.google.com)
//  Purpose: tune the LOOK on one field before the batch run. Adjust BANDS / VIS
//  / dates until the 6 layers match your reference tiles, then copy those exact
//  values into gee/build_from_gee.py and run the Python batch.
// ============================================================================

// ---- fill these in ----
var PARCELS_ASSET  = 'projects/your-project/assets/morocco_parcels';  // your uploaded layer
var PROVINCE_FIELD = 'province';                                       // its province attribute
var PROVINCE       = 'Settat';
var SEASON_YEAR    = 2020;

// ---- knobs to tune ----
var SEASON_START = ee.Date.fromYMD(SEASON_YEAR, 10, 1);   // ~1 Oct
var N_STEPS = 6, STEP_DAYS = 14, BUFFER_M = 600;
var BANDS = ['B11', 'B8', 'B2'];        // agriculture false colour: veg=green, soil=red/brown
var VIS   = {min: 0, max: 3000};
var MAX_CLOUD = 60;

// ---- pick one random field ----
var parcels = ee.FeatureCollection(PARCELS_ASSET)
                .filter(ee.Filter.eq(PROVINCE_FIELD, PROVINCE));
var field  = ee.Feature(parcels.randomColumn('rnd', 42).sort('rnd').first());
var region = field.geometry().centroid(1).buffer(BUFFER_M).bounds();
Map.centerObject(region, 14);
print('field centroid [lon, lat]:', field.geometry().centroid(1).coordinates());

// ---- cloud mask + composite + red boundary ----
function maskS2(img) {
  var scl = img.select('SCL');
  var bad = scl.eq(3).or(scl.eq(8)).or(scl.eq(9)).or(scl.eq(10)).or(scl.eq(11));
  return img.updateMask(bad.not());
}
var outline = ee.Image().byte().paint(ee.FeatureCollection([field]), 1, 2);
var red = ee.Image.constant([236, 58, 40]).visualize({min: 0, max: 255});

for (var i = 0; i < N_STEPS; i++) {
  var s = SEASON_START.advance(i * STEP_DAYS, 'day');
  var e = s.advance(STEP_DAYS, 'day');
  var comp = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
      .filterBounds(region).filterDate(s, e)
      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', MAX_CLOUD))
      .map(maskS2).median();
  var shown = comp.visualize({bands: BANDS, min: VIS.min, max: VIS.max}).where(outline, red);
  Map.addLayer(shown.clip(region), {}, 'step ' + (i + 1));   // toggle layers to compare dates
}
print('Tune BANDS / VIS / SEASON_START above, then copy them into build_from_gee.py');
