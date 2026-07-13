# 04 — Cloud Security

**Project:** BAZspark v1.55.0
**Audit Date:** 2026-07-13

---

## Cloud Security Posture: STRONG ✅

### Encryption at Rest
- ✅ Database: PostgreSQL supports encryption at rest (Supabase/Neon managed)
- ✅ Redis: Append-only file persistence with optional encryption
- ✅ File uploads: Stored in `/app/data` (container volume, access-controlled)

### Encryption in Transit
- ✅ HSTS enforced: `max-age=63072000; includeSubDomains; preload`
- ✅ HTTPS required in production (cookie `Secure` flag set when `FIREAI_ENV=production`)
- ✅ Backend enforces HTTPS redirect in production mode
- ✅ WebSocket: `wss://` in production CSP `connect-src`

### TLS/SSL Configuration
- ✅ Hugging Face Spaces: Auto-TLS via Let's Encrypt
- ✅ Vercel: Auto-TLS via Vercel managed certificates
- ✅ K8s: TLS secret configured (`deploy/k8s/secret.yaml` → `fireai-tls`)
- ✅ Nginx: TLS termination configured (when used as reverse proxy)

### Least Privilege
- ✅ Docker: Non-root user (`appuser`, UID 1000) in all Dockerfiles
- ✅ Docker Compose: `cap_drop: ALL` + `no-new-privileges:true` (V248)
- ✅ K8s: `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `seccompProfile: RuntimeDefault`
- ✅ CI/CD: Least-privilege `permissions:` blocks (V248)

### Secrets Management
- ✅ K8s: Secrets in `Secret` resources (not ConfigMaps) — V248 fix
- ✅ Docker Compose: Env vars from `.env` file (git-ignored)
- ✅ Session secrets: File-based option (`FIREAI_SESSION_SECRET_FILE`)
- ✅ No hardcoded secrets in source code
- ✅ `.env` properly git-ignored
- ✅ `.env.example` uses placeholders (V243 fix)

### Network Isolation
- ✅ Docker Compose: `fireai-net` bridge network for service-to-service (V248)
- ✅ K8s: NetworkPolicy restricts ingress/egress
- ✅ CORS: Production fails-fast on missing or wildcard origins
- ✅ Allowed hosts: Configurable via `CORS_ALLOWED_ORIGINS`

### Firewall / Access Control
- ✅ Rate limiting: 104+ endpoints protected (V244-V246)
- ✅ Auth middleware: All endpoints except `/auth/login`, `/health`, `/docs` require auth
- ✅ CSRF middleware: All state-changing requests require CSRF token
- ✅ Path traversal protection on all file upload endpoints

### Public Endpoints (intentionally public)
- `GET /api/health` — Health check (no sensitive data)
- `POST /api/v1/auth/login` — Authentication (rate-limited)
- `GET /api/v1/auth/csrf-token` — CSRF token issuance

All other endpoints require authentication + authorization.
