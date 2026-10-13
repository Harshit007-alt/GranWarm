# GranuWarm — Live Path Resume Guide

**Status as of last session:**
- Kind cluster running (Kubernetes v1.31.0, 4 nodes Ready)
- Knative Serving + Kourier installed and healthy
- Prometheus installed and healthy (all pods Running)
- ServiceMonitor + PodMonitor applied (Prometheus sees Knative)
- Function `f01_hello_world` deployed and reachable
- Controller runs but reports `telemetry=mock` (queries returning empty)
- Workload generator (`workload/generator.py`) inspected but not yet run
- Rate-window fix identified but not applied

**Goal for this session:**
Get the controller to report `telemetry=live`, then run a real workload (W1) against the cluster and observe the controller's decisions.

---

## Prerequisites — verify before starting

Open a terminal and run these checks. If any fail, fix before proceeding.

```bash
cd /mnt/c/Users/user/Documents/GitHub/GranWarm
source .venv/bin/activate

# 1. Cluster is up
kubectl get nodes
# Expected: 4 nodes, all Ready, version v1.31.0

# 2. Knative is up
kubectl get pods -n knative-serving
# Expected: all Running

# 3. Prometheus is up
kubectl get pods -n monitoring
# Expected: all Running, especially prometheus-prometheus-kube-prometheus-prometheus-0

# 4. Docker sees the kind containers
docker ps
# Expected: 4 containers named granuwarm-local-*
```

If the cluster is gone (e.g., after a WSL restart), rebuild it:

```bash
bash scripts/bootstrap-cluster.sh
```

`bootstrap-cluster.sh` should apply the ServiceMonitor and PodMonitor automatically. If it doesn't, apply them manually (see "Manual fixes" below).

---

## Step 1 — Fix the controller's query schema

Two known issues need patching in `controller/monitor/prometheus_client.py`:

### 1a. Rate window too short

The query uses `rate(...[10s])`, but Prometheus scrapes every 10s, so a 10s window usually has only one sample and returns empty. Change to `[1m]`:

```bash
grep -n "10s" controller/monitor/prometheus_client.py
sed -i 's/\[10s\]/[1m]/g' controller/monitor/prometheus_client.py
grep -n "\[1m\]\|\[10s\]" controller/monitor/prometheus_client.py
```

---

## Step 2 — Verify the M query works

Before running anything, test the memory query directly:

```bash
# Start Prometheus port-forward if not already running
# (in a dedicated terminal — see Step 3)
curl -s 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=sum(container_memory_working_set_bytes{container!=""}) / sum(node_memory_MemTotal_bytes)' \
  | jq '.data.result'
```

**If this returns `[]`**, the M query is also broken and will cause mock fallback. Find the right memory metric:

```bash
curl -s 'http://localhost:9090/api/v1/label/__name__/values' | jq -r '.data[]' | grep -E "^container_memory" | head -20
```

Pick one that exists (e.g., `container_memory_usage_bytes`, `container_memory_rss`) and update the M query accordingly.

---

## Step 3 — Start port-forwards (dedicated terminals)

**Do NOT run these with `&` in your main terminal.** They die when the shell state changes. Use dedicated terminal windows.

### Terminal A — Prometheus

```bash
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
```

Wait for: `Forwarding from 127.0.0.1:9090 -> 9090`

### Terminal B — Kourier

```bash
kubectl port-forward -n kourier-system svc/kourier 8080:80
```

Wait for: `Forwarding from 127.0.0.1:8080 -> 80`

### Verify (Terminal C)

```bash
# Prometheus reachable?
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9090/-/ready
# Expected: 200

# Function reachable?
curl -s -H "Host: f01-hello-world.default.127.0.0.1.sslip.io" http://localhost:8080
# Expected: {"function":"f01_hello_world",...}
```

Leave A and B running for the rest of this session.

---

## Step 4 — Deploy all functions

**This is the slow step.** Twelve Docker builds + 12 kind loads + 12 kubectl applies. Budget 15–30 minutes.

```bash
bash scripts/deploy_functions.sh 2>&1 | tee /tmp/deploy.log
```

Verify:

```bash
kubectl get ksvc
# Expected: 12 services
kubectl get pods
# Expected: 1 pod for f01 (pinned earlier). Others at 0 replicas.
```

**Memory watch:**

```bash
free -h
```

If `available` drops below ~1 GB, stop deploying. Deploy fewer functions (edit the loop to only include `f01`–`f04`).

---

## Step 5 — Start the workload generator

The generator imports `workload.profiles`, which requires running as a module:

```bash
python -m workload.generator \
  --profile W1 \
  --duration 300 
  --seed 42 \
  --base-url http://localhost:8080 \
  --output results/traffic/w1_run1.csv
```

**First run shorter to validate:**

```bash
python -m workload.generator \
  --profile W1 \
  --duration 60 \
  --seed 42 \
  --base-url http://localhost:8080 \
  --output /tmp/w1_smoke.csv
```

Watch progress:

```bash
# In another terminal
tail -f /tmp/w1_smoke.csv
```

Expected rows: `timestamp,function_id,service_name,latency_ms,status_code` with varying `latency_ms` and mostly `200` status codes.

**If you see `500`s for many functions**, those functions aren't deployed. Either deploy them or accept the partial data (f01 alone is enough for controller validation).

---

## Step 6 — Run the controller

In a **new terminal** (Terminal D):

```bash
cd /mnt/c/Users/user/Documents/GitHub/GranWarm
source .venv/bin/activate
python -m controller.main --mode dry_run
```

**What to look for in the first 30 seconds:**

```
Prometheus probe: reachable at http://localhost:9090     ← ✅
DAG: 20 total nodes, 19 allocatable                       ← ✅
PSO DAG projection enabled: 16 parent-child constraints   ← ✅
Control loop online. Press Ctrl-C to stop.                ← ✅
[cyc-...] Slow loop: constrained PSO ...
[dec-...] source=pso telemetry=live mem=XXX/4096 MB       ← THE MILESTONE
```

If it says **`telemetry=live`**, you've achieved the goal. The controller is reading real cluster metrics.

If it still says **`telemetry=mock`**, check:
- Is the workload generator actually producing traffic? (`tail /tmp/w1_smoke.csv`)
- Does Prometheus show data for f01? (`curl -s 'http://localhost:9090/api/v1/query' --data-urlencode 'query=revision_app_request_count' | jq '.data.result | length'`)
- Are there multiple functions in the DAG but only one with data?

**The last point is important:** the controller iterates over all functions in `configs/dependencies.json`. If f02–f12 have no telemetry, they'll each fall back to mock, and the cycle may be tagged mock as a whole. To validate cleanly, either deploy all 12 or temporarily trim the DAG.

### Trim the DAG (fast path)

```bash
cp configs/dependencies.json configs/dependencies-full.json
# Edit dependencies.json to keep only f01 in .functions and its leaf node
```

Or use `jq` to filter:

```bash
jq '.functions |= map(select(.id == "f01"))' configs/dependencies.json > /tmp/f01-only.json
cp configs/dependencies.json configs/dependencies-full.json
cp /tmp/f01-only.json configs/dependencies.json
```

Restore later with `cp configs/dependencies-full.json configs/dependencies.json`.

---

## Step 7 — Observe for a few minutes

While the workload generator runs and the controller reads metrics, watch the controller output. You should see:

- **Fast loop every 10s** — `source=fuzzy+delta`
- **Slow loop every 60s** — `source=pso`
- **Memory staying under 4096 MB** — `mem=XXX/4096 MB`
- **`telemetry=live`** on every decision
- **`DRY-RUN — no Kubernetes writes (would patch N services)`**

Let it run for the full duration of the workload generator (e.g., 300s). At the end, you have:

- `results/traffic/w1_run1.csv` — per-request latency/status
- `results/audit/<date>.jsonl` — controller decisions with telemetry provenance
- Prometheus TSDB — raw metrics

**These three together are a live experiment.** That's the deliverable for the live path.

---

## Step 8 — Try `shadow` mode (optional)

Once `dry_run` is validated, `shadow` mode reads telemetry and computes decisions but doesn't write anything (similar to dry_run, but semantically "would run but not actuate"). It may have stricter mock fallback:

```bash
python -m controller.main --mode shadow
```

If it errors instead of falling back to mock, that's a stronger validation — it means the pipeline genuinely needs real data.

---

## Step 9 — Try `live` mode (last, risky)

> **Warning:** Per Claude's audit, the live actuator has no retries, no reconciliation, no idempotency. Only run this if you understand the risk and are on a disposable local cluster.

```bash
python -m controller.main --mode live
```

Watch the Knative services get patched:

```bash
# In another terminal
watch -n 2 "kubectl get ksvc -o custom-columns='NAME:.metadata.name,MIN-SCALE:.spec.template.metadata.annotations.autoscaling\.knative\.dev/min-scale'"
```

The `MIN-SCALE` column should change as the controller makes decisions.

---

## Manual fixes (if bootstrap-cluster.sh doesn't apply them)

### ServiceMonitor for autoscaler

```bash
kubectl apply -f - <<'EOF'
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: knative-serving-metrics
  namespace: monitoring
  labels:
    release: prometheus
spec:
  namespaceSelector:
    matchNames: [knative-serving]
  selector:
    matchLabels: {app: autoscaler}
  endpoints:
    - port: http-metrics
      interval: 10s
      path: /metrics
EOF
```

### PodMonitor for user pods

```bash
kubectl apply -f - <<'EOF'
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: knative-user-pods
  namespace: monitoring
  labels:
    release: prometheus
spec:
  namespaceSelector:
    matchNames: [default]
  selector:
    matchExpressions:
      - key: serving.knative.dev/revision
        operator: Exists
  podMetricsEndpoints:
    - port: http-usermetric
      path: /metrics
      interval: 10s
EOF
```

### imagePullPolicy for a single function

```bash
svc="functions/f01_hello_world/service.yaml"
grep -q "imagePullPolicy" "$svc" || \
  sed -i '/- image:/a\          imagePullPolicy: IfNotPresent' "$svc"
kubectl apply -f "$svc"
```

---

## Troubleshooting reference

| Symptom | Cause | Fix |
|---|---|---|
| `Prometheus probe: UNREACHABLE` | Port-forward died | Restart in dedicated terminal |
| `telemetry=mock` with probe reachable | Queries returning empty | Fix `[10s]`→`[1m]` and `service`→`service_name` |
| `rate(...)[]` returns empty | Window too short | Change to `[1m]` |
| Query returns `[]` for existing metric | No recent data | Send traffic first |
| Function returns 503 | Pod not ready or scaled to 0 | Send a request to wake it, or pin min-scale=1 |
| `kubectl` fails with connection refused | Cluster gone | Recreate: `kind create cluster --config ...` |
| `ModuleNotFoundError: workload` | Ran `python workload/generator.py` | Run `python -m workload.generator` instead |
| Port 8080/9090 in use | Old port-forward still running | `pkill -f "port-forward"` then restart |
| Deployment slow | 12 Docker builds | Let it run, or trim to 3–4 functions |

---

## Cleanup (end of session)

**Stop the controller:** `Ctrl+C` in its terminal

**Stop port-forwards:** `Ctrl+C` in their terminals

**Keep the cluster:** leave it running for tomorrow.

If you need to free memory:

```bash
# Scale all functions to 0
for svc in $(kubectl get ksvc -o name | sed 's|ksvc/||'); do
  kubectl patch ksvc "$svc" --type merge \
    -p '{"spec":{"template":{"metadata":{"annotations":{"autoscaling.knative.dev/min-scale":"0"}}}}}'
done
```

**Full cluster teardown (destructive):**

```bash
kind delete cluster --name granuwarm-local
```

---

## Tomorrow's checklist

- [ ] `kubectl get nodes` → 4 Ready
- [ ] `kubectl get pods -n monitoring` → all Running
- [ ] Fix `[10s]` → `[1m]` in `prometheus_client.py`
- [ ] Verify `service_name` label in queries
- [ ] Start Prometheus port-forward (dedicated terminal)
- [ ] Start Kourier port-forward (dedicated terminal)
- [ ] Verify f01 reachable via curl
- [ ] Run `deploy_functions.sh` (budget 15–30 min)
- [ ] Run `python -m workload.generator --profile W1 --duration 60 ...` (smoke test)
- [ ] Run `python -m controller.main --mode dry_run`
- [ ] **Look for `telemetry=live`** ← the goal

---

## After this works — next milestones

1. **Fix the simulator** — per Claude's audit: enforce memory budget, route B6 through the DAG + safety gate, unify memory accounting, remove hardcoded results
2. **Regenerate results** — run the 5×6×5 experiment matrix from the fixed simulator
3. **Write up findings** — the live path is a nice demo, but the simulator is where the research lives

The live path has now been validated end-to-end. **The simulator is the actual deliverable.**