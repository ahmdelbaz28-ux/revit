# FireAI Digital Twin — Installation Guide

## Prerequisites

- **Python 3.12+** (3.14 supported)
- **Node.js 18+** and npm (9+ (for frontend build)
- **Git** 2.30+

## Quick Start (Development)

```bash
# 1. Clone the repository
git clone https://github.com/ahmdelbaz28-ux/revit.git
cd revit

# 2. Create environment configuration
cp .env.example .env
# Edit .env and set:
#   FIREAI_API_KEY=<your-api-key>
#   FIREAI_EVIDENCE_HMAC_KEY=<your-hmac-key>
#   FIREAI_ENV=development

# 3. Install Python dependencies (P0.3: pyproject.toml is SSoT, requirements.txt removed)
pip install .

# 4. Install optional features (if needed)
pip install fireai[workflow]   # LangGraph workflow engine
pip install fireai[memory]     # Mem0 + Qdrant long-term memory
pip install fireai[ifc]        # IFC (ifcopenshell) support

# 5. Install dev tools (for testing/linting)
pip install -e ".[dev]"

# 6. Start the API server
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000

# 7. Build and serve the frontend
cd frontend
npm install
npm run build

# 8. Run the test suite
pytest tests/ -v
```

## Docker Deployment (Production)

```bash
# 1. Set required environment variables
export FIREAI_API_KEY="your-production-api-key"
export FIREAI_EVIDENCE_HMAC_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

# 2. Build and run with Docker Compose
docker compose up -d

# 3. Verify health check
curl http://localhost:8000/api/health
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FIREAI_API_KEY` | Yes | API key for authentication. Mutating endpoints require `X-API-Key` header. |
| `FIREAI_EVIDENCE_HMAC_KEY` | Yes | HMAC-SHA256 key for audit log integrity. Must be cryptographically generated for production. |
| `FIREAI_ENV` | No | `development` or `production`. Defaults to `production`. |
| `FIREAI_DB_PATH` | No | Override path for audit database. Defaults to `data/fireai_audit.db`. |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR`. Defaults to `WARNING`. |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated origins for CORS. Wildcards always rejected in production. |
| `GEMINI_API_KEY` | No | Required only for workflow/memory optional features. |

## Platform-Specific Notes

### Windows
- Use Python 3.12+ (not the system Python 3.8)
- Ensure `python3` or `py -3` points to the correct Python version
- SQLite file locks may require explicit `close()` calls before temp file cleanup

### macOS/Linux
- Standard installation procedure works
- `/tmp/` paths are valid for default database locations

## Verification Checklist

- [ ] Server starts without errors: `python -m uvicorn backend.app:app`
- [ ] Health check returns 200: `curl http://localhost:8000/api/health`
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Frontend builds: `cd frontend && npm run build`
- [ ] Linting passes: `ruff check fireai/ backend/ parsers/`