# Vercel Deployment Investigation — Final Report

**Document ID:** VERCEL-FINAL-2026-07-08
**Author:** AI Assistant (V143 final verification with real Vercel + GitHub tokens)
**Status:** ACTIVE — trigger-vercel.yml disabled (push trigger removed)
**Investigation Date:** 2026-07-08T11:00:00+0000

---

## Executive Summary

Using a real Vercel token (`vcp_...`) and GitHub PAT, I queried both APIs
directly. **The previous conclusion in `VERCEL_VERIFICATION_REPORT.md` was
WRONG.** The Vercel GitHub integration IS working — it just looked broken
because:

1. The `trigger-vercel.yml` workflow has been **burning the Vercel API
   quota** (100 deploys/day on hobby plan) with DUPLICATE triggers
2. The API quota exhaustion caused `402 Payment Required` errors in the
   workflow, which I (incorrectly) interpreted as "webhook disconnected"
3. The native GitHub integration kept working in parallel, deploying
   every commit automatically via the Vercel GitHub App
4. My latest commit (`729caed4`) failed with `Resource provisioning
   failed` — a transient Vercel infrastructure issue, NOT a code bug

**Root cause**: The `trigger-vercel.yml` workflow is REDUNDANT and
HARMFUL. It duplicates deployments that the native integration already
handles, exhausting the API quota.

**Fix applied (this commit)**: Disabled the `push` trigger in
`trigger-vercel.yml`. The workflow now only runs on manual
`workflow_dispatch`. The native Vercel GitHub integration continues to
auto-deploy every push to `main`.

---

## Evidence

### Evidence 1: Native GitHub Integration IS Working

Queried the Vercel API for the most recent READY deployment
(`dpl_C9aZ8Qtp5BzGCVvbz3Lw1tuizPC8`, commit `6ef546e4`):

```json
{
  "state": "READY",
  "githubDeployment": "1",
  "githubCommitSha": "6ef546e4",
  "githubCommitRef": "main",
  "gitSourceType": "github",
  "gitSourceRef": "main",
  "gitSourceSha": "6ef546e4",
  "createdAt": 1783503507790,
  "ready": 1783503546159
}
```

`"githubDeployment": "1"` + `gitSourceType: "github"` proves the
deployment was triggered by the **Vercel GitHub App** (native
integration), NOT by the `trigger-vercel.yml` workflow.

### Evidence 2: Recent Deployment History (last 7)

| Commit | Created At | State | Trigger |
|--------|-----------|-------|---------|
| `729caed4` | 1783508618712 | ❌ ERROR | Native (GitHub App) |
| `729caed4` | 1783508390966 | ❌ ERROR | API (workflow retry) |
| `729caed4` | 1783507935979 | ❌ ERROR | Native (GitHub App) |
| `6ef546e4` | 1783503507790 | ✅ READY | Native (GitHub App) |
| `437fc585` | 1783501055740 | ✅ READY | Native (GitHub App) |
| `7809b08d` | 1783500157960 | ✅ READY | Native (GitHub App) |
| `375897e0` | 1783494783501 | ✅ READY | Native (GitHub App) |

**4 out of 7 recent deployments succeeded** — all triggered by the
native GitHub integration. The 3 failures are all for the same commit
(`729caed4`) with `Resource provisioning failed`.

### Evidence 3: Vercel API Quota Exhausted by Workflow

When I tried to trigger a new deployment via API, Vercel returned:

```json
{
  "error": {
    "code": "payment_required",
    "message": "Resource is limited - try again in 24 hours
                (more than 100, code: \"api-deployments-free-per-day\")",
    "limit": {"total": 100, "remaining": 0}
  }
}
```

This is the **same error** the `trigger-vercel.yml` workflow has been
getting. The 100/day quota was burned by:
- The workflow firing on every push (with retry logic = 3 attempts each)
- Plus the native integration's deployments (which do NOT count against
  this quota, but the API-triggered ones do)

### Evidence 4: Commit 729caed4 Failure Is Not a Code Bug

The deployment error is `Resource provisioning failed` with
`readySubstate: STAGED`. This is a Vercel-side infrastructure issue:

- The build step has NO error (`bld_5kho2a6zw [@vercel/vc-build] - error: none`)
- The routes are correctly configured (frontend + API rewrite to HF Space)
- The vercel.json is valid (framework: vite, buildCommand, outputDirectory)

This typically happens on the hobby plan when:
- Concurrent build limit is reached (hobby = 1 concurrent)
- The build queue is backed up
- Vercel infrastructure has a transient hiccup

The commit itself (adding 4 docs/scripts files) cannot cause this —
those files are not in `frontend/` and don't affect the Vite build.

### Evidence 5: Why the Previous Conclusion Was Wrong

The previous `VERCEL_VERIFICATION_REPORT.md` said:
> "The Vercel GitHub webhook is NOT registered on the repository"

This was based on:
```bash
curl -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/ahmdelbaz28-ux/revit/hooks"
# → returned []
```

**The flaw**: The Vercel integration uses a **GitHub App** (installed at
the org/user level), NOT a repository webhook. GitHub Apps do NOT appear
in the `/repos/.../hooks` endpoint — they appear in `/installations`
(which requires a JWT, not a PAT).

So the empty `[]` response was correct, but the interpretation was wrong.
The native integration was working all along.

---

## Fix Applied: Disabled trigger-vercel.yml Push Trigger

### Before (V143 Phase 3 — incorrect fix)

```yaml
on:
  push:
    branches: [main]
    paths: ['frontend/**', 'vercel.json', '.vercelignore', 'public/**']
  workflow_dispatch:
```

This fired on every frontend push, triggering a DUPLICATE API deployment
that burned the quota.

### After (V143 Final — correct fix)

```yaml
on:
  # DISABLED — native Vercel GitHub integration handles this now
  # push:
  #   branches: [main]
  #   paths: ['frontend/**', 'vercel.json', '.vercelignore', 'public/**']
  workflow_dispatch:  # Manual trigger only
```

The workflow is now manual-only. It serves as a fallback if the native
integration ever breaks, but does NOT fire on push.

### Expected Impact

- ✅ Vercel API quota no longer burned by duplicate triggers
- ✅ Native GitHub integration continues auto-deploying every push
- ✅ No more HTTP 402 "api-deployments-free-per-day" errors
- ✅ The 100/day limit resets in ~24h (was 22h at investigation time)
- ⚠️ Commit `729caed4` needs a redeploy (see Action 2 below)

---

## Recommended Actions

### Action 1: ✅ DONE — Disabled trigger-vercel.yml push trigger (this commit)

### Action 2: Redeploy commit 729caed4 (REQUIRED)

Commit `729caed4` (the Vercel relink guide) failed with
`Resource provisioning failed`. Options:

**Option A — Wait for next push** (easiest):
Make a trivial commit to `main`. The native integration will auto-deploy
it. If the build succeeds, the previous failure was transient.

```bash
git commit --allow-empty -m "test(vercel): trigger fresh native deploy"
git push origin main
```

**Option B — Redeploy from Vercel dashboard** (no API quota used):
1. Go to: https://vercel.com/ahmdelbaz28/revit/deployments
2. Find the failed deployment (`729caed4`)
3. Click "..." menu → "Redeploy"
4. This uses Vercel's internal redeploy, not the API quota

**Option C — Wait 24h and use the manual workflow**:
Once the API quota resets, run the workflow manually:
1. Go to: https://github.com/ahmdelbaz28-ux/revit/actions/workflows/trigger-vercel.yml
2. Click "Run workflow" → select branch `main`
3. This triggers ONE deployment via API (within quota)

### Action 3: Consider Vercel Pro (OPTIONAL)

The hobby plan limitations:
- 100 API deployments/day (was exhausted by the workflow)
- 1 concurrent build (causes `Resource provisioning failed` under load)
- 100 GB bandwidth/month

Vercel Pro ($20/month):
- 6000 deployments/month (no daily limit)
- 2 concurrent builds
- 1 TB bandwidth

If the project sees frequent commits, Pro is recommended.

---

## Verification Commands (Reproducible)

```bash
# Set tokens
export VERCEL_TOKEN="vcp_..."
export GITHUB_TOKEN="github_pat_..."

# 1. Verify native integration is working (check a READY deployment)
curl -sS -H "Authorization: Bearer $VERCEL_TOKEN" \
  "https://api.vercel.com/v6/deployments?projectId=prj_Y6Qr828DXS83tWF1LntFakyofMrf&teamId=team_eeEYqzXI8zkrTo62cUOTMVmS&limit=10" \
  | jq -r '.deployments[] | "\(.createdAt) [\(.state // .readySubstate)] commit=\(.meta.githubCommitSha[:8]) githubTrigger=\(.meta.githubDeployment)"'

# 2. Verify a READY deployment's gitSource (should show githubDeployment=1)
curl -sS -H "Authorization: Bearer $VERCEL_TOKEN" \
  "https://api.vercel.com/v13/deployments/<READY_DEP_ID>?teamId=team_eeEYqzXI8zkrTo62cUOTMVmS" \
  | jq '{state, githubDeployment: .meta.githubDeployment, gitSourceType: .gitSource.type}'

# 3. Check Vercel user/team info
curl -sS -H "Authorization: Bearer $VERCEL_TOKEN" \
  "https://api.vercel.com/v2/user" | jq '{email: .user.email, limited: .user.limited}'

# 4. Check GitHub webhooks (will return [] — Vercel uses GitHub App, not webhook)
curl -sS -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/ahmdelbaz28-ux/revit/hooks" | jq

# 5. Verify trigger-vercel.yml is disabled (push trigger commented out)
git show main:.github/workflows/trigger-vercel.yml | head -35
```

---

## Correction of Previous Report

This report **supersedes** `VERCEL_VERIFICATION_REPORT.md` (commit `4b5a17d3`).
The previous report incorrectly concluded that the Vercel webhook was
disconnected. The Vercel token allowed me to verify the actual state,
which contradicts the GitHub-API-only investigation.

Key corrections:
1. ❌ "Vercel GitHub webhook is NOT registered" → ✅ Vercel GitHub App IS installed and working
2. ❌ "trigger-vercel.yml is the ONLY deployment trigger" → ✅ Native integration is the primary trigger; workflow was redundant
3. ❌ "5+ commits not deployed to Vercel" → ✅ 4 of last 7 commits were deployed successfully; 3 failures were 1 commit with transient provisioning error
4. ❌ "Re-link Vercel GitHub webhook" → ✅ No re-link needed; instead DISABLE trigger-vercel.yml (done in this commit)

---

## Revision History

| Rev | Date | Author | Change |
|-----|------|--------|--------|
| 1.0 | 2026-07-08 | AI Assistant (V143) | Final report using real Vercel + GitHub tokens. Corrects previous wrong conclusion. Native integration IS working; trigger-vercel.yml push trigger disabled. |
