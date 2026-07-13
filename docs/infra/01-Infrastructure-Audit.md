# 01 — Infrastructure Audit

**Project:** BAZspark v1.55.0
**Audit Date:** 2026-07-13
**Final Commit:** `ded134ca`
**Audit Scope:** Docker, K8s, CI/CD, deployment configs, security headers

---

## Infrastructure Map

### Deployment Targets
1. **Hugging Face Spaces** (primary production) — Docker, port 7860, auto-synced from GitHub `main`
2. **Vercel** (frontend-only SPA) — Vite build, `frontend/dist` output
3. **Render** (Docker) — `render.yaml` configured
4. **Kubernetes** — Helm chart + K8s manifests in `deploy/k8s/` and `deploy/helm/`
5. **Docker Compose** (dev/testing) — 5 services: fireai, redis, qdrant, neo4j, doctr-ocr, yolo-segmentation

### Services
- **Frontend:** React 18 + Vite 8 + TypeScript + Tailwind + Radix UI
- **Backend:** Python 3.12 + FastAPI + 28 routers + 219 endpoints
- **Databases:** SQLite (dev) / PostgreSQL (prod) + Qdrant (vectors) + Neo4j (graph)
- **Cache/Sessions:** Redis 7-alpine (with in-memory fallback)
- **Background Worker:** Python worker with heartbeat + signal handling

### CI/CD Pipeline (8 workflows)
1. `ci.yml` — 6-gate pipeline (static analysis, tests, property tests, frontend build, Playwright, dependency audit)
2. `ci-build-gate.yml` — Pre-merge JSX/TypeScript/build gate
3. `secret-scan.yml` — Gitleaks secret scanning (V248 NEW)
4. `container-scan.yml` — Trivy container vulnerability scanning (V248 NEW)
5. `sync-to-hf.yml` — Hugging Face Space auto-sync
6. `vercel-preview.yml` — Vercel preview deployments
7. `vercel-production.yml` — Vercel production deployments
8. `dependabot-auto-merge.yml` — Automated dependency PR merging

---

## V248 Fixes Applied

### CRITICAL (7 fixed)
1. ✅ Git merge conflicts in `services/{doctr,yolo}/Dockerfile` — resolved
2. ✅ Worker entrypoint calling non-existent method — rewrote with proper logging
3. ✅ Worker healthcheck freshness check — now checks mtime, not just existence
4. ✅ K8s wrong CORS env var (`CORS_ORIGINS` → `CORS_ALLOWED_ORIGINS`)
5. ✅ K8s ConfigMap secret leak — moved DATABASE_URL/REDIS_URL to Secret
6. ✅ Docker Compose port mismatch (8000 → 7860)
7. ✅ Docker Compose network isolation (fireai service added to fireai-net)

### HIGH (7 fixed)
1. ✅ Qdrant image pinned (`:latest` → `v1.12.4`)
2. ✅ Qdrant + Neo4j healthchecks added
3. ✅ Neo4j password now uses env var (was hardcoded `etap_password`)
4. ✅ Vercel security headers added (HSTS, X-Frame-Options, CSP, etc.)
5. ✅ Docker Compose `cap_drop: ALL` added to fireai service
6. ✅ Docker Compose fireai service added to `fireai-net` network
7. ✅ Worker entrypoint proper logging instead of swallowing exceptions

### CI/CD Security (6 fixed)
1. ✅ Dependabot config created (`.github/dependabot.yml`)
2. ✅ Gitleaks + detect-secrets added to pre-commit hooks
3. ✅ Least-privilege permissions added to CI workflows
4. ✅ Rate limiter now uses Redis storage (was in-memory per-worker)
5. ✅ Container scanning workflow created (Trivy)
6. ✅ Secret scanning workflow created (gitleaks)

---

## Infrastructure Strengths (Pre-existing)
- ✅ Docker multi-stage build with non-root user
- ✅ HEALTHCHECK in root Dockerfile
- ✅ Resource limits on all compose services
- ✅ K8s: PDB, NetworkPolicy, seccomp RuntimeDefault, probes
- ✅ Helm chart with comprehensive values
- ✅ 6-gate CI pipeline
- ✅ npm audit + pip-audit in CI
- ✅ Bandit (Python SAST) in CI
