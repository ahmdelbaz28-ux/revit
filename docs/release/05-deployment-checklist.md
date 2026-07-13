# 05 — Deployment Checklist

**Project:** BAZspark v1.55.0

---

## Pre-Deployment

### Required Environment Variables

- [ ] `FIREAI_ENV=production`
- [ ] `FIREAI_SESSION_SECRET` (generate: `python3 -m backend.session_secret generate`)
- [ ] `FIREAI_API_KEY` (64-char hex key)
- [ ] `CORS_ALLOWED_ORIGINS` (your production frontend URL)
- [ ] `VITE_API_URL` (in Vercel — your HF Spaces backend URL)

### Optional (Recommended)

- [ ] `REDIS_URL` (for persistent sessions — survives restarts)
- [ ] `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- [ ] `SENTRY_DSN` (error tracking)
- [ ] `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` (LLM observability)

### Build Verification

- [ ] `cd frontend && npm ci`
- [ ] `npm run build` — verify 0 errors
- [ ] `npm run test` — verify 0 failures
- [ ] `npx playwright test` — verify 0 skips

## Deployment Targets

### Primary: Hugging Face Spaces (Docker)
- Port: 7860
- Auto-synced from GitHub `main` via `sync-to-hf.yml`
- Single-origin FastAPI serving React SPA + API

### Secondary: Vercel (Frontend-only SPA)
- Build: `cd frontend && npm run build`
- Output: `frontend/dist`
- Set `VITE_API_URL` to HF Spaces backend URL

### Tertiary: Render (Docker)
- `render.yaml` configured with correct env vars (V243 fix)
- Health check: `/api/health`

## Post-Deployment

- [ ] Verify `/api/health` returns 200
- [ ] Verify login flow (POST /api/v1/auth/login)
- [ ] Verify protected routes redirect to /login when unauthenticated
- [ ] Verify CORS headers correct
- [ ] Verify CSP headers present
- [ ] Verify HSTS header present
- [ ] Run Lighthouse audit (target: 80+ Perf, 100 A11y/BP/SEO)
- [ ] Monitor Sentry for errors
- [ ] Monitor Langfuse for LLM usage

## Ongoing

- [ ] Add unit tests for safety-critical engine modules (done — 95 tests)
- [ ] Add Redis for session storage (done — V244)
- [ ] Add rate limiting to all routers (done — 104+ endpoints)
- [ ] Migrate useApi → React Query (scheduled v2.0)
