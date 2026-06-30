#!/usr/bin/env python3
"""
generate_pairs.py - Synthetic image PAIRS for the crowdsourced comparison app.

Pure Python standard library (no numpy / Pillow). Produces seeded, reproducible
256x256 RGB PNG chips organised as the production app expects:

    images/{province}/{year}/pair_{NNNN}_a.png
    images/{province}/{year}/pair_{NNNN}_b.png

Each pair = two independent "field" chips (image A and image B), each one either
tilled (bare/disturbed soil, brown, faint furrows) or no-till (residue-covered,
greener, straw speckle). That lets your two questions ask about each image
independently OR compare them.

Outputs:
    images/...                 the PNG chips
    pairs_metadata.csv         one row per pair (province, year, paths, A/B truth)
    manifest.json              full generation parameters (reproducibility)

The "truth" is for your own validation only; the app never shows it.

Usage:
    python generate_pairs.py                                  # 10 starter pairs (Settat 2023/2024)
    python generate_pairs.py --provinces Settat Khouribga --years 2023 2024 --per-cell 50
    python generate_pairs.py --clean                          # wipe images/ + metadata first
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


def fbm_field(seed, base_freq=4, octaves=5):
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


TILL_RAMP = [(0.00, (62, 46, 36)), (0.40, (118, 88, 62)),
             (0.72, (170, 134, 96)), (1.00, (208, 182, 150))]
NOTILL_RAMP = [(0.00, (52, 66, 42)), (0.40, (84, 104, 60)),
               (0.72, (122, 138, 90)), (1.00, (156, 168, 122))]
RESIDUE_STRAW = (196, 186, 142)


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


def render_chip(seed, truth):
    """One 256x256 chip. truth in {till, no_till, ambiguous}."""
    rng = random.Random(seed)
    base = fbm_field(seed, 4, 5)
    speck = fbm_field(seed + 4441, 48, 1)
    if truth == "till":
        tillness = 0.86
    elif truth == "no_till":
        tillness = 0.14
    else:
        tillness = 0.42 + 0.16 * (rng.random() - 0.5)

    residue_density = rng.uniform(0.10, 0.32)
    ang = math.radians(rng.uniform(0, 180))
    ca, sa = math.cos(ang), math.sin(ang)
    furrow_freq = 18.0 + 8.0 * rng.random()
    furrow_amp = rng.uniform(0.10, 0.18)
    tone = rng.uniform(0.92, 1.06)

    px = bytearray(W * H * 3)
    i = 0
    for y in range(H):
        for x in range(W):
            v = base[y * W + x]
            rt, gt, bt = ramp(v, TILL_RAMP)
            rn, gn, bn = ramp(v, NOTILL_RAMP)
            r = rn + (rt - rn) * tillness
            g = gn + (gt - gn) * tillness
            b = bn + (bt - bn) * tillness
            if tillness > 0.4:
                s = math.sin((x * ca + y * sa) / W * furrow_freq * 2 * math.pi)
                m = 1.0 - furrow_amp * tillness * (0.5 + 0.5 * s)
                r, g, b = r * m, g * m, b * m
            if tillness < 0.6 and speck[y * W + x] > (1.0 - residue_density):
                a = 0.55 * (1.0 - tillness)
                r += (RESIDUE_STRAW[0] - r) * a
                g += (RESIDUE_STRAW[1] - g) * a
                b += (RESIDUE_STRAW[2] - b) * a
            n = rng.randint(-4, 4)
            px[i] = clamp8(r * tone + n)
            px[i + 1] = clamp8(g * tone + n)
            px[i + 2] = clamp8(b * tone + n)
            i += 3
    return px


# ----------------------------------------------------------------------------
# Pair planning
# ----------------------------------------------------------------------------
# A spread of A/B truth combinations so either question style is exercised.
PAIR_TRUTHS = [
    ("till", "no_till"), ("no_till", "till"), ("till", "till"),
    ("no_till", "no_till"), ("till", "no_till"), ("no_till", "till"),
    ("till", "ambiguous"), ("ambiguous", "no_till"),
]


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic image pairs.")
    ap.add_argument("--provinces", nargs="+", default=["Settat"])
    ap.add_argument("--years", nargs="+", type=int, default=[2023, 2024])
    ap.add_argument("--per-cell", type=int, default=5,
                    help="pairs per province-year cell (default 5)")
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
    print(f"Generating {total} pairs ({total * 2} chips) ...")
    done = 0
    for province in args.provinces:
        for year in args.years:
            cell_dir = os.path.join(IMAGES_DIR, province, str(year))
            os.makedirs(cell_dir, exist_ok=True)
            for k in range(1, args.per_cell + 1):
                pid_num = f"{k:04d}"
                pair_id = f"{province}_{year}_{pid_num}"
                truth_a, truth_b = rng.choice(PAIR_TRUTHS)
                seed_a = rng.randint(1, 2_000_000_000)
                seed_b = rng.randint(1, 2_000_000_000)
                rel_a = f"{province}/{year}/pair_{pid_num}_a.png"
                rel_b = f"{province}/{year}/pair_{pid_num}_b.png"
                write_png(os.path.join(IMAGES_DIR, rel_a), render_chip(seed_a, truth_a))
                write_png(os.path.join(IMAGES_DIR, rel_b), render_chip(seed_b, truth_b))
                rows.append({
                    "pair_id": pair_id, "province": province, "year": year,
                    "image_a": rel_a, "image_b": rel_b,
                    "truth_a": truth_a, "truth_b": truth_b,
                    "seed_a": seed_a, "seed_b": seed_b,
                })
                done += 1
                print(f"  [{done:3d}/{total}] {pair_id}  A={truth_a} B={truth_b}")

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
    print("These are SYNTHETIC placeholders. Replace images/ with real chips for production.")


if __name__ == "__main__":
    main()
