# FireAI Deployment Guide

## Docker Deployment (Recommended)

### Prerequisites
- Docker 20.10+ and Docker Compose 2.0+
- Cryptographically generated API key and HMAC key

### Steps

1. Generate secrets:
```bash
export FIREAI_API_KEY=$(openssl rand -hex 32)
export FIREAI_EVIDENCE_HMAC_KEY=$(openssl rand -hex 32)
```

2. Deploy:
```bash
docker compose up -d
```

3. Verify:
```bash
curl http://localhost:8000/api/health
# Expected: {"success":true,"data":{"status":"ok","version":"1.0.0"}}
```

### Container Security
- Runs as non-root `fireai` user
- Read-only filesystem (except `/data` and `/logs` volumes)
- tmpfs for `/tmp` (100MB, ephemeral)
- `no-new-privileges:true` security option
- Health check every 30s with 3 retries

## Manual Deployment (Linux)

### Prerequisites
- Python 3.12+
- Node.js 18+ (for frontend build)

### Steps

1. Install:
```bash
pip install -r requirements.txt
pip install fireai[workflow]  # optional
pip install fireai[memory]    # optional
```

2. Configure:
```bash
cp .env.example .env
# Edit .env with production secrets
```

3. Build frontend:
```bash
cd frontend && npm install && npm run build
```

4. Start:
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --workers 4
```

5. Verify:
```bash
curl http://localhost:8000/api/health
```

## Production Checklist

- [ ] `FIREAI_ENV=production` set
- [ ] `FIREAI_API_KEY` is cryptographically generated (not `dev-test-key`)
- [ ] `FIREAI_EVIDENCE_HMAC_KEY` is cryptographically generated
- [ ] CORS origins explicitly configured (no wildcards)
- [ ] Secrets managed by secrets manager (not `.env` file)
- [ ] Frontend build served via FastAPI static mount
- [ ] Health check endpoint responding
- [ ] Database persistence volume configured
- [ ] Log aggregation configured
- [ ] Rate limits appropriate for traffic

## Rollback Strategy

1. Docker: `docker compose down` → redeploy previous image
2. Manual: Stop uvicorn, revert git commit, restart
3. Database: SQLite WAL mode supports atomic rollback within a session