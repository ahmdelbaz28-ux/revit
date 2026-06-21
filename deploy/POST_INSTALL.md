# Enterprise Infrastructure — Post-Install Steps

> **V133 (2026-06-21)** — Required manual steps after `helm install` to
> fully activate the enterprise infrastructure additions.

## 1. Redis Cluster Bootstrap (REQUIRED after first install)

The Helm chart deploys 6 Redis pods (3 masters + 3 replicas), but they
start as **standalone instances**. You MUST run `redis-cli --cluster
create` to form them into a cluster.

### Prerequisites

- `redis-cli` installed locally (or use `kubectl exec` into a Redis pod)
- The Redis password (from the `fireai-secrets` Secret, key `REDIS_PASSWORD`)

### Bootstrap procedure

```bash
# Get the Redis password
REDIS_PASSWORD=$(kubectl -n fireai get secret fireai-secrets \
  -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d)

# Get the Redis pod hostnames (3 masters + 3 replicas = 6 pods)
REDIS_PODS=$(kubectl -n fireai get pods -l app.kubernetes.io/name=redis-cluster \
  -o jsonpath='{range .items[*]}{.metadata.name}.fireai-redis-cluster.fireai.svc.cluster.local:6379 {end}')

# Form the cluster (3 masters + 3 replicas, 1 replica per master)
kubectl -n fireai exec -it fireai-redis-cluster-0 -- redis-cli \
  --cluster create $REDIS_PODS \
  --cluster-replicas 1 \
  -a "$REDIS_PASSWORD" \
  --cluster-yes

# Verify the cluster is healthy
kubectl -n fireai exec -it fireai-redis-cluster-0 -- redis-cli \
  -a "$REDIS_PASSWORD" cluster info
```

Expected output: `cluster_state:ok` and `cluster_slots_assigned:16384`.

### Why this isn't automated

Redis Cluster formation requires all 6 pods to be running and reachable
before the `--cluster create` command can succeed. The Helm chart can't
guarantee this during `helm install` (pods may still be starting). The
bootstrap must be run manually after all pods are Ready.

For automated deployments, use an init Job:

```yaml
# Add this as a post-install hook in your values.yaml overlay
apiVersion: batch/v1
kind: Job
metadata:
  name: redis-cluster-bootstrap
  annotations:
    "helm.sh/hook": post-install
    "helm.sh/hook-weight": "10"
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: redis-cli
          image: redis:7.2-alpine
          command: ["/bin/sh", "-c"]
          args:
            - |
              # Wait for all 6 pods to be ready
              # ... (full bootstrap script here)
```

## 2. PostgreSQL HA Configuration

The PostgreSQL StatefulSet uses the bitnami/postgresql image with
`POSTGRESQL_REPLICATION_MODE: master` on all pods initially. After
install, the bitnami image's entrypoint will:

1. Initialize the primary (pod 0) as a fresh PostgreSQL instance
2. Initialize replicas (pods 1-2) by streaming from the primary

**No manual action required** — the bitnami image handles replication
setup automatically via the `POSTGRESQL_REPLICATION_*` env vars.

### Verify HA is working

```bash
# Check that pod 0 is the primary
kubectl -n fireai exec fireai-postgresql-ha-0 -- \
  psql -U postgres -c "SELECT pg_is_in_recovery();"
# Expected: f (false = primary)

# Check that pods 1-2 are replicas
kubectl -n fireai exec fireai-postgresql-ha-1 -- \
  psql -U postgres -c "SELECT pg_is_in_recovery();"
# Expected: t (true = replica)
```

## 3. Velero Schedules

The Velero schedules are created automatically in the `velero` namespace.
No manual action required — Velero will start taking hourly/daily/weekly
backups immediately.

### Verify schedules are active

```bash
velero schedule get
# Expected:
# NAME                STATUS    CREATED                SCHEDULE       BACKUP TTL
# fireai-hourly       Enabled   2026-06-21T...         0 * * * *      24h
# fireai-daily        Enabled   2026-06-21T...         30 2 * * *     720h
# fireai-weekly       Enabled   2026-06-21T...         0 4 * * 0      5040h
```

## 4. Chaos Mesh Experiments

Chaos experiments are **disabled by default**. Enable them only after
validating in staging:

```bash
helm upgrade fireai ./deploy/helm/fireai \
  --set chaosEngineering.enabled=true
```

Experiments run during business hours only (10-14 UTC, Mon-Fri). See
`deploy/chaos/README.md` for monitoring and safety controls.
