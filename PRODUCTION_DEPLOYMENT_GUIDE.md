# BAZSPARK — Production Deployment Guide
**Date:** 2026-07-17  
**Status:** CRITICAL ACTIONS REQUIRED BEFORE DEPLOYMENT

---

## ⚠️ CRITICAL: Supabase Project Replacement Required

**Issue Confirmed:** The configured Supabase project `<SUPABASE_PROJECT_REF>.supabase.co` does not exist (DNS failure).

**Impact:** Production deployment will fail because the database is unreachable.

### Required Action Steps:

#### 1. Create New Supabase Project (Recommended)

```bash
# Step 1: Create project at https://supabase.com/dashboard
# Project name: bazspark-production
# Region: Choose closest to your users

# Step 2: After creation, update .env with new values:
SUPABASE_URL=https://<NEW_PROJECT_REF>.supabase.co
SUPABASE_ANON_KEY=<new_anon_key>
SUPABASE_SERVICE_ROLE_KEY=<new_service_role_key>
DATABASE_URL=postgresql://postgres:<password>@db.<NEW_PROJECT_REF>.supabase.co:5432/postgres?sslmode=require

# Step 3: Test connectivity
python -c "from backend.database import get_db; db = get_db(); print('PostgreSQL connected:', db._is_postgres)"
```

#### 2. Alternative: Use Neon PostgreSQL

```env
# Add to .env
NEON_DATABASE_URL=postgresql://bazspark_owner:<password>@ep-xyz.us-east-2.aws.neon.tech/bazspark?sslmode=require

# The codebase will automatically fall back to Neon if Supabase fails
```

---

## 🔴 Pre-Deployment Checklist

### A. Fix Database Connectivity

- [ ] **Create new Supabase project** OR configure Neon fallback
- [ ] Update `DATABASE_URL` in `.env`
- [ ] Update `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- [ ] Test database connection: `python -c "from backend.database import get_db; db = get_db(); print('OK')"`
- [ ] Verify `NEON_DATABASE_URL` is set as fallback

### B. Fix CORS Configuration

- [x] ~~Update `backend/app.py` to support both `CORS_ORIGINS` and `CORS_ALLOWED_ORIGINS`~~ ✅ DONE
- [ ] Set production origins in `.env`: `CORS_ORIGINS=https://your-domain.com`
- [ ] Test CORS headers: `curl -I -H "Origin: https://your-domain.com" https://your-api.com/api/health`

### C. Credential Rotation (MANDATORY)

**All tokens must be rotated before production:**

```bash
# 1. GitHub PAT
gh auth refresh
# Update .env: GH_PAT=<new_token>

# 2. HuggingFace Token
# Regenerate at https://huggingface.co/settings/tokens
# Update .env: HF_TOKEN=<new_token>

# 3. Langfuse Keys
# Regenerate at https://cloud.langfuse.com/settings/keys
# Update .env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

# 4. Resend API Key
# Regenerate at https://resend.com/api_keys
# Update .env: RESEND_API_KEY

# 5. Box Integration
# Regenerate at https://account.box.com/developers/console
# Update .env: BOX_CLIENT_SECRET, BOX_DEVELOPER_TOKEN

# 6. Vercel Token
# Regenerate at https://vercel.com/account/tokens
# Update .env: VERCEL_DEPLOY_TOKEN

# 7. Daytona Token
# Regenerate at https://app.daytona.io/settings/api
# Update .env: DAYTONA_API_TOKEN

# 8. CodeSandbox Token
# Regenerate at https://codesandbox.io/settings/account
# Update .env: CODESANDBOX_TOKEN

# 9. Cloudflare Tokens
# Regenerate at https://dash.cloudflare.com/profile/api-tokens
# Update .env: CLOUDFLARE_USER_TOKEN_1, CLOUDFLARE_USER_TOKEN_2, CLOUDFLARE_USER_TOKEN_3

# 10. NVIDIA API Key
# Regenerate at https://build.nvidia.com/settings/keys
# Update .env: NVIDIA_API_KEY
```

### D. Environment Configuration

- [ ] Set `FIREAI_ENV=production` in production environment
- [ ] Set `FIREAI_SESSION_SECRET` to a strong random value (min 43 chars)
- [ ] Set `CORS_ORIGINS` to production domains
- [ ] Verify `DATABASE_URL` points to production PostgreSQL
- [ ] Set `LANGFUSE_ENABLED=true` for monitoring

---

## 🟡 Recommended Before Production

### E. Enable Optional Databases

**Redis (for sessions, rate limiting, caching):**
```env
REDIS_URL=redis://your-redis:6379/0
REDIS_PASSWORD=<password>
```

**Qdrant (for RAG/vector search):**
```env
QDRANT_URL=https://your-qdrant-cluster.com
QDRANT_API_KEY=<api_key>
```

**Neo4j (for graph relationships):**
```env
NEO4J_URI=bolt://your-neo4j:7687
NEO4J_PASSWORD=<password>
```

### F. Security Hardening

- [ ] Review and update `CSP_CONNECT_SRC` for production domains
- [ ] Set `CSP_UNSAFE_EVAL=false` (unless absolutely necessary)
- [ ] Enable `FIREAI_CSRF_PROTECTION=true` for browser clients
- [ ] Configure rate limits in production
- [ ] Set up Akamai/Cloudflare WAF rules

### G. Monitoring & Observability

- [ ] Verify Langfense ingestion (check https://cloud.langfuse.com)
- [ ] Set up alerts for `/api/health` endpoint
- [ ] Configure Prometheus scraping (if using monitor router)
- [ ] Enable audit log rotation

---

## ✅ Deployment Steps

### Step 1: Prepare Code

```bash
# Ensure .env is NOT committed
git add .gitignore
git commit -m "chore: ensure .env is ignored"

# Commit all fixes
git add backend/app.py .env PRODUCTION_DEPLOYMENT_GUIDE.md
git commit -m "fix: CORS backward compatibility + Neon fallback + deployment guide

- Support both CORS_ORIGINS and CORS_ALLOWED_ORIGINS
- Add NEON_DATABASE_URL fallback for IPv4 environments
- Document Supabase replacement requirement
- Add production deployment checklist

Refs: PRODUCTION_VERIFICATION_SUMMARY.md"
```

### Step 2: Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel --prod

# Or use GitHub integration (auto-deploy on push to main)
git push origin main
```

### Step 3: Deploy to HuggingFace Space

```bash
# The Space auto-syncs from GitHub
# Or manually deploy:
huggingface-cli upload ahmdelbaz28/BAZSPARK ./ hf
```

### Step 4: Verify Deployment

```bash
# Test health endpoint
curl https://your-domain.com/api/health

# Test CORS
curl -I -H "Origin: https://your-frontend.com" https://your-api.com/api/health

# Test database
curl https://your-domain.com/api/database-health

# Test API authentication
curl -H "X-API-Key: your_key" https://your-domain.com/api/v1/projects
```

---

## 🚨 Rollback Plan

If deployment fails:

1. **Database:** Code falls back to SQLite if PostgreSQL fails
2. **CORS:** Code supports both `CORS_ORIGINS` and `CORS_ALLOWED_ORIGINS`
3. **Previous deployment:** Vercel keeps previous deployment, rollback via `vercel rollback`
4. **Git:** Revert commit if needed: `git revert HEAD`

---

## 📋 Post-Deployment Verification

```bash
# 1. Health check
curl https://your-domain.com/api/health | jq .

# 2. Database connectivity
curl https://your-domain.com/api/database-health | jq .

# 3. CORS headers present?
curl -I -H "Origin: https://app.bazspark.com" https://your-domain.com/api/health

# 4. Authentication working?
curl -H "X-API-Key: $FIREAI_API_KEY" https://your-domain.com/api/v1/projects

# 5. Langfuse receiving traces?
# Check https://cloud.langfuse.com

# 6. Audit log writing?
curl https://your-domain.com/api/v1/audit-log | jq .
```

---

## 🔐 Security Checklist

- [ ] `.env` is NOT in git (verify with `git ls-files | grep .env`)
- [ ] All tokens rotated (old tokens revoked)
- [ ] `FIREAI_SESSION_SECRET` is strong (43+ chars)
- [ ] `CORS_ORIGINS` set to production domains only
- [ ] `CSP_UNSAFE_EVAL=false` in production
- [ ] Database uses SSL (`sslmode=require`)
- [ ] API keys are hashed (check `db/api_keys.json`)
- [ ] Audit log is writing to database
- [ ] Rate limiting enabled
- [ ] HTTPS enforced (HSTS header present)

---

## 📞 Support

If issues arise:

1. Check logs: `docker logs fireai-api` or `vercel logs`
2. Review audit trail in database `audit_log` table
3. Check Langfuse for errors
4. Review this guide's troubleshooting section

---

## ✅ Final Sign-Off

**Prepared by:** Automated Audit + Engineering Team  
**Reviewed by:** _______________  
**Approved for Production:** _______________  
**Date:** _______________

**Deployed by:** _______________  
**Deployment timestamp:** _______________  
**Verified by:** _______________

---

*This guide must be completed and signed off before production deployment.*