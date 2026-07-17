#!/usr/bin/env python3
"""
pick_examples_step.py — pick two REAL montages by CHANGEPOINT score.

The user's criterion, verbatim:

    "only the field inside the boundaries (and maybe some neighbouring fields)
     has its TEXTURE change SUDDENLY from one picture to the next, while being
     more CONSISTENT before and after."

So tillage is a STEP: one big jump between consecutive dates, stability either
side. No-till is a flat line: no jump anywhere.

Method
------
For every field, for each of the 8 panels (A..H, 14 days apart from 1 Sep), we
sample the field INTERIOR (true point-in-polygon, eroded away from the magenta
outline and the centroid dot) and compute:

  tone_i   = mean(R-B)          brown #8c510a -> +130, teal #01665e -> -93
  sd_i     = stdev(R-B)         texture: within-field spread
  rough_i  = mean |v - v_nbr|   texture: local roughness (lag-1 neighbour MAD)

tone and texture are z-scaled by their POPULATION spread so they are
commensurable, then combined into a 2-D (tone, texture) point per panel with
EQUAL weight -- the user said TEXTURE, so texture is not a tiebreaker:

  tex_i  = 0.5*(sd_i/S_sd + rough_i/S_rough)
  step_i = || (tone_z, tex_z)[i+1] - (tone_z, tex_z)[i] ||     i = 0..6

  best_step  = max(step_i)
  step_ratio = best_step / (median(other 6 steps) + EPS)

  TILL   candidate = highest step_ratio   (one jump, stable either side)
  NOTILL candidate = lowest  best_step    (no jump anywhere, all season)

Honesty diagnostic
------------------
A previous audit found the montages are dominated by the SEASONAL cycle: all
500 fields drift together. A big raw step can therefore be pure season and say
nothing about the field. So we ALSO recompute every score after subtracting the
per-panel population median (the common mode). The difference between the raw
and common-mode-removed rank is reported, not hidden -- it is the honest measure
of how field-specific a "step" really is.

    python3 prep/pick_examples_step.py
"""
import collections
import csv
import json
import math
import os
import shutil
import statistics

from PIL import Image
from pyproj import Transformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON = os.path.join(ROOT, "prep", "fields_settat_500.geojson")
META = os.path.join(ROOT, "pairs_metadata.csv")
IMAGES = os.path.join(ROOT, "images")
SOURCE = os.path.join(ROOT, "source")

# must match the montage that was actually generated (verified: 1305x695)
BOX_M, PANEL_PX, COLS, ROWS, PAD, CAP = 650, 320, 4, 2, 5, 20
NPANEL = COLS * ROWS
LETTERS = "ABCDEFGH"
DATES = ["1 Sep", "15 Sep", "29 Sep", "13 Oct", "27 Oct", "10 Nov", "24 Nov", "8 Dec"]

UTM_CRS = "EPSG:32629"
TO_UTM = Transformer.from_crs("EPSG:4326", UTM_CRS, always_xy=True)

ERODE_PX = 3      # pull the interior mask away from the magenta outline (~6 m)
DILATE_PX = 2     # grow detected overlay to swallow its JPEG halo
MIN_VALID = 200   # screen px of clean interior needed to trust a field
EPS = 1e-3        # keeps step_ratio finite when a field is perfectly flat


def panel_origin(i):
    c, r = i % COLS, i // COLS
    return PAD + c * (PANEL_PX + PAD), PAD + r * (PANEL_PX + CAP + PAD) + CAP


def is_overlay(px):
    r, g, b = px
    return r > 190 and g < 90 and b > 190          # magenta outline / centroid dot


def poly_panel_px(feat):
    """Field ring -> panel-local pixel coords (same mapping as pick_examples.py)."""
    lon, lat = feat["properties"]["lon"], feat["properties"]["lat"]
    cx, cy = TO_UTM.transform(lon, lat)
    half = BOX_M / 2.0
    xmin, ymax = cx - half, cy + half
    ring = [TO_UTM.transform(x, y) for x, y in feat["geometry"]["coordinates"][0]]
    return [((X - xmin) / BOX_M * PANEL_PX, (ymax - Y) / BOX_M * PANEL_PX) for X, Y in ring]


def point_in_poly(x, y, poly):
    """Ray casting. pick_examples.py used the bbox, which drags in the neighbours;
    for a TEXTURE measure that would inject the field's own edges as fake texture."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
                inside = not inside
        j = i
    return inside


def pixels(crop):
    """Pillow 12 deprecates getdata() in favour of get_flattened_data(); support both."""
    fn = getattr(crop, "get_flattened_data", None)
    return list(fn() if fn else crop.getdata())


def erode(mask, w, h, k):
    """Keep a cell only if every cell within Chebyshev distance k is also set."""
    out = [False] * (w * h)
    for y in range(h):
        for x in range(w):
            if not mask[y * w + x]:
                continue
            ok = True
            for dy in range(-k, k + 1):
                yy = y + dy
                if yy < 0 or yy >= h:
                    ok = False
                    break
                for dx in range(-k, k + 1):
                    xx = x + dx
                    if xx < 0 or xx >= w or not mask[yy * w + xx]:
                        ok = False
                        break
                if not ok:
                    break
            out[y * w + x] = ok
    return out


def dilate(mask, w, h, k):
    out = [False] * (w * h)
    for y in range(h):
        for x in range(w):
            if not mask[y * w + x]:
                continue
            for dy in range(-k, k + 1):
                for dx in range(-k, k + 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < w and 0 <= yy < h:
                        out[yy * w + xx] = True
    return out


def field_signals(img, feat):
    """Per-panel (tone, sd, rough) over the clean field interior. None if unusable."""
    poly = poly_panel_px(feat)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1 = max(0, int(min(xs)) - 1), min(PANEL_PX, int(max(xs)) + 2)
    y0, y1 = max(0, int(min(ys)) - 1), min(PANEL_PX, int(max(ys)) + 2)
    w, h = x1 - x0, y1 - y0
    if w < 6 or h < 6:
        return None

    # geometric interior, eroded off the outline
    inside = [point_in_poly(x0 + x + 0.5, y0 + y + 0.5, poly)
              for y in range(h) for x in range(w)]
    inside = erode(inside, w, h, ERODE_PX)
    if sum(inside) < MIN_VALID:
        return None

    tone, sd, rough, nvalid = [], [], [], []
    for i in range(NPANEL):
        ox, oy = panel_origin(i)
        px = pixels(img.crop((ox + x0, oy + y0, ox + x1, oy + y1)))

        # overlay (magenta line + centroid dot) grown to cover JPEG bleed
        ov = dilate([is_overlay(p) for p in px], w, h, DILATE_PX)
        val = [None] * (w * h)
        for k in range(w * h):
            if inside[k] and not ov[k]:
                val[k] = px[k][0] - px[k][2]

        v = [t for t in val if t is not None]
        if len(v) < MIN_VALID:
            return None

        # lag-1 neighbour MAD, both axes, only where both cells are valid
        diffs = []
        for y in range(h):
            for x in range(w):
                a = val[y * w + x]
                if a is None:
                    continue
                if x + 1 < w and val[y * w + x + 1] is not None:
                    diffs.append(abs(a - val[y * w + x + 1]))
                if y + 1 < h and val[(y + 1) * w + x] is not None:
                    diffs.append(abs(a - val[(y + 1) * w + x]))
        if not diffs:
            return None

        tone.append(statistics.fmean(v))
        sd.append(statistics.pstdev(v))
        rough.append(statistics.fmean(diffs))
        nvalid.append(len(v))

    return {"tone": tone, "sd": sd, "rough": rough, "nvalid": min(nvalid)}


def score(tone_z, tex_z):
    """step_i, best_step, step_ratio for one field's 8-panel trace."""
    steps = [math.dist((tone_z[i], tex_z[i]), (tone_z[i + 1], tex_z[i + 1]))
             for i in range(NPANEL - 1)]
    best = max(steps)
    bi = steps.index(best)
    rest = [s for k, s in enumerate(steps) if k != bi]
    return steps, best, bi, best / (statistics.median(rest) + EPS)


def trace(vals, fmt="%+6.1f"):
    return " ".join(fmt % v for v in vals)


def main():
    feats = json.load(open(GEOJSON, encoding="utf-8"))["features"]
    by_id = {f["properties"]["field_id"]: f for f in feats}
    rows = list(csv.DictReader(open(META, encoding="utf-8")))

    # ---- pass 1: raw per-panel signals -------------------------------------
    fields, skipped = [], 0
    for r in rows:
        f = by_id.get(r["pair_id"])
        p = os.path.join(IMAGES, r["image_a"].replace("/", os.sep))
        if not f or not os.path.exists(p):
            skipped += 1
            continue
        with Image.open(p) as im:
            s = field_signals(im.convert("RGB"), f)
        if not s:
            skipped += 1
            continue
        s.update(id=r["pair_id"], path=p, rel=r["image_a"],
                 area=f["properties"]["area_ha"])
        fields.append(s)

    print(f"scored {len(fields)} / {len(rows)} montages  ({skipped} skipped: "
          f"missing, off-panel, or < {MIN_VALID} px clean interior)\n")
    if not fields:
        return

    # ---- population scales, so tone and texture are commensurable ----------
    all_tone = [v for f in fields for v in f["tone"]]
    all_sd = [v for f in fields for v in f["sd"]]
    all_rough = [v for f in fields for v in f["rough"]]
    S_tone = statistics.pstdev(all_tone) or 1.0
    S_sd = statistics.pstdev(all_sd) or 1.0
    S_rough = statistics.pstdev(all_rough) or 1.0
    print(f"population scale   tone sd={S_tone:.2f}   texture-sd sd={S_sd:.2f}   "
          f"roughness sd={S_rough:.2f}")

    # seasonal common mode = per-panel median across all 500 fields
    cm_tone = [statistics.median([f["tone"][i] for f in fields]) for i in range(NPANEL)]
    cm_sd = [statistics.median([f["sd"][i] for f in fields]) for i in range(NPANEL)]
    cm_rough = [statistics.median([f["rough"][i] for f in fields]) for i in range(NPANEL)]
    print("seasonal common mode (median of all 500 fields, A..H)")
    print("   tone      ", trace(cm_tone))
    print("   texture sd", trace(cm_sd))
    print("   roughness ", trace(cm_rough))
    cm_steps = [abs(cm_tone[i + 1] - cm_tone[i]) for i in range(NPANEL - 1)]
    print("   |d tone|  ", trace(cm_steps), "  <- the season every field shares\n")

    # ---- pass 2: score raw, and score with the season removed --------------
    for f in fields:
        f["tone_z"] = [v / S_tone for v in f["tone"]]
        f["tex_z"] = [0.5 * (f["sd"][i] / S_sd + f["rough"][i] / S_rough)
                      for i in range(NPANEL)]
        f["steps"], f["best"], f["bi"], f["ratio"] = score(f["tone_z"], f["tex_z"])

        # same thing, but each panel expressed as a departure from that date's
        # population median -> what is left is specific to THIS field
        dt = [(f["tone"][i] - cm_tone[i]) / S_tone for i in range(NPANEL)]
        dx = [0.5 * ((f["sd"][i] - cm_sd[i]) / S_sd + (f["rough"][i] - cm_rough[i]) / S_rough)
              for i in range(NPANEL)]
        f["a_steps"], f["a_best"], f["a_bi"], f["a_ratio"] = score(dt, dx)

    till = sorted(fields, key=lambda f: -f["ratio"])
    notill = sorted(fields, key=lambda f: f["best"])

    def show(f, rank):
        print(f"  #{rank} {f['id']:14s} {f['area']:.2f} ha  {f['nvalid']:4d} px  "
              f"step_ratio {f['ratio']:6.2f}   best_step {f['best']:.3f} at "
              f"{LETTERS[f['bi']]}->{LETTERS[f['bi'] + 1]} ({DATES[f['bi']]} -> {DATES[f['bi'] + 1]})")
        print(f"      tone   A..H  {trace(f['tone'])}")
        print(f"      sd     A..H  {trace(f['sd'])}")
        print(f"      rough  A..H  {trace(f['rough'])}")
        print(f"      step   A-H   {trace(f['steps'], '%6.2f')}   (7 gaps)")
        print(f"      season-removed: step_ratio {f['a_ratio']:5.2f}  best_step "
              f"{f['a_best']:.3f} at {LETTERS[f['a_bi']]}->{LETTERS[f['a_bi'] + 1]}")

    print("=" * 78)
    print("TILL candidates - highest step_ratio (one sudden change, consistent either side)")
    print("=" * 78)
    for k, f in enumerate(till[:5], 1):
        show(f, k)
    print()
    print("=" * 78)
    print("NO-TILL candidates - lowest max step (consistent all season, no jump)")
    print("=" * 78)
    for k, f in enumerate(notill[:5], 1):
        show(f, k)

    # ---- how special is the winner, really? -------------------------------
    ratios = sorted((f["ratio"] for f in fields), reverse=True)
    bests = sorted(f["best"] for f in fields)
    w = till[0]
    print("\n" + "=" * 78)
    print("HOW STRONG IS THIS, HONESTLY")
    print("=" * 78)
    print(f"step_ratio across {len(fields)} fields: max {ratios[0]:.2f}  p99 {ratios[len(ratios) // 100]:.2f}  "
          f"p95 {ratios[len(ratios) // 20]:.2f}  median {statistics.median(ratios):.2f}  min {ratios[-1]:.2f}")
    print(f"  winner {w['id']} step_ratio {w['ratio']:.2f} vs median {statistics.median(ratios):.2f} "
          f"-> {w['ratio'] / statistics.median(ratios):.2f}x the typical field")
    print(f"  fields within 90% of the winner's step_ratio: "
          f"{sum(1 for r in ratios if r >= 0.9 * ratios[0])}")
    print(f"best_step across fields: min {bests[0]:.3f}  median {statistics.median(bests):.3f}  max {bests[-1]:.3f}")
    n = notill[0]
    print(f"  no-till pick {n['id']} best_step {n['best']:.3f} = {n['best'] / statistics.median(bests):.2f}x the median field")

    # is the winner's step field-specific, or is it just the season?
    print(f"\n  winner's biggest gap is {LETTERS[w['bi']]}->{LETTERS[w['bi'] + 1]}; the "
          f"population's own |d tone| there is {cm_steps[w['bi']]:.1f} "
          f"(max seasonal gap {max(cm_steps):.1f} at "
          f"{LETTERS[cm_steps.index(max(cm_steps))]}->{LETTERS[cm_steps.index(max(cm_steps)) + 1]})")
    a_rank = sorted(fields, key=lambda f: -f["a_ratio"])
    pos = [f["id"] for f in a_rank].index(w["id"]) + 1
    print(f"  once the season is removed, {w['id']} ranks {pos} / {len(fields)} on step_ratio "
          f"({w['ratio']:.2f} -> {w['a_ratio']:.2f})")
    print(f"  season-removed top 5: " + ", ".join(f"{f['id']}({f['a_ratio']:.1f})" for f in a_rank[:5]))

    # The killer diagnostic: if every field steps at the same gap, the score is
    # not finding tillage, it is finding the date the whole region changed.
    raw_hist = collections.Counter(f["bi"] for f in fields)
    adj_hist = collections.Counter(f["a_bi"] for f in fields)
    print("\n  WHERE the biggest step lands (if this piles up on one gap, the score is a season detector)")
    print("    gap        " + "  ".join(f" {LETTERS[i]}->{LETTERS[i + 1]}" for i in range(NPANEL - 1)))
    for nm, hist in (("raw      ", raw_hist), ("season-rm", adj_hist)):
        top = max(hist, key=lambda k: hist[k])
        print(f"    {nm}  " + "  ".join(f"{hist[i]:4d} " for i in range(NPANEL - 1)) +
              f"  -> {100 * hist[top] / len(fields):.1f}% land on {LETTERS[top]}->{LETTERS[top + 1]}")

    # Is there any dynamic range before H at all, or is the ramp saturated brown?
    print("\n  TONE RANGE per date (brown #8c510a=+130 is the ramp end; teal #01665e=-93)")
    for i in range(NPANEL):
        v = sorted(f["tone"][i] for f in fields)
        nn = len(v)
        print(f"    {LETTERS[i]} {DATES[i]:<7s} p10 {v[nn // 10]:+7.1f}  med {statistics.median(v):+7.1f}  "
              f"p90 {v[9 * nn // 10]:+7.1f}   p10-p90 spread {v[9 * nn // 10] - v[nn // 10]:5.1f}")
    n_teal = sum(1 for f in fields if max(f["tone"][:7]) < 0)
    print(f"\n    fields TEAL (residue-toned) on all of A..G: {n_teal} / {len(fields)}"
          f"   <- a residue-covered no-till example needs this")

    # ---- write the picks ---------------------------------------------------
    os.makedirs(SOURCE, exist_ok=True)
    shutil.copy(till[0]["path"], os.path.join(SOURCE, "example_till.jpg"))
    shutil.copy(notill[0]["path"], os.path.join(SOURCE, "example_notill.jpg"))
    print(f"\nwrote source/example_till.jpg   <- {till[0]['id']}  ({till[0]['rel']})")
    print(f"wrote source/example_notill.jpg <- {notill[0]['id']}  ({notill[0]['rel']})")

    json.dump({
        "method": "changepoint on (tone, texture) z-space; till=max step_ratio, notill=min best_step",
        "till": {"id": till[0]["id"], "file": till[0]["rel"], "step_ratio": round(till[0]["ratio"], 3),
                 "best_step": round(till[0]["best"], 3),
                 "step_panel": f"{LETTERS[till[0]['bi']]}->{LETTERS[till[0]['bi'] + 1]}",
                 "season_removed_step_ratio": round(till[0]["a_ratio"], 3)},
        "no_till": {"id": notill[0]["id"], "file": notill[0]["rel"],
                    "best_step": round(notill[0]["best"], 3),
                    "step_ratio": round(notill[0]["ratio"], 3)},
        "caveat": "ILLUSTRATIVE ONLY - not verified ground truth. Montages are "
                  "dominated by the seasonal cycle; see script output for numbers.",
    }, open(os.path.join(SOURCE, "examples_picked_step.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
