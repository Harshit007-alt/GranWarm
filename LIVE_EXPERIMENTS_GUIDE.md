# Live Cluster Experiments - Complete Guide

## 🎯 Goal
Run **real end-to-end experiments** on your Kubernetes cluster with:
- ✅ Real HTTP traffic → Knative services
- ✅ Real Prometheus metrics (no mocks)
- ✅ Controller actuating real K8s
- ✅ Measure actual latency, cold starts, memory

---

## 📊 Current Status

### What You Have Now:
- ❌ 150 experiments from **simulator** (synthetic data)
- ✅ Kubernetes cluster running
- ✅ Prometheus running
- ✅ Knative installed
- ✅ Traffic generator implemented
- ✅ Controller working
- ❌ **Function images not built** → services failing

### What You Need:
1. ✅ Build Docker images for functions
2. ✅ Load images into Kind cluster
3. ✅ Verify services are Ready
4. ✅ Run experiments with real traffic
5. ✅ Collect real metrics
6. ✅ Generate plots from live data

---

## 🚀 Quick Start (2 Hours to First Results)

### **Step 1: Build & Load Function Images** (30 mins)

```bash
cd ~/Documents/GitHub/GranWarm

# Make scripts executable
chmod +x scripts/build_and_load_images.sh
chmod +x scripts/deploy_simple_services.sh

# Build all function images and load into Kind
# (If already built and loaded, skip build_and_load_images.sh)
./scripts/build_and_load_images.sh

# Deploy services with correct routing and resource limits
./scripts/deploy_simple_services.sh

# Verify services are Ready
kubectl get ksvc -n default
```

**Expected output:**
```
NAME                   URL                                          READY
f01-hello-world        http://f01-hello-world.default...            True
f02-json-transform     http://f02-json-transform.default...         True
...
```

---

### **Step 2: Test Traffic Generator** (5 mins)

```bash
# Port-forward Knative ingress
kubectl port-forward -n kourier-system svc/kourier 8080:80 &

# Generate 60 seconds of test traffic
python -m workload.generator \
  --profile W3 \
  --duration 60 \
  --seed 42 \
  --base-url http://localhost:8080 \
  --config configs/dependencies_light.json \
  --output results/test_traffic.csv

# Check results
head -20 results/test_traffic.csv
```

**Expected output:**
```
timestamp,function_id,service_name,latency_ms,status_code,error
1729134201.2345,f01,f01-hello-world,245.67,200,
1729134201.5678,f02,f02-json-transform,156.23,200,
```

If you see `status_code=200` and latency numbers, **it's working!** ✅

---

### **Step 3: Run ONE Live Experiment**

You can run the automated script directly:
```bash
# Run automated live experiment (e.g., duration 60s, wait 15s)
./run_one_experiment.sh 60 15

# Or full 5-minute experiment
./run_one_experiment.sh 300 30
```

Alternatively, run controller and traffic generator manually:
```bash
# Create results directory
mkdir -p results/live_experiments

# Run controller + traffic for 5 minutes
# Terminal 1: Start controller
python -m controller.main \
  --config configs/dependencies_light.json \
  --mode live \
  --cycles 20 \
  --audit-dir results/live_experiments/test_run &

CONTROLLER_PID=$!

# Terminal 2: Generate traffic (after controller stabilizes)
sleep 60

python -m workload.generator \
  --profile W3 \
  --duration 300 \
  --seed 42 \
  --base-url http://localhost:8080 \
  --config configs/dependencies_light.json \
  --output results/live_experiments/test_traffic.csv

# Wait for controller to finish
wait $CONTROLLER_PID
```

**Check results:**
```bash
# Traffic log
wc -l results/live_experiments/test_traffic.csv
# Should be ~1000-5000 requests

# Controller decisions
wc -l results/live_experiments/test_run/2026-10-17.jsonl
# Should be ~20 decisions

# Calculate average latency
python -c "import pandas as pd; df=pd.read_csv('results/live_experiments/test_traffic.csv'); print(f'P95 Latency: {df[df.status_code==200].latency_ms.quantile(0.95):.1f}ms')"
```

If you see **realistic latency numbers** (50-500ms for warm, 1000-3000ms for cold), **you're done with testing!** 🎉

---

## 📊 Full Experimental Matrix

### **Option A: Full Matrix** (6-8 hours)

Run all combinations:
- 5 workloads × 6 baselines × 5 seeds = **150 experiments**
- 5 minutes each = **12.5 hours** (can run overnight)

### **Option B: Reduced Matrix** (2-3 hours) **RECOMMENDED**

Run subset:
- 3 workloads (W1, W3, W5) × 6 baselines × 3 seeds = **54 experiments**
- 5 minutes each = **4.5 hours**

### **Option C: Mini Matrix** (1 hour) **FOR QUICK VALIDATION**

Run minimal set:
- 1 workload (W3) × 6 baselines × 3 seeds = **18 experiments**
- 5 minutes each = **1.5 hours**

---

## 🎯 **RECOMMENDATION: Start with Option C**

Run 18 experiments to prove the live setup works, then decide if you need more.

### Create Experiment Script:

```bash
cat > scripts/run_one_live_experiment.sh << 'EOF'
#!/bin/bash
# Run ONE live experiment

WORKLOAD=$1
BASELINE=$2
SEED=$3
DURATION=${4:-300}

RESULTS_DIR="results/live_experiments"
EXP_NAME="${WORKLOAD}_${BASELINE}_seed${SEED}"

echo "=== Experiment: $EXP_NAME ==="

# Reset services to 0 replicas
echo "Resetting services..."
kubectl scale --replicas=0 deployment --all -n default --selector='serving.knative.dev/service'
sleep 30

# Start controller
echo "Starting controller ($BASELINE)..."
python -m baselines.${BASELINE} \
  --mode live \
  --cycles 20 \
  --config configs/dependencies_light.json \
  --audit-dir $RESULTS_DIR/${EXP_NAME}_audit &

CONTROLLER_PID=$!
sleep 60  # Let controller stabilize

# Generate traffic
echo "Generating traffic ($WORKLOAD, ${DURATION}s)..."
python -m workload.generator \
  --profile $WORKLOAD \
  --duration $DURATION \
  --seed $SEED \
  --base-url http://localhost:8080 \
  --config configs/dependencies_light.json \
  --output $RESULTS_DIR/${EXP_NAME}_traffic.csv

# Wait for controller
wait $CONTROLLER_PID

echo "✓ Experiment complete!"
EOF

chmod +x scripts/run_one_live_experiment.sh
```

### Run Mini Matrix:

```bash
# 18 experiments: W3 × 6 baselines × 3 seeds
for baseline in b1_no_prewarm b2_fixed_prewarm b3_fuzzy_only b4_pso_only b5_fuzzy_pso_no_granularity b6_granuwarm_full; do
  for seed in 42 123 456; do
    ./scripts/run_one_live_experiment.sh W3 $baseline $seed 300
    sleep 60  # Cool down between experiments
  done
done
```

---

## 📈 Analyze Live Results

### Create Analysis Script:

```bash
cat > scripts/analyze_live_results.py << 'EOF'
import pandas as pd
import glob
import json

results = []

for traffic_file in glob.glob('results/live_experiments/*_traffic.csv'):
    # Parse filename: W3_b6_granuwarm_full_seed42_traffic.csv
    parts = traffic_file.split('/')[-1].replace('_traffic.csv', '').split('_')
    workload = parts[0]
    baseline = '_'.join(parts[1:-1]).replace('_seed', '')
    seed = parts[-1].replace('seed', '')
    
    # Load traffic log
    df = pd.read_csv(traffic_file)
    df_success = df[df['status_code'] == 200]
    
    # Compute metrics
    total_requests = len(df)
    successful_requests = len(df_success)
    
    if len(df_success) == 0:
        continue
    
    mean_latency = df_success['latency_ms'].mean()
    median_latency = df_success['latency_ms'].median()
    p95_latency = df_success['latency_ms'].quantile(0.95)
    p99_latency = df_success['latency_ms'].quantile(0.99)
    
    # Cold start proxy: requests > 1000ms
    cold_starts = len(df_success[df_success['latency_ms'] > 1000])
    cold_start_rate = cold_starts / successful_requests * 100
    
    # SLA violation proxy: requests > 500ms
    sla_violations = len(df_success[df_success['latency_ms'] > 500])
    sla_violation_rate = sla_violations / successful_requests * 100
    
    # Load controller audit log for memory
    audit_pattern = traffic_file.replace('_traffic.csv', '_audit/*.jsonl')
    audit_files = glob.glob(audit_pattern)
    
    avg_memory = 0
    if audit_files:
        with open(audit_files[0]) as f:
            decisions = [json.loads(line) for line in f if line.strip()]
            if decisions:
                avg_memory = sum(d.get('estimated_memory_mb', 0) for d in decisions) / len(decisions)
    
    # Compute composite cost
    norm_L = p95_latency / 1000.0
    norm_C = cold_start_rate / 100.0
    norm_M = avg_memory / 1500.0  # budget = 1500MB
    norm_S = sla_violation_rate / 100.0
    composite_cost = 0.35 * norm_L + 0.25 * norm_C + 0.25 * norm_M + 0.15 * norm_S
    
    results.append({
        'workload': workload,
        'baseline': baseline,
        'seed': seed,
        'total_requests': total_requests,
        'mean_latency_ms': mean_latency,
        'median_latency_ms': median_latency,
        'p95_latency_ms': p95_latency,
        'p99_latency_ms': p99_latency,
        'cold_start_rate_pct': cold_start_rate,
        'sla_violation_rate_pct': sla_violation_rate,
        'avg_memory_used_mb': avg_memory,
        'composite_cost': composite_cost
    })

# Save summary
df_results = pd.DataFrame(results)
df_results.to_csv('results/live_experiments/summary_live.csv', index=False)
print(f"✓ Analyzed {len(results)} experiments")
print(f"✓ Summary saved to: results/live_experiments/summary_live.csv")
print("\nPreview:")
print(df_results.groupby('baseline')['p95_latency_ms', 'cold_start_rate_pct', 'composite_cost'].mean())
EOF

chmod +x scripts/analyze_live_results.py
```

### Run Analysis:

```bash
python scripts/analyze_live_results.py

# Generate all publication plots (Figures 1-5), LaTeX tables, and stats from real data
python scripts/plot_results.py
```

---

## ✅ Success Criteria

After running live experiments, you should see:

1. **Traffic logs** with realistic latencies:
   - Warm hits: 50-200ms
   - Cold starts: 1000-3000ms

2. **Controller audit logs** showing:
   - Real Prometheus metrics (no mocks)
   - Successful K8s actuation

3. **Summary CSV** with 18-150 experiments

4. **Plots** showing B6 (GranuWarm) beats baselines

---

## 🎓 For Your Research Paper

### Before (Simulation):
> "We evaluated GranuWarm using a discrete-event simulator..."

### After (Live Cluster):
> "We evaluated GranuWarm on a 2-node Kubernetes cluster with Knative Serving and Prometheus monitoring. We deployed 10 representative serverless functions and generated traffic using 5 realistic workload patterns. Our controller actuated Knative services in real-time based on observed Prometheus metrics. We measured actual end-to-end latency, cold start rates, and memory usage over 54 experiments (3 workloads × 6 baselines × 3 seeds)."

**Much more credible!** 🎉

---

## 🚧 Troubleshooting

### Problem: Services not becoming Ready
```bash
# Check pod logs
kubectl logs -n default -l serving.knative.dev/service=f01-hello-world

# Check events
kubectl get events -n default --sort-by='.lastTimestamp'
```

### Problem: Traffic generator gets connection refused
```bash
# Verify ingress is accessible
curl -H "Host: f01-hello-world.default.127.0.0.1.sslip.io" http://localhost:8080/

# If fails, restart port-forward
kubectl port-forward -n kourier-system svc/kourier 8080:80
```

### Problem: Experiments take too long
```bash
# Reduce duration to 3 minutes instead of 5
./scripts/run_one_live_experiment.sh W3 b6_granuwarm_full 42 180
```

---

## ⏱️ Timeline

| Phase | Task | Time |
|-------|------|------|
| 1 | Build Docker images | 30 mins |
| 2 | Test traffic generator | 5 mins |
| 3 | Run one test experiment | 10 mins |
| 4 | Run mini matrix (18 exps) | 1.5 hours |
| 5 | Analyze results | 5 mins |
| 6 | Generate plots | 5 mins |
| **Total** | **Mini matrix** | **~2-3 hours** |

**OR:**

| Phase | Task | Time |
|-------|------|------|
| 4 | Run full matrix (54 exps) | 4.5 hours |
| **Total** | **Full matrix** | **~6 hours** |

---

## 🎯 Next Steps

**START NOW:**
```bash
cd ~/Documents/GitHub/GranWarm

# 1. Build images (30 mins)
./scripts/build_and_load_images.sh

# 2. Restart services (2 mins)
./scripts/restart_services.sh

# 3. Test traffic (5 mins)
python -m workload.generator --profile W3 --duration 60 --seed 42 --base-url http://localhost:8080 --output test.csv

# 4. If test works, run mini matrix (1.5 hours)
# (see "Run Mini Matrix" section above)
```

**DONE! 🎉**
