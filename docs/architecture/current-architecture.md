# Current architecture

> **Last updated:** 2026-10-11 — reflects the P0 contract, safety,
> telemetry, and operating-mode work. See the
> [gap analysis and roadmap](gap-analysis-and-roadmap.md) for what
> remains.

This document describes what the repository implements today. It is
deliberately separate from the target design in the root
[README](../../README.md).

## Current system boundary

The repository has two partially related execution paths:

1. An offline simulator with baselines and an experiment matrix.
2. A live controller that reads Prometheus and patches Knative services.

The offline path is the more complete and reproducible path. The live
path is an integration prototype built on the same controller
components. As of this revision, the live controller can also run
fully offline in `dry_run` / `simulation` / `replay` modes, which makes
the pipeline testable without a cluster.

## Current operating modes

The controller supports five explicit modes via `--mode`. The default
is `dry_run`.

| Mode | Purpose | Prometheus required | Mocks allowed | K8s writes |
| --- | --- | --- | --- | --- |
| `simulation` | Offline, synthetic telemetry | No | Yes | No |
| `replay` | Deterministic replay of a recorded trace | No | Yes | No |
| `dry_run` | Full pipeline, no Kubernetes writes | Yes at fetch time | No | No |
| `shadow` | Real telemetry, decisions logged only | Yes | No | No |
| `live` | Full actuation | Yes | No | Yes |

At startup, `shadow` and `live` validate the Prometheus metric schema and
refuse to run if Prometheus is unreachable. `shadow`, `live`, and
`dry_run` never permit mock telemetry. Simulation and replay may use mock
telemetry; a failed Prometheus probe selects a pure-mock fast path.

## Current workflow

```
Offline simulator:
workload profile
  -> simulator telemetry
  -> selected baseline
  -> function/tree prewarm targets
  -> container simulation
  -> CSV metrics

Live / dry-run / shadow controller:
Prometheus
  -> PrometheusMonitor.fetch_snapshot()
  -> TelemetrySnapshot (typed, validated for freshness)
  -> FuzzyEngine.evaluate() per function
  -> GranularityTree.project_capacities()
  -> bounded-delta fast loop OR DAG-aware DiscreteConstrainedPSO
  -> AllocationRequest
  -> FeasibilityService.process()           <-- hard safety gate
  -> AllocationDecision
  -> audit log (results/audit/YYYY-MM-DD.jsonl)
  -> KnativeScaler.apply_allocation()       (dry_run / shadow: no-op)
```

## Current components

### Controller orchestration

[controller/main.py](../../controller/main.py) runs a dual-timescale
loop:

- **Fast loop (default 10s).** Fetch a telemetry snapshot, run fuzzy
  inference per function, project to DAG nodes, move the current
  allocation at most ±1 per node per cycle toward the fuzzy target
  (`fuzzy+delta`), then pass through the safety gate.
- **Slow loop (default 60s).** Run DAG-aware constrained PSO, pass
  through the safety gate.
- **Every cycle.** Audit the decision. In `live` mode, call the
  actuator.

The controller has configurable fast/slow intervals, memory budget,
Prometheus URL, operating mode, audit directory, and stale-telemetry
policy.

### Contracts

[controller/contracts/](../../controller/contracts/) defines the shared
typed data model used by the simulator, the controller, the safety
gate, and (in the future) the actuator:

- `TelemetrySnapshot` / `FunctionTelemetry` — one cycle of telemetry,
  with `source` provenance (`prometheus`, `mock`, `replay`,
  `simulator`).
- `AllocationRequest` / `AllocationDecision` — proposed and validated
  allocations, including `node_capacities` and `function_capacities`.
- `FunctionSpec` / `LayerSpec` — function and layer metadata (currently
  used for validation and future layer materialization).
- `validation.py` — domain checks, freshness checks, and the
  `STALENESS_THRESHOLD_SEC` constant.

Serialization is stable (JSON) so audit and replay records are
reproducible.

### Safety gate

[controller/safety/feasibility.py](../../controller/safety/feasibility.py)
runs after BOTH the fuzzy fast path and the PSO slow path. It:

1. validates node bounds, dependency constraints (child ≤ parent), and
   total memory against the configured budget;
2. repairs infeasible requests (child clamps, then proportional scale
   down while respecting minimum bounds);
3. rejects requests that cannot be repaired, with an explicit reason;
4. returns a typed `AllocationDecision`.

PSO penalties remain as search guidance but are NOT the safety
mechanism. Only the feasibility service can authorize an allocation for
actuation.

### Audit trail

Every decision is appended as one JSON line to
`results/audit/YYYY-MM-DD.jsonl` with fields including:

- `decision_id`, `cycle_id`, `source` (`pso`, `fuzzy+delta`)
- `telemetry_source` (`prometheus`, `mock`, `replay`, `simulator`)
- `mode` (`dry_run`, `shadow`, `live`, etc.)
- `estimated_memory_mb`, `within_budget`, `rejected_reason`,
  `repair_notes`
- `node_capacities`, `function_capacities`
- fast-loop extras: `fuzzy_prior`, `fuzzy_target`,
  `delta_from_previous`

### Telemetry

[controller/monitor/prometheus_client.py](../../controller/monitor/prometheus_client.py)
queries Prometheus for invocation rate, a cold-start-related signal,
and memory pressure, then normalizes them into the fuzzy controller
domains and returns a typed `TelemetrySnapshot`. See the
[Prometheus query schema](./prometheus-schema.md) for the exact selectors
and deployment assumptions.

Current behavior:

- Mock fallback is **opt-in** (`enable_mock_fallback=False` by
  default).
- `probe()` performs a one-shot reachability check with a 0.5s connect
  timeout.
- If the probe fails and the current mode permits mocks,
  `force_mock_only()` disables HTTP entirely so cycles complete in
  ~10s instead of blocking on a dead Prometheus.
- Missing required signals in `shadow` / `live` raise `TelemetryError`
  — there is no silent fallback.
- Staleness is validated per snapshot against
  `STALENESS_THRESHOLD_SEC`; `mock`, `replay`, and `simulator` sources
  are exempt because they have no real-time contract.

### Fuzzy inference

[controller/fuzzy/fuzzy_engine.py](../../controller/fuzzy/fuzzy_engine.py)
implements a 27-rule Mamdani system with triangular and trapezoidal
membership functions, min-AND implication, max aggregation, and
centroid defuzzification. Its output is a continuous value in `[0, 1]`,
which the controller scales to an integer instance count via
`FUZZY_CAPACITY_SCALE` (default 8.0).

### Dependency graph

[controller/granularity/tree.py](../../controller/granularity/tree.py)
loads the graph from `configs/dependencies.json`. Nodes marked
`"allocatable": false` (for example, the structural `root`) are parsed
for traversal but excluded from the optimization vector and from memory
accounting.

Key attributes:

- `node_ids` — allocatable nodes only (currently 19).
- `all_node_ids` — every node including structural ones (currently 20).
- `parent_map` — `{node_id: parent_id or None}`.
- `node_index` — position of each allocatable node in the PSO vector.

The projection is still:

```
projected_node_capacity(node)
  = max(recommendation(function)
        for function depending on node)
```

The mapping back to functions uses each function's `leaf_node`.

### PSO

[controller/pso/pso_optimizer.py](../../controller/pso/pso_optimizer.py)
optimizes an integer allocation vector with configurable swarm size,
iterations, bounds, and memory budget.

The PSO is **DAG-aware**. When constructed with `node_ids` and
`parent_map`, it clamps each child's capacity to its parent after every
position update (and at initialization). This makes the search space
feasible-by-construction, so the downstream safety gate rarely has to
repair PSO output.

The objective still uses analytic latency, cold-start, memory, and SLA
surrogates. Grounding the objective in measured metrics is
[Phase 4](gap-analysis-and-roadmap.md#phase-4-connect-optimization-to-observations).

### Actuation

[controller/allocator/knative_scaler.py](../../controller/allocator/knative_scaler.py)
uses the Kubernetes custom-object API to patch Knative Service
`autoscaling.knative.dev/min-scale` annotations.

Current behavior:

- scale-up is applied immediately;
- scale-down is applied only beyond an epsilon deadband;
- Kubernetes initialization failures switch to dry-run behavior;
- patch failures are logged;
- every call receives the full function → target map from the validated
  `AllocationDecision`.

The actuator is not yet idempotent, does not retry transient failures,
and does not reconcile after controller restart. See
[Phase 5](gap-analysis-and-roadmap.md#phase-5-build-a-reliable-actuator).

The actuator receives function service targets. It does not currently
create or manage independent shared runtime / library warm-layer
resources.

### Simulator

[simulator/env.py](../../simulator/env.py) models:

- cold, warm, busy, and reclaimed containers;
- function-level minimum warm targets;
- tree prewarmed capacities;
- dependency-based cold-start savings;
- memory use and idle memory;
- latency, cold-start, and SLA records.

[simulator/run_sim.py](../../simulator/run_sim.py) generates
non-homogeneous Poisson arrivals every 500 ms and evaluates one of six
baseline policies.

### Workloads and experiments

[workload/profiles.py](../../workload/profiles.py) defines W1–W5. The
experiment runner executes workloads, baselines, and seeds, then writes
raw traces and a summary CSV. Plotting and table generation are handled
by `scripts/plot_results.py`.

## Current strengths

- All offline execution paths work without a live cluster; a dead
  Prometheus does not block or slow the fast loop.
- Every allocation passes a hard feasibility gate before actuation.
- Telemetry provenance is explicit and audited; production modes cannot
  silently fall back to synthetic values.
- PSO searches the DAG-feasible subspace directly.
- The fast loop applies bounded deltas, giving natural hysteresis
  without a dedicated state machine.
- 21 unit tests cover contracts, safety, tree projection, PSO,
  monitoring, and simulator behavior.
- Five operating modes isolate simulation from production and make
  shadow experiments possible.

## Current limitations

- Shared dependency nodes are still simulated; they are not
  materialized as live Kubernetes resources (Phase 1).
- The actuator controls function-level Knative services only; it is not
  yet idempotent, retrying, or reconciling (Phase 5).
- PSO fitness is primarily surrogate-based; it does not yet consume a
  rolling metrics store (Phase 4).
- The cold-start PromQL query requires validation against the deployed
  Knative metric schema (Phase 3, partial).
- No CI pipeline; tests must be run locally (Phase 7).
- The simulator and live controller share contract shapes but have not
  yet been cross-validated on one trace (Phase 6).
- `simulation` and `replay` are currently aliases for `dry_run` with
  mocks; they will diverge once a generated-telemetry adapter and a
  recorded-trace loader exist.

## Current verification

The repository has tests for fuzzy inference, monitoring, tree
projection, PSO, safety, contracts, and simulator behavior. The
expected local command is:

```
python -m pytest tests -q
```

A minimal offline smoke run of the controller is:

```
python -m controller.main --mode dry_run --cycles 3
```

Each cycle writes an audit record to `results/audit/YYYY-MM-DD.jsonl`.