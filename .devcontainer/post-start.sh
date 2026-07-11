#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# post-start.sh — runs EVERY TIME the devbox starts.
# Starts the local Postgres + Redis (if installed), prints a health banner.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

echo "▶ [post-start] BAZSPARK FireAI devbox session bootstrap"

# ── 1. Start Postgres + Redis (if available as services) ─────────────────
if command -v pg_ctlcluster >/dev/null 2>&1; then
  if ! pg_isready -q 2>/dev/null; then
    sudo service postgresql start 2>/dev/null || true
  fi
fi
if command -v redis-server >/dev/null 2>&1; then
  if ! redis-cli ping >/dev/null 2>&1; then
    redis-server --daemonize yes --save "" --appendonly no 2>/dev/null || true
  fi
fi

# ── 2. Banner ─────────────────────────────────────────────────────────────
cat <<'BANNER'

  ════════════════════════════════════════════════════════════════════
    BAZSPARK FireAI — Devbox ready
  ════════════════════════════════════════════════════════════════════
    Backend  : uvicorn backend.app:app --reload --port 8000
    Frontend : ( cd frontend && npm run dev )          # :5173
    Tests    : pytest                                  # backend
               ( cd frontend && npm run test )         # vitest
               ( cd frontend && npm run test:visual )  # playwright
    Lint     : ruff check . && ( cd frontend && npm run lint )
  ════════════════════════════════════════════════════════════════════

BANNER

# ── 3. Quick health check (informational, non-fatal) ─────────────────────
if [[ -f .env ]]; then
  if grep -q "^FIREAI_SESSION_SECRET=your-session-secret" .env; then
    echo "⚠ .env still uses placeholder FIREAI_SESSION_SECRET — generate one with:"
    echo "    python3 -m backend.session_secret generate"
  fi
fi
