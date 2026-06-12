/**
 * copy-backend.cjs — Copies Python backend files into the frontend build
 * so electron-builder can include them as extraResources.
 *
 * Usage: node scripts/copy-backend.cjs
 *
 * This script:
 *   1. Copies ../backend -> electron/backend (excluding __pycache__)
 *   2. Copies ../parsers -> electron/parsers (excluding __pycache__)
 *   3. Copies ../core -> electron/core (excluding __pycache__)
 *   4. Copies ../requirements.txt -> electron/requirements.txt
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const PROJECT_ROOT = path.resolve(ROOT, "..");

const COPY_MAP = [
  { from: path.join(PROJECT_ROOT, "backend"), to: path.join(ROOT, "electron", "backend") },
  { from: path.join(PROJECT_ROOT, "parsers"), to: path.join(ROOT, "electron", "parsers") },
  { from: path.join(PROJECT_ROOT, "core"), to: path.join(ROOT, "electron", "core") },
  { from: path.join(PROJECT_ROOT, "fireai"), to: path.join(ROOT, "electron", "fireai") },
  { from: path.join(PROJECT_ROOT, "requirements.txt"), to: path.join(ROOT, "electron", "requirements.txt") },
];

function copyRecursive(src, dest) {
  if (!fs.existsSync(src)) {
    console.warn(`[copy-backend] WARNING: source not found: ${src}`);
    return;
  }

  if (fs.statSync(src).isDirectory()) {
    if (path.basename(src) === "__pycache__") return;
    if (path.basename(dest) === "__pycache__") return;

    fs.mkdirSync(dest, { recursive: true });
    const entries = fs.readdirSync(src);
    for (const entry of entries) {
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
  } else {
    if (src.endsWith(".pyc")) return;
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(src, dest);
    console.log(`[copy-backend] ${src} -> ${dest}`);
  }
}

for (const { from, to } of COPY_MAP) {
  copyRecursive(from, to);
}

console.log("[copy-backend] Done.");
