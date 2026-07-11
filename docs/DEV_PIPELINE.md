# BAZSPARK FireAI — Development Pipeline

> **Integrated workflow**: CodeSandbox (human dev) → GitHub → Daytona (AI review) → HF Spaces + Vercel (production).

This document is the canonical reference for how the four environments in the BAZSPARK FireAI stack fit together. It is referenced by `agent.md` (V206) and should be updated whenever the pipeline topology changes.

---

## 1. Topology at a glance

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 1 — Human development (CodeSandbox)                              │
│  • 8GB RAM devbox booted from .devcontainer/devcontainer.json           │
│  • Python 3.12 + Node 20 + Postgres + Redis + Playwright                │
│  • 40h/month regenerates, 5 members, live collaboration                 │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ git push to feature branch
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  GITHUB — source of truth (ahmdelbaz28-ux/revit)                        │
│  • main is always deployable                                            │
│  • feature branches open PRs to main                                    │
└──────────┬─────────────────────────────────────────────┬────────────────┘
           │ PR opened                                   │ PR merged to main
           ▼                                             ▼
┌──────────────────────────────────┐  ┌────────────────────────────────────┐
│  PHASE 2 — AI review (Daytona)   │  │  PHASE 3 — Production               │
│  • .github/workflows/            │  │  • HF Spaces (FastAPI + React)      │
│    ai-code-review.yml            │  │    Dockerfile (16GB RAM, always-on) │
│  • Daytona sandbox per PR        │  │  • Vercel (preview + production)    │
│  • ruff + mypy + pytest + tsc    │  │  • Supabase (PostgreSQL primary)    │
│  • structured PR comment         │  │  • Neon (IPv4 fallback for HF)      │
│  • 1h session limit is ample     │  │  • Langfuse (LLM observability)     │
└──────────────────────────────────┘  └────────────────────────────────────┘
```

---

## 2. Phase 1 — CodeSandbox (daily human development)

### Why CodeSandbox
| Strength | Detail |
|---|---|
| Browser IDE | Full VS Code in the browser — no local install |
| 8GB RAM | Enough for Postgres + Redis + Vite + FastAPI simultaneously |
| 40h/month regenerates | Resets per month (not per session) — enough for 13–20 dev days |
| 5 members | Small team can share a devbox |
| Live collaboration | Pair-program inside the same session |
| `devcontainer.json` parity | Same file works for CodeSandbox and VS Code Remote-Containers |

### Bootstrapping
1. Sign in to [CodeSandbox](https://codesandbox.io) with GitHub.
2. **Import** the repo `ahmdelbaz28-ux/revit` as a Devbox.
3. CodeSandbox detects `.devcontainer/devcontainer.json` and builds the image.
4. `post-create.sh` runs automatically:
   - `pip install -e .` (backend)
   - `npm ci` in `frontend/`
   - Playwright Chromium install
   - Generates a local `.env` with a random `FIREAI_SESSION_SECRET`
5. `post-start.sh` runs on every session restart:
   - Starts local Postgres + Redis (if installed)
   - Prints a banner with the common dev commands

### Daily loop
```bash
# Backend (hot-reload)
uvicorn backend.app:app --reload --port 8000

# Frontend (Vite, separate shell)
cd frontend && npm run dev          # → http://localhost:5173

# Run a focused test subset
pytest core/tests parsers/tests -q
cd frontend && npm run test         # vitest
cd frontend && npm run test:visual  # playwright

# Lint before commit
ruff check .
cd frontend && npm run lint
```

### Resource budget
- 40h/month ÷ ~2-3h/day ≈ **13–20 dev days/month**.
- If you exhaust the budget, fall back to a local clone with the same `devcontainer.json` (VS Code Remote-Containers or `docker compose up`).

---

## 3. Phase 2 — Daytona (AI agent sandbox)

### Why Daytona
| Strength | Detail |
|---|---|
| 20 concurrent sandboxes | CodeSandbox free tier is more limited |
| SDK designed for AI agents | `fork`, `snapshot`, `hibernate` primitives |
| Self-hostable | If you later get a VPS, install Daytona there to remove cloud limits |
| 1h session limit | Not a problem — AI agent finishes and the sandbox auto-evicts |
| `devcontainer.json` support | Same standard as CodeSandbox |

### Trigger
`.github/workflows/ai-code-review.yml` fires on:
- `pull_request` to `main` (opened / synchronize / reopened / ready_for_review)
- `workflow_dispatch` with a `pr_number` input (manual re-run)

### What the workflow does
1. Checks out the PR head.
2. Installs `daytona-sdk` on the runner (control plane).
3. Provisions a Daytona sandbox (`python:3.12-slim`, 2 vCPU / 4GB RAM / 10GB disk).
4. Streams the PR source into the sandbox via the SDK filesystem API.
5. Runs the validation matrix:
   - `ruff check` (lint)
   - `mypy` (type-check backend, fireai, core — skills excluded per V140 root-cause)
   - `pytest core/tests parsers/tests fireai/core/tests` (fast subset)
   - `tsc --noEmit` on the frontend
6. Posts a structured Markdown table + collapsible output tails as a PR comment.
7. Tears down the sandbox in an `if: always()` step (so it cleans up even on failure).

### Required GitHub secrets
| Secret | Purpose | Example |
|---|---|---|
| `DAYTONA_API_TOKEN` | Daytona cloud auth | `dtn_…` |
| `DAYTONA_SERVER_URL` | Optional — defaults to `https://app.daytona.io` | `https://app.daytona.io` |

> Set them via **Settings → Secrets and variables → Actions** in the GitHub repo, or via the GitHub API (see `scripts/set-github-secrets.sh` in this PR).

### Cost model
- The $100 Daytona credit yields roughly **100–200 AI execution hours**.
- A typical review pass uses 5–10 minutes of sandbox time.
- → ~600–1200 PR reviews per credit refill.

---

## 4. Phase 3 — Production (HF Spaces + Vercel + Supabase)

| Layer | Provider | Why |
|---|---|---|
| Backend (FastAPI) | **HF Spaces** (Docker SDK, 16GB RAM, always-on) | Free tier covers the full backend indefinitely |
| Frontend (React + Vite) | **Vercel** | Already wired via `trigger-vercel.yml`; preview deploys per PR |
| Database (PostgreSQL) | **Supabase** (primary) + **Neon** (IPv4 fallback) | HF Spaces free tier can't reach Supabase's IPv6-only endpoint; `backend/database.py::_init_postgres` falls back to `NEON_DATABASE_URL` automatically |
| LLM observability | **Langfuse** | `LANGFUSE_*` env vars in `docker-compose.yml` |
| Vector store | **Qdrant Cloud** | Optional — only for GraphRAG features |

### Deployment paths
- **HF Spaces**: `.github/workflows/sync-to-hf.yml` mirrors runtime files to `huggingface.co/spaces/ahmdelbaz28/BAZSPARK` on every push to `main`.
- **Vercel**: `.github/workflows/trigger-vercel.yml` fires a deploy hook. The Vercel project overrides the build command to `cd frontend && npm install && npm run build` (see V161/V162 fix history in `agent.md`).
- **Supabase**: schema migrations live in `alembic/`; run `alembic upgrade head` against the production DB after deploy.

---

## 5. Safe push protocol (per `agent.md` Rule 7/8/9)

Every push to `main` MUST follow this sequence — no exceptions:

```bash
# 1. Verify remote state
git fetch origin --prune

# 2. Rebase on latest main BEFORE committing
git checkout main
git pull --rebase origin main

# 3. Create a feature branch
git checkout -b feat/v206-dev-pipeline

# 4. Make changes, test LOCALLY first
ruff check .
pytest core/tests parsers/tests -q
( cd frontend && npm run typecheck )

# 5. Commit with a descriptive message (V### prefix)
git add -A
git commit -m "V206: devcontainer + Daytona AI review workflow + DEV_PIPELINE doc"

# 6. Rebase AGAIN before pushing (in case main moved)
git fetch origin
git rebase origin/main

# 7. Push the feature branch
git push origin feat/v206-dev-pipeline

# 8. Open a PR — the Daytona AI review workflow runs automatically
```

**Never** `git push --force` to `main`. Force-push only to your own feature branch and only after coordinating with reviewers.

---

## 6. ETAP COM Windows testing (GitHub Actions)

ETAP (Electrical Transient Analyzer Program) integration requires a Windows runtime. We use GitHub Actions' `windows-latest` runner (2,000 free minutes/month for public repos) for this:

- Triggered manually via `workflow_dispatch` or on changes to `skills/etap-expert/`.
- Installs ETAP COM dependencies, runs `skills/etap-expert/tests/`.
- No impact on the Linux-based CI matrix — runs as a separate job.

---

## 7. Token inventory (where each lives)

> ⚠️ **Never commit secrets to the repo.** All tokens below MUST live in GitHub Secrets, HF Spaces secrets, or Vercel env vars.

| Token | Stored in | Used by |
|---|---|---|
| `CODESANDBOX_API_KEY` | (per-user, not repo) | CodeSandbox CLI for `csb` commands |
| `DAYTONA_API_TOKEN` | GitHub Secrets | `ai-code-review.yml` |
| `HF_TOKEN` | GitHub Secrets | `sync-to-hf.yml` |
| `SUPABASE_SERVICE_ROLE_KEY` | HF Spaces secrets + Vercel env | Backend runtime |
| `NEON_DATABASE_URL` | HF Spaces secrets | Backend runtime (fallback) |
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` | HF Spaces secrets | Backend LLM observability |
| `VERCEL_DEPLOY_HOOK_TOKEN` | GitHub Secrets | `trigger-vercel.yml` |
| `GITHUB_TOKEN` | Automatic | All workflows (PR comments, etc.) |

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| CodeSandbox devbox fails to build | `devcontainer.json` JSON syntax error | `jq . .devcontainer/devcontainer.json` locally |
| Daytona sandbox creation times out | `DAYTONA_API_TOKEN` expired or wrong region | Rotate token; verify `DAYTONA_SERVER_URL` |
| HF Spaces 404 on `/` | Frontend build missing in image (V206 regression) | Verify Stage 1 of `Dockerfile` ran and `dist/index.html` exists |
| Vercel build fails on Python auto-detect | `vercel.json` not overriding build command | See V161/V162 fix history in `agent.md` |
| `psycopg2.OperationalError` on HF | IPv6-only Supabase unreachable | Set `NEON_DATABASE_URL` (IPv4) as fallback |
| `FIREAI_SESSION_SECRET` not set | `.env` not generated | `python3 -m backend.session_secret generate` |

---

## 9. Change log

| Date | Version | Change |
|---|---|---|
| 2026-07-11 | V206 | Initial pipeline: `devcontainer.json`, Daytona AI review workflow, this doc |
