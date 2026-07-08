#!/usr/bin/env bash
#
# verify_vercel_integration.sh — Comprehensive Vercel integration verification
#
# This script verifies the EXACT state of the Vercel project's Git integration
# using the DEFINITIVE check: the project's gitRepository field.
#
# It replaces the incomplete check from VERCEL_VERIFICATION_REPORT.md (Phase 1)
# which only checked /repos/.../hooks — that check returned [] but the
# interpretation was incomplete (Vercel could use a GitHub App).
#
# The definitive check is: GET /v9/projects/{projectId} → .gitRepository
#   - If null: NO native integration configured (workflow is only trigger)
#   - If not null: native integration IS configured (workflow can be disabled)
#
# Usage:
#   export VERCEL_TOKEN="vcp_..."
#   bash scripts/verify_vercel_integration.sh
#
# Exit codes:
#   0 = native integration IS configured (gitRepository not null)
#   1 = native integration NOT configured (gitRepository is null)
#   2 = error (token invalid, network issue, etc.)

set -euo pipefail

PROJECT_ID="prj_Y6Qr828DXS83tWF1LntFakyofMrf"
TEAM_ID="team_eeEYqzXI8zkrTo62cUOTMVmS"
REPO="ahmdelbaz28-ux/revit"

VERCEL_TOKEN="${VERCEL_TOKEN:-}"
if [ -z "$VERCEL_TOKEN" ]; then
    echo "❌ ERROR: VERCEL_TOKEN is not set"
    echo "   export VERCEL_TOKEN=\"vcp_...\""
    exit 2
fi

echo "═══════════════════════════════════════════════════════════════════"
echo "Vercel Integration Verification (DEFINITIVE)"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Check project's gitRepository field (DEFINITIVE) ──
echo "─── Step 1: Project gitRepository (DEFINITIVE check) ───"
PROJECT_RESPONSE=$(curl -sS -H "Authorization: Bearer $VERCEL_TOKEN" \
    "https://api.vercel.com/v9/projects/$PROJECT_ID?teamId=$TEAM_ID" 2>&1)

GIT_REPO=$(echo "$PROJECT_RESPONSE" | jq -r '.gitRepository')
FRAMEWORK=$(echo "$PROJECT_RESPONSE" | jq -r '.framework')
GIT_STATUS=$(echo "$PROJECT_RESPONSE" | jq -r '.gitStatus')

echo "  Project framework: $FRAMEWORK"
echo "  gitRepository: $GIT_REPO"
echo "  gitStatus: $GIT_STATUS"
echo ""

if [ "$GIT_REPO" = "null" ]; then
    echo "  ❌ NATIVE INTEGRATION NOT CONFIGURED"
    echo "     The Vercel project has gitRepository=null — no GitHub repo is connected."
    echo "     trigger-vercel.yml is the ONLY deployment trigger."
    echo ""
    echo "  📋 TO FIX (requires Vercel dashboard access):"
    echo "     1. Go to: https://vercel.com/ahmdelbaz28/revit/settings/git"
    echo "     2. Click 'Connect Git Repository'"
    echo "     3. Select GitHub → ahmdelbaz28-ux/revit"
    echo "     4. Set Production Branch = main"
    echo "     5. Save"
    echo "     6. Re-run this script to verify"
    echo ""
    echo "  ⚠️  DO NOT disable trigger-vercel.yml until this is fixed!"
    exit 1
else
    echo "  ✅ NATIVE INTEGRATION IS CONFIGURED"
    echo "     gitRepository details:"
    echo "$PROJECT_RESPONSE" | jq '.gitRepository' | sed 's/^/      /'
    echo ""
    echo "  ✅ You can now safely disable trigger-vercel.yml push trigger."
    echo "     Edit .github/workflows/trigger-vercel.yml:"
    echo "       Change 'on: push: ...' to 'on: workflow_dispatch:' only"
fi

# ── Step 2: Check recent deployments ──
echo ""
echo "─── Step 2: Recent deployments (last 5) ───"
curl -sS -H "Authorization: Bearer $VERCEL_TOKEN" \
    "https://api.vercel.com/v6/deployments?projectId=$PROJECT_ID&teamId=$TEAM_ID&limit=5" 2>&1 | \
    jq -r '.deployments[] | "  \(.createdAt) [\(.state // .readySubstate // "?")] commit=\(.meta.githubCommitSha[:8] // "n/a") url=\(.url)"' 2>&1 | head -8

# ── Step 3: Check team plan ──
echo ""
echo "─── Step 3: Team plan ───"
curl -sS -H "Authorization: Bearer $VERCEL_TOKEN" \
    "https://api.vercel.com/v2/teams?limit=10" 2>&1 | \
    jq -r '.teams[] | "  Team: \(.slug) plan=\(.billing.plan // "?")"' 2>&1 | head -3

# ── Step 4: Check GitHub webhooks (informational only) ──
echo ""
echo "─── Step 4: GitHub webhooks (informational — may be empty even with native integration) ───"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
if [ -n "$GITHUB_TOKEN" ]; then
    HOOK_COUNT=$(curl -sS -H "Authorization: token $GITHUB_TOKEN" \
        "https://api.github.com/repos/$REPO/hooks" 2>&1 | jq 'length' 2>/dev/null || echo "?")
    echo "  Webhooks registered on GitHub repo: $HOOK_COUNT"
    echo "  (Note: Vercel native integration uses a GitHub App, not a webhook.")
    echo "   The definitive check is Step 1 — gitRepository field.)"
else
    echo "  ⏭️  GITHUB_TOKEN not set — skipping GitHub webhook check"
fi

# ── Step 5: Check trigger-vercel.yml state ──
echo ""
echo "─── Step 5: trigger-vercel.yml current trigger state ───"
WORKFLOW_FILE=".github/workflows/trigger-vercel.yml"
if [ -f "$WORKFLOW_FILE" ]; then
    PUSH_ENABLED=$(grep -c "^  push:" "$WORKFLOW_FILE" || echo "0")
    if [ "$PUSH_ENABLED" -gt 0 ]; then
        echo "  ✅ Push trigger: ENABLED (workflow fires on push to main)"
        if [ "$GIT_REPO" = "null" ]; then
            echo "     → CORRECT: native integration not configured, workflow is needed"
        else
            echo "     → ⚠️  WARNING: native integration IS configured but workflow push trigger is still enabled"
            echo "       This causes DUPLICATE deployments. Disable the push trigger:"
            echo "       Edit $WORKFLOW_FILE → change 'on: push: ...' to 'on: workflow_dispatch:'"
        fi
    else
        echo "  ✅ Push trigger: DISABLED (workflow is manual-only)"
        if [ "$GIT_REPO" = "null" ]; then
            echo "     → ❌ CRITICAL ERROR: native integration NOT configured but push trigger is disabled!"
            echo "       NO deployments will happen! Re-enable the push trigger immediately:"
            echo "       Edit $WORKFLOW_FILE → uncomment the 'push:' trigger"
        else
            echo "     → CORRECT: native integration is configured, workflow is fallback-only"
        fi
    fi
else
    echo "  ⚠️  Workflow file not found: $WORKFLOW_FILE"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
if [ "$GIT_REPO" = "null" ]; then
    echo "VERDICT: ❌ Native integration NOT configured — workflow is the only trigger"
    exit 1
else
    echo "VERDICT: ✅ Native integration IS configured — workflow can be disabled"
    exit 0
fi
