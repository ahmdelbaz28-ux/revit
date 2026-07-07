#!/usr/bin/env bash
# V193 (R4): Pre-merge CI gate — verifies the frontend builds cleanly.
#
# This script catches JSX parse errors (like the {{{ corruption that
# blocked V192) BEFORE they reach production. Run it:
#   - Locally before committing: bash scripts/ci-build-gate.sh
#   - In CI (GitHub Actions) on every PR
#
# Exits 0 on success, 1 on any failure.

set -euo pipefail

echo "═══════════════════════════════════════════════════════════════════════════"
echo "V193 CI Build Gate — Vite production build + TypeScript check"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

cd "$(dirname "$0")/../frontend"

echo "▶ Step 1/3: Install dependencies (npm ci)"
npm ci --no-audit --no-fund
echo ""

echo "▶ Step 2/3: TypeScript type-check (tsc --noEmit)"
npm run typecheck
echo ""

echo "▶ Step 3/3: Production build (vite build)"
npm run build
echo ""

echo "═══════════════════════════════════════════════════════════════════════════"
echo "✓ CI BUILD GATE PASSED — frontend builds cleanly"
echo "═══════════════════════════════════════════════════════════════════════════"  # NOSONAR - shelldre:S1192
exit 0
