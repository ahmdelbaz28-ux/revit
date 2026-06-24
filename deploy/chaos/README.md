# Chaos Engineering — FireAI Platform

> **V133 (2026-06-21)** — Five scheduled Chaos Mesh experiments to
> verify resilience during business hours (10:00-14:00 UTC, Mon-Fri).

## Experiments

| # | Experiment | Verifies | Schedule |
|---|-----------|----------|----------|
| 1 | Pod-kill (API) | HPA spins up replacement + LB routes around killed pod within 30s | Every 30 min, 10-14 UTC, Mon-Fri |
| 2 | Network latency (API↔PG) | API degrades gracefully (timeout + retry, not crash) under DB slowness | Daily 11:00 UTC, Mon-Fri |
| 3 | Redis failover | Redis Cluster fails over to replica without queue loss | Daily 11:30 UTC, Mon-Fri |
| 4 | Disk pressure (Worker) | Worker handles disk-full gracefully (log + alert, not silent corruption) | Daily 12:00 UTC, Mon-Fri |
| 5 | DNS blackout | Pods cache critical service DNS and don't crash on transient failures | Daily 12:30 UTC, Mon-Fri |

## Prerequisites

1. **Chaos Mesh** installed in the cluster:
   ```bash
   helm repo add chaos-mesh https://charts.chaos-mesh.org
   helm install chaos-mesh chaos-mesh/chaos-mesh \
     --namespace chaos-mesh \
     --create-namespace \
     --set chaosDaemon.runtime=containerd \
     --set dashboard.create=true
   ```

2. **ServiceAccount** for FireAI chaos experiments (the experiment
   manifests reference labels, not ServiceAccounts — but the Chaos Mesh
   controller needs RBAC to manage experiments in the `fireai` namespace).

3. **Slack webhook** (optional) for experiment notifications:
   ```bash
   kubectl -n chaos-mesh create secret generic slack-webhook \
     --from-literal=webhook-url=https://hooks.slack.com/services/...
   ```

## Enabling chaos engineering

Chaos engineering is **disabled by default**. Enable it only after
validating in staging:

```bash
helm upgrade fireai ./deploy/helm/fireai \
  --set chaosEngineering.enabled=true
```

## Monitoring experiments

```bash
# List all experiments
kubectl -n chaos-mesh get podchaos,networkchaos,iochaos,dnschaos

# Watch a specific experiment
kubectl -n chaos-mesh describe podchaos fireai-chaos-pod-kill-api

# View experiment history
kubectl -n chaos-mesh get events --field-selector reason=ChaosInjected
```

## Safety controls

Every experiment has multiple safety controls:

1. **Duration** — every experiment auto-rolls back after its `duration`
   expires. No experiment runs indefinitely.

2. **Business-hours only** — all schedules run 10:00-14:00 UTC, Mon-Fri.
   No experiments run at 3am when on-call engineers are asleep.

3. **`startingDeadlineSeconds: 300`** — if the Chaos Mesh controller
   is down for more than 5 minutes, missed schedules are skipped
   (not retroactively fired).

4. **`chaosEngineering.enabled` master toggle** — one command disables
   ALL experiments:
   ```bash
   helm upgrade fireai ./deploy/helm/fireai \
     --set chaosEngineering.enabled=false
   ```

5. **Label selectors** — every experiment targets ONLY FireAI-labeled
   resources. No experiment can affect other namespaces.

## Alerting

The Prometheus alert rules in `deploy/observability/prometheus-alert-rules.yml`
include alerts for chaos experiment failures:

- `ChaosExperimentFailed` — an experiment failed to inject or roll back
- `ChaosExperimentStuck` — an experiment has been running longer than
  its `duration` (controller may be down)

## Disabling during incidents

During a real production incident, disable all chaos experiments:

```bash
helm upgrade fireai ./deploy/helm/fireai \
  --set chaosEngineering.enabled=false \
  --reuse-values
```

Or use the Chaos Mesh CLI:

```bash
# Pause all schedules
kubectl -n chaos-mesh annotate schedule --all chaos-mesh.org/pause=true

# Resume all schedules
kubectl -n chaos-mesh annotate schedule --all chaos-mesh.org/pause-
```

## Adding new experiments

1. Add the experiment config to `values.yaml` under
   `chaosEngineering.experiments.*`
2. Add the experiment manifest to `templates/enterprise/chaos-experiments.yaml`
3. Test in staging FIRST — never test a new experiment in production
4. Document the experiment in this README's table above

## References

- [Chaos Mesh docs](https://chaos-mesh.org/docs/)
- [Chaos Mesh GitHub](https://github.com/chaos-mesh/chaos-mesh)
- [Principles of Chaos Engineering](https://principlesofchaos.org/)
- [NFPA 72 §14.4](https://www.nfpa.org/codes-and-standards/) — Inspection,
  testing, and maintenance (the inspiration for chaos testing FireAI)
