#!/usr/bin/env bash
# ============================================================
# FireAI ML Subsystem — Push to GitHub & Trigger CI/CD
# ============================================================
# This script provides a SAFE way to push the ML subsystem changes
# to GitHub without exposing credentials in chat history.
#
# USAGE:
#   1. Create a NEW GitHub Personal Access Token at:
#      https://github.com/settings/tokens (NOT the leaked one)
#      - Required scopes: repo, workflow
#   2. Set it as an environment variable in YOUR shell (NOT in chat):
#      export FIREAI_GH_TOKEN='ghp_YOUR_NEW_TOKEN_HERE'
#   3. Run this script:
#      bash scripts/push_ml_subsystem.sh
# ============================================================

set -e

REPO_DIR="${REPO_DIR:-/tmp/revit}"
REMOTE_URL="https://github.com/ahmdelbaz28-ux/revit.git"

echo "============================================================"
echo "  FireAI ML Subsystem — GitHub Push & CI/CD Trigger"
echo "============================================================"
echo ""

# ── 1. Verify token is set ─────────────────────────────────────
if [ -z "$FIREAI_GH_TOKEN" ]; then
    echo "❌ ERROR: FIREAI_GH_TOKEN environment variable is not set."
    echo ""
    echo "To fix:"
    echo "  1. Create a NEW PAT at https://github.com/settings/tokens"
    echo "     (Scopes: repo, workflow)"
    echo "  2. Set it in your shell:"
    echo "       export FIREAI_GH_TOKEN='ghp_NEW_TOKEN'"
    echo "  3. Re-run this script."
    echo ""
    echo "⚠️  NEVER paste the token in chat. Always set it in your shell."
    exit 1
fi

echo "✓ FIREAI_GH_TOKEN is set (length: ${#FIREAI_GH_TOKEN} chars)"

# ── 2. Verify commit exists ────────────────────────────────────
cd "$REPO_DIR"
COMMIT_HASH=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --pretty=format:"%s")
echo "✓ Latest commit: $COMMIT_HASH"
echo "  Message: $COMMIT_MSG"
echo ""

# ── 3. Push to GitHub ──────────────────────────────────────────
echo "─── Pushing to $REMOTE_URL ───"
git -c "credential.helper=!/home/z/.local/bin/git-cred-helper.sh" push origin main 2>&1 | tail -10
echo ""

# ── 4. Trigger CI/CD via GitHub API ────────────────────────────
echo "─── Triggering ML CI/CD workflow ───"
WORKFLOW_FILE="ml-tests.yml"
API_URL="https://api.github.com/repos/ahmdelbaz28-ux/revit/actions/workflows/$WORKFLOW_FILE/dispatches"

curl -s -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer $FIREAI_GH_TOKEN" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$API_URL" \
    -d '{"ref":"main"}' \
    -o /tmp/curl-response.json -w "HTTP %{http_code}\n"

echo ""
if [ -s /tmp/curl-response.json ]; then
    cat /tmp/curl-response.json
    echo ""
fi

echo ""
echo "─── Recent workflow runs ───"
curl -s \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer $FIREAI_GH_TOKEN" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/ahmdelbaz28-ux/revit/actions/runs?per_page=5" \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
for run in data.get('workflow_runs', []):
    print(f\"  {run['name']:40s} | {run['status']:15s} | {run['conclusion'] or 'running':15s} | {run['html_url']}\")
" 2>&1

echo ""
echo "============================================================"
echo "  ✓ Push & CI/CD trigger complete"
echo "============================================================"
echo ""
echo "Monitor CI/CD at:"
echo "  https://github.com/ahmdelbaz28-ux/revit/actions"
echo ""
echo "If CI fails, common fixes:"
echo "  1. Ensure requirements-ml.txt installs cleanly on ubuntu-latest"
echo "  2. Check that fireai/ml/__init__.py exports match backend/routers/ml.py imports"
echo "  3. Verify pytest discovers tests/ml/ (already in pyproject.toml)"
