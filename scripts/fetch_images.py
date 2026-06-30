#!/usr/bin/env python3
"""
fetch_images.py — Vocabulary flashcard image fetcher for tamreen-ai/vocab-images

Fetches images from Unsplash (primary) or Pexels for Arabic vocabulary words,
crops them to a square, resizes to 400×400, and saves as WebP.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUICK START
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Install dependencies (once):
     pip install -r requirements.txt

2. Create .env in the vocab-images root (copy from .env.example):
     UNSPLASH_ACCESS_KEY=your_key_here   ← free at https://unsplash.com/developers

3. Run a batch (20 images starting from the top of the word list):
     python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 20

4. Run next batch (resume where you left off):
     python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 20 --offset 20

5. Preview without downloading:
     python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 10 --dry-run

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALL USAGE MODES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# From the word-list .txt file (fastest, no DB needed)
python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 20
python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 20 --offset 40

# From MongoDB (reads live vocabulary_set collection)
python scripts/fetch_images.py --from-mongo --set-name "At-Tareeqatul" --limit 20

# From vocab JSON directly (no DB, offline)
python scripts/fetch_images.py --from-json --volume 1 --limit 20
python scripts/fetch_images.py --from-json --limit 50   # all volumes

# Dry run — print what would be fetched, no API calls
python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 10 --dry-run

# Use Pexels instead of Unsplash
python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 20 --source pexels

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AFTER DOWNLOADING — PUBLISH TO CDN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  node scripts/generate-manifest.js --version X.Y.Z
  git add images/ manifest.json
  git commit -m "Add batch X: lessons ..."
  git tag vX.Y.Z && git push --tags

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import json
import re
import time
import argparse
from pathlib import Path
from io import BytesIO
from typing import Optional

# Third-party — install via: pip install -r requirements.txt
try:
    import requests
    from PIL import Image
except ImportError as e:
    print(f"\nMissing dependency: {e}")
    print("Run:  pip install -r requirements.txt")
    sys.exit(1)

# dotenv is optional — env vars can also be set in the shell
try:
    from dotenv import load_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
REPO_ROOT   = SCRIPT_DIR.parent
IMAGES_DIR  = REPO_ROOT / "images"
MANIFEST    = REPO_ROOT / "manifest.json"

DEFAULT_VOCAB_JSON = REPO_ROOT / "../tamreen-ai/Vocabulary/At-Tareeqatul-Arabia-Vocab.json"

# ── Image constants ───────────────────────────────────────────────────────────
IMAGE_SIZE   = (400, 400)   # final square dimensions
MAX_BYTES    = 80 * 1024    # 80 KB soft cap — re-encode at lower quality if exceeded
MIN_QUALITY  = 50           # never go below this WebP quality

# ── API endpoints ─────────────────────────────────────────────────────────────
UNSPLASH_BASE = "https://api.unsplash.com"
PEXELS_BASE   = "https://api.pexels.com/v1"


# ╔══════════════════════════════════════════════════════════════╗
# ║  HELPERS                                                     ║
# ╚══════════════════════════════════════════════════════════════╝

def slugify(text: str) -> str:
    """Convert an English phrase to a lowercase URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[''`\u2018\u2019\u201b]", "", text)   # strip apostrophes
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def expected_filename(word_id: str, english: str) -> str:
    """Build the canonical filename: {wordId}_{slug}.webp"""
    primary = english.split(",")[0].strip()   # first variant when multi-word
    return f"{word_id}_{slugify(primary)}.webp"


def image_already_exists(word_id: str) -> Optional[Path]:
    """Return path if ANY file already exists for this wordId prefix."""
    prefix = word_id + "_"
    for f in IMAGES_DIR.iterdir():
        if f.name.startswith(prefix) and f.suffix.lower() in {".webp", ".jpg", ".jpeg", ".png"}:
            return f
    return None


# ── manifest helpers ──────────────────────────────────────────
def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"version": "0.0.0", "updatedAt": "", "wordIds": []}


def add_to_manifest(word_id: str):
    """Add wordId to manifest.json if not already present."""
    manifest = load_manifest()
    if word_id not in manifest["wordIds"]:
        from datetime import date
        manifest["wordIds"].append(word_id)
        manifest["wordIds"].sort()
        manifest["updatedAt"] = str(date.today())
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


# ╔══════════════════════════════════════════════════════════════╗
# ║  IMAGE PROCESSING                                            ║
# ╚══════════════════════════════════════════════════════════════╝

def download_and_save(url: str, dest: Path, word_id: str) -> bool:
    """
    Download from URL, center-crop to square, resize to 400×400,
    save as WebP. Returns True on success.
    """
    try:
        resp = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "tamreen-ai-vocab-fetcher/1.0"},
            stream=True
        )
        resp.raise_for_status()

        img = Image.open(BytesIO(resp.content)).convert("RGB")

        # Center-square crop
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top  = (h - side) // 2
        img  = img.crop((left, top, left + side, top + side))

        # Resize to target dimensions
        img = img.resize(IMAGE_SIZE, Image.LANCZOS)

        # Save as WebP; reduce quality if over size limit
        quality = 85
        buf = BytesIO()
        while quality >= MIN_QUALITY:
            buf = BytesIO()
            img.save(buf, format="WEBP", quality=quality, method=6)
            if buf.tell() <= MAX_BYTES:
                break
            quality -= 10

        dest.write_bytes(buf.getvalue())
        add_to_manifest(word_id)
        return True

    except Exception as e:
        print(f"    ✗  Download/process error: {e}")
        return False


# ╔══════════════════════════════════════════════════════════════╗
# ║  IMAGE SEARCH PROVIDERS                                      ║
# ╚══════════════════════════════════════════════════════════════╝

def search_unsplash(query: str, access_key: str) -> Optional[str]:
    """
    Return an image URL from Unsplash.
    Free tier: 5 000 requests/hour with API key.
    Get a free key: https://unsplash.com/developers
    """
    try:
        resp = requests.get(
            f"{UNSPLASH_BASE}/photos/random",
            params={
                "query": query,
                "orientation": "squarish",
                "content_filter": "high",
            },
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Unsplash API requirement: trigger download event
            dl_location = data.get("links", {}).get("download_location")
            if dl_location:
                try:
                    requests.get(
                        dl_location,
                        headers={"Authorization": f"Client-ID {access_key}"},
                        timeout=10,
                    )
                except Exception:
                    pass
            # "regular" is ~1080px wide — we resize to 400 locally
            return data.get("urls", {}).get("regular")
        elif resp.status_code == 403:
            print("    ✗  Unsplash: rate limit reached. Wait an hour or use a different key.")
        elif resp.status_code == 401:
            print("    ✗  Unsplash: invalid API key. Check UNSPLASH_ACCESS_KEY.")
    except Exception as e:
        print(f"    ✗  Unsplash error: {e}")
    return None


def search_pexels(query: str, api_key: str) -> Optional[str]:
    """
    Return an image URL from Pexels.
    Free tier: 200 requests/hour with API key.
    Get a free key: https://www.pexels.com/api/
    """
    try:
        resp = requests.get(
            f"{PEXELS_BASE}/search",
            params={"query": query, "per_page": 1, "size": "medium"},
            headers={"Authorization": api_key},
            timeout=15,
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            if photos:
                return photos[0]["src"].get("large")   # ~1280×853
        elif resp.status_code == 403:
            print("    ✗  Pexels: rate limit or invalid key. Check PEXELS_API_KEY.")
    except Exception as e:
        print(f"    ✗  Pexels error: {e}")
    return None


# ╔══════════════════════════════════════════════════════════════╗
# ║  WORD SOURCES                                                ║
# ╚══════════════════════════════════════════════════════════════╝

def words_from_word_list_file(filepath: Path, offset: int, limit: int) -> list[dict]:
    """
    Parse a word-list .txt file produced by generate-word-list.js.
    Format per line:
      {filename}.webp  |  Arabic: {arabic}  |  English: {english}
    """
    raw = filepath.read_bytes()
    # Detect BOM / encoding
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8", errors="replace")

    words = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue

        filename_part = parts[0]             # e.g. v1_c1_l1_w1_book.webp
        arabic_part   = parts[1]             # e.g. Arabic: كتاب
        english_part  = parts[2]             # e.g. English: book

        m = re.match(r"(v\d+_c\d+_l\d+_w\d+)", filename_part)
        if not m:
            continue

        words.append({
            "wordId":  m.group(1),
            "english": english_part.replace("English:", "").strip(),
            "arabic":  arabic_part.replace("Arabic:", "").strip(),
        })

    return words[offset : offset + limit]


def words_from_vocab_json(json_path: Path, volume_filter: Optional[int],
                          offset: int, limit: int) -> list[dict]:
    """
    Read words from At-Tareeqatul-Arabia-Vocab.json.
    Structure: { volumes: [ { index, chapters: [ { index, lessons: [ { index, words: [{id, words[], english, ...}] } ] } ] } ] }
    """
    if not json_path.exists():
        print(f"Vocab JSON not found: {json_path}")
        print("Set --vocab-json to the correct path, or use --word-list instead.")
        sys.exit(1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    all_words = []

    for vol in data.get("volumes", []):
        vol_idx = vol.get("index", 1)
        if volume_filter and vol_idx != volume_filter:
            continue
        for ch in vol.get("chapters", []):
            ch_idx = ch.get("index", 1)
            for ls in ch.get("lessons", []):
                ls_idx = ls.get("index", 1)
                for w in ls.get("words", []):
                    word_id = f"v{vol_idx}_c{ch_idx}_l{ls_idx}_w{w['id']}"
                    arabic_forms = w.get("words", [])
                    arabic = arabic_forms[0] if arabic_forms else ""
                    all_words.append({
                        "wordId":  word_id,
                        "english": w.get("english", ""),
                        "arabic":  arabic,
                    })

    return all_words[offset : offset + limit]


def words_from_mongo(set_name: str, offset: int, limit: int) -> list[dict]:
    """
    Query MongoDB vocabulary_set collection.
    Uses DATABASE_URL env var (same as tamreen-ai app).
    """
    try:
        import pymongo
    except ImportError:
        print("pymongo not installed. Run:  pip install pymongo")
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL env var not set.")
        print("  Add to .env:  DATABASE_URL=mongodb://admin:password@localhost:27017/tamreen?authSource=admin")
        sys.exit(1)

    try:
        client = pymongo.MongoClient(db_url, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")   # verify connection
    except Exception as e:
        print(f"ERROR: Cannot connect to MongoDB: {e}")
        sys.exit(1)

    # Extract database name from connection string
    db_name = db_url.rsplit("/", 1)[-1].split("?")[0] or "tamreen"
    db = client[db_name]

    # Build query
    query: dict = {}
    if set_name:
        query["name"] = {"$regex": set_name, "$options": "i"}

    vocab_sets = list(db.vocabularysets.find(query))
    if not vocab_sets:
        print(f"No vocabulary sets found matching: '{set_name}'")
        available = list(db.vocabularysets.find({}, {"name": 1}))
        if available:
            print("Available sets:")
            for s in available:
                print(f"  - {s['name']}")
        else:
            print("  (vocabulary_set collection is empty)")
        client.close()
        sys.exit(1)

    all_words = []
    for vset in vocab_sets:
        print(f"  Set: {vset['name']}  ({len(vset.get('subsets', []))} subsets)")
        for subset in vset.get("subsets", []):
            for word in subset.get("words", []):
                all_words.append({
                    "wordId":  word["wordId"],
                    "english": word.get("english", ""),
                    "arabic":  word.get("arabic", ""),
                    "subset":  subset.get("name", ""),
                })

    client.close()
    return all_words[offset : offset + limit]


# ╔══════════════════════════════════════════════════════════════╗
# ║  MAIN                                                        ║
# ╚══════════════════════════════════════════════════════════════╝

def main():
    # Load .env from vocab-images root, then fall back to tamreen-ai .env.local
    if _HAS_DOTENV:
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / "../tamreen-ai/apps/web/.env.local")

    parser = argparse.ArgumentParser(
        description="Fetch vocabulary flashcard images from Unsplash or Pexels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Source (mutually exclusive) ──────────────────────────────
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--word-list", metavar="FILE",
        help="Word list .txt file produced by generate-word-list.js "
             "(e.g. needed-images-part1.txt). Fastest — no DB needed."
    )
    src.add_argument(
        "--from-mongo", action="store_true",
        help="Read words from MongoDB vocabulary_set collection (requires DATABASE_URL)."
    )
    src.add_argument(
        "--from-json", action="store_true",
        help="Read words from At-Tareeqatul-Arabia-Vocab.json directly (offline)."
    )

    # ── Filters ──────────────────────────────────────────────────
    parser.add_argument(
        "--set-name", default="",
        metavar="NAME",
        help="Vocabulary set name filter for --from-mongo (e.g. 'At-Tareeqatul')."
    )
    parser.add_argument(
        "--volume", type=int, default=None,
        help="Volume number filter for --from-json (e.g. 1). Omit to include all."
    )
    parser.add_argument(
        "--vocab-json", metavar="PATH", default=None,
        help=f"Path to vocab JSON (default: {DEFAULT_VOCAB_JSON})."
    )

    # ── Batch control ─────────────────────────────────────────────
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Max images to fetch in this run (default: 20)."
    )
    parser.add_argument(
        "--offset", type=int, default=0,
        help="Skip this many words from the start — use to resume a batch "
             "(e.g. --offset 20 --limit 20 for the second batch)."
    )

    # ── Image provider ─────────────────────────────────────────────
    parser.add_argument(
        "--source", choices=["unsplash", "pexels"], default="unsplash",
        help="Image provider (default: unsplash). "
             "Set UNSPLASH_ACCESS_KEY or PEXELS_API_KEY in .env."
    )

    # ── Behavior flags ─────────────────────────────────────────────
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be fetched without making any API calls."
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Re-fetch images even if a file already exists (default: skip existing)."
    )
    parser.add_argument(
        "--delay", type=float, default=0.6,
        help="Seconds to wait between API requests (default: 0.6)."
    )

    args = parser.parse_args()

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load words ────────────────────────────────────────────────
    prefix = "DRY RUN — " if args.dry_run else ""
    print(f"\n{prefix}Loading words…")

    if args.word_list:
        wl = Path(args.word_list)
        if not wl.is_absolute():
            # Try relative to repo root first, then cwd
            if (REPO_ROOT / wl).exists():
                wl = REPO_ROOT / wl
        words = words_from_word_list_file(wl, args.offset, args.limit)
        print(f"  Source : word list  →  {wl.name}")

    elif args.from_mongo:
        words = words_from_mongo(args.set_name, args.offset, args.limit)
        print(f"  Source : MongoDB  (set: '{args.set_name}')")

    else:  # --from-json
        json_path = Path(args.vocab_json) if args.vocab_json else DEFAULT_VOCAB_JSON
        words = words_from_vocab_json(json_path, args.volume, args.offset, args.limit)
        print(f"  Source : vocab JSON  →  {json_path.name}  (volume: {args.volume or 'all'})")

    print(f"  Offset : {args.offset}")
    print(f"  Limit  : {args.limit}  →  {len(words)} words to process\n")

    if not words:
        print("No words found. Check --offset / source.")
        sys.exit(0)

    # ── API key check ─────────────────────────────────────────────
    unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    pexels_key   = os.environ.get("PEXELS_API_KEY", "")

    if not args.dry_run:
        if args.source == "unsplash" and not unsplash_key:
            print("ERROR: UNSPLASH_ACCESS_KEY not set.")
            print("  Get a free key: https://unsplash.com/developers  (5 000 req/hr)")
            print("  Then add to c:\\vocab-images\\.env:")
            print("    UNSPLASH_ACCESS_KEY=your_key_here\n")
            sys.exit(1)
        if args.source == "pexels" and not pexels_key:
            print("ERROR: PEXELS_API_KEY not set.")
            print("  Get a free key: https://www.pexels.com/api/  (200 req/hr)")
            print("  Then add to c:\\vocab-images\\.env:")
            print("    PEXELS_API_KEY=your_key_here\n")
            sys.exit(1)

    # ── Process ───────────────────────────────────────────────────
    fetched = skipped = failed = 0
    separator = "─" * 56

    for word in words:
        word_id = word["wordId"]
        english = word["english"]
        arabic  = word.get("arabic", "")
        dest    = IMAGES_DIR / expected_filename(word_id, english)

        # Skip existing
        existing = image_already_exists(word_id)
        if existing and not args.overwrite:
            print(f"  SKIP    {word_id:<22}  ({english})  →  already have {existing.name}")
            skipped += 1
            continue

        label = arabic or english
        print(f"  FETCH   {word_id:<22}  {label}  →  {english}")

        if args.dry_run:
            print(f"           would save: {dest.name}")
            fetched += 1
            continue

        # Search
        query = english.split(",")[0].strip()
        image_url: Optional[str] = None

        if args.source == "unsplash":
            image_url = search_unsplash(query, unsplash_key)
        else:
            image_url = search_pexels(query, pexels_key)

        if not image_url:
            print(f"           ✗  No result for '{query}'")
            failed += 1
        else:
            ok = download_and_save(image_url, dest, word_id)
            if ok:
                kb = dest.stat().st_size / 1024
                print(f"           ✓  {dest.name}  ({kb:.0f} KB)")
                fetched += 1
            else:
                failed += 1

        time.sleep(args.delay)

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{separator}")
    print(f"  Fetched : {fetched}")
    print(f"  Skipped : {skipped}  (already existed)")
    print(f"  Failed  : {failed}")
    print(f"  Images  : {IMAGES_DIR}")

    if not args.dry_run and fetched > 0:
        manifest = load_manifest()
        total = len(manifest["wordIds"])
        print(f"  Manifest: {total} word(s) indexed  (version {manifest['version']})")

    next_offset = args.offset + len(words)
    skipped_count = sum(1 for w in words if image_already_exists(w["wordId"]) and not args.overwrite)
    if args.word_list and not args.dry_run:
        print(f"\n  Resume next batch:")
        if args.word_list:
            print(f"    python scripts/fetch_images.py --word-list {Path(args.word_list).name} "
                  f"--limit {args.limit} --offset {next_offset}")

    if not args.dry_run and fetched > 0:
        print(f"\n  Publish when ready:")
        print(f"    node scripts/generate-manifest.js --version X.Y.Z")
        print(f"    git add images/ manifest.json")
        print(f"    git commit -m 'Add image batch (offset {args.offset}-{next_offset - 1})'")
        print(f"    git tag vX.Y.Z && git push --tags")

    print(f"{separator}\n")


if __name__ == "__main__":
    main()
