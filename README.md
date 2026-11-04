# GranuWarm

**Adaptive dependency-aware pre-warming for serverless functions under
non-stationary workloads, using fuzzy-controlled constrained Particle Swarm
Optimization.**

GranuWarm is a closed-loop serverless resource-management framework that
combines workload telemetry, Mamdani fuzzy inference, a dependency-granularity
tree, and a constrained discrete Particle Swarm Optimizer (PSO) to reduce
cold-start latency under a cluster memory budget.

This README describes **what the repository actually implements today**, not an
aspirational end state.

---

## Two paths

The repository contains two independent execution paths that share the same
core algorithms (fuzzy engine, granularity tree, constrained PSO, feasibility
gate) but differ in how they obtain telemetry and how they actuate:

| Path | Status | Purpose | Entry point |
| --- | --- | --- | --- |
| **Offline simulation** | Primary, complete | Event-driven, trace-driven evaluation of all six baseline configurations across five workload regimes. This is the **research focus** and the source of every quantitative result in the paper. | `simulator/run_sim.py`, `experiments/run_experiment.py`, `reproduce.py` |
| **Live Kubernetes** | Secondary, functional | A dual-timescale controller that reads Prometheus telemetry and actuates Knative `min-scale` on a real cluster. | `controller/main.py`, `configure_baseline.py`, `scripts/deploy_*.sh` |

The offline path is self-contained and needs no cluster. All committed research
figures, tables, and statistical tests are reproducible from the offline path
alone.

---

## How GranuWarm works

The framework is built around three coordinated mechanisms, each implemented as
real (non-stubbed) code:

1. **Mamdani fuzzy inference system** (`controller/fuzzy/fuzzy_engine.py`,
   `configs/fuzzy_rules.json`) — a 27-rule FIS with triangular/trapezoidal
   membership functions, min-AND antecedents, max aggregation, and centroid
   defuzzification. It maps four normalized workload signals — invocation
   intensity `R`, traffic trend `T`, cold-start pressure `C`, memory pressure
   `M` — to a per-function warm-capacity recommendation `P ∈ [0, 1]` on a fast
   10 s loop.
2. **Dependency-granularity tree** (`controller/granularity/tree.py`,
   `configs/dependencies.json`) — decomposes the 12-function fleet into
   hierarchical, shareable layers (runtimes → library bundles → function leaf
   code). It projects per-function fuzzy recommendations onto tree nodes via
   the max-projection `P_k = max{ P_i : f_i depends on v_k }`, enforces
   parent/child dependency constraints, and accounts shared layers only once
   per family.
3. **Constrained discrete PSO** (`controller/pso/pso_optimizer.py`) — a
   vectorized integer PSO (30 particles, 50 iterations, inertia decaying
   0.7 → 0.4, c1 = c2 = 1.5) that searches the allocation vector across
   granularity-tree nodes. It uses informed seeding from the fuzzy prior,
   Deb's parameter-less constraint penalty for budget violations, and DAG
   projection to keep particles feasible by construction.

A **safety/feasibility gate** (`controller/safety/feasibility.py`) validates
every candidate allocation against bounds, dependency constraints, and the hard
memory budget, and repairs infeasible solutions with a proportional shrink
before they reach actuation.

---

## The offline simulation path (research focus)

### Engine

`simulator/env.py` (`SimEnvironment`) is a time-stepped serverless simulator
that processes discrete arrival events chronologically. It models:

- a **container state machine** (`COLD → WARM → BUSY → WARM → RECLAIMED`);
- **warm hits**, **cold starts / scale-out**, and **concurrency reuse** of busy
  containers (with a small per-extra-request queue penalty);
- **partial warm starts** — when shared granularity-tree nodes on a function's
  dependency path are pre-warmed, their init time is deducted from the
  cold-start latency, floored at the warm-start latency
  (`_compute_granularity_cold_delay`);
- a **hard memory budget** — new containers that would exceed the budget
  trigger eviction of idle warm containers (above `min_scale` first, then other
  functions'), and if still over budget the request queues behind the
  earliest-finishing busy container, capped at a 15 s platform timeout;
- **SLA violations** (`latency > sla_threshold_ms`); and
- **shared-layer vs. isolated memory accounting** — B6 counts each shared
  runtime/library layer once per family, while B1–B5 count every container's
  full footprint independently.

The engine is driven by `simulator/run_sim.py`, which advances in `dt = 0.5 s`
steps, generates Poisson arrivals per step from the active workload profile
(`rng.poisson(rate · dt)`), scatters them uniformly within the interval, sorts
them chronologically, and dispatches each to `step_invoke`. Every 10 simulated
seconds the control loop synthesizes telemetry signals from the profile and
current memory, calls the active policy's `compute_allocation`, and applies
the resulting pre-warm targets.

### Six baseline configurations (ablation)

All six are real, distinct policies in `baselines/`, subclassing
`base_policy.py`:

| ID | Policy | What it does |
| --- | --- | --- |
| B1 | `b1_no_prewarm` | Scale-to-zero; `min_scale = 0` everywhere. |
| B2 | `b2_fixed_prewarm` | Static one-container-per-function, budget-aware greedy packing (smaller footprint first). |
| B3 | `b3_fuzzy_only` | Real FIS per function, scaled to instances, budget-aware greedy by fuzzy demand. No PSO, no tree. |
| B4 | `b4_pso_only` | Constrained PSO over the 12-function space with a uniform prior. No fuzzy, no tree. |
| B5 | `b5_fuzzy_pso_no_granularity` | Fuzzy-seeded PSO over the 12-function space. No granularity tree / DAG projection. |
| B6 | `b6_granuwarm_full` | Full stack: FIS → tree max-projection → scaled fuzzy prior → constrained PSO over tree nodes → feasibility gate. The only policy returning a non-empty tree allocation. |

### Workload regimes

Five canonical regimes in `workload/profiles.py`, evaluated for 300 seconds per
run by the experiment runner by default:

- **W1 Stable** — constant Poisson arrivals.
- **W2 Growth** — linear ramp (`slope = 0.002`).
- **W3 Bursty** — 10× spikes lasting 60 s every 300 s (optional warmup ramp).
- **W4 Periodic** — sinusoidal modulation (period 600 s, amplitude 0.8).
- **W5 Non-stationary** — regime shift at `t = duration/2` with popularity
  inversion across functions.

### Benchmark functions

Twelve heterogeneous functions F01–F12 are defined in
`configs/dependencies.json` (lightweight web handlers, image manipulation, ML
inference, data processing), each with `cold_start_ms` (150 ms for F01 up to
8000 ms for F07), `warm_start_ms`, `container_memory_mb` (128–2048),
`base_rate`, `leaf_node`, and a `dependency_path` through the granularity tree.

---

## Repository layout

| Area | Responsibility |
| --- | --- |
| `simulator/` | Offline simulation engine (`env.py`) and CLI (`run_sim.py`). **Research focus.** |
| `baselines/` | The six ablation policies B1–B6 + `base_policy.py`. |
| `workload/` | Workload profiles W1–W5. |
| `experiments/` | Matrix runner that executes all 150 runs and computes the composite fitness `J`. |
| `controller/` | Shared algorithms (fuzzy, granularity tree, PSO, safety) plus the **live** dual-timescale controller, Prometheus client, Knative scaler, and rolling metrics store. |
| `configs/` | Function/dependency metadata, fuzzy rules, cluster + monitoring configs. |
| `functions/` | Per-function workload directories (F01–F12). |
| `scripts/` | Cluster bootstrap/deploy scripts and `plot_results.py` (figures, LaTeX tables, Wilcoxon tests). |
| `tests/` | 15 test modules covering the simulator, fuzzy, PSO, tree, feasibility, workloads, monitor, controller, and plotting. |
| `results/` | Committed outputs: `raw/` (150 per-run CSVs + summary matrix), `plots/` (Figures 1–4), `tables/` (LaTeX tables 8–11, 16), `stats_summary.txt`. Figure 5 is generated only after a live run. |
| `docker/` | Base Node.js / Python images for the live path. |
| `docs/` | Architecture notes, paper PDFs, and parsed paper Markdown. |

Architecture notes live in `docs/architecture/` (`mamdani-fuzzy-rules.md` and
`prometheus-schema.md`).

---

## Quick start

### Install

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run a single simulation

```bash
python simulator/run_sim.py \
  --workload W3 \
  --policy granuwarm \
  --duration 300 \
  --seed 42 \
  --output results/raw/W3_B6_seed42.csv
```

`--policy` accepts `b1`–`b6` or aliases (`none`, `fixed`, `fuzzy`, `pso`,
`granuwarm`). `--budget` defaults to **8192 MB**.

### Run the full experiment matrix

```bash
# 5 workloads x 6 baselines x 5 seeds = 150 runs
python -m experiments.run_experiment --full
```

Seeds are `[42, 123, 456, 789, 1024]`; the paper's N=10 significance subset uses
seeds 42 and 123. Output lands in `results/raw/` (per-run traces +
`summary_experiment_matrix.csv`).

### One-command reproduction

```bash
python reproduce.py            # regenerate figures/tables/stats from saved results
python reproduce.py --quick   # mini smoke-test matrix + artifacts
python reproduce.py --full    # re-run all 150 simulations + artifacts
```

`reproduce.py` runs the experiment matrix (if requested) then
`scripts/plot_results.py`, which produces Figures 1–5, LaTeX tables 8–11 and
16, and the two-tailed Wilcoxon signed-rank tests written to
`results/stats_summary.txt`.

### Tests

```bash
python -m pytest tests -q      # 78 tests
```

The suite is self-contained and does not require Kubernetes or Prometheus.
Cluster-dependent checks belong to the live-path setup in [`guide.md`](guide.md).

---

## Results & statistical significance

Committed results in `results/raw/` contain 150 per-run CSVs plus the summary
matrix. `scripts/plot_results.py` computes a post-run composite fitness

```
J = 0.35·(P95/1000) + 0.25·(CSR/100) + 0.25·(Mem/Budget) + 0.15·(SVR/100)
```

whose weights (0.35 / 0.25 / 0.25 / 0.15) match the paper's `w_L / w_C / w_M /
w_S`, and runs two-tailed Wilcoxon signed-rank tests of
`H0: median(J_baseline − J_B6) = 0`.

`results/stats_summary.txt` reports:

- **Paper matrix (seeds 42 & 123, N = 10):** B6 strictly dominates every
  baseline on all 10 paired trials → `W = 0.0`, `p = 0.00195` for B1–B5. This
  matches the paper exactly.
- **Full matrix (all 5 seeds, N = 25):** `W = 0.0`, `p = 5.96e-08` for B1–B5.

The qualitative ordering (B6 best on composite `J`, then B2, then the
non-granular dynamic baselines) and the statistical significance are
reproducible from the committed results.

---

## The live Kubernetes path

The live path is functional code for cluster validation and is secondary to
the research:

- `controller/main.py` (`GranuWarmController`) implements the true
  **dual-timescale loop**: a fast 10 s fuzzy/bounded-delta loop and a slow 60 s
  PSO re-optimization, with modes `simulation | replay | dry_run | shadow |
  live`. Only `live` performs Kubernetes writes.
- `controller/monitor/prometheus_client.py` issues real PromQL, validates the
  metric schema, and raises on stale/missing telemetry (no silent fallback
  unless explicitly enabled).
- `controller/allocator/knative_scaler.py` uses the real `kubernetes` client to
  patch Knative Service `autoscaling.knative.dev/min-scale`, with idempotency,
  hysteresis deadband on scale-down, exponential-backoff retries, and startup
  reconciliation.
- `configure_baseline.py` shells out to `kubectl` to configure B1/B2 static
  `min-scale` (and resets it for B3–B6, where the controller decides
  dynamically).
- `docker/` holds base Node.js/Python images; `scripts/` holds cluster
  bootstrap, build/load, and deploy scripts.


---

## Research paper

The accompanying paper drafts the full GranuWarm design, formulation, and
evaluation:

- **Draft (parsed Markdown):** [`docs/research-paper-parsed/granuwarm_draft.md`](docs/research-paper-parsed/granuwarm_draft.md)
- **Paper PDFs:** `docs/research-paper/` (the GranuWarm draft and related
  reference papers).
- **Parsed reference papers:** `docs/research-paper-parsed/` (Markdown
  versions of the draft and related papers).

The paper formalizes the cold-start latency model, the dependency-granularity
decomposition and partial-warm-start latency, the constrained allocation
objective `J`, the dual-timescale control loop, and the six-configuration
ablation across the five workload regimes.

## Research questions

1. **RQ1** — Does workload-aware fuzzy control reduce cold-start frequency and
   latency compared with no or fixed pre-warming?
2. **RQ2** — Does constrained PSO improve the latency/resource trade-off beyond
   fuzzy control alone?
3. **RQ3** — Does dependency-granularity modeling improve resource efficiency
   compared with function-level pre-warming?

The ablation (B1 → B3 → B5 → B6) isolates each contribution; `scripts/plot_results.py`
annotates Figure 4 with the measured per-stage `J` drops.

---

## Citation

```bibtex
@article{granuwarm2026,
  title   = {GranuWarm: Adaptive Dependency-Aware Pre-warming for Serverless
             Functions Under Non-Stationary Workloads Using Fuzzy-Controlled
             Constrained Particle Swarm Optimization},
  author  = {Arya, Harshit and Rawat, Ayush and Yadav, Bhavya and Gupta, Tijil},
  year    = {2026}
}
```
