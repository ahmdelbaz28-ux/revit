# FireAI Maintenance Guide

## Routine Maintenance Tasks

### Daily
- [ ] Check health endpoint: `curl http://localhost:8000/api/health`
- [ ] Monitor logs for warnings/errors
- [ ] Verify disk space for data/ and logs/ volumes

### Weekly
- [ ] Review audit log size (`data/fireai_audit.db`)
- [ ] Check for stale SQLite WAL files
- [ ] Review rate-limit logs for abuse patterns
- [ ] Verify HMAC key rotation schedule

### Monthly
- [ ] Rotate HMAC signing keys (requires app restart)
- [ ] Review and update CORS allowed origins
- [ ] Audit API key usage patterns
- [ ] Review bandit security scan results
- [ ] Update dependencies: `pip-audit --strict`

## Database Maintenance

### Audit Database (SQLite)
The audit database stores tamper-evident hash chains for all engineering results.

```bash
# Check database size
ls -lh data/fireai_audit.db

# Vacuum to reclaim space (requires brief downtime)
sqlite3 data/fireai_audit.db "VACUUM;"
```

### UDM Elements Database
```bash
# Check database size
ls -lh data/udm_elements.db

# Integrity check
sqlite3 data/udm_elements.db "PRAGMA integrity_check;"
```

## Log Management

### Log Rotation
Logs are written via loguru. Configure rotation in environment:
```
LOG_LEVEL=WARNING
```

### Cleanup
```bash
# Remove logs older than 30 days
find logs/ -name "*.log" -mtime +30 -delete
```

## Monitoring

### Health Check
```bash
curl http://localhost:8000/api/health
# Expected: {"success":true,"data":{"status":"ok","version":"1.0.0"}}
```

### Key Metrics
- Response latency (target: <200ms for NFPA 72 calculations)
- Memory usage (target: <500MB)
- Database connection pool health
- Rate-limit rejection count

## Upgrades

### Steps
1. Pull latest code: `git pull origin main`
2. Install dependencies: `pip install .`
3. Build frontend: `cd frontend && npm install && npm run build`
4. Run tests: `pytest tests/ -v`
5. Stop service: `docker compose down` or kill uvicorn process
6. Start service: `docker compose up -d` or restart uvicorn
7. Verify health: `curl http://localhost:8000/api/health`