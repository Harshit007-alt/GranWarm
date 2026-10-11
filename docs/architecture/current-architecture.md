# Current architecture

This document describes what the repository implements today. It is
deliberately separate from the target design in the root
[README](../../README.md).

## Current system boundary

The repository currently has two partially related execution paths:

1. An offline simulator with baselines and an experiment matrix.
2. A live controller that reads Prometheus and patches Knative services.

The offline path is the more complete and reproducible path. The live path is
an integration prototype around the same controller components.

## Current workflow

```text
Offline:
workload profile
  -> simulator telemetry
  -> selected baseline
  -> function/tree prewarm targets
  -> container simulation
  -> CSV metrics

Live:
Prometheus
  -> PrometheusMonitor
  -> FuzzyEngine
  -> GranularityTree max projection
  -> DiscreteConstrainedPSO or fast scaling
  -> leaf allocation mapping
  -> KnativeScaler
  -> Knative min-scale patch
```

## Current components

### Controller orchestration

[controller/main.py](../../controller/main.py) runs a dual-timescale loop:

- It reads telemetry independently for each configured function.
- It evaluates fuzzy recommendations.
- It projects function recommendations to graph nodes.
- It invokes PSO every 60 seconds.
- Between PSO executions, it rounds and proportionally scales fuzzy targets
  when the estimated memory exceeds the budget.
- It maps node allocations back to function leaf allocations.
- It patches Knative service `min-scale` through the scaler.

The controller has configurable fast and slow intervals, memory budget,
Prometheus URL, dry-run mode, and cycle count.

### Telemetry

[controller/monitor/prometheus_client.py](../../controller/monitor/prometheus_client.py)
queries Prometheus for invocation rate, a cold-related signal, and memory
pressure, then derives traffic trend from the previous rate. It normalizes the
values into the fuzzy controller domains.

The current adapter has mock fallback values enabled by default when a query
fails.

### Fuzzy inference

[controller/fuzzy/fuzzy_engine.py](../../controller/fuzzy/fuzzy_engine.py)
implements a 27-rule Mamdani system with triangular and trapezoidal membership
functions, min-AND implication, max aggregation, and centroid
defuzzification. Its output is a continuous value in `[0, 1]`, which can be
scaled to an integer instance count.

### Dependency graph

[controller/granularity/tree.py](../../controller/granularity/tree.py) loads
the graph from `configs/dependencies.json`. The current projection is:

```text
projected_node_capacity(node)
  = max(recommendation(function)
        for function depending on node)
```

The configuration contains 20 nodes and 12 functions. The current mapping back
to functions uses each function's `leaf_node`.

### PSO

[controller/pso/pso_optimizer.py](../../controller/pso/pso_optimizer.py)
optimizes an integer vector with configurable swarm size, iteration count,
allocation bounds, memory budget, and objective weights.

The current objective uses analytic latency, cold-start, memory, and SLA
surrogates. The optional metrics argument is not yet a complete measured
telemetry-to-objective pipeline.

### Actuation

[controller/allocator/knative_scaler.py](../../controller/allocator/knative_scaler.py)
uses the Kubernetes custom-object API to patch Knative Service
`autoscaling.knative.dev/min-scale` annotations.

Current behavior:

- scale-up is applied immediately;
- scale-down is applied only beyond an epsilon deadband;
- Kubernetes initialization failures switch to dry-run behavior;
- patch failures are logged.

The actuator receives function service targets. It does not currently create
or manage independent shared runtime/library warm-layer resources.

### Simulator

[simulator/env.py](../../simulator/env.py) models:

- cold, warm, busy, and reclaimed containers;
- function-level minimum warm targets;
- tree prewarmed capacities;
- dependency-based cold-start savings;
- memory use and idle memory;
- latency, cold-start, and SLA records.

[simulator/run_sim.py](../../simulator/run_sim.py) generates non-homogeneous
Poisson arrivals every 500 ms and evaluates one of six baseline policies.

### Workloads and experiments

[workload/profiles.py](../../workload/profiles.py) defines W1–W5. The
experiment runner executes workloads, baselines, and seeds, then writes raw
traces and a summary CSV. Plotting and table generation are handled by
`scripts/plot_results.py`.

## Current strengths

- The core fuzzy, tree, PSO, simulator, and scaler modules exist.
- The baseline policies provide useful ablation comparisons.
- The simulator is fast enough for matrix experiments.
- The tests cover the major algorithmic modules.
- The live controller has a clear dual-timescale orchestration boundary.

## Current limitations

- Shared dependency nodes are modeled in the simulator but not materialized as
  live runtime resources.
- The live actuator controls function-level Knative services only.
- Prometheus fallback values can hide missing telemetry.
- The cold-start metric query requires validation against the deployed metric
  schema.
- PSO fitness is primarily surrogate-based.
- The fast-loop budget scaling is a proportional approximation.
- There is no persistent desired-state store or reconciliation loop.
- Live decisions are not yet recorded as a complete audit trail.
- Simulator and live telemetry/allocation models are not represented by one
  shared typed contract.

## Current verification

The repository currently has tests for fuzzy inference, monitoring, tree
projection, PSO, and simulator behavior. The expected local command is:

```bash
python -m pytest tests -q
```
