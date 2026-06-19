#!/usr/bin/env node
// FireAI rule-copy sync checker.
// Adapted from ponytail/scripts/check-rule-copies.js (MIT, DietrichGebert).
//
// Asserts:
//   1. The compact rule body in AGENTS.md is byte-identical to the bodies of
//      .windsurf/rules/ponytail.md, .clinerules/ponytail.md,
//      .agents/rules/ponytail.md, .github/copilot-instructions.md,
//      .kiro/steering/ponytail.md. (.cursor/rules/ponytail.mdc has Cursor
//      frontmatter prepended, so its body is checked separately.)
//   2. The 8 load-bearing rule invariants appear verbatim in BOTH
//      AGENTS.md AND skills/ponytail/SKILL.md.
//
// Run: node scripts/check-rule-copies.js
// Exits 1 on drift, 0 on match. Wire into CI after Phase 1 lands.

const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');

function read(relPath) {
  return fs.readFileSync(path.join(root, relPath), 'utf8').replace(/\r\n/g, '\n').trim();
}

function stripFrontmatter(text) {
  return text.replace(/^---\n[\s\S]*?\n---\n*/, '').trim();
}

const agents = read('AGENTS.md');
// Strip the trailing "(Yes, this file also applies..." line — it's a ponytail
// signature, not load-bearing rule text. Adapter copies may or may not include it.
const canonical = agents.replace(/\n\n\(Yes, this file also applies[\s\S]*?\)$/, '').trim();

// Compact copies: body must match AGENTS.md (after stripping host-specific frontmatter).
const copies = [
  ['.cursor/rules/ponytail.mdc', stripFrontmatter],
  ['.windsurf/rules/ponytail.md', text => text.trim()],
  ['.clinerules/ponytail.md', text => text.trim()],
  ['.agents/rules/ponytail.md', text => text.trim()],
  ['.github/copilot-instructions.md', text => text.trim()],
  ['.kiro/steering/ponytail.md', text => text.trim()],
];

let failed = false;

for (const [relPath, normalize] of copies) {
  let actual;
  try {
    actual = normalize(read(relPath));
  } catch (e) {
    console.error(`${relPath} missing or unreadable: ${e.message}`);
    failed = true;
    continue;
  }
  if (actual !== canonical) {
    console.error(`${relPath} drifted from AGENTS.md`);
    console.error(`  Run: bash scripts/sync-agent-rules.sh`);
    failed = true;
  }
}

// SKILL.md is the runtime source of truth and is longer than the compact body,
// so it cannot be byte-compared. ponytail: canary, not full equality. Assert the
// load-bearing rules survive verbatim in both the source and AGENTS.md. Changing
// a rule's wording trips this, which is the reminder to propagate it everywhere.
// Upgrade path: generate the copies from SKILL.md if this ever misses a real drift.
const INVARIANTS = [
  'naive heuristic',                       // ceiling-comment rule
  'ONE runnable check',                    // test reflex
  'flimsier algorithm',                    // robust-variant rule
  // the four "not lazy about" safety carve-outs: pin each so a reword in either
  // file can't silently drop one. Only validation was pinned before. These are the
  // continuous substrings present in both files ("prevents data loss" because the
  // full "error handling that prevents data loss" wraps a line in SKILL.md).
  'input validation at trust boundaries',
  'prevents data loss',
  'security',
  'accessibility',
  'Lazy code without its check is unfinished', // one-check promoted to headline
];

const skill = read('skills/ponytail/SKILL.md');
const sources = [['skills/ponytail/SKILL.md', skill], ['AGENTS.md', agents]];
for (const phrase of INVARIANTS) {
  for (const [label, text] of sources) {
    if (!text.includes(phrase)) {
      console.error(`${label} is missing rule invariant: "${phrase}"`);
      failed = true;
    }
  }
}

if (failed) {
  console.error('Update the copied rule text, AGENTS.md, or SKILL.md so the shared rules match.');
  process.exit(1);
}

console.log(`Rule copies match AGENTS.md; ${INVARIANTS.length} rule invariants present in SKILL.md and AGENTS.md.`);
