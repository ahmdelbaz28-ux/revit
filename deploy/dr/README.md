# Multi-Region Disaster Recovery — FireAI Platform

> **V133 (2026-06-21)** — Active-passive multi-region deployment with
> Velero backups and PostgreSQL WAL archiving for point-in-time recovery.

## Architecture

```
                     ┌─────────────────────────────────────┐
                     │     Global DNS (Route53 / Cloud DNS) │
                     │     fireai.example.com (CNAME, 60s)  │
                     └────────────┬────────────────────────┘
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
        ┌─────────────────┐             ┌─────────────────┐
        │  PRIMARY REGION │             │ SECONDARY REGION │
        │   us-east-1     │             │    us-west-2     │
        │                 │             │  (warm standby)  │
        │  API: 3-20 pods │             │  API: 1 pod      │
        │  Worker: 2-20   │             │  Worker: 0       │
        │  PG: 1 primary  │             │  PG: 1 primary   │
        │  Redis: 6 nodes │             │  Redis: 6 nodes  │
        └────────┬────────┘             └────────┬────────┘
                 │                               │
                 │  Velero hourly backup ───────►│
                 │  WAL archive (60s) ──────────►│
                 │                               │
                 └───── Cross-region S3 ─────────┘
                        (versioned, lifecycle)
```

## RPO / RTO

| Metric | Target | How |
|--------|--------|-----|
| **RPO** (data loss) | 1 hour | Velero hourly backups + 60s WAL archive |
| **RTO** (recovery time) | 15 minutes | DNS failover + warm pod startup |

## Prerequisites

1. **Two Kubernetes clusters** in different regions (e.g., EKS us-east-1 + us-west-2)
2. **Velero** installed in both clusters: [velero.io/docs](https://velero.io/docs/)
3. **Cross-region S3 bucket** for Velero backups (versioned, lifecycle-managed)
4. **Cross-region S3 bucket** for PostgreSQL WAL archives
5. **Global DNS** with health checks (Route53, Cloud DNS, or Cloudflare)
6. **Helm 3.8+** installed locally

## Initial setup

### 1. Create the S3 buckets

```bash
# Velero backups bucket — must be in a THIRD region or use cross-region replication
aws s3api create-bucket --bucket fireai-velero-backups --region us-east-1
aws s3api put-bucket-versioning --bucket fireai-velero-backups \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket fireai-velero-backups \
  --lifecycle-configuration file://deploy/dr/velero/backup-lifecycle.json

# PostgreSQL WAL archive bucket — separate from Velero for independent retention
aws s3api create-bucket --bucket fireai-prod-wal-archive --region us-east-1
aws s3api put-bucket-versioning --bucket fireai-prod-wal-archive \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket fireai-prod-wal-archive \
  --lifecycle-configuration file://deploy/dr/velero/wal-lifecycle.json
```

### 2. Install Velero in both clusters

```bash
# Primary cluster (us-east-1)
aws eks update-kubeconfig --name fireai-prod-us-east-1 --region us-east-1
velero install \
  --provider aws \
  --bucket fireai-velero-backups \
  --backup-location-config region=us-east-1 \
  --snapshot-location-config region=us-east-1 \
  --secret-file credentials-velero \
  --use-volume-snapshots=true

# Secondary cluster (us-west-2)
aws eks update-kubeconfig --name fireai-prod-us-west-2 --region us-west-2
velero install \
  --provider aws \
  --bucket fireai-velero-backups \
  --backup-location-config region=us-west-2 \
  --snapshot-location-config region=us-west-2 \
  --secret-file credentials-velero \
  --use-volume-snapshots=true
```

### 3. Deploy to the primary region

```bash
aws eks update-kubeconfig --name fireai-prod-us-east-1 --region us-east-1
helm install fireai ./deploy/helm/fireai \
  --namespace fireai \
  --create-namespace \
  --set multiRegion.enabled=false \
  --set velero.backupStorageLocation.bucket=fireai-velero-backups \
  --set velero.backupStorageLocation.region=us-east-1 \
  --set postgresqlHA.walArchive.destination=s3://fireai-prod-wal-archive/
```

### 4. Deploy to the secondary region (standby mode)

```bash
aws eks update-kubeconfig --name fireai-prod-us-west-2 --region us-west-2
helm install fireai ./deploy/helm/fireai \
  --namespace fireai \
  --create-namespace \
  --set multiRegion.enabled=true \
  --set multiRegion.secondary.standby=true \
  --set velero.backupStorageLocation.bucket=fireai-velero-backups \
  --set velero.backupStorageLocation.region=us-west-2 \
  --set postgresqlHA.walArchive.destination=s3://fireai-prod-wal-archive/
```

The secondary region will:
- Scale Worker to 0 (no duplicate job processing)
- Reduce API to 1 replica (warm standby)
- Disable Ingress (no external traffic)
- Mark all resources with `fireai.io/dr-role: standby`

## Failover procedure

When the primary region fails:

### 1. Halt Velero backups in the failed primary

```bash
# Switch to primary context
aws eks update-kubeconfig --name fireai-prod-us-east-1 --region us-east-1

# Pause all Velero schedules
velero schedule pause fireai-hourly
velero schedule pause fireai-daily
velero schedule pause fireai-weekly
```

### 2. Restore the latest backup in the secondary region

```bash
# Switch to secondary context
aws eks update-kubeconfig --name fireai-prod-us-west-2 --region us-west-2

# Find the latest successful backup
LATEST_BACKUP=$(velero backup get -o json | \
  jq -r '.items | sort_by(.status.startTimestamp) | last | .metadata.name')

# Restore it
velero restore create --from-backup "$LATEST_BACKUP" --wait
```

### 3. Promote the secondary to primary

```bash
helm upgrade fireai ./deploy/helm/fireai \
  --namespace fireai \
  --set multiRegion.enabled=true \
  --set multiRegion.secondary.standby=false \
  --set velero.backupStorageLocation.bucket=fireai-velero-backups \
  --set velero.backupStorageLocation.region=us-west-2 \
  --set postgresqlHA.walArchive.destination=s3://fireai-prod-wal-archive/
```

This will:
- Scale Worker back up (HPA resumes)
- Scale API back to 3-20 (HPA resumes)
- Re-enable Ingress
- Remove the `fireai.io/dr-role: standby` label

### 4. Update DNS

```bash
# Route53 example — point the CNAME at the secondary region's hostname
aws route53 change-resource-record-sets --hosted-zone-id Z1234567890ABC \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "fireai.example.com",
        "Type": "CNAME",
        "TTL": 60,
        "ResourceRecords": [{"Value": "fireai-dr.example.com"}]
      }
    }]
  }'
```

### 5. Switch WAL archive destination

Update the WAL archive bucket to point at the new primary region's bucket
(so the new primary starts archiving WALs for the next failover).

## Failback procedure

Once the original primary region is healthy:

1. Restore the latest backup from the (now-primary) secondary region
2. Deploy to the original primary in standby mode
3. Verify the standby is healthy
4. Swap DNS back to the original primary's hostname
5. Promote the original primary (set `standby=false`)
6. Demote the secondary back to standby

## Testing

### Monthly DR drill

Run a full failover + failback on the first Saturday of every month:

```bash
# 1. Announce maintenance window (15 min)
# 2. Run failover procedure above
# 3. Verify the application is healthy in the secondary region
# 4. Run failback procedure
# 5. Document any issues in the DR drill report
```

### Chaos engineering validation

The chaos experiments in `deploy/helm/fireai/templates/enterprise/chaos-experiments.yaml`
verify that:
- HPA recovers from pod kills within 30s
- API degrades gracefully under database latency
- Redis Cluster fails over without queue loss
- Worker handles disk pressure without corrupting the audit chain
- Pods survive DNS blackouts via cached resolution

See `deploy/chaos/README.md` for chaos engineering setup.

## Compliance

This DR setup satisfies:
- **NFPA 72 §14.6** — Audit-trail retention (PITR to any second within 30d)
- **ISO 22301** — Business continuity (RPO 1h, RTO 15m, documented procedures)
- **SOC 2 Type II** — Availability (multi-region, automated backups, DR drills)
