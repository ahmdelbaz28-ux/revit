# FireAI Configuration Guide

## Environment Variables

All configuration is handled through environment variables. Copy `.env.example` to `.env` and customize.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `FIREAI_API_KEY` | API key for authentication. Required in production. | `sk-...your-key...` |
| `FIREAI_EVIDENCE_HMAC_KEY` | HMAC-SHA256 key for audit log integrity. Must be cryptographically generated. | `openssl rand -hex 32` |
| `FIREAI_ENV` | Environment mode. `production` or `development`. | `production` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREAI_DB_PATH` | Override audit database path | `data/fireai_audit.db` |
| `LOG_LEVEL` | Logging verbosity | `WARNING` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins | — |
| `FIREAI_MEMORY_LLM_PROVIDER` | LLM provider for memory service | `gemini` |
| `FIREAI_MEMORY_LLM_MODEL` | LLM model for memory service | `gemini-2.0-flash` |
| `GEMINI_API_KEY` | Gemini API key for optional AI features | — |
| `FIREAI_PDF_MAX_FILE_SIZE_BYTES` | Max PDF file size | `52428800` |
| `FIREAI_DWG_MAX_FILE_SIZE_BYTES` | Max DWG file size | `52428800` |
| `FIREAI_IMAGE_MAX_FILE_SIZE_BYTES` | Max image file size | `10485760` |

## Production Configuration

### Security Requirements

1. **API Key**: Generate with `openssl rand -hex 32`. Never use dev keys.
2. **HMAC Key**: Generate with `openssl rand -hex 32`. Dev fallback is blocked in production.
3. **CORS**: Wildcards (`*`) are ALWAYS rejected in production. Specify explicit origins.
4. **Secrets**: Use a secrets manager (Vault, AWS Secrets, etc.) — NOT `.env` files.

### Docker Configuration

```yaml
# docker-compose.yml requires:
FIREAI_API_KEY: ${FIREAI_API_KEY:?ERROR: must be set}
FIREAI_EVIDENCE_HMAC_KEY: ${FIREAI_EVIDENCE_HMAC_KEY:?ERROR: must be set}
```

The container runs as non-root `fireai` user with read-only filesystem and tmpfs for `/tmp`.

## Development Configuration

Set `FIREAI_ENV=development` to relax certain security checks:
- CORS wildcards allowed (for local development only)
- HMAC key defaults to dev key (WARNING: not for production)
- Debug logging enabled