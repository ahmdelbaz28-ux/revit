#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# post-create.sh — runs ONCE after the devbox is first built.
# Installs Python + Node deps, sets up Playwright browsers, generates the
# local SQLite DBs and the session secret if missing.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

echo "▶ [post-create] BAZSPARK FireAI devbox bootstrap"

# ── 1. Python backend deps ────────────────────────────────────────────────
if [[ -f pyproject.toml ]]; then
  echo "▶ Installing Python project (editable)…"
  pip install --user -e . 2>&1 | tail -5 || pip install -e . 2>&1 | tail -5
fi

# ── 2. Frontend deps ──────────────────────────────────────────────────────
if [[ -f frontend/package.json ]]; then
  echo "▶ Installing frontend deps (npm ci)…"
  ( cd frontend && npm ci --no-audit --no-fund 2>&1 | tail -5 )
fi

# ── 3. Playwright browsers (for visual tests) ────────────────────────────
if command -v npx >/dev/null 2>&1; then
  echo "▶ Installing Playwright browsers…"
  npx playwright install --with-deps chromium 2>&1 | tail -3 || true
fi

# ── 4. Local SQLite DBs + session secret ─────────────────────────────────
mkdir -p db
if [[ ! -f .env ]]; then
  echo "▶ Generating local .env from .env.example…"
  cp .env.example .env
  # Generate a session secret (43-256 chars, URL-safe base64)
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))' 2>/dev/null || openssl rand -base64 48 | tr -d "\n" | tr "+/" "-_")"
  python3 -c "
import re, pathlib
p = pathlib.Path('.env')
t = p.read_text()
t = re.sub(r'^FIREAI_SESSION_SECRET=.*\$', 'FIREAI_SESSION_SECRET=${SECRET}', t, flags=re.M)
p.write_text(t)
print('  → FIREAI_SESSION_SECRET set')
"
fi

# ── 5. Pre-commit hooks (optional, non-fatal) ────────────────────────────
if [[ -f .pre-commit-config.yaml ]] && command -v pre-commit >/dev/null 2>&1; then
  echo "▶ Installing pre-commit hooks…"
  pre-commit install --install-hooks 2>&1 | tail -3 || true
fi

echo "✓ [post-create] bootstrap complete. Run 'bash .devcontainer/post-start.sh' to launch services."
