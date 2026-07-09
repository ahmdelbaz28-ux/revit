# BAZSPARK — Standard Database Configuration

This document describes the **standard dual-database configuration** used in
production (HuggingFace BAZSPARK Space + Vercel `revit` project).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Backend (FastAPI)                            │
│                                                                     │
│   backend/database.py::Database.__init__()                          │
│       │                                                             │
│       ▼                                                             │
│   _init_postgres()                                                  │
│       │                                                             │
│       │  1. Try DATABASE_URL (Supabase — standard primary)          │
│       │     │                                                       │
│       │     ▼                                                       │
│       │   smoke-test connection (SELECT 1)                          │
│       │     │                                                       │
│       │     ├── OK ──► use Supabase for all queries                 │
│       │     │                                                       │
│       │     └── FAIL (IPv6 unreachable on HF free tier)             │
│       │           │                                                 │
│       │           ▼                                                 │
│       │     2. Fall back to NEON_DATABASE_URL (IPv4 direct)         │
│       │           │                                                 │
│       │           ▼                                                 │
│       │         use Neon for all queries                            │
│       │                                                             │
│       ▼                                                             │
│   _init_schema_pg()  ◄── CREATE TABLE IF NOT EXISTS (idempotent)    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
        │                                  │
        ▼                                  ▼
┌────────────────────┐         ┌──────────────────────────────────┐
│   Supabase         │         │   Neon                           │
│   (primary)        │         │   (IPv4 fallback)                │
│                    │         │                                  │
│   host: db.<ref>   │         │   host: ep-xxx.c-9.us-east-1     │
│   port: 5432       │         │   port: 5432                     │
│   IPv6: yes        │         │   IPv4: 52.45.105.76             │
│   IPv4: no         │         │   IPv6: yes                      │
│                    │         │                                  │
│   ⚠ unreachable    │         │   ✓ reachable from any container │
│     from HF free   │         │     runtime                      │
│     tier           │         │                                  │
└────────────────────┘         └──────────────────────────────────┘
```

## Why two databases?

1. **Supabase is the standard primary** — matches the original project setup
   and provides additional services (Auth, Storage, Realtime, Edge Functions)
   that the project may consume via REST API.

2. **Neon is the IPv4 fallback** — HuggingFace Spaces free tier does NOT
   support outbound IPv6 connections, and Supabase's direct Postgres
   endpoint (`db.<ref>.supabase.co:5432`) is IPv6-only. Without a fallback,
   the HF Space health check reports `database: "disconnected"` and all DB
   queries fail. Neon's direct endpoint supports IPv4, so the backend can
   always reach it.

3. **Both are configured simultaneously** — the code's `_init_postgres`
   method tries `DATABASE_URL` first, then `NEON_DATABASE_URL`. This makes
   both databases "work together" automatically.

## Environment variables

### HuggingFace Space (`ahmdelbaz28/BAZSPARK`)

| Secret | Purpose |
|--------|---------|
| `DATABASE_URL` | Supabase direct Postgres URL (standard primary) |
| `NEON_DATABASE_URL` | Neon IPv4 Postgres URL (fallback) |
| `SUPABASE_URL` | `https://<ref>.supabase.co` (for REST API) |
| `SUPABASE_ANON_KEY` | Supabase anon JWT (for client-side REST) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service_role JWT (for server-side REST) |
| `FIREAI_API_KEY` | FireAI platform API key |
| `FIREAI_SESSION_SECRET` | Session cookie signing secret |
| `LANGFUSE_*` | Langfuse observability (3 vars) |
| `DIGITAL_TWIN_DB_PATH` / `UDM_DB_PATH` | SQLite fallback paths |
| `CORS_ALLOWED_ORIGINS` | CORS allowlist |

### Vercel project (`revit`)

Same env vars as above, plus Vercel-Postgres-integration compatibility
vars (all populated with Neon credentials since Neon has IPv4):

| Env var | Value |
|---------|-------|
| `POSTGRES_URL` | Neon connection URL |
| `POSTGRES_PRISMA_URL` | Neon connection URL (Prisma format) |
| `POSTGRES_URL_NON_POOLING` | Neon direct URL (no PgBouncer) |
| `POSTGRES_HOST` | `ep-restless-surf-atp743eu.c-9.us-east-1.aws.neon.tech` |
| `POSTGRES_USER` | `bazspark_owner` |
| `POSTGRES_PASSWORD` | `npg_DxS8IsBMAg6Q` |
| `POSTGRES_DATABASE` | `bazspark` |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon JWT |

## Verification

### HF Space health

```bash
curl https://ahmdelbaz28-bazspark.hf.space/api/health
# Expected:
#   "status": "ok"
#   "database": "connected"   ← was "disconnected" before this fix
#   "udm_database": "connected"
```

### Local test (simulate HF Space env)

```bash
export DATABASE_URL="postgresql://postgres:<PW>@db.<ref>.supabase.co:5432/postgres?sslmode=require"
export NEON_DATABASE_URL="postgresql://bazspark_owner:<PW>@ep-xxx.c-9.us-east-1.aws.neon.tech/bazspark?sslmode=require"
python -c "from backend.database import get_db; print(get_db().list_projects(page=1, limit=1))"
# Expected log line:
#   Primary DATABASE_URL failed (OperationalError); falling back to NEON_DATABASE_URL ...
# Expected output:
#   {'total': 0, 'items': [], 'page': 1, 'limit': 1, ...}
```

## Connection details

### Supabase

| Field | Value |
|-------|-------|
| Project ref | `nrdqdnmyxbbdrrmqxzej` |
| Project name | `mmx-agent-1777931988324` |
| Region | `us-east-1` |
| Postgres version | 17.6.1.113 |
| Direct host | `db.nrdqdnmyxbbdrrmqxzej.supabase.co` (IPv6-only) |
| PgBouncer host | `db.nrdqdnmyxbbdrrmqxzej.supabase.co:6543` (IPv6-only) |
| Supavisor pooler | NOT ENABLED for this project (would give IPv4) |
| REST base URL | `https://nrdqdnmyxbbdrrmqxzej.supabase.co/rest/v1/` |
| Status | ACTIVE_HEALTHY |

### Neon

| Field | Value |
|-------|-------|
| Project ID | `divine-bar-17848047` |
| Branch | `br-round-mode-at9cfb4a` (primary, name=`production`) |
| Database | `bazspark` |
| Role | `bazspark_owner` |
| Region | `aws-us-east-1` |
| Postgres version | 18.4 |
| Direct host (IPv4) | `ep-restless-surf-atp743eu.c-9.us-east-1.aws.neon.tech` |
| IPv4 address | `52.45.105.76` |
| Pooled host (IPv4) | `ep-restless-surf-atp743eu-pooler.c-9.us-east-1.aws.neon.tech` |
| Plan | free |

## How to add Supabase IPv4 pooler (future work)

If you want Supabase itself to be reachable via IPv4 (eliminating the
Neon fallback), enable the **Supavisor** pooler:

1. Go to <https://supabase.com/dashboard/project/nrdqdnmyxbbdrrmqxzej/settings/database>
2. Click "Enable Connection Pooler" (Supavisor)
3. The new pooler host will be `aws-0-us-east-1.pooler.supabase.com` (IPv4)
4. Update `DATABASE_URL` to use the pooler URL with tenant prefix:
   ```
   postgresql://postgres.nrdqdnmyxbbdrrmqxzej:<PW>@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
   ```
5. Once verified, the Neon fallback becomes unnecessary (but keep it as
   a safety net).

## Code reference

- `backend/database.py::_init_postgres` — fallback chain implementation
- `backend/database.py::_scalar` — cursor-backend-aware scalar reader
  (handles both SQLite tuples and PostgreSQL RealDictCursor dicts)
- `backend/config.py::Config.DATABASE_URL` — reads `DATABASE_URL` env var
- `alembic/env.py` — uses `DATABASE_URL` for migrations (apply to Neon
  via `DATABASE_URL=...neon... alembic upgrade head`)
