#!/usr/bin/env node
/**
 * generate-manifest.js
 *
 * Scans images/ directory, extracts wordIds from filenames,
 * writes manifest.json.
 *
 * Usage:
 *   node scripts/generate-manifest.js --version 1.0.0
 *
 * Filename format expected: {wordId}_{english_slug}.{ext}
 *   e.g. v1_c1_l1_w1_book.webp  →  wordId = v1_c1_l1_w1
 */

const fs = require('fs');
const path = require('path');

// ── Parse args ────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const versionIdx = args.indexOf('--version');
if (versionIdx === -1 || !args[versionIdx + 1]) {
  console.error('Usage: node scripts/generate-manifest.js --version <semver>');
  console.error('Example: node scripts/generate-manifest.js --version 1.0.0');
  process.exit(1);
}
const version = args[versionIdx + 1];
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  console.error(`Invalid version "${version}". Must be semver format: X.Y.Z`);
  process.exit(1);
}

// ── Paths ─────────────────────────────────────────────────────────────────────
const repoRoot = path.resolve(__dirname, '..');
const imagesDir = path.join(repoRoot, 'images');
const manifestPath = path.join(repoRoot, 'manifest.json');

// ── Read images dir ───────────────────────────────────────────────────────────
if (!fs.existsSync(imagesDir)) {
  console.error(`images/ directory not found at ${imagesDir}`);
  process.exit(1);
}

const SUPPORTED_EXTS = new Set(['.webp', '.jpg', '.jpeg', '.png']);
const WORD_ID_PATTERN = /^(v\d+_c\d+_l\d+_w\d+)_.+/;

const files = fs.readdirSync(imagesDir).filter(f => {
  const ext = path.extname(f).toLowerCase();
  return SUPPORTED_EXTS.has(ext) && !f.startsWith('.');
});

const wordIdSet = new Set();
const skipped = [];

for (const file of files) {
  const basename = path.basename(file, path.extname(file));
  const match = basename.match(WORD_ID_PATTERN);
  if (match) {
    wordIdSet.add(match[1]);
  } else {
    skipped.push(file);
  }
}

// Warn about files that don't match naming convention
if (skipped.length > 0) {
  console.warn('\nWarning: These files do not match naming convention and were skipped:');
  skipped.forEach(f => console.warn(`  ${f}`));
  console.warn('  Expected format: {wordId}_{english_slug}.webp');
  console.warn('  Example: v1_c1_l1_w1_book.webp\n');
}

// ── Build and write manifest ──────────────────────────────────────────────────
const wordIds = Array.from(wordIdSet).sort();

const manifest = {
  version,
  updatedAt: new Date().toISOString().slice(0, 10), // YYYY-MM-DD
  wordIds,
};

fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n', 'utf8');

// ── Summary ───────────────────────────────────────────────────────────────────
console.log(`✓ manifest.json written`);
console.log(`  version:   ${version}`);
console.log(`  updatedAt: ${manifest.updatedAt}`);
console.log(`  wordIds:   ${wordIds.length} unique IDs from ${files.length} image files`);
if (wordIds.length > 0) {
  console.log(`  first:     ${wordIds[0]}`);
  console.log(`  last:      ${wordIds[wordIds.length - 1]}`);
}
