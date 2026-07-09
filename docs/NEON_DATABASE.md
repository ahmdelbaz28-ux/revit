# Neon Postgres — BAZSPARK Production Database

## Connection Details

| Field | Value |
|-------|-------|
| **Provider** | [Neon](https://neon.tech) (free tier) |
| **Project ID** | `divine-bar-17848047` |
| **Branch ID** | `br-round-mode-at9cfb4a` (primary, `production`) |
| **Branch name** | `production` |
| **Database** | `bazspark` |
| **Role** | `bazspark_owner` |
| **Region** | `aws-us-east-1` |
| **PostgreSQL version** | 18.4 |
| **PG version (numeric)** | 18 |
| **Direct host (IPv4)** | `ep-restless-surf-atp743eu.c-9.us-east-1.aws.neon.tech` |
| **Pooled host (IPv4)** | `ep-restless-surf-atp743eu-pooler.c-9.us-east-1.aws.neon.tech` |
| **IPv4 address (direct)** | `52.45.105.76` |
| **IPv4 address (pooled)** | `3.220.135.142` |
| **Pooler mode** | transaction (PgBouncer) |
| **Autoscaling** | 0.25 – 2 CU |
| **Suspend timeout** | 0 (always-on, scales to zero on idle) |

## Connection Strings

> **The password is stored ONLY as a HuggingFace Space secret.** It is NOT
> committed to the repository. If you need to rotate it, see
> [Rotation](#rotation) below.

### Production (used by HuggingFace BAZSPARK Space)

```text
postgresql://bazspark_owner:<PASSWORD>@ep-restless-surf-atp743eu.c-9.us-east-1.aws.neon.tech/bazspark?sslmode=require
```

This is the **direct** (non-pooled) endpoint — chosen because:
1. It resolves to IPv4 (`52.45.105.76`) — required by the deployment target.
2. The BAZSPARK Docker container runs a single uvicorn worker, so connection
   pooling is handled by SQLAlchemy's queue pool, not PgBouncer.
3. Lower latency than the pooled variant (no extra hop).

### Serverless / Alternative (pooled)

Use this variant only if deploying to a serverless platform that rapidly
recycles connections (e.g. Vercel Functions, AWS Lambda):

```text
postgresql://bazspark_owner:<PASSWORD>@ep-restless-surf-atp743eu-pooler.c-9.us-east-1.aws.neon.tech/bazspark?sslmode=require
```

## Schemas

After `alembic upgrade head` (revision `001`), the `bazspark` database contains:

| Table | Purpose |
|-------|---------|
| `alembic_version` | Migration tracking |
| `projects` | FireAI engineering projects |
| `devices` | Devices registered per project |
| `connections` | Device-to-device connections |
| `reports` | Generated compliance reports (PDF/DXF/Excel) |
| `sync_operations` | BIM sync operations log |
| `sync_status` | Sync status tracking |

## Deployment Wiring

### HuggingFace Space (production)

`DATABASE_URL` is registered as a **Space secret** (not a variable) on
`ahmdelbaz28/BAZSPARK`. The Dockerfile intentionally does NOT set
`DATABASE_URL` — it reads it from the HF secret at runtime.

To update the secret:

```bash
# Use the HF API (requires a token with write scope on the Space)
curl -X POST \
  -H "Authorization: Bearer $HF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"DATABASE_URL","value":"postgresql://..."}' \
  https://huggingface.co/api/spaces/ahmdelbaz28/BAZSPARK/secrets
```

Or via the web UI:
<https://huggingface.co/spaces/ahmdelbaz28/BAZSPARK/settings>

### Local Development

Local dev defaults to SQLite (see `env.example.txt`):

```text
DATABASE_URL=sqlite:///./db/digital_twin.db
```

To test against Neon locally, override `DATABASE_URL` in your shell:

```bash
export DATABASE_URL="postgresql://bazspark_owner:<PASSWORD>@ep-restless-surf-atp743eu.c-9.us-east-1.aws.neon.tech/bazspark?sslmode=require"
alembic upgrade head      # apply migrations
uvicorn backend.app:app --reload   # start backend
```

## Migrations

The repo uses Alembic. Migration scripts live under `alembic/versions/`. To
apply migrations to the Neon database:

```bash
export DATABASE_URL="postgresql://bazspark_owner:<PASSWORD>@ep-restless-surf-atp743eu.c-9.us-east-1.aws.neon.tech/bazspark?sslmode=require"
cd /path/to/revit
alembic upgrade head
```

To check current revision:

```bash
alembic current
```

## Rotation

If the `bazspark_owner` password is compromised:

```bash
# 1. Rotate via Neon API (returns the new password)
curl -X PUT \
  -H "Authorization: Bearer $NEON_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role":{"name":"bazspark_owner"}}' \
  https://console.neon.tech/api/v2/projects/divine-bar-17848047/branches/br-round-mode-at9cfb4a/roles/bazspark_owner

# 2. Build the new DATABASE_URL with the new password.

# 3. Update the HF Space secret:
curl -X POST \
  -H "Authorization: Bearer $HF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"DATABASE_URL","value":"postgresql://...new_password..."}' \
  https://huggingface.co/api/spaces/ahmdelbaz28/BAZSPARK/secrets

# 4. The HF Space rebuilds automatically.
```

## Verification

To verify the connection works:

```bash
psql "postgresql://bazspark_owner:<PASSWORD>@ep-restless-surf-atp743eu.c-9.us-east-1.aws.neon.tech/bazspark?sslmode=require" \
  -c "SELECT version(), current_database(), inet_server_addr()::text;"
```

Expected output:

```
                              version                               | current_database | inet_server_addr
--------------------------------------------------------------------+------------------+------------------
 PostgreSQL 18.4 on aarch64-unknown-linux-gnu ...                  | bazspark         | 169.254.254.254
```

The `169.254.254.254` link-local address is Neon's internal proxy IP — it
confirms the connection is being routed through Neon's IPv4 proxy.
