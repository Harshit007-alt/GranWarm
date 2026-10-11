# Architecture gap analysis and roadmap

This document explains how to move from the implementation described in
[Current architecture](current-architecture.md) to the target design in the
root [README](../../README.md).

## Gap summary

| Area | Current state | Target state | Priority |
| --- | --- | --- | --- |
| Contracts | Dictionaries passed between modules | Shared typed telemetry, allocation, and decision contracts | P0 |
| Dependency layers | Simulated cache-like nodes | Real, explicitly managed shared warm-layer resources | P0 |
| Memory safety | PSO penalty plus fast proportional scaling | Hard feasibility and repair before actuation | P0 |
| Telemetry | Queries plus default mock fallback | Validated schema, freshness, explicit failure | P0 |
| Optimization | Mostly analytic surrogates | Objective grounded in measured/simulated metrics | P1 |
| Actuation | Function-level `min-scale` patching | Layer and function actuation with reconciliation | P1 |
| Reliability | Logged failures | Retry, backoff, idempotency, desired-state reconciliation | P1 |
| Operating modes | Live and dry-run flags | Simulation, replay, shadow, dry-run, and live modes | P1 |
| Evaluation | Offline matrix and selected artifacts | Reproducible offline/live comparison with controller metrics | P2 |
| Delivery | Tests but no complete release workflow | CI, pinned dependencies, manifests, and experiment metadata | P2 |

## Execution roadmap

### Phase 0: Freeze the contracts

**Goal:** make every execution path use the same data model.

Implement shared models for:

- `TelemetrySnapshot`
- `FunctionSpec`
- `LayerSpec`
- `AllocationRequest`
- `AllocationDecision`
- `ObservedMetrics`
- `ActuationResult`

Define validation rules for domains, timestamps, service names, allocation
bounds, and configuration versions. Use the models in the simulator,
baselines, live controller, and actuator.

**Acceptance criteria**

- simulator and live controller accept the same telemetry shape;
- invalid values fail with an explicit error;
- serialization is stable for replay and audit logs;
- tests cover missing, stale, and out-of-range fields.

### Phase 1: Make dependency semantics executable

**Goal:** close the gap between the simulated dependency graph and the live
runtime.

First decide the implementation model. The recommended first target is a
layer-aware runtime contract in which each function declares the reusable
layers it needs, while a node-level manager tracks warm capacity and memory
for those layers.

Then implement:

1. layer ownership and lifecycle;
2. shared memory accounting;
3. layer startup-time savings;
4. dependency-aware capacity mapping;
5. observed layer state; and
6. an actuator interface for layer resources.

Do not claim live dependency sharing until the runtime can observe and manage
those resources.

**Acceptance criteria**

- one shared runtime layer can serve multiple functions;
- memory is counted once for a shared layer;
- cold-start savings match between simulator and live model;
- a layer allocation can be reconciled independently of leaf allocation.

### Phase 2: Enforce hard budget safety

**Goal:** guarantee that no emitted decision exceeds the memory budget.

Add a feasibility service used by both fuzzy fast-path decisions and PSO:

```text
validate(allocation)
repair(allocation)
reject_or_report(allocation)
```

The service should account for shared layers, function capacity, reserved
memory, and any runtime overhead. Keep the penalty term for optimization
guidance, but never rely on it as the only safety mechanism.

**Acceptance criteria**

- every applied allocation satisfies the budget;
- infeasible PSO candidates are repaired or rejected;
- fast-loop decisions also pass the same validator;
- tests cover zero budget, oversized nodes, and rounding overflow.

### Phase 3: Make telemetry production-safe

**Goal:** ensure decisions are based on real and correctly interpreted
signals.

1. Document the exact Prometheus metric schema.
2. Validate labels and units at startup.
3. Implement a real cold-start measurement.
4. Track sample timestamp and freshness.
5. Make mock data opt-in.
6. Return explicit telemetry errors for missing required signals.

Use recorded Prometheus responses as fixtures and add an integration test
against the selected Knative version.

**Acceptance criteria**

- live mode cannot silently continue on synthetic values;
- every signal has a documented query, unit, and normalization;
- stale data is rejected or clearly marked;
- telemetry snapshots are replayable.

### Phase 4: Connect optimization to observations

**Goal:** replace disconnected surrogate optimization with a measured
closed-loop objective.

Create a rolling metrics store keyed by function, layer, and time window.
Compute objective terms from observed or simulator-generated values:

```text
J(x) =
  latency_cost(x)
  + cold_start_cost(x)
  + idle_memory_cost(x)
  + sla_cost(x)
```

Keep normalization and weights in configuration. Record the objective
breakdown for every PSO decision.

**Acceptance criteria**

- PSO can optimize against a replayed metric window;
- objective terms appear in decision logs;
- identical input trace and seed produce identical output;
- tests prove that changing measured latency can change the selected policy.

### Phase 5: Build a reliable actuator

**Goal:** make Kubernetes changes safe and convergent.

Add:

- desired-state records;
- idempotent patch generation;
- retry with bounded exponential backoff;
- conflict handling;
- observed-state refresh;
- reconciliation after controller restart;
- rate limits and change budgets;
- structured actuation results.

The actuator should support both shared-layer resources and function services.
It should expose a read-only plan for shadow and dry-run modes.

**Acceptance criteria**

- repeated application of the same decision produces no unnecessary patch;
- transient Kubernetes failures are retried;
- permanent failures are surfaced to the controller;
- restart recovery converges to the desired allocation;
- every change has a decision ID and outcome.

### Phase 6: Add operating modes and end-to-end validation

**Goal:** validate the architecture without risking the live cluster.

Implement the target modes:

1. **Simulation:** generated telemetry and simulated resources.
2. **Replay:** recorded telemetry and deterministic decisions.
3. **Shadow:** real telemetry, no actuation.
4. **Dry run:** validated plan, no Kubernetes writes.
5. **Live:** actuation, retries, and reconciliation.

Run the following progression:

```text
unit tests
  -> simulator smoke test
  -> offline matrix
  -> telemetry fixture replay
  -> shadow controller
  -> dry-run cluster
  -> one live W3 trial
  -> complete live workload matrix
```

**Acceptance criteria**

- offline and replay modes are deterministic;
- shadow decisions are inspectable;
- dry-run plans match live patch plans;
- one live trial records telemetry, decisions, patches, and outcomes together.

### Phase 7: Reproducible research release

**Goal:** make the final evaluation defensible and repeatable.

Add:

- pinned dependencies;
- CI for tests and smoke runs;
- experiment manifest files;
- commit and environment metadata;
- clean output directories per run;
- confidence intervals and effect sizes;
- controller overhead measurements;
- a limitations section covering simulator assumptions and live constraints.

**Acceptance criteria**

- a new machine can reproduce the offline matrix;
- every result maps to a commit, configuration, seed, and environment;
- figures and tables are generated from raw results;
- live and offline results are clearly distinguished.

## Recommended immediate sequence

Do these tasks next, in order:

1. Implement shared typed contracts.
2. Add the hard allocation validator and tests.
3. Disable default mock telemetry in live mode.
4. Validate the Prometheus metric schema.
5. Define and implement the shared-layer runtime contract.
6. Add desired-state reconciliation to the actuator.
7. Run a W3 shadow experiment.
8. Run one dry-run and then one live experiment.

The key milestone is not simply “the controller runs.” The target is reached
when the following statement is true:

> The simulator, telemetry adapter, optimizer, dependency graph, safety layer,
> and Kubernetes actuator describe and enforce the same allocation semantics.
