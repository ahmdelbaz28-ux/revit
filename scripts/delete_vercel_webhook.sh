#!/usr/bin/env bash
#
# delete_vercel_webhook.sh — Delete the GitHub webhook created by create_vercel_webhook.sh
#
# Usage:
#   export GITHUB_TOKEN="github_pat_..."
#   bash delete_vercel_webhook.sh
#
# This script reads the webhook ID from /home/z/my-project/work/vercel_webhook_id.txt
# and deletes it via GitHub API.

set -euo pipefail

REPO="ahmdelbaz28-ux/revit"
WEBHOOK_FILE="/home/z/my-project/work/vercel_webhook_id.txt"

GITHUB_TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ ERROR: GITHUB_TOKEN is not set"
    echo "   export GITHUB_TOKEN=\"github_pat_...\""
    exit 1
fi

if [ ! -f "$WEBHOOK_FILE" ]; then
    echo "❌ ERROR: Webhook ID file not found: $WEBHOOK_FILE"
    echo "   Run create_vercel_webhook.sh first."
    exit 1
fi

HOOK_ID=$(cat "$WEBHOOK_FILE")
echo "Deleting webhook ID: $HOOK_ID"

HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$REPO/hooks/$HOOK_ID")

if [ "$HTTP_CODE" = "204" ]; then
    echo "✅ Webhook $HOOK_ID deleted successfully"
    rm -f "$WEBHOOK_FILE"
    echo "   Webhook ID file removed."
else
    echo "❌ Failed to delete webhook (HTTP $HTTP_CODE)"
    echo "   The webhook may have already been deleted, or the ID is invalid."
    echo "   Check: https://github.com/$REPO/settings/hooks"
    exit 1
fi
