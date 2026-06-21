# Velero Backups — FireAI Platform

> **V133 (2026-06-21)** — Tiered backup schedules for point-in-time recovery.

## Schedules

| Schedule | Frequency | Retention | Includes | Purpose |
|----------|-----------|-----------|----------|---------|
| Hourly | `0 * * * *` | 24h | PV snapshots + FireAI namespace | 1 day of PV-level PITR |
| Daily | `30 2 * * *` | 720h (30d) | PV snapshots + K8s resources | 1 month of resource-level recovery |
| Weekly | `0 4 * * 0` | 5040h (90d) | K8s resources only | ~3 months of weekly recovery |

## Point-in-time recovery (PITR)

Combined with PostgreSQL WAL archiving (every 60s to S3), this provides
PITR to **any second** within the 30-day retention window:

1. **Restore the daily backup** closest to (but before) the target time
   via Velero: `velero restore create --from-backup fireai-daily-2026-06-20`
2. **Replay WAL files** from the target time forward using `pg_walfile_restore`
3. **Verify** the database state matches the target time

This satisfies **NFPA 72 §14.6** audit-trail retention requirements.

## Setup

See `deploy/dr/README.md` for the full setup procedure including:
- S3 bucket creation with versioning + lifecycle
- Velero server installation
- IAM role / ServiceAccount configuration
- Cross-region replication for DR

## Lifecycle policies

- `backup-lifecycle.json` — Velero backup bucket lifecycle (1d/30d/90d tiers)
- `wal-lifecycle.json` — PostgreSQL WAL archive bucket lifecycle (30d)

## PostgreSQL quiesce hooks

The daily and hourly backup schedules include pre/post hooks that run
`pg_start_backup()` and `pg_stop_backup()` on the PostgreSQL primary
before/after the PV snapshot. This ensures the on-disk files are a
valid backup that can be recovered with WAL replay.

If the PostgreSQL primary is unavailable when a backup runs, the hook
will fail and the backup is aborted (not silently corrupted). Monitor
the `VeleroBackupFailed` Prometheus alert.

## Verifying backups

```bash
# List all backups
velero backup get

# Verify a backup is complete
velero backup describe fireai-hourly-2026-06-21-0600 --details

# Test restore to a separate namespace (non-destructive)
velero restore create \
  --from-backup fireai-hourly-2026-06-21-0600 \
  --namespace-mappings fireai:fireai-restore-test \
  --wait

# Verify the restore
kubectl -n fireai-restore-test get all

# Clean up
kubectl delete namespace fireai-restore-test
```

## Restore procedures

### Full namespace restore (disaster recovery)

See `deploy/dr/README.md` → "Failover procedure".

### Single-resource restore (accidental deletion)

```bash
# Restore just the accidentally-deleted ConfigMap
velero restore create \
  --from-backup fireai-hourly-2026-06-21-0600 \
  --include-resources configmap \
  --include-namespaces fireai \
  --selector app.kubernetes.io/name=fireai-config \
  --wait
```

### Point-in-time database recovery

```bash
# 1. Restore the PV snapshot from the closest hourly backup
velero restore create \
  --from-backup fireai-hourly-2026-06-21-0600 \
  --include-resources persistentvolumeclaim \
  --include-namespaces fireai \
  --selector app.kubernetes.io/name=postgresql-ha \
  --wait

# 2. Replay WAL files from 06:00 to the target time (e.g., 06:45:30)
#    on the restored PostgreSQL primary
kubectl -n fireai exec -it postgresql-ha-0 -- \
  pg_walfile_restore \
    --source s3://fireai-prod-wal-archive/ \
    --target-time "2026-06-21 06:45:30 UTC"
```

## Monitoring

Prometheus alerts (in `deploy/observability/prometheus-alert-rules.yml`):

- `VeleroBackupFailed` — a backup failed (hook error, S3 error, etc.)
- `VeleroBackupStale` — no successful backup in 2 hours (hourly schedule broken)
- `VeleroRestoreFailed` — a restore failed (would block DR failover)

Grafana dashboard: `deploy/observability/grafana-dashboards/fireai-overview.json`
includes a "Backups" panel showing backup success rate and restore time.
