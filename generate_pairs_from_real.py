#!/usr/bin/env python3
"""
generate_pairs_from_real.py - build the study dataset from REAL source screenshots.

Takes the two annotated satellite screenshots in source/ (till.jpg = red/tilled,
notill.jpg = green/no-till) and produces 200 image pairs. Each output image is a
randomly ROTATED + flipped + centre-cropped variant of one of the two sources, so
the dataset looks like varied real imagery and stands in for the true per-pair
images that will replace it later. The "truth" of each image is simply which
source it came from.

Requires Pillow (pip install Pillow).

Output layout (same as the synthetic generator, so the app/Supabase pipeline is
unchanged):
    images/{province}/{year}/pair_{NNNN}_a.jpg  (+ _b.jpg)
    pairs_metadata.csv   (truth_a/truth_b for self-checking)
    manifest.json

Usage:
    python generate_pairs_from_real.py                 # 200 pairs (5 prov x 5 yr x 8)
    python generate_pairs_from_real.py --per-cell 2 --provinces Settat --years 2023
    python generate_pairs_from_real.py --out-size 384
"""
import argparse
import csv
import json
import os
import random
import shutil

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(ROOT, "source")
IMAGES_DIR = os.path.join(ROOT, "images")
META_CSV = os.path.join(ROOT, "pairs_metadata.csv")
MANIFEST = os.path.join(ROOT, "manifest.json")

SOURCES = {"till": "till.jpg", "no_till": "notill.jpg"}


def load_square(path):
    """Open an image and return its largest centred square crop (RGB)."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    return img.crop((left, top, left + s, top + s))


def variant(square, rng, out_size):
    """A randomly rotated / flipped / centre-cropped variant — no black corners."""
    s = square.size[0]
    angle = rng.uniform(0, 360)
    rot = square.rotate(angle, resample=Image.BICUBIC, expand=False)
    # central inscribed square (factor <= 0.70 stays clear of the rotated corners)
    f = rng.uniform(0.60, 0.70)
    c = int(s * f)
    off = (s - c) // 2
    crop = rot.crop((off, off, off + c, off + c))
    if rng.random() < 0.5:
        crop = crop.transpose(Image.FLIP_LEFT_RIGHT)
    if rng.random() < 0.5:
        crop = crop.transpose(Image.FLIP_TOP_BOTTOM)
    return crop.resize((out_size, out_size), Image.LANCZOS)


def pick_truth(rng):
    return "till" if rng.random() < 0.5 else "no_till"


def main():
    ap = argparse.ArgumentParser(description="Build pairs from real source screenshots.")
    ap.add_argument("--provinces", nargs="+",
                    default=["Settat", "Khouribga", "Safi", "El-Jadida", "Beni-Mellal"])
    ap.add_argument("--years", nargs="+", type=int, default=[2021, 2022, 2023, 2024, 2025])
    ap.add_argument("--per-cell", type=int, default=8)
    ap.add_argument("--out-size", type=int, default=320)
    ap.add_argument("-s", "--seed", type=int, default=20260630)
    args = ap.parse_args()

    squares = {}
    for cls, fn in SOURCES.items():
        p = os.path.join(SOURCE_DIR, fn)
        if not os.path.exists(p):
            raise SystemExit(f"Missing source image: {p}")
        squares[cls] = load_square(p)
        print(f"loaded {cls:8s} <- source/{fn}  ({squares[cls].size[0]}px square)")

    # fresh image tree
    if os.path.isdir(IMAGES_DIR):
        shutil.rmtree(IMAGES_DIR)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    rng = random.Random(args.seed)
    rows = []
    total = len(args.provinces) * len(args.years) * args.per_cell
    print(f"Generating {total} pairs ({total * 2} images @ {args.out_size}px) from real sources ...")
    done = 0
    for province in args.provinces:
        for year in args.years:
            cell = os.path.join(IMAGES_DIR, province, str(year))
            os.makedirs(cell, exist_ok=True)
            for k in range(1, args.per_cell + 1):
                num = f"{k:04d}"
                rec = {"pair_id": f"{province}_{year}_{num}", "province": province, "year": year}
                for slot in ("a", "b"):
                    cls = pick_truth(rng)
                    rel = f"{province}/{year}/pair_{num}_{slot}.jpg"
                    variant(squares[cls], rng, args.out_size).save(
                        os.path.join(IMAGES_DIR, rel), quality=88)
                    rec[f"image_{slot}"] = rel
                    rec[f"truth_{slot}"] = cls
                rows.append(rec)
                done += 1
                if done % 25 == 0 or done == total:
                    print(f"  {done}/{total} pairs")

    cols = ["pair_id", "province", "year", "image_a", "image_b", "truth_a", "truth_b"]
    with open(META_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"source": "real screenshots (random rotation/flip/crop)",
                   "master_seed": args.seed, "provinces": args.provinces,
                   "years": args.years, "per_cell": args.per_cell,
                   "out_size": args.out_size, "count": len(rows), "pairs": rows}, f, indent=2)

    na = sum(1 for r in rows if r["truth_a"] == "till") + sum(1 for r in rows if r["truth_b"] == "till")
    print(f"\nDone. {len(rows)} pairs -> {IMAGES_DIR}")
    print(f"till images: {na} / {len(rows) * 2}   metadata -> {META_CSV}")
    print("Placeholder dataset (rotated copies of 2 real tiles); swap in true per-pair images later.")


if __name__ == "__main__":
    main()
