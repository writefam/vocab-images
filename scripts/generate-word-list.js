#!/usr/bin/env node
/**
 * generate-word-list.js
 *
 * Reads At-Tareeqatul Arabiyya vocab JSON (from tamreen-ai repo) and outputs
 * the expected image filenames for all words, so you know what images to source.
 *
 * Usage:
 *   node scripts/generate-word-list.js                   # all volumes
 *   node scripts/generate-word-list.js --volume 1        # volume 1 only
 *   node scripts/generate-word-list.js --volume 1 > needed-images.txt
 *
 * Output format (one line per word):
 *   {wordId}_{english_slug}.webp  |  Arabic: {arabic}  |  English: {english}
 *
 * wordId format: v{volumeIdx}_c{chapterIdx}_l{lessonIdx}_w{wordId}
 *
 * Vocab JSON location (relative to this script):
 *   ../../tamreen-ai/Vocabulary/At-Tareeqatul-Arabia-Vocab.json
 *
 * Override with: VOCAB_JSON_PATH=/path/to/vocab.json node scripts/generate-word-list.js
 */

const fs = require('fs');
const path = require('path');

// ── Helpers ───────────────────────────────────────────────────────────────────
function slugify(str) {
  return str.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
}

function buildWordId(volumeIdx, chapterIdx, lessonIdx, wordId) {
  return `v${volumeIdx}_c${chapterIdx}_l${lessonIdx}_w${wordId}`;
}

// ── Args ──────────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const volIdx = args.indexOf('--volume');
const filterVolume = volIdx !== -1 ? parseInt(args[volIdx + 1], 10) : null;

if (filterVolume !== null && isNaN(filterVolume)) {
  console.error('--volume must be a number');
  process.exit(1);
}

// ── Load vocab JSON ───────────────────────────────────────────────────────────
const vocabJsonPath =
  process.env.VOCAB_JSON_PATH ||
  path.resolve(__dirname, '../../tamreen-ai/Vocabulary/At-Tareeqatul-Arabia-Vocab.json');

if (!fs.existsSync(vocabJsonPath)) {
  console.error(`Vocab JSON not found at: ${vocabJsonPath}`);
  console.error('Set VOCAB_JSON_PATH env var to override the path.');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(vocabJsonPath, 'utf8'));

// ── Generate list ─────────────────────────────────────────────────────────────
let totalWords = 0;

for (const volume of data.volumes) {
  if (filterVolume !== null && volume.index !== filterVolume) continue;

  for (const chapter of volume.chapters) {
    for (const lesson of chapter.lessons) {
      for (const word of lesson.words) {
        const wordId = buildWordId(volume.index, chapter.index, lesson.index, word.id);
        // Some words have multiple Arabic forms — use the first
        const arabic = Array.isArray(word.words) ? word.words[0] : word.words;
        const slug = slugify(word.english);
        const filename = `${wordId}_${slug}.webp`;

        console.log(`${filename}  |  Arabic: ${arabic}  |  English: ${word.english}`);
        totalWords++;
      }
    }
  }
}

console.error(`\nTotal: ${totalWords} words`);
if (filterVolume !== null) {
  console.error(`(filtered to volume ${filterVolume})`);
}
