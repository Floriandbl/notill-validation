#!/usr/bin/env python3
"""
burn_panel_letters.py — draw a large A..H into each panel of every montage.

The generator already writes a date caption ("A · 1 Sep") in the 20px strip above
each panel, but at ~37x10 px it is unreadable on a phone, where a whole panel is
only ~74px wide. This burns a big letter INTO the top-left corner of each panel,
so the montage and the "which image?" buttons can be matched at a glance.

Geometry (measured against all 500 files, not assumed):
    every montage is exactly 1305x695
    panel_origin(i) = (PAD + (i%4)*(PANEL_PX+PAD),  PAD + (i//4)*(PANEL_PX+CAP+PAD) + CAP)
    -> A(5,25) B(330,25) C(655,25) D(980,25) E(5,370) F(330,370) G(655,370) H(980,370)

Why white-with-a-black-stroke rather than plain white: the panel corner luminance
across 480 real panels runs p5=91 / p50=135 / p95=228. The pale middle of the NDTI
ramp (#f6e8c3, #c7eae5) lands there as often as the dark ends (#8c510a, #01665e),
so a white letter vanishes on pale panels and a black one dies on dark teal. The
stroke carries the light backgrounds, the body carries the dark ones.

The top-left corner is provably free of field data: across 480 panels there is not
one magenta pixel in the 74x74 corner box, and the nearest outline pixel is 143px
away. The glyph ends at (56,50).

    python prep/burn_panel_letters.py            # all 500, in place
    python prep/burn_panel_letters.py --force    # re-run over already-lettered files
    python prep/burn_panel_letters.py --limit 3  # try a few first
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "images", "Settat", "2025")
MARKER = os.path.join(ROOT, "images", ".letters_burned")

PANEL_PX, COLS, ROWS, PAD, CAP = 320, 4, 2, 5, 20
EXPECT_SIZE = (1305, 695)
LETTERS = "ABCDEFGH"

FONT_PATH = "C:/Windows/Fonts/ariblk.ttf"      # Arial Black — heaviest stem, survives the stroke
FONT_PX = 64
X_OFF, Y_OFF = 6, 4
STROKE = 3
# JPEG generational loss: the source is quality=88 with 4:2:0 chroma. Re-encoding a
# decoded JPEG compounds artifacts, and here they sit on the very texture people are
# asked to judge. Measured re-encode RMSE over a field interior (vs the decoded
# source), and the driver turned out to be chroma, not the quality number:
#     q88 4:2:0 -> 5.02      q88 4:4:4 -> 2.25
#     q95 4:2:0 -> 4.83      q95 4:4:4 -> 1.45
# 4:2:0 stays ~5 however high quality goes, because the 3px magenta outline IS
# chroma detail. So: keep 4:4:4, and q92 as the size/fidelity knee.
#     q92 4:4:4 -> RMSE 1.99, 224 KB/image, ~112 MB for the set (from 67 MB).
JPEG_QUALITY = 92


def panel_origin(i):
    c, r = i % COLS, i // COLS
    return PAD + c * (PANEL_PX + PAD), PAD + r * (PANEL_PX + CAP + PAD) + CAP


def burn(path, font):
    img = Image.open(path)
    if img.size != EXPECT_SIZE:
        return f"skip (size {img.size})"
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)
    for i, letter in enumerate(LETTERS):
        ox, oy = panel_origin(i)
        d.text((ox + X_OFF, oy + Y_OFF), letter, font=font, anchor="lt",
               fill=(255, 255, 255), stroke_width=STROKE, stroke_fill=(0, 0, 0))
    img.save(path, "JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=True)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-run even if already burned")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    if os.path.exists(MARKER) and not a.force:
        sys.exit("Letters already burned (images/.letters_burned exists).\n"
                 "Re-running would double-draw. Use --force if that is what you want,\n"
                 "or `git checkout -- images/` first to restore the originals.")

    if not os.path.exists(FONT_PATH):
        sys.exit(f"font not found: {FONT_PATH}")
    font = ImageFont.truetype(FONT_PATH, FONT_PX)

    files = sorted(f for f in os.listdir(IMAGES) if f.lower().endswith(".jpg"))
    if a.limit:
        files = files[:a.limit]

    before = sum(os.path.getsize(os.path.join(IMAGES, f)) for f in files)
    done = skipped = 0
    for n, f in enumerate(files, 1):
        r = burn(os.path.join(IMAGES, f), font)
        if r:
            skipped += 1
            print(f"  {f}: {r}")
        else:
            done += 1
        if n % 100 == 0:
            print(f"  ... {n}/{len(files)}")
    after = sum(os.path.getsize(os.path.join(IMAGES, f)) for f in files)

    if not a.limit:
        open(MARKER, "w").write("panel letters A-H burned in by prep/burn_panel_letters.py\n")

    print(f"\nburned {done} montages, skipped {skipped}")
    print(f"size {before/1e6:.1f} MB -> {after/1e6:.1f} MB  (quality={JPEG_QUALITY})")


if __name__ == "__main__":
    main()
