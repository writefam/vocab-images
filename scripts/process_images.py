#!/usr/bin/env python3
"""
Process manually downloaded images from images/new/ into final vocabulary images.

Usage:
    python scripts/process_images.py [--size WxH] [--quality Q]

Workflow:
  1. Reads needed-images-part1.txt to map English keywords → final filenames.
  2. For each image in images/new/ (jpg/jpeg/png/webp/bmp/gif):
       - Matches the stem (e.g. "book" from "book.jpg") to an English keyword.
       - Resizes/centre-crops to TARGET_SIZE.
       - Saves as WebP to images/<final_filename>.
       - Moves the original to images/done/.
  3. Prints a summary of processed vs. skipped files.

Multi-word English entries (e.g. "watch, clock, hour") are split on commas so
any of the individual words can match an image filename.
"""

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
WORD_LIST  = REPO_ROOT / "needed-images-part1.txt"
NEW_DIR    = REPO_ROOT / "images" / "new"
OUT_DIR    = REPO_ROOT / "images"
DONE_DIR   = REPO_ROOT / "images" / "done"

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_SIZE    = (400, 400)
DEFAULT_QUALITY = 85
SUPPORTED_EXTS  = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--size",
        default=f"{DEFAULT_SIZE[0]}x{DEFAULT_SIZE[1]}",
        help="Output size as WxH pixels (default: 400x400)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_QUALITY,
        help="WebP quality 1-100 (default: 85)",
    )
    return parser.parse_args()


def parse_size(size_str: str) -> tuple[int, int]:
    try:
        w, h = size_str.lower().split("x")
        return int(w), int(h)
    except ValueError:
        sys.exit(f"ERROR: Invalid --size value '{size_str}'. Use format WxH, e.g. 400x400")


def load_word_map(word_list_path: Path) -> dict[str, str]:
    """Return {english_keyword: final_filename} parsed from the word list.

    Each line format:
        v1_c1_l1_w1_book.webp  |  Arabic: كتاب  |  English: book
    Multi-word English values like "watch, clock, hour" register each
    comma-separated word as a separate key pointing to the same filename.
    """
    mapping: dict[str, str] = {}
    text = word_list_path.read_text(encoding="utf-16")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        filename = parts[0].strip()          # e.g. v1_c1_l1_w1_book.webp
        english_raw = parts[2].strip()       # e.g. English: book
        if not english_raw.lower().startswith("english:"):
            continue
        english_value = english_raw[len("English:"):].strip()
        for word in english_value.split(","):
            key = word.strip().lower()
            if key:
                mapping[key] = filename
    return mapping


def to_rgb(img: Image.Image) -> Image.Image:
    """Convert any image mode to RGB, compositing over white for transparency."""
    if img.mode == "RGB":
        return img
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    return img.convert("RGB")


def resize_crop_centre(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale image to fill `size` exactly, centre-cropping any overflow."""
    target_w, target_h = size
    orig_w, orig_h = img.size
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = round(orig_w * scale)
    new_h = round(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def process_image(
    src: Path,
    dest_filename: str,
    out_dir: Path,
    done_dir: Path,
    size: tuple[int, int],
    quality: int,
) -> None:
    dest = out_dir / dest_filename
    with Image.open(src) as img:
        img.load()          # force full decode before closing file
        img = to_rgb(img)
        img = resize_crop_centre(img, size)
        img.save(dest, "WEBP", quality=quality, method=6)
    done_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), done_dir / src.name)
    print(f"  ✓  {src.name}  →  {dest_filename}  ({size[0]}x{size[1]}, q{quality})")


def main() -> None:
    args = parse_args()
    size = parse_size(args.size)
    quality = max(1, min(100, args.quality))

    # ── Validate paths ────────────────────────────────────────────────────────
    if not WORD_LIST.exists():
        sys.exit(f"ERROR: Word list not found: {WORD_LIST}")
    if not NEW_DIR.exists():
        sys.exit(f"ERROR: Source directory not found: {NEW_DIR}")

    # ── Build keyword → filename map ──────────────────────────────────────────
    word_map = load_word_map(WORD_LIST)
    print(f"Loaded {len(word_map)} English keyword(s) from word list.")
    print(f"Output size: {size[0]}x{size[1]} px  |  WebP quality: {quality}\n")

    # ── Find candidate images ─────────────────────────────────────────────────
    image_files = sorted(
        f for f in NEW_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
    )

    if not image_files:
        print(f"No supported image files found in {NEW_DIR}")
        print(f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTS))}")
        return

    print(f"Found {len(image_files)} image(s) in images/new/\n")

    # ── Process each image ────────────────────────────────────────────────────
    matched = 0
    skipped: list[str] = []

    for img_path in image_files:
        keyword = img_path.stem.lower()  # "book" from "book.jpg"
        if keyword in word_map:
            try:
                process_image(img_path, word_map[keyword], OUT_DIR, DONE_DIR, size, quality)
                matched += 1
            except Exception as exc:
                print(f"  ✗  {img_path.name}  →  ERROR: {exc}")
                skipped.append(img_path.name)
        else:
            print(f"  ✗  {img_path.name}  →  no match for keyword '{keyword}' in word list")
            skipped.append(img_path.name)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print(f"Processed : {matched}")
    print(f"Skipped   : {len(skipped)}")
    if skipped:
        print(f"  Files   : {', '.join(skipped)}")


if __name__ == "__main__":
    main()
