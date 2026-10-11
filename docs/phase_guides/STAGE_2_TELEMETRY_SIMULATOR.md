# 📡 STAGE 2: Telemetry, Workload Generation & Simulation

> **Assigned to:** Ayush Rawat — Workload Profiling, Prometheus Signals & Discrete Simulation Lead
>
> **Phases:** 5 → 6 → 7
>
> **Estimated Duration:** 2 weeks
>
> **Prerequisite:** Stage 1 complete (KinD cluster + Knative + 12 functions deployed)

---

## Phase 5 — Prometheus Monitoring & Signal Extraction

### 5.1 Learning Objectives

- Time-series metric collection (pull model, scrape intervals)
- PromQL query syntax (`sum`, `rate`, `increase`, `offset`)
- Python HTTP client for Prometheus API

### 5.2 Practical Steps

#### Verify Prometheus is Running

```bash
# Prometheus should be deployed by scripts/setup_env.sh
kubectl get pods -n monitoring
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090 &
# Access: http://localhost:9090
```

#### Implement `controller/monitor/prometheus_client.py`

This module extracts the 4 GranuWarm workload signals via PromQL:

| Signal | Symbol | PromQL Pattern | Range |
|:---|:---:|:---|:---:|
| Invocation Intensity | `R_i(t)` | `rate(revision_request_count{...}[10s])` | [0, 1] |
| Traffic Trend | `T_i(t)` | `R_i(t) - R_i(t - Δt)` | [-1, 1] |
| Cold-Start Pressure | `C_i(t)` | `N_cold / N_total` over 60s window | [0, 1] |
| Resource Pressure | `M(t)` | `M_used / M_available` (cluster-wide) | [0, 1] |

**Key implementation details:**

- Use `requests` library to query `http://prometheus:9090/api/v1/query`
- Parse JSON response: `response["data"]["result"][0]["value"][1]`
- Normalize `R_i` relative to function's historical maximum rate
- `T_i` requires computing difference between current and previous `R_i`
- Cold-start count tracked via custom counter metric or inferred from latency

### 5.3 Unit Test

```python
# tests/test_monitor.py
from controller.monitor.prometheus_client import PrometheusMonitor

def test_signal_extraction():
    pm = PrometheusMonitor(prometheus_url="http://localhost:9090")
    metrics = pm.get_function_metrics("f01-hello-world")

    assert "R_i" in metrics  # Invocation intensity
    assert "T_i" in metrics  # Traffic trend
    assert "C_i" in metrics  # Cold-start pressure
    assert "M" in metrics    # Resource pressure
    assert 0.0 <= metrics["R_i"] <= 1.0
    assert -1.0 <= metrics["T_i"] <= 1.0
    assert 0.0 <= metrics["C_i"] <= 1.0
    assert 0.0 <= metrics["M"] <= 1.0
```

### 5.4 Verification

- [ ] Prometheus pod running in `monitoring` namespace
- [ ] Scrape interval = 2s (verify in Prometheus config)
- [ ] `PrometheusMonitor.get_function_metrics()` returns all 4 signals
- [ ] Signals update in real-time as traffic hits functions

### 5.5 Common Pitfalls

| Issue | Solution |
|:---|:---|
| Empty PromQL response | Verify metric label filters match Knative's label schema |
| Scrape interval too slow | Must be 2s to support 10s fast loop (≥5 samples per cycle) |
| Port-forward dropping | Use `kubectl port-forward --address 0.0.0.0` for stability |

---

## Phase 6 — Workload Generator

### 6.1 Learning Objectives

- Asynchronous HTTP programming (`asyncio` + `httpx`)
- Mathematical workload rate modeling
- Reproducible random seeds

### 6.2 Five Workload Regimes (Table 5)

| Regime | Description | Mathematical Model | Character |
|:---|:---|:---|:---|
| **W1: Stable** | Constant-rate Poisson | `λ_i(t) = λ̄_i ∀t` | Baseline steady-state |
| **W2: Gradual Growth** | Linearly increasing rate | `λ_i(t) = λ̄_i · (1 + 0.05t)` | Ramp-up stress test |
| **W3: Bursty** | Periodic 10× spikes | `λ_i(t) = λ̄_i + 9λ̄_i · 𝟙[burst]` | Flash crowd test |
| **W4: Periodic** | Sinusoidal diurnal | `λ_i(t) = λ̄_i · (1 + 0.8·sin(2πt/T))` | Diurnal cycle |
| **W5: Non-Stationary** | Regime change at t=T/2 | `λ̄_i^(1) → λ̄_i^(2)` with inversion | Drift/shift test |

> **W3 detail:** Burst intervals last 60s and occur every 5 minutes.
>
> **W5 detail:** At t=T/2, both rate magnitude shifts AND function popularity inverts.

### 6.3 Implementation Steps

#### `workload/profiles.py`

Implement pure mathematical rate functions for each regime:

```python
# Each profile returns instantaneous target rate at time t
def w1_stable(t: float, base_rate: float) -> float:
    return base_rate

def w3_bursty(t: float, base_rate: float,
              burst_duration: float = 60.0,
              burst_interval: float = 300.0) -> float:
    cycle_pos = t % burst_interval
    if cycle_pos < burst_duration:
        return base_rate * 10.0  # 10× spike
    return base_rate
```

#### `workload/generator.py`

Async HTTP client firing requests at Knative endpoints:

```python
# Core loop structure
async def generate_traffic(profile, duration, seed, functions, base_url):
    rng = np.random.default_rng(seed)
    async with httpx.AsyncClient() as client:
        t_start = time.monotonic()
        while (elapsed := time.monotonic() - t_start) < duration:
            for func in functions:
                rate = profile.get_rate(elapsed, func.base_rate)
                # Poisson inter-arrival: next_wait = -ln(U) / rate
                wait = rng.exponential(1.0 / max(rate, 0.001))
                await asyncio.sleep(wait)
                asyncio.create_task(
                    client.get(f"{base_url}",
                              headers={"Host": func.knative_host})
                )
```

### 6.4 CLI Interface

```bash
python workload/generator.py \
    --profile W3 \
    --duration 1800 \
    --seed 42 \
    --base-url http://localhost:80 \
    --output workload_log.csv
```

### 6.5 Verification

- [ ] All 5 profiles (W1–W5) generate distinct traffic shapes
- [ ] W3 burst shows 10× rate visible in Prometheus dashboard
- [ ] `--seed 42` produces identical request sequences across runs
- [ ] Generator sustains 100+ req/s without client-side bottleneck
- [ ] No socket exhaustion (single `httpx.AsyncClient` reused)

---

## Phase 7 — Discrete-Event Simulator

### 7.1 Learning Objectives

- Discrete-event simulation in pure Python
- Container lifecycle state modeling (Cold → Warm → Busy → Idle → Reclaimed)
- Performance: 1000 simulated seconds in < 3 real seconds

### 7.2 Architecture

```
┌─────────────────────────────────────────┐
│         Simulator Environment           │
│                                         │
│  ┌───────────┐    ┌──────────────────┐  │
│  │ Workload  │───►│ Container Pool   │  │
│  │ Generator │    │                  │  │
│  │ (W1–W5)   │    │ COLD  → WARM    │  │
│  └───────────┘    │ WARM  → BUSY    │  │
│                   │ BUSY  → WARM    │  │
│                   │ WARM  → RECLAIM │  │
│                   └────────┬─────────┘  │
│                            │            │
│                   ┌────────▼─────────┐  │
│                   │ Metrics Tracker  │  │
│                   │ • Latency        │  │
│                   │ • Cold-start cnt │  │
│                   │ • Memory usage   │  │
│                   │ • SLA violations │  │
│                   └──────────────────┘  │
└─────────────────────────────────────────┘
```

### 7.3 Container State Machine

```
                    ┌─────────┐
        invoke      │  COLD   │  τ_cold delay
    ┌──────────────►│(no pod) │──────────────┐
    │               └─────────┘              │
    │                                        ▼
    │               ┌─────────┐        ┌─────────┐
    │    invoke     │  WARM   │        │  BUSY   │
    └──────────────►│ (idle)  │◄───────│(running)│
                    └────┬────┘  done  └─────────┘
                         │
                    idle timeout
                         │
                    ┌────▼────┐
                    │RECLAIMED│
                    │ (freed) │
                    └─────────┘
```

### 7.4 Key Simulation Parameters

| Parameter | Symbol | Description |
|:---|:---:|:---|
| Cold-start delay | `τ_i^cold` | From Table 4 (150ms – 8.0s per function) |
| Warm-start delay | `τ_i^warm` | ~5ms for all functions |
| Container memory | `m_i` | From Table 4 (128MB – 2048MB) |
| Idle timeout | `t_idle` | 60s (default Knative) |
| Sim time step | `Δt_sim` | 0.1s (100ms resolution) |

### 7.5 Implementation: `simulator/env.py`

Core classes:

- **`Container`** — state (COLD/WARM/BUSY), creation time, last-used time, function_id
- **`FunctionSpec`** — cold_start_ms, warm_start_ms, memory_mb, sla_threshold_ms
- **`SimEnvironment`** — main simulation loop, container pool, metrics collection

### 7.6 Implementation: `simulator/run_sim.py`

CLI runner:

```bash
python simulator/run_sim.py \
    --workload W3 \
    --policy fixed \
    --duration 1000 \
    --seed 42 \
    --output results/raw/sim_W3_fixed_42.csv
```

Output CSV columns:

```
timestamp, function_id, latency_ms, is_cold_start, is_sla_violation, memory_used_mb, idle_memory_mb
```

### 7.7 Verification

- [ ] `python simulator/run_sim.py --workload W1 --policy fixed --duration 1000` completes in < 3s
- [ ] Output CSV has correct columns and non-empty data
- [ ] Cold-start latencies match Table 4 values (±10%)
- [ ] With `--policy fixed`, containers stay warm; with `--policy none`, all starts are cold
- [ ] Memory tracking: sum of active container memory never exceeds budget

### 7.8 Common Pitfalls

| Issue | Solution |
|:---|:---|
| Simulation too slow | Use numpy arrays, avoid per-event Python object creation |
| Time step drift | Use integer tick counter, multiply by `Δt_sim` for float time |
| Cold/warm latency mismatch | Cross-reference Table 4 values exactly |

---

## ➡️ Handoff to Stage 3

Once the following are verified, notify **Bhavya Yadav** and **Harshit Arya** to begin Phases 8–10:

1. Prometheus extracts live `R_i`, `T_i`, `C_i`, `M` signals
2. Workload generator produces W1–W5 traffic shapes visible in Prometheus
3. Simulator runs 1000s in < 3s with correct metrics output

> **Important:** The simulator enables rapid offline iteration on fuzzy rules and PSO parameters without waiting for live cluster runs. Both teams will use it extensively.
