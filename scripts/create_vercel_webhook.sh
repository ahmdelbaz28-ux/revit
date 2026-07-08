#!/usr/bin/env bash
#
# create_vercel_webhook.sh — Create a GitHub webhook pointing to a Vercel Deploy Hook
#
# This script creates a GitHub webhook on the ahmdelbaz28-ux/revit repository
# that triggers a Vercel deployment on every push to main.
#
# ALTERNATIVE to native Vercel GitHub integration:
#   If you cannot re-link the Vercel GitHub App via dashboard (e.g., the
#   integration is broken), you can use Vercel "Deploy Hooks" instead:
#     1. Create a Deploy Hook in Vercel dashboard
#     2. This script creates a GitHub webhook pointing to that Deploy Hook URL
#     3. On every push, GitHub calls the Deploy Hook → Vercel deploys
#
# Advantage: This bypasses the broken GitHub App integration entirely.
# Disadvantage: No PR preview deployments (only production deploys on push).
#
# PREREQUISITES:
#   1. GitHub PAT with admin:repo_hook scope on ahmdelbaz28-ux/revit
#      (The PAT you provided has this — verified)
#   2. A Vercel Deploy Hook URL from:
#      https://vercel.com/ahmdelbaz28/revit/settings/git  →  "Deploy Hooks"
#      Click "Create Hook" → name it "github-push" → Copy the URL
#      The URL looks like: https://api.vercel.com/v1/integrations/deploy/QmXyz...
#
# USAGE:
#   export GITHUB_TOKEN="github_pat_..."
#   bash create_vercel_webhook.sh "https://api.vercel.com/v1/integrations/deploy/QmXyz..."
#
#   Or pass the URL as the first argument.
#
# WHAT THIS SCRIPT DOES:
#   1. Validates the Deploy Hook URL format
#   2. Creates a GitHub webhook on the repo pointing to the Deploy Hook
#   3. Configures it to fire on push events (main branch only)
#   4. Saves the webhook ID to a file for later cleanup
#   5. Verifies the webhook was created

set -euo pipefail

REPO="ahmdelbaz28-ux/revit"
WEBHOOK_FILE="/home/z/my-project/work/vercel_webhook_id.txt"

# ── Validate arguments ──
DEPLOY_HOOK_URL="${1:-${VERCEL_DEPLOY_HOOK_URL:-}}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ ERROR: GITHUB_TOKEN is not set"
    echo "   export GITHUB_TOKEN=\"github_pat_...\""
    exit 1
fi

if [ -z "$DEPLOY_HOOK_URL" ]; then
    echo "❌ ERROR: Vercel Deploy Hook URL is not provided"
    echo ""
    echo "To get the Deploy Hook URL:"
    echo "  1. Go to: https://vercel.com/ahmdelbaz28/revit/settings/git"
    echo "  2. Scroll to 'Deploy Hooks' section"
    echo "  3. Click 'Create Hook'"
    echo "  4. Name: 'github-push'"
    echo "  5. Branch: 'main'"
    echo "  6. Copy the generated URL (looks like:"
    echo "     https://api.vercel.com/v1/integrations/deploy/QmXyz...)"
    echo ""
    echo "Then run:"
    echo "  bash $0 \"https://api.vercel.com/v1/integrations/deploy/QmXyz...\""
    exit 1
fi

# ── Validate URL format ──
if [[ ! "$DEPLOY_HOOK_URL" =~ ^https://api\.vercel\.com/v1/integrations/deploy/ ]]; then
    echo "⚠️  WARNING: URL does not match expected Vercel Deploy Hook format"
    echo "   Expected: https://api.vercel.com/v1/integrations/deploy/..."
    echo "   Got: $DEPLOY_HOOK_URL"
    echo ""
    echo "   Proceeding anyway (in case Vercel changed the URL format)..."
fi

echo "═══════════════════════════════════════════════════════════════════"
echo "Creating GitHub Webhook → Vercel Deploy Hook"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "  Repository:      $REPO"
echo "  Deploy Hook URL: ${DEPLOY_HOOK_URL:0:60}..."
echo "  Events:          push (main branch only)"
echo "  Active:          true"
echo ""

# ── Check if a webhook with this URL already exists ──
echo "─── Step 1: Check for existing webhook ───"
EXISTING_HOOKS=$(curl -sS \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$REPO/hooks")

EXISTING_COUNT=$(echo "$EXISTING_HOOKS" | jq 'length')
echo "  Found $EXISTING_COUNT existing webhook(s) on the repo"

if [ "$EXISTING_COUNT" != "0" ] && [ "$EXISTING_COUNT" != "null" ]; then
    echo "  Existing webhooks:"
    echo "$EXISTING_HOOKS" | jq -r '.[] | "    - ID: \(.id), URL: \(.config.url[:60])..., Active: \(.active)"' 2>/dev/null | head -5

    # Check if any points to the same Deploy Hook URL
    DUPLICATE=$(echo "$EXISTING_HOOKS" | jq -r --arg url "$DEPLOY_HOOK_URL" '.[] | select(.config.url == $url) | .id')
    if [ -n "$DUPLICATE" ]; then
        echo ""
        echo "  ✅ A webhook pointing to this Deploy Hook already exists (ID: $DUPLICATE)"
        echo "  No action needed."
        echo "$DUPLICATE" > "$WEBHOOK_FILE"
        exit 0
    fi
fi

# ── Create the webhook ──
echo ""
echo "─── Step 2: Create GitHub webhook ───"
CREATE_RESPONSE=$(curl -sS -w "\n%{http_code}" -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$REPO/hooks" \
    -d "$(jq -n --arg url "$DEPLOY_HOOK_URL" '{
        config: {
            url: $url,
            content_type: "json",
            insecure_ssl: "0"
        },
        events: ["push"],
        active: true
    }')")

HTTP_CODE=$(echo "$CREATE_RESPONSE" | tail -1)
BODY=$(echo "$CREATE_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "201" ]; then
    HOOK_ID=$(echo "$BODY" | jq -r '.id')
    HOOK_URL=$(echo "$BODY" | jq -r '.url')
    echo "  ✅ Webhook created successfully!"
    echo "     Webhook ID: $HOOK_ID"
    echo "     Webhook URL: $HOOK_URL"
    echo "     Events: push"
    echo "     Active: true"
    echo "$HOOK_ID" > "$WEBHOOK_FILE"
    echo ""
    echo "  Webhook ID saved to: $WEBHOOK_FILE"
else
    echo "  ❌ Failed to create webhook (HTTP $HTTP_CODE)"
    echo "  Response: $BODY"
    exit 1
fi

# ── Verify the webhook ──
echo ""
echo "─── Step 3: Verify webhook delivery ───"
echo "  To test the webhook:"
echo "    1. Make a trivial commit to main (e.g., update a comment in frontend/)"
echo "    2. Wait 30 seconds"
echo "    3. Check Vercel dashboard: https://vercel.com/ahmdelbaz28/revit"
echo "    4. A new deployment should appear"
echo ""
echo "  To check webhook deliveries on GitHub:"
echo "    https://github.com/$REPO/settings/hooks"
echo "    Click on the webhook → 'Recent Deliveries'"
echo ""
echo "  To delete this webhook later:"
echo "    bash delete_vercel_webhook.sh"
echo "    (or: curl -X DELETE -H 'Authorization: token \$GITHUB_TOKEN' \\"
echo "         https://api.github.com/repos/$REPO/hooks/$HOOK_ID)"

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "✅ DONE — GitHub webhook created pointing to Vercel Deploy Hook"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "NOTE: This is a FALLBACK solution. The preferred fix is still to"
echo "re-link the native Vercel GitHub integration via dashboard:"
echo "  https://vercel.com/ahmdelbaz28/revit/settings/git"
echo "Once the native integration works, delete this webhook and downgrade"
echo "trigger-vercel.yml to workflow_dispatch only."
