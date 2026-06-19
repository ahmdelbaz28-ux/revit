#!/usr/bin/env bash
# Synchronize FireAI agent rules to all AI-agent adapter files.
# Each adapter file is a copy of AGENTS.md body (with appropriate frontmatter
# for hosts that require it). Run after editing AGENTS.md.
# Drift is caught by scripts/check-rule-copies.js in CI.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/AGENTS.md"

if [[ ! -f "$SRC" ]]; then
  echo "ERROR: AGENTS.md not found at $SRC" >&2
  exit 1
fi

BODY=$(sed '/^---$/,$d' "$SRC" | sed -e '1,/^[^#]/d' )
# Actually: just copy everything after any leading frontmatter. AGENTS.md has
# no frontmatter, so use it verbatim.
BODY=$(cat "$SRC")

# Strip the trailing ponytail signature line (not load-bearing, kept only in
# AGENTS.md). check-rule-copies.js enforces this.
BODY=$(printf '%s\n' "$BODY" | sed '/^(Yes, this file also applies/,/)$/d' | sed -e :a -e '/^\n*$/{$d;N;ba}' -)

# .windsurf/rules/ponytail.md — verbatim
mkdir -p "$REPO_ROOT/.windsurf/rules"
printf '%s\n' "$BODY" > "$REPO_ROOT/.windsurf/rules/ponytail.md"

# .clinerules/ponytail.md — verbatim
mkdir -p "$REPO_ROOT/.clinerules"
printf '%s\n' "$BODY" > "$REPO_ROOT/.clinerules/ponytail.md"

# .agents/rules/ponytail.md — verbatim
mkdir -p "$REPO_ROOT/.agents/rules"
printf '%s\n' "$BODY" > "$REPO_ROOT/.agents/rules/ponytail.md"

# .github/copilot-instructions.md — verbatim
mkdir -p "$REPO_ROOT/.github"
printf '%s\n' "$BODY" > "$REPO_ROOT/.github/copilot-instructions.md"

# .kiro/steering/ponytail.md — verbatim
mkdir -p "$REPO_ROOT/.kiro/steering"
printf '%s\n' "$BODY" > "$REPO_ROOT/.kiro/steering/ponytail.md"

# .cursor/rules/ponytail.mdc — frontmatter + body (Cursor requires frontmatter)
mkdir -p "$REPO_ROOT/.cursor/rules"
cat > "$REPO_ROOT/.cursor/rules/ponytail.mdc" <<'FRONTMATTER'
---
description: FireAI hybrid rules — safety-critical (Rule 17) for regulated paths, ponytail ladder for everything else
alwaysApply: true
---

FRONTMATTER
printf '%s\n' "$BODY" >> "$REPO_ROOT/.cursor/rules/ponytail.mdc"

echo "Synchronized FireAI agent rules to 6 adapter files."
echo "  - .windsurf/rules/ponytail.md"
echo "  - .clinerules/ponytail.md"
echo "  - .agents/rules/ponytail.md"
echo "  - .github/copilot-instructions.md"
echo "  - .kiro/steering/ponytail.md"
echo "  - .cursor/rules/ponytail.mdc (with Cursor frontmatter)"
