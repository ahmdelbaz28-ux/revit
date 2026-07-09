#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# verify_sync.sh — Verify GitHub ↔ HuggingFace Space sync integrity
#
# Compares the runtime files between the local GitHub working copy and the
# local HF Space working copy. Reports any differences.
#
# Usage:
#   bash scripts/verify_sync.sh
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

GH_REPO="/home/z/my-project/repos/revit"
HF_SPACE="/home/z/my-project/repos/BAZSPARK"

# Runtime paths that MUST be in sync (matches sync-to-hf.yml RUNTIME_PATHS)
RUNTIME_PATHS=(
  "Dockerfile"
  "pyproject.toml"
  "requirements.txt"
  ".dockerignore"
  "adapters"
  "backend"
  "core"
  "facp_system"
  "fireai"
  "frontend"
  "integration"
  "marine"
  "parsers"
  "qomn_conduit"
  "qomn_fire"
)

# rsync exclude patterns (must match sync-to-hf.yml)
EXCLUDES=(
  --exclude='node_modules/'
  --exclude='__pycache__/'
  --exclude='*.pyc'
  --exclude='.venv/'
  --exclude='venv/'
  --exclude='dist/'
  --exclude='build/'
  --exclude='.env*'
  --exclude='*.db'
  --exclude='*.sqlite*'
  --exclude='coverage/'
  --exclude='.pytest_cache/'
  --exclude='.mypy_cache/'
  --exclude='.ruff_cache/'
  --exclude='.git/'
  --exclude='.wrangler/'
  --exclude='.cache/'
  --exclude='*.log'
  --exclude='.DS_Store'
  --exclude='Thumbs.db'
)

echo "═══════════════════════════════════════════════════════════════════════"
echo "  GitHub ↔ HuggingFace Space Sync Verification"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "GitHub:  $GH_REPO"
echo "HF Space: $HF_SPACE"
echo ""

# Get commit SHAs
GH_SHA=$(cd "$GH_REPO" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")
HF_SHA=$(cd "$HF_SPACE" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo "GitHub HEAD:  $GH_SHA"
echo "HF Space HEAD: $HF_SHA"
echo ""

# Check if HF is an auto-sync commit pointing to GitHub HEAD
HF_COMMIT_MSG=$(cd "$HF_SPACE" && git log -1 --format='%s' 2>/dev/null || echo "")
if echo "$HF_COMMIT_MSG" | grep -q "Auto-sync from GitHub @ $GH_SHA"; then
  echo "✓ HF Space is auto-synced to GitHub HEAD"
elif echo "$HF_COMMIT_MSG" | grep -q "Auto-sync"; then
  echo "⚠ HF Space is auto-synced but to a DIFFERENT GitHub SHA"
  echo "  HF commit message: $HF_COMMIT_MSG"
else
  echo "⚠ HF Space has a manual commit (not auto-synced):"
  echo "  $HF_COMMIT_MSG"
fi
echo ""

# Compare each runtime path
echo "── File-level comparison ──"
DIFF_FOUND=false
TOTAL_PATHS=${#RUNTIME_PATHS[@]}
SYNCED=0

for p in "${RUNTIME_PATHS[@]}"; do
  if [ ! -e "$GH_REPO/$p" ]; then
    echo "  ⚠ $p: missing in GitHub"
    DIFF_FOUND=true
    continue
  fi
  if [ ! -e "$HF_SPACE/$p" ]; then
    echo "  ✗ $p: missing in HF Space"
    DIFF_FOUND=true
    continue
  fi

  # Use rsync --dry-run to compare (respects exclude patterns)
  if [ -d "$GH_REPO/$p" ]; then
    DIFF=$(rsync -a --dry-run --itemize-changes "${EXCLUDES[@]}" \
      "$GH_REPO/$p/" "$HF_SPACE/$p/" 2>/dev/null || true)
  else
    # File comparison
    if diff -q "$GH_REPO/$p" "$HF_SPACE/$p" >/dev/null 2>&1; then
      DIFF=""
    else
      DIFF="modified"
    fi
  fi

  if [ -z "$DIFF" ]; then
    echo "  ✓ $p — in sync"
    SYNCED=$((SYNCED + 1))
  else
    echo "  ✗ $p — DIFFERS:"
    echo "$DIFF" | head -5 | sed 's/^/      /'
    DIFF_FOUND=true
  fi
done

echo ""
echo "── Summary ──"
echo "  Paths in sync: $SYNCED / $TOTAL_PATHS"

if [ "$DIFF_FOUND" = "false" ]; then
  echo ""
  echo "═══════════════════════════════════════════════════════════════════════"
  echo "  ✅ ALL RUNTIME FILES ARE IN SYNC"
  echo "═══════════════════════════════════════════════════════════════════════"
  exit 0
else
  echo ""
  echo "═══════════════════════════════════════════════════════════════════════"
  echo "  ⚠ SYNC DIFFERENCES DETECTED"
  echo "═══════════════════════════════════════════════════════════════════════"
  echo ""
  echo "To fix:"
  echo "  1. Commit changes on GitHub:  cd $GH_REPO && git add -A && git commit -m '...' && git push"
  echo "  2. Wait for GitHub Actions to auto-sync to HF"
  echo "  3. OR manually sync:          bash $GH_REPO/../scripts/sync_gh_to_hf.sh"
  echo "  4. Re-run this check:         bash $0"
  exit 1
fi
