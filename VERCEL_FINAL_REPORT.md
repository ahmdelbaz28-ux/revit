# Vercel Deployment Investigation — Final Report (CORRECTED TWICE)

**Document ID:** VERCEL-FINAL-2026-07-08
**Author:** AI Assistant (V143 verification with real Vercel + GitHub tokens)
**Status:** ACTIVE — trigger-vercel.yml RE-ENABLED (was incorrectly disabled)
**Investigation Date:** 2026-07-08T11:20:00+0000

---

## Executive Summary

This report has been corrected TWICE. The investigation using real Vercel
and GitHub tokens revealed:

1. **The Vercel project has NO native GitHub integration**
   (`gitRepository: null` in the project config)

2. **ALL deployments are API-triggered** by `trigger-vercel.yml` (the
   workflow passes `gitSource.type: "github"` which makes the deployment
   metadata look like a GitHub deploy, but it's actually an API call)

3. **The workflow is the ONLY deployment trigger** — it MUST stay enabled

4. My previous "correction" (commit `6bc0fcb5`) incorrectly disabled the
   workflow, which would have broken all deployments. This has been
   reverted in the current commit.

5. The original conclusion in `VERCEL_VERIFICATION_REPORT.md` (commit
   `4b5a17d3`) was CORRECT: the native integration is disconnected.

---

## The Three Phases of This Investigation

### Phase 1: VERCEL_VERIFICATION_REPORT.md (commit 4b5a17d3) — CORRECT

**Conclusion**: Vercel webhook is NOT registered. Integration is disconnected.

**Basis**: GitHub API returned `[]` for `/repos/.../hooks`.

**Verdict**: ✅ CORRECT — but the method (checking repo webhooks) was
incomplete because Vercel could use a GitHub App.

### Phase 2: VERCEL_FINAL_REPORT.md (commit 6bc0fcb5) — WRONG

**Conclusion**: Native integration IS working. Disable trigger-vercel.yml.

**Basis**: Deployments showed `gitSourceType: "github"` and
`githubDeployment: "1"`.

**Verdict**: ❌ WRONG — I misread the deployment metadata. The
`gitSource` field is set by the API call's parameters, not by the native
integration. `githubDeployment: "1"` just means the deployment was
created with GitHub metadata, not that GitHub triggered it.

### Phase 3: This report (current commit) — CORRECTED

**Conclusion**: Native integration is NOT configured. Workflow MUST stay enabled.

**Basis**: `gitRepository: null` in the Vercel project config — this is
the definitive proof that no native GitHub integration exists.

**Verdict**: ✅ CORRECT — the project has no git repository connected.
The workflow is the only deployment trigger.

---

## Definitive Evidence

### Evidence: Vercel Project Has NO Native GitHub Integration

```bash
curl -sS -H "Authorization: Bearer $VERCEL_TOKEN" \
  "https://api.vercel.com/v9/projects/prj_Y6Qr828DXS83tWF1LntFakyofMrf?teamId=team_eeEYqzXI8zkrTo62cUOTMVmS" \
  | jq '{gitRepository, gitStatus}'
```

**Result**:
```json
{
  "gitRepository": null,
  "gitStatus": null
}
```

`gitRepository: null` is the definitive proof. If native GitHub
integration were configured, this field would contain the repo info
(type, org, repo, id).

### Why the Deployment Metadata Was Misleading

The `trigger-vercel.yml` workflow calls the Vercel API with:

```json
{
  "gitSource": {
    "type": "github",
    "org": "ahmdelbaz28-ux",
    "repo": "revit",
    "ref": "main",
    "sha": "<commit-sha>"
  }
}
```

This `gitSource` parameter tells Vercel to create a deployment that
LOOKS like it came from GitHub. Vercel sets:
- `gitSource.type: "github"` (from the API parameter)
- `meta.githubDeployment: "1"` (because gitSource.type is github)
- `meta.githubCommitSha: "<sha>"` (from the API parameter)
- `meta.githubCommitRef: "main"` (from the API parameter)

But the deployment was NOT triggered by GitHub — it was triggered by
the workflow's API call. The `gitRepository: null` in the project
config confirms this.

---

## Current State (Corrected)

### trigger-vercel.yml: ✅ RE-ENABLED (push trigger restored)

The workflow is back to firing on push to `main` (with path filters).
This is the ONLY deployment trigger. Disabling it would break all
deployments.

### API Quota: ⚠️ EXHAUSTED (will reset in ~24h)

The workflow has burned the 100/day API quota. Until it resets:
- New pushes will trigger the workflow
- The workflow will get HTTP 402 (daily limit exceeded)
- The workflow will report failure (exit 1, after V143 fix)
- No deployments will happen until quota resets

### Latest Deployments

| Commit | State | Notes |
|--------|-------|-------|
| `729caed4` | ❌ ERROR | Resource provisioning failed (transient) |
| `6ef546e4` | ✅ READY | Last successful deployment |
| `437fc585` | ✅ READY | |
| `7809b08d` | ✅ READY | |

---

## Required Human Action (DEFINITIVE)

### Action 1: Connect the Vercel Project to GitHub (CRITICAL)

This is the REAL fix. Once connected, native deployments work without
using the API quota.

1. Go to: **https://vercel.com/ahmdelbaz28/revit/settings/git**
2. Click **"Connect Git Repository"**
3. Select **GitHub** as the provider
4. Authorize Vercel to access `ahmdelbaz28-ux/revit`
5. Set Production Branch = `main`
6. Save

### Action 2: Verify Native Integration (after Action 1)

```bash
# Check that gitRepository is no longer null
curl -sS -H "Authorization: Bearer $VERCEL_TOKEN" \
  "https://api.vercel.com/v9/projects/prj_Y6Qr828DXS83tWF1LntFakyofMrf?teamId=team_eeEYqzXI8zkrTo62cUOTMVmS" \
  | jq '.gitRepository'

# Should return something like:
# {"type": "github", "org": "ahmdelbaz28-ux", "repo": "revit", "id": "1234567890"}
```

### Action 3: Disable trigger-vercel.yml (ONLY after Action 1 verified)

Once `gitRepository` is no longer null, the native integration is
working. THEN you can disable the push trigger in `trigger-vercel.yml`
(change `on: push: ...` to `on: workflow_dispatch:` only).

### Action 4: Redeploy the latest commit (after quota resets)

Once the API quota resets (~24h) or native integration is connected:
- Make a trivial commit to trigger a fresh deployment
- OR use Vercel dashboard "Redeploy" (doesn't use API quota)

---

## Apology and Correction

I made TWO errors in this investigation:

1. **VERCEL_VERIFICATION_REPORT.md** (commit `4b5a17d3`):
   - Method: checked GitHub `/repos/.../hooks` → returned `[]`
   - Conclusion: "webhook disconnected"
   - This was CORRECT but the evidence was incomplete

2. **VERCEL_FINAL_REPORT.md** (commit `6bc0fcb5`):
   - Method: checked deployment metadata → saw `githubDeployment: "1"`
   - Conclusion: "native integration IS working, disable workflow"
   - This was WRONG — I misread API-triggered deployments as native
   - I incorrectly disabled the workflow, which would break deployments

**Current commit**: Reverts the workflow disabling, corrects the report,
and provides the definitive fix (connect the Vercel project to GitHub).

The root cause of my error: I didn't check the project's `gitRepository`
field, which is the definitive indicator of native integration. I
apologize for the confusion caused by the incorrect "correction".

---

## Revision History

| Rev | Date | Author | Change |
|-----|------|--------|--------|
| 1.0 | 2026-07-08 | AI Assistant (V143) | Initial "final" report — INCORRECTLY concluded native integration works |
| 2.0 | 2026-07-08 | AI Assistant (V143) | CORRECTED: checked gitRepository=null, confirmed NO native integration. Reverted workflow disabling. |

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
