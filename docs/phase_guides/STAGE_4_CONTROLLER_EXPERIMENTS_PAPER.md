<![CDATA[# STAGE 4: Controller Integration, Experiments & Paper Results

> **Assigned to: Harshit Arya (Phase 11) + Member 4 (Phase 12–14) + All for review**
> **Phases: 11 → 12 → 13 → 14**
> **Estimated Duration: 3–4 weeks**
> **Prerequisites: All 3 prior stages complete**

---

## Phase 11 — Dual-Timescale Controller Integration

> **Owner: Harshit Arya**

### 11.1 Learning Objectives
- Asynchronous dual-timescale event loops (`asyncio`)
- Kubernetes Python SDK (`kubernetes-client`)
- Hysteresis deadband logic to prevent flapping
- Patching Knative CRD annotations

### 11.2 Architecture: The Control Loop

```
┌──────────────────────────────────────────────┐
│              FAST LOOP (every 10s)            │
│                                              │
│  Prometheus ──► Monitor ──► Fuzzy FIS        │
│                              │               │
│                    Per-function P_i           │
│                              │               │
│              Granularity Tree projection      │
│                    P_k^tree                   │
│                              │               │
│  ┌───────────────────────────┼──────────┐    │
│  │     SLOW LOOP (every 60s)  │          │    │
│  │                            ▼          │    │
│  │              Constrained PSO          │    │
│  │               x* optimal              │    │
│  └───────────────┬───────────────────────┘    │
│                  │                            │
│          Hysteresis Check                     │
│     |x*_k - x_current_k| > ε_reclaim?        │
│                  │                            │
│          Knative Scaler                       │
│   Patch min-scale annotations                │
└──────────────────────────────────────────────┘
```

### 11.3 `controller/main.py` — Algorithm 2 Implementation

```
INITIALIZE:
    x ← uniform allocation within M_budget
    t_last_pso ← current_time()

LOOP FOREVER:
    ─── FAST LOOP (every Δt_fast = 10s) ───
    metrics ← WorkloadMonitor.collect()
    
    for each function f_i ∈ F:
        R_i ← metrics.invocation_rate(f_i)
        T_i ← metrics.trend(f_i)
        C_i ← metrics.cold_start_pressure(f_i)
        M   ← metrics.resource_pressure()
        P_i ← FuzzyController.infer(R_i, T_i, C_i, M)
    
    P_tree ← GranularityTree.project({P_1, ..., P_N})
    
    ─── SLOW LOOP (every Δt_slow = 60s) ───
    if current_time() - t_last_pso ≥ Δt_slow:
        x* ← PSO.optimize(P_tree, G, M_budget, metrics)
        x ← x*
        t_last_pso ← current_time()
    else:
        x ← BudgetScale(P_tree, M_budget)  # Fast approximate
    
    ContainerManager.apply(x)  # With hysteresis
    WAIT(Δt_fast)
```

### 11.4 `controller/allocator/knative_scaler.py` — Hysteresis Logic

```python
def apply_allocation(self, new_allocation: dict[str, int], current: dict[str, int]):
    for node_id, desired in new_allocation.items():
        current_val = current.get(node_id, 0)
        diff = desired - current_val
        
        if diff > 0:
            # Scale UP: always apply immediately
            self._patch_min_scale(node_id, desired)
        elif diff < -self.epsilon_reclaim:
            # Scale DOWN: only if exceeds hysteresis threshold
            self._patch_min_scale(node_id, desired)
        # else: within hysteresis band, do nothing
```

**Hysteresis threshold:** ε_reclaim = 2 instances

### 11.5 Kubernetes API Patching

```python
from kubernetes import client, config

def _patch_min_scale(self, service_name: str, min_scale: int):
    """Patch autoscaling.knative.dev/min-scale on Knative Service"""
    config.load_kube_config()
    api = client.CustomObjectsApi()
    
    body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "autoscaling.knative.dev/min-scale": str(min_scale)
                    }
                }
            }
        }
    }
    
    api.patch_namespaced_custom_object(
        group="serving.knative.dev",
        version="v1",
        namespace="default",
        plural="services",
        name=service_name,
        body=body
    )
```

### 11.6 Verification
- [ ] Controller runs for 30+ minutes without crashes
- [ ] Fast loop executes every ~10s (check logs)
- [ ] PSO executes every ~60s (check logs)
- [ ] `kubectl get ksvc` shows `min-scale` annotations changing dynamically
- [ ] No flapping: scale-down only when delta > 2 instances
- [ ] Memory budget never exceeded

---

## Phase 12 — Baseline Implementations

> **Owner: Member 4**

### 12.1 Six Baseline Configurations (Table 6)

| Config | Description | Components Used |
|:---|:---|:---|
| **B1: No Prewarming** | Default Knative scale-to-zero | None |
| **B2: Fixed Prewarming** | Static N ∈ {1, 2, 5} warm containers per function | Manual allocation |
| **B3: Fuzzy-Only** | Fuzzy + budget scaling, no PSO, no granularity | Fuzzy |
| **B4: PSO-Only** | PSO with uniform init (no fuzzy), per-function space | PSO |
| **B5: Fuzzy + PSO (no Gran.)** | Full controller but per-function search space | Fuzzy + PSO |
| **B6: GranuWarm (Full)** | Complete framework | Fuzzy + Granularity + PSO |

### 12.2 Unified Interface

```python
# baselines/base_policy.py
from abc import ABC, abstractmethod

class BasePolicy(ABC):
    @abstractmethod
    def compute_allocation(self, metrics: dict) -> dict[str, int]:
        """Return allocation: {function_or_node_id: warm_count}"""
        ...
    
    @abstractmethod
    def reset(self):
        """Reset all internal state between experiment runs"""
        ...
    
    @property
    @abstractmethod
    def name(self) -> str: ...
```

### 12.3 Implementation Notes

- **B1**: Always returns `{f: 0 for f in functions}` — Knative default
- **B2**: Always returns `{f: N for f in functions}` where N is fixed
- **B3**: Runs fuzzy engine, scales output to fit budget proportionally, NO PSO
- **B4**: Runs PSO with random/uniform initialization (no fuzzy seeding), per-function allocation
- **B5**: Runs fuzzy→PSO pipeline but with per-function search space (no granularity tree)
- **B6**: Full GranuWarm (fuzzy→granularity projection→PSO)

### 12.4 Verification
- [ ] All 6 baselines implement `BasePolicy` interface
- [ ] `reset()` clears all state (historical averages, PSO particles, etc.)
- [ ] B1 keeps min-scale=0 always
- [ ] B2 keeps min-scale=N always
- [ ] B3–B6 produce different allocations under same workload

---

## Phase 13 — Automated Experiment Pipeline

> **Owner: Member 4 + Harshit Arya**

### 13.1 Experiment Matrix

```
5 Workloads × 6 Baselines × 5 Seeds = 150 Runs
```

| Dimension | Values |
|:---|:---|
| Workloads | W1 (Stable), W2 (Growth), W3 (Bursty), W4 (Periodic), W5 (Non-Stationary) |
| Baselines | B1, B2 (N=best), B3, B4, B5, B6 |
| Seeds | 42, 123, 456, 789, 1024 |
| Duration per run | 30 minutes (1800 seconds) |

### 13.2 `experiments/run_experiment.py`

```python
# Experiment orchestration pseudocode
WORKLOADS = ["W1", "W2", "W3", "W4", "W5"]
BASELINES = ["B1", "B2", "B3", "B4", "B5", "B6"]
SEEDS = [42, 123, 456, 789, 1024]
DURATION = 1800  # seconds

for workload in WORKLOADS:
    for baseline in BASELINES:
        for seed in SEEDS:
            # 1. Reset cluster state
            reset_cluster()
            
            # 2. Deploy baseline controller
            controller = deploy_baseline(baseline)
            
            # 3. Run workload generator
            generator = start_workload(workload, duration=DURATION, seed=seed)
            
            # 4. Collect metrics
            await asyncio.sleep(DURATION + 30)  # +30s cooldown
            
            # 5. Export results
            export_csv(
                filepath=f"results/raw/{workload}_{baseline}_seed{seed}.csv",
                headers=["timestamp", "seed", "workload_id", "baseline_id",
                         "function_id", "latency_ms", "is_cold_start", 
                         "is_sla_violation", "memory_used_mb", "idle_memory_mb"]
            )
            
            # 6. Cleanup
            controller.stop()
            generator.stop()
```

### 13.3 `scripts/reset_cluster.py`

Between each run:
1. Delete all active pods: `kubectl delete pods --all`
2. Reset Knative min-scale to 0 for all services
3. Clear Prometheus metrics: restart Prometheus pod
4. Wait 30s for cluster stabilization

### 13.4 Mini-Test Validation

```bash
# Quick validation: 1 Workload × 2 Baselines × 2 Seeds = 4 runs
python experiments/run_experiment.py --mini-test
# Verify: 4 CSV files in results/raw/
```

### 13.5 Verification
- [ ] Mini-test (4 runs) completes without errors
- [ ] Each CSV file has correct headers and non-empty data
- [ ] `reset_cluster.py` fully clears state between runs
- [ ] Full 150-run matrix runs unattended to completion
- [ ] Total experiment time: ~150 × 33min ≈ 82.5 hours (plan accordingly)

---

## Phase 14 — Results Analysis & Paper Publication Pipeline

> **Owner: Member 4 + All team members for review**

### 14.1 Statistical Metrics to Compute

| Category | Metric | Computation |
|:---|:---|:---|
| Central Tendency | Mean, Median | `df.mean()`, `df.median()` |
| Spread | Std Dev | `df.std()` |
| Tail Latency | P95, P99 | `df.quantile(0.95)`, `df.quantile(0.99)` |
| Cold-Start | CSR (%) | `N_cold / N_total × 100` |
| SLA | SVR (%) | `N_violation / N_total × 100` |
| Resource | Idle Memory Ratio | `M_idle / M_used` |
| Significance | Wilcoxon p-value | `scipy.stats.wilcoxon(B6, Bi)` |

### 14.2 `scripts/plot_results.py` — 4 Publication Figures

#### Figure 1: Latency vs. Memory Pareto Frontier
- X-axis: Average Memory (MB)
- Y-axis: P95 Latency (ms)
- One point per baseline (B1–B6), mean across all workloads
- Pareto-dominant configurations form lower-left frontier
- **Expected result**: B6 appears on or near Pareto frontier

#### Figure 2: Cold-Start Rate (CSR %) Grouped Bar Chart
- X-axis: Workload regimes W1–W5
- Y-axis: CSR (%)
- Grouped bars: B1–B6
- **Expected result**: B6 has lowest CSR across all regimes

#### Figure 3: Temporal Adaptation (3-Panel, Bursty W3)
- Top panel: Invocation rate λ(t) over time (showing burst spikes)
- Middle panel: Warm container count for B2 (flat) vs B6 (adaptive)
- Bottom panel: Cold-start event markers for B2 vs B6
- **Expected result**: B6 scales up before/during bursts, scales down between

#### Figure 4: Ablation Study Cost Attribution
- X-axis: Configurations B1→B2→B3→B4→B5→B6
- Y-axis: Composite cost J
- Show incremental improvement at each step
- Annotate with RQ1 (B1→B3), RQ2 (B3→B5), RQ3 (B5→B6)

### 14.3 Publication Formatting Requirements

```python
# Matplotlib settings for publication
import matplotlib.pyplot as plt
import matplotlib as mpl

mpl.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman'],
    'font.size': 10,
    'axes.labelsize': 11,
    'legend.fontsize': 9,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.05,
})
```

### 14.4 LaTeX Table Auto-Generation

Generate ready-to-paste LaTeX for paper Tables 8–16:

```python
def generate_latex_table(df, caption, label):
    """Generate LaTeX table from pandas DataFrame"""
    latex = df.to_latex(
        index=True,
        float_format="%.2f",
        column_format="l" + "c" * len(df.columns),
        caption=caption,
        label=label,
        escape=False
    )
    return latex
```

#### Tables to Generate:
| Table | Content |
|:---|:---|
| **Table 8** | Overall performance: CSR, ACST, P95, Avg Memory, SVR, Composite J (Mean ± Std) |
| **Table 9** | P95 Latency by workload regime (W1–W5) |
| **Table 10** | Cold-Start Rate by workload regime |
| **Table 11** | Average Memory by workload regime |
| **Table 12** | Sensitivity: Memory budget scaling (2/4/8/16 GB) |
| **Table 13** | Sensitivity: Objective weight profiles |
| **Table 14** | Sensitivity: PSO swarm size & iterations |
| **Table 15** | Sensitivity: Control loop intervals |
| **Table 16** | Controller overhead (execution time, CPU%, memory) |

### 14.5 Wilcoxon Signed-Rank Tests

```python
from scipy.stats import wilcoxon

# Compare B6 against each baseline
for baseline in ["B1", "B2", "B3", "B4", "B5"]:
    stat, p_value = wilcoxon(
        df_b6["composite_cost"], 
        df_baseline["composite_cost"],
        alternative='less'  # B6 should be lower
    )
    print(f"B6 vs {baseline}: W={stat:.1f}, p={p_value:.4f}")
    assert p_value < 0.05, f"B6 not significantly better than {baseline}!"
```

### 14.6 Complete Pipeline Execution

```bash
# 1. Compute statistics and generate all outputs
python scripts/plot_results.py

# 2. Check outputs
ls results/plots/    # figure_1_pareto.pdf, figure_2_csr.pdf, etc.
ls results/tables/   # table_8.tex, table_9.tex, etc.

# 3. Copy into LaTeX paper
cp results/plots/*.pdf paper/figures/
cat results/tables/table_8.tex  # Paste into paper
```

### 14.7 Final Verification Checklist
- [ ] All 4 figures render clearly at 300 DPI
- [ ] All LaTeX tables compile without errors
- [ ] Wilcoxon tests show p < 0.05 for B6 vs all baselines
- [ ] Results are reproducible across seeds (low variance)
- [ ] No fabricated data — all results from actual experiments

---

## Final Deliverables

| Deliverable | Location | Status |
|:---|:---|:---|
| Full codebase | `granuwarm/` | ☐ |
| 150-run raw data | `results/raw/` | ☐ |
| 4 publication figures | `results/plots/` | ☐ |
| 9 LaTeX tables | `results/tables/` | ☐ |
| Statistical analysis | `results/stats_summary.txt` | ☐ |
| Research paper | `paper/granuwarm_full_paper.tex` | ☐ |

> **⚠️ CRITICAL**: Section 6 results MUST come from real experiments. Do NOT fabricate data — this constitutes academic fraud and will result in retraction.
]]>
