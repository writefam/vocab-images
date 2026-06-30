# Vocabulary Image Fetcher — Operator Guide

Run `scripts/fetch_images.py` on demand to build the flashcard image library in batches.  
Images are saved as 400×400 WebP files in `images/`, named `{wordId}_{english_slug}.webp`.  
After each batch you tag a new version and the app picks it up automatically via jsDelivr CDN.

---

## One-Time Setup

### 1 — Install Python dependencies

```powershell
cd c:\vocab-images
pip install -r requirements.txt
```

Already have Pillow and requests? Only two new ones needed:
```powershell
pip install python-dotenv pymongo
```

### 2 — Create `.env`

```powershell
Copy-Item .env.example .env
```

Edit `.env` and add your Unsplash key (free, takes 30 seconds):

```
UNSPLASH_ACCESS_KEY=your_key_here
```

Get a key at **https://unsplash.com/developers** → "New Application" → copy "Access Key".  
Free tier: **5 000 requests / hour** — enough to fetch ~5 000 images per hour unattended.

---

## Running a Batch

All commands are run from `c:\vocab-images\` (or any directory — paths are relative to the script).

### Fastest method — word-list file (no DB needed)

`needed-images-part1.txt` already exists in the repo and lists every word that needs an image for Part 1.

```powershell
# Fetch first 20 images
python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 20

# Fetch next 20 (resume)
python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 20 --offset 20

# Fetch next 20
python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 20 --offset 40
```

The script prints the exact resume command at the end of every run — just copy-paste it.

### From MongoDB (live data)

Reads the `vocabulary_set` collection directly. Docker must be running.

```powershell
# All words from any set matching "At-Tareeqatul"
python scripts/fetch_images.py --from-mongo --set-name "At-Tareeqatul" --limit 20

# Second batch
python scripts/fetch_images.py --from-mongo --set-name "At-Tareeqatul" --limit 20 --offset 20

# List all available sets (no matches = shows list)
python scripts/fetch_images.py --from-mongo --set-name "NOMATCH" --limit 1
```

### From vocab JSON (offline, no DB)

```powershell
# Volume 1 only, first 20 words
python scripts/fetch_images.py --from-json --volume 1 --limit 20

# All volumes, offset 100
python scripts/fetch_images.py --from-json --limit 50 --offset 100
```

### Dry run — preview without downloading

```powershell
python scripts/fetch_images.py --word-list needed-images-part1.txt --limit 10 --dry-run
```

---

## Batch Strategy

The word list has ~600+ words for Part 1. Recommended workflow:

| Session | Command |
|---------|---------|
| Session 1 | `--limit 50 --offset 0` |
| Session 2 | `--limit 50 --offset 50` |
| Session 3 | `--limit 50 --offset 100` |
| … | … |

The script automatically skips words that already have an image — safe to re-run the same offset.  
Use `--overwrite` to re-fetch a word even if an image exists.

### Which words to prioritize

Concrete nouns have the best images (book, chair, door, car).  
Abstract words (this, that, new, old) and grammatical particles have no useful image — the app falls back to English text for those automatically, so there's no rush to image them.

---

## After a Batch — Publish to CDN

Once you've fetched a satisfying batch:

```powershell
# 1. Regenerate manifest (pick next semver)
node scripts/generate-manifest.js --version 1.0.0

# 2. Commit
git add images/ manifest.json
git commit -m "Add image batch: lessons 1-3 (50 images)"

# 3. Tag and push
git tag v1.0.0
git push origin main --tags
```

jsDelivr caches by tag. The app fetches the manifest from `raw.githubusercontent.com/main` (uncached),  
reads the version from it, and builds CDN URLs pinned to that tag. New images are live within ~1 minute.

---

## Script Reference

```
python scripts/fetch_images.py [source] [options]
```

### Sources (pick one)

| Flag | Description |
|------|-------------|
| `--word-list FILE` | Parse a word-list .txt file (fastest, recommended) |
| `--from-mongo` | Query MongoDB vocabulary_set collection |
| `--from-json` | Read from At-Tareeqatul-Arabia-Vocab.json (offline) |

### Filters

| Flag | Default | Description |
|------|---------|-------------|
| `--set-name NAME` | (all) | Vocab set name regex for `--from-mongo` |
| `--volume N` | (all) | Volume number for `--from-json` |
| `--vocab-json PATH` | auto | Custom path to vocab JSON |

### Batch control

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | 20 | Max images to fetch in this run |
| `--offset N` | 0 | Skip first N words (for resuming) |
| `--overwrite` | false | Re-fetch even if image already exists |

### Image provider

| Flag | Default | Description |
|------|---------|-------------|
| `--source unsplash\|pexels` | unsplash | Which API to use |
| `--delay SECONDS` | 0.6 | Pause between API calls |

### Behavior

| Flag | Description |
|------|-------------|
| `--dry-run` | Print what would be fetched, no downloads |

---

## Image Spec

| Property | Value |
|----------|-------|
| Format | WebP |
| Dimensions | 400 × 400 px (square) |
| Max file size | 80 KB (re-encoded at lower quality if needed) |
| Crop | Center square crop before resize |
| Naming | `{wordId}_{english_slug}.webp` |

---

## Environment Variables

Set in `c:\vocab-images\.env` (copy `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `UNSPLASH_ACCESS_KEY` | Yes (for `--source unsplash`) | [Get free key](https://unsplash.com/developers) |
| `PEXELS_API_KEY` | Yes (for `--source pexels`) | [Get free key](https://www.pexels.com/api/) |
| `DATABASE_URL` | Yes (for `--from-mongo`) | Same as tamreen-ai `DATABASE_URL` |

---

## Troubleshooting

**"UNSPLASH_ACCESS_KEY not set"**  
→ Create `c:\vocab-images\.env`, add `UNSPLASH_ACCESS_KEY=your_key_here`

**"No vocabulary sets found"**  
→ Docker must be running: `docker-compose -f c:\tamreen-ai\docker-compose.dev.yml up -d`  
→ Check set name spelling (case-insensitive regex match)

**"Vocab JSON not found"**  
→ Use `--vocab-json "c:\tamreen-ai\Vocabulary\At-Tareeqatul-Arabia-Vocab.json"` explicitly

**Images look wrong / stretched**  
→ Script does center-square crop then resize — should be fine for most photos.  
→ Manually replace any poor result: save a better `{wordId}_{slug}.webp` over it.

**Rate limit hit (Unsplash 403)**  
→ Unsplash free tier: 5 000/hr. If you hit it, wait an hour or get a second free key.

**VS Code doesn't show `vocab-images` folder**  
→ Open the workspace file directly: `File → Open Workspace from File → c:\tamreen-ai\tamreen-ai.code-workspace`  
→ This shows tamreen-ai, At-tareeq-text, and vocab-images side by side.
