# FireAI Troubleshooting Guide

## Common Issues

### Backend Won't Start

**Symptom**: `ModuleNotFoundError: No module named 'X'`

**Fix**:
```bash
pip install .
# For optional features:
pip install fireai[workflow]  # if you need /api/workflow
pip install fireai[memory]    # if you need /api/memory
pip install fireai[ifc]       # if you need IFC export
```

**Symptom**: `FIREAI_API_KEY must be set`

**Fix**: Set environment variable:
```bash
export FIREAI_API_KEY=$(openssl rand -hex 32)
export FIREAI_EVIDENCE_HMAC_KEY=$(openssl rand -hex 32)
```

### CORS Errors

**Symptom**: Browser shows CORS policy errors

**Fix**: In `.env`, set `CORS_ALLOWED_ORIGINS=https://your-domain.com`
- NEVER use `*` in production
- Development mode allows wildcards automatically

### Database Locked (Windows)

**Symptom**: `PermissionError: [WinError 32]` on SQLite files

**Fix**: This is a Windows-specific SQLite file locking issue. Ensure all connections are closed before file operations. Use `DeltaCache.persist()` or `AuditLog.close()` before cleanup.

### 503 Service Unavailable on /api/workflow or /api/memory

**Symptom**: Optional endpoints return 503

**Fix**: Install optional dependencies:
```bash
pip install fireai[workflow]  # requires langgraph
pip install fireai[memory]    # requires mem0 + qdrant-client
```

### Health Check Failing

**Symptom**: `/api/health` returns non-200

**Fix**: Check:
1. Database path is accessible and writable
2. Core modules can be imported: `python -c "from fireai.core.qomn_kernel import QOMNKernel"`
3. Environment variables are set correctly

### Frontend Not Loading

**Symptom**: Blank page or API-only mode

**Fix**: Build and serve frontend:
```bash
cd frontend && npm install && npm run build
# Backend auto-serves frontend/dist when it exists
```

### Parser Security Errors

**Symptom**: File parsing returns "path rejected" errors

**Fix**: This is intentional security behavior. Paths with null bytes, traversal sequences, or leading dashes are rejected. Ensure file paths are clean.

## Getting Help

1. Check logs: `LOG_LEVEL=DEBUG` for detailed output
2. Review ARCHITECTURE.md for system design
3. Check API docs: `http://localhost:8000/docs` (Swagger UI)