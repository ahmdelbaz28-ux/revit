#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# set-github-secrets.sh — push secrets to GitHub via the REST API.
# ═══════════════════════════════════════════════════════════════════════════
# Requires: GH_PAT (GitHub PAT with `repo` scope), GH_REPO, and the secret
# values exported in the environment.
#
# Usage (replace <...> placeholders with your actual token values):
#   export GH_PAT="<your-github-pat>"
#   export GH_REPO="ahmdelbaz28-ux/revit"
#   export DAYTONA_API_TOKEN="<your-daytona-token>"
#   export HF_TOKEN="<your-hf-token>"
#   bash scripts/set-github-secrets.sh
#
# The script uses libsodium-sealed-boxes via the GitHub API:
#   1. Fetch the repo's public key (modulus + id).
#   2. Encrypt each secret value with libsodium.
#   3. PUT /repos/{owner}/{repo}/actions/secrets/{name}.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

: "${GH_PAT:?GH_PAT is required}"
: "${GH_REPO:?GH_REPO is required (owner/repo)}"

API="https://api.github.com/repos/${GH_REPO}/actions"

# ── 1. Ensure Python deps for the encryption step ────────────────────────
python3 - <<'PY'
import sys, shutil, subprocess
for mod in ("requests", "pynacl"):
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", mod])
PY

# ── 2. Fetch repo public key (one call) ─────────────────────────────────
echo "▶ Fetching GitHub Actions public key for ${GH_REPO}…"
KEY_JSON=$(curl -fsSL -X GET \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GH_PAT}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "${API}/secrets/public-key")

export KEY_JSON
echo "✓ Public key fetched"

# ── 3. For each secret, encrypt + push ───────────────────────────────────
python3 - <<'PY'
import base64, json, os, sys, urllib.request, urllib.error
from nacl import public

key_json = json.loads(os.environ["KEY_JSON"])
pub = public.PublicKey(base64.b64decode(key_json["key"]))
sealed = public.SealedBox(pub)
key_id = key_json["key_id"]

pat = os.environ["GH_PAT"]
api = os.environ["API"]

# Map of env-var → secret-name to set
secrets = {
    "DAYTONA_API_TOKEN":  "DAYTONA_API_TOKEN",
    "HF_TOKEN":           "HF_TOKEN",
    "VERCEL_DEPLOY_HOOK_TOKEN": "VERCEL_DEPLOY_HOOK_TOKEN",
    "SUPABASE_SERVICE_ROLE_KEY": "SUPABASE_SERVICE_ROLE_KEY",
}

for env_var, secret_name in secrets.items():
    val = os.environ.get(env_var)
    if not val:
        print(f"⚠ {secret_name}: env var {env_var} not set — skipping")
        continue
    enc = sealed.encrypt(val.encode())
    body = json.dumps({
        "encrypted_value": base64.b64encode(enc).decode(),
        "key_id": key_id,
    }).encode()
    req = urllib.request.Request(
        f"{api}/secrets/{secret_name}",
        data=body,
        method="PUT",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {pat}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"✓ {secret_name}: set (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        print(f"✗ {secret_name}: HTTP {e.code} {e.reason}", file=sys.stderr)
        print(f"  body: {e.read().decode()[:200]}", file=sys.stderr)
        sys.exit(1)
PY

echo "✓ All secrets pushed."
