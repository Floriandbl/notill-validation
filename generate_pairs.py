#!/usr/bin/env python3
"""
generate_pairs.py - Synthetic FALSE-COLOUR field-parcel pairs for the study.

Pure Python standard library (no numpy / Pillow). Produces seeded, reproducible
256x256 RGB PNG chips that imitate the false-colour satellite tiles used in the
project (à la the two reference screenshots):

    TILL     -> bare / worked soil = RED / maroon, with fine plough (furrow) lines
    NO_TILL  -> vegetation / residue cover = GREEN
    AMBIGUOUS-> in between (hard cases)

Each chip shows several irregular parcels (Voronoi cells) with dark field
boundaries, occasional pixelated cloud/no-data patches (teal/blue-grey), and a
RED ARROW pointing at the TARGET parcel — the field the question is about. The
target parcel's class is the chip's "truth".

Organised as the app expects:
    images/{province}/{year}/pair_{NNNN}_a.png  (+ _b.png)

Outputs pairs_metadata.csv (truth_a/truth_b for self-checking) and manifest.json.
These are SYNTHETIC placeholders; drop real exported chips into images/ for production.

Usage:
    python generate_pairs.py                       # 200 pairs (5 provinces x 5 years x 8)
    python generate_pairs.py --per-cell 2 --provinces Settat --years 2023   # tiny test set
    python generate_pairs.py --clean               # wipe images/ + metadata first
"""
import argparse
import csv
import json
import math
import os
import random
import struct
import zlib

W = H = 256
ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(ROOT, "images")
META_CSV = os.path.join(ROOT, "pairs_metadata.csv")
MANIFEST = os.path.join(ROOT, "manifest.json")


# ----------------------------------------------------------------------------
# PNG writing (stdlib only)
# ----------------------------------------------------------------------------
def write_png(path, pixels):
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    stride = W * 3
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += pixels[y * stride:(y + 1) * stride]
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


# ----------------------------------------------------------------------------
# Value-noise fbm
# ----------------------------------------------------------------------------
def _grid(freq, rng):
    return [[rng.random() for _ in range(freq + 1)] for _ in range(freq + 1)]


def fbm_field(seed, base_freq=5, octaves=5):
    field = [0.0] * (W * H)
    rng = random.Random(seed)
    amp, freq, amp_total = 1.0, base_freq, 0.0
    for _ in range(octaves):
        g = _grid(freq, rng)
        sx, sy = freq / W, freq / H
        i = 0
        for y in range(H):
            gy = y * sy
            y0 = int(gy)
            fy = gy - y0
            vy = fy * fy * (3 - 2 * fy)
            row0, row1 = g[y0], g[y0 + 1]
            for x in range(W):
                gx = x * sx
                x0 = int(gx)
                fx = gx - x0
                vx = fx * fx * (3 - 2 * fx)
                n0 = row0[x0] + vx * (row0[x0 + 1] - row0[x0])
                n1 = row1[x0] + vx * (row1[x0 + 1] - row1[x0])
                field[i] += amp * (n0 + vy * (n1 - n0))
                i += 1
        amp_total += amp
        amp *= 0.5
        freq *= 2
    inv = 1.0 / amp_total
    return [v * inv for v in field]


# false-colour ramps: red = tilled bare soil, green = vegetation / no-till
TILL_RAMP = [(0.00, (66, 27, 31)), (0.38, (112, 48, 52)),
             (0.68, (150, 74, 73)), (1.00, (190, 124, 118))]
NOTILL_RAMP = [(0.00, (33, 50, 29)), (0.40, (58, 92, 47)),
               (0.70, (94, 126, 70)), (1.00, (128, 158, 100))]
CLOUD_COLORS = [(98, 126, 128), (74, 96, 104), (50, 64, 72), (122, 142, 140)]
ARROW_COLOR = (236, 58, 40)


def ramp(t, stops):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if t <= p1:
            f = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            return (c0[0] + (c1[0] - c0[0]) * f,
                    c0[1] + (c1[1] - c0[1]) * f,
                    c0[2] + (c1[2] - c0[2]) * f)
    return stops[-1][1]


def clamp8(v):
    return 0 if v < 0 else 255 if v > 255 else int(v)


# ----------------------------------------------------------------------------
# Parcels (low-res Voronoi, upsampled by lookup)
# ----------------------------------------------------------------------------
def voronoi_labels(seeds, pg):
    lab = [[0] * pg for _ in range(pg)]
    for gy in range(pg):
        for gx in range(pg):
            best, bestd = 0, 1e18
            for i, (sx, sy) in enumerate(seeds):
                d = (gx - sx) ** 2 + (gy - sy) ** 2
                if d < bestd:
                    bestd, best = d, i
            lab[gy][gx] = best
    return lab


# ----------------------------------------------------------------------------
# Simple raster drawing for the arrow
# ----------------------------------------------------------------------------
def _disc(px, cx, cy, r, color):
    r2 = r * r
    for yy in range(int(cy - r), int(cy + r) + 1):
        if 0 <= yy < H:
            dy = yy - cy
            for xx in range(int(cx - r), int(cx + r) + 1):
                if 0 <= xx < W and (xx - cx) ** 2 + dy * dy <= r2:
                    idx = (yy * W + xx) * 3
                    px[idx], px[idx + 1], px[idx + 2] = color


def _thick_line(px, x0, y0, x1, y1, r, color):
    steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for s in range(steps + 1):
        t = s / steps
        _disc(px, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, color)


def _triangle(px, p0, p1, p2, color):
    xs = (p0[0], p1[0], p2[0])
    ys = (p0[1], p1[1], p2[1])
    minx, maxx = max(0, int(min(xs))), min(W - 1, int(max(xs)))
    miny, maxy = max(0, int(min(ys))), min(H - 1, int(max(ys)))

    def sign(ax, ay, bx, by, cx, cy):
        return (ax - cx) * (by - cy) - (bx - cx) * (ay - cy)

    for yy in range(miny, maxy + 1):
        for xx in range(minx, maxx + 1):
            d1 = sign(xx, yy, p0[0], p0[1], p1[0], p1[1])
            d2 = sign(xx, yy, p1[0], p1[1], p2[0], p2[1])
            d3 = sign(xx, yy, p2[0], p2[1], p0[0], p0[1])
            has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
            has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
            if not (has_neg and has_pos):
                idx = (yy * W + xx) * 3
                px[idx], px[idx + 1], px[idx + 2] = color


def draw_arrow(px, tx, ty, rng):
    """Red arrow whose tip lands on the target field at (tx, ty)."""
    ang = math.radians(rng.choice([28, 55, 125, 152, 208, 235, 305, 332]))
    L = rng.uniform(0.34, 0.46) * W
    sx = min(W - 10, max(10, tx + math.cos(ang) * L))
    sy = min(H - 10, max(10, ty + math.sin(ang) * L))
    _thick_line(px, sx, sy, tx, ty, 4.2, ARROW_COLOR)
    # arrowhead pointing from start -> tip
    dx, dy = tx - sx, ty - sy
    dlen = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dlen, dy / dlen
    size = 18.0
    bx, by = tx - ux * size, ty - uy * size      # base centre, behind tip
    perpx, perpy = -uy, ux                       # perpendicular unit vector
    a = (bx + perpx * size * 0.62, by + perpy * size * 0.62)
    b = (bx - perpx * size * 0.62, by - perpy * size * 0.62)
    _triangle(px, (tx, ty), a, b, ARROW_COLOR)


# ----------------------------------------------------------------------------
# Chip rendering
# ----------------------------------------------------------------------------
def tillness_of(c):
    return 0.85 if c == "till" else (0.12 if c == "no_till" else 0.46)


def render_chip(seed, truth):
    rng = random.Random(seed)
    pg = 100
    nseeds = rng.randint(5, 8)
    seeds = [(rng.uniform(6, pg - 6), rng.uniform(6, pg - 6)) for _ in range(nseeds)]
    labels = voronoi_labels(seeds, pg)

    # target parcel = seed nearest the centre -> arrow points roughly to middle
    cx0, cy0 = pg / 2, pg / 2
    target = min(range(nseeds), key=lambda i: (seeds[i][0] - cx0) ** 2 + (seeds[i][1] - cy0) ** 2)

    pclass, pang, pfreq, ptone = {}, {}, {}, {}
    for i in range(nseeds):
        if i == target:
            pclass[i] = truth
        else:
            r = rng.random()
            pclass[i] = "till" if r < 0.68 else ("no_till" if r < 0.93 else "ambiguous")
        pang[i] = math.radians(rng.uniform(0, 180))
        pfreq[i] = 26 + 18 * rng.random()
        ptone[i] = rng.uniform(0.90, 1.08)

    base = fbm_field(seed, base_freq=5, octaves=5)
    cloud = fbm_field(seed + 7777, base_freq=7, octaves=2)
    has_clouds = rng.random() < 0.6
    cloud_thr = rng.uniform(0.66, 0.78)

    px = bytearray(W * H * 3)
    sxw, syh = pg / W, pg / H
    i = 0
    for y in range(H):
        gy = int(y * syh)
        gy2 = int((y + 1) * syh) if y + 1 < H else gy
        for x in range(W):
            gx = int(x * sxw)
            pid = labels[gy][gx]
            till = tillness_of(pclass[pid])
            v = base[y * W + x]
            rt, gt, bt = ramp(v, TILL_RAMP)
            rn, gn, bn = ramp(v, NOTILL_RAMP)
            r = rn + (rt - rn) * till
            g = gn + (gt - gn) * till
            b = bn + (bt - bn) * till
            # plough furrows (directional, per parcel)
            ang = pang[pid]
            s = math.sin((x * math.cos(ang) + y * math.sin(ang)) / W * pfreq[pid] * 2 * math.pi)
            m = 1.0 - 0.16 * (0.5 + 0.5 * s)
            tone = ptone[pid]
            r *= m * tone
            g *= m * tone
            b *= m * tone
            # field boundary (neighbour parcel differs)
            gx2 = int((x + 1) * sxw) if x + 1 < W else gx
            if labels[gy][gx2] != pid or labels[gy2][gx] != pid:
                r *= 0.45
                g *= 0.45
                b *= 0.45
            # pixelated cloud / no-data patches
            if has_clouds and cloud[y * W + x] > cloud_thr:
                cc = CLOUD_COLORS[((x // 6) * 7 + (y // 6) * 13 + pid) % len(CLOUD_COLORS)]
                a = 0.82
                r += (cc[0] - r) * a
                g += (cc[1] - g) * a
                b += (cc[2] - b) * a
            n = rng.randint(-4, 4)
            px[i] = clamp8(r + n)
            px[i + 1] = clamp8(g + n)
            px[i + 2] = clamp8(b + n)
            i += 3

    tx = seeds[target][0] / pg * W
    ty = seeds[target][1] / pg * H
    draw_arrow(px, tx, ty, rng)
    return px


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def pick_truth(rng):
    r = rng.random()
    return "till" if r < 0.5 else ("no_till" if r < 0.9 else "ambiguous")


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic false-colour image pairs.")
    ap.add_argument("--provinces", nargs="+",
                    default=["Settat", "Khouribga", "Safi", "El-Jadida", "Beni-Mellal"])
    ap.add_argument("--years", nargs="+", type=int, default=[2021, 2022, 2023, 2024, 2025])
    ap.add_argument("--per-cell", type=int, default=8,
                    help="pairs per province-year cell (default 8 -> 5x5x8 = 200)")
    ap.add_argument("-s", "--seed", type=int, default=20260626)
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()

    if args.clean and os.path.isdir(IMAGES_DIR):
        import shutil
        shutil.rmtree(IMAGES_DIR)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    for p in (META_CSV, MANIFEST):
        if args.clean and os.path.exists(p):
            os.remove(p)

    rng = random.Random(args.seed)
    rows = []
    total = len(args.provinces) * len(args.years) * args.per_cell
    print(f"Generating {total} pairs ({total * 2} chips, {W}x{H}) ...")
    done = 0
    for province in args.provinces:
        for year in args.years:
            cell_dir = os.path.join(IMAGES_DIR, province, str(year))
            os.makedirs(cell_dir, exist_ok=True)
            for k in range(1, args.per_cell + 1):
                num = f"{k:04d}"
                pair_id = f"{province}_{year}_{num}"
                truth_a, truth_b = pick_truth(rng), pick_truth(rng)
                seed_a, seed_b = rng.randint(1, 2_000_000_000), rng.randint(1, 2_000_000_000)
                rel_a = f"{province}/{year}/pair_{num}_a.png"
                rel_b = f"{province}/{year}/pair_{num}_b.png"
                write_png(os.path.join(IMAGES_DIR, rel_a), render_chip(seed_a, truth_a))
                write_png(os.path.join(IMAGES_DIR, rel_b), render_chip(seed_b, truth_b))
                rows.append({"pair_id": pair_id, "province": province, "year": year,
                             "image_a": rel_a, "image_b": rel_b,
                             "truth_a": truth_a, "truth_b": truth_b,
                             "seed_a": seed_a, "seed_b": seed_b})
                done += 1
                if done % 25 == 0 or done == total:
                    print(f"  {done}/{total} pairs")

    cols = ["pair_id", "province", "year", "image_a", "image_b",
            "truth_a", "truth_b", "seed_a", "seed_b"]
    with open(META_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"master_seed": args.seed, "provinces": args.provinces,
                   "years": args.years, "per_cell": args.per_cell,
                   "count": len(rows), "pairs": rows}, f, indent=2)

    print(f"\nDone. {len(rows)} pairs -> {IMAGES_DIR}")
    print(f"Metadata -> {META_CSV}")
    print("SYNTHETIC placeholders. Replace images/ with real chips for production.")


if __name__ == "__main__":
    main()
