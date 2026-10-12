# Architecture gap analysis and roadmap

> **Last updated:** 2026-10-11 — reflects the P0 contract, safety,
> telemetry, and operating-mode work.

This document explains how to move from the implementation described in
[Current architecture](current-architecture.md) to the target design in
the root [README](../../README.md).

## Gap summary

| Area | Current state | Target state | Priority | Status |
| --- | --- | --- | --- | --- |
| Contracts | Dictionaries passed between modules | Shared typed telemetry, allocation, and decision contracts | P0 | **Done** |
| Memory safety | PSO penalty plus fast proportional scaling | Hard feasibility and repair before actuation | P0 | **Done** |
| Telemetry | Queries plus default mock fallback | Validated schema, freshness, explicit failure | P0 | **Done** (cold-start query still to validate) |
| Operating modes | Live and dry-run flags | Simulation, replay, shadow, dry-run, and live modes | P1 | **Done** |
| Dependency layers | Simulated cache-like nodes | Real, explicitly managed shared warm-layer resources | P0 | Not started |
| Optimization | Mostly analytic surrogates | Objective grounded in measured/simulated metrics | P1 | Not started |
| Actuation | Function-level `min-scale` patching | Layer and function actuation with reconciliation | P1 | Not started |
| Reliability | Logged failures | Retry, backoff, idempotency, desired-state reconciliation | P1 | Not started |
| Evaluation | Offline matrix and selected artifacts | Reproducible offline/live comparison with controller metrics | P2 | Not started |
| Delivery | Tests but no complete release workflow | CI, pinned dependencies, manifests, and experiment metadata | P2 | Not started |

## Execution roadmap

### Phase 0: Freeze the contracts

**Goal:** make every execution path use the same data model.

**Status: COMPLETE.** Implemented in
[controller/contracts/](../../controller/contracts/).

Implemented shared models for:

- `TelemetrySnapshot`
- `FunctionTelemetry`
- `FunctionSpec`
- `LayerSpec`
- `AllocationRequest`
- `AllocationDecision`

Additional models planned by the target design (`ObservedMetrics`,
`ActuationResult`) will land with Phase 5. Validation rules exist for
domains, timestamps, service names, allocation bounds, and freshness.

**Acceptance criteria**

- ✅ simulator and live controller accept the same telemetry shape;
- ✅ invalid values fail with an explicit error;
- ✅ serialization is stable for replay and audit logs;
- ✅ tests cover missing, stale, and out-of-range fields.

### Phase 1: Make dependency semantics executable

**Goal:** close the gap between the simulated dependency graph and the
live runtime.

**Status: NOT STARTED.** The DAG is parsed, projections are enforced,
and non-allocatable nodes are excluded, but shared layers are still
simulated; no Kubernetes resources are created for them.

First decide the implementation model. The recommended first target is
a layer-aware runtime contract in which each function declares the
reusable layers it needs, while a node-level manager tracks warm
capacity and memory for those layers.

Then implement:

1. layer ownership and lifecycle;
2. shared memory accounting;
3. layer startup-time savings;
4. dependency-aware capacity mapping;
5. observed layer state; and
6. an actuator interface for layer resources.

Do not claim live dependency sharing until the runtime can observe and
manage those resources.

**Acceptance criteria**

- one shared runtime layer can serve multiple functions;
- memory is counted once for a shared layer;
- cold-start savings match between simulator and live model;
- a layer allocation can be reconciled independently of leaf allocation.

### Phase 2: Enforce hard budget safety

**Goal:** guarantee that no emitted decision exceeds the memory budget.

**Status: COMPLETE.** Implemented in
[controller/safety/feasibility.py](../../controller/safety/feasibility.py).

The service exposes:

```
validate(allocation)
repair(allocation)
reject_or_report(allocation)
```

It accounts for shared layers, function capacity, and reserved memory.
The penalty term inside PSO is retained for optimization guidance, but
it is no longer the only safety mechanism.

**Acceptance criteria**

- ✅ every applied allocation satisfies the budget;
- ✅ infeasible PSO candidates are repaired or rejected;
- ✅ fast-loop decisions also pass the same validator;
- ✅ tests cover zero budget, oversized nodes, and rounding overflow.

### Phase 3: Make telemetry production-safe

**Goal:** ensure decisions are based on real and correctly interpreted
signals.

**Status: MOSTLY COMPLETE.** Mock fallback is opt-in, freshness is
validated, and `mock` / `replay` / `simulator` sources are exempt from
the staleness check. A reachability `probe()` and a pure-mock fast path
eliminate the pathological 144-second cycle observed on Windows when
Prometheus was unreachable.

Remaining work:

- validate the cold-start PromQL query against the deployed Knative
  metric schema;
- add recorded Prometheus fixtures and an integration test against the
  selected Knative version.

**Acceptance criteria**

- ✅ live mode cannot silently continue on synthetic values;
- ⏳ every signal has a documented query, unit, and normalization
  (partially done — cold-start query still to be confirmed);
- ✅ stale data is rejected or clearly marked;
- ⏳ telemetry snapshots are replayable (contract supports it; loader
  not yet implemented).

### Phase 4: Connect optimization to observations

**Goal:** replace disconnected surrogate optimization with a measured
closed-loop objective.

**Status: NOT STARTED.**

Create a rolling metrics store keyed by function, layer, and time
window. Compute objective terms from observed or simulator-generated
values:

```
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
- tests prove that changing measured latency can change the selected
  policy.

### Phase 5: Build a reliable actuator

**Goal:** make Kubernetes changes safe and convergent.

**Status: NOT STARTED.** The current `KnativeScaler` patches
`min-scale` immediately, applies a deadband for scale-down, and logs
failures. It does not retry, does not reconcile, and does not persist a
desired state.

Add:

- desired-state records;
- idempotent patch generation;
- retry with bounded exponential backoff;
- conflict handling;
- observed-state refresh;
- reconciliation after controller restart;
- rate limits and change budgets;
- structured actuation results.

The actuator should support both shared-layer resources and function
services. It should expose a read-only plan for `shadow` and `dry_run`
modes.

**Acceptance criteria**

- repeated application of the same decision produces no unnecessary
  patch;
- transient Kubernetes failures are retried;
- permanent failures are surfaced to the controller;
- restart recovery converges to the desired allocation;
- every change has a decision ID and outcome.

### Phase 6: Add operating modes and end-to-end validation

**Goal:** validate the architecture without risking the live cluster.

**Status: PARTIALLY COMPLETE.**

Implemented modes:

1. ✅ **Simulation:** generated telemetry (currently aliased to mocks).
2. ✅ **Replay:** recorded telemetry (loader not yet implemented; mode
   flag exists).
3. ✅ **Shadow:** real telemetry, no actuation.
4. ✅ **Dry run:** validated plan, no Kubernetes writes.
5. ✅ **Live:** actuation path exists; retries and reconciliation are
   pending Phase 5.

Remaining work: complete the simulation and replay adapters, then run
the progression below.

```
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

- ⏳ offline and replay modes are deterministic (offline is; replay
  loader pending);
- ✅ shadow decisions are inspectable (audit log);
- ⏳ dry-run plans match live patch plans (depends on Phase 5);
- ⏳ one live trial records telemetry, decisions, patches, and outcomes
  together.

### Phase 7: Reproducible research release

**Goal:** make the final evaluation defensible and repeatable.

**Status: NOT STARTED.**

Add:

- pinned dependencies;
- CI for tests and smoke runs;
- experiment manifest files;
- commit and environment metadata;
- clean output directories per run;
- confidence intervals and effect sizes;
- controller overhead measurements;
- a limitations section covering simulator assumptions and live
  constraints.

**Acceptance criteria**

- a new machine can reproduce the offline matrix;
- every result maps to a commit, configuration, seed, and environment;
- figures and tables are generated from raw results;
- live and offline results are clearly distinguished.

## Recommended immediate sequence

Completed:

1. ✅ Shared typed contracts.
2. ✅ Hard allocation validator and tests.
3. ✅ Opt-in mock telemetry in live mode.
4. ✅ Five operating modes.

Next, in order:

5. **Phase 5 (P1):** rewrite
   [controller/allocator/knative_scaler.py](../../controller/allocator/knative_scaler.py)
   with idempotency, retries, reconciliation, and a persistent
   desired-state store.
6. **Phase 4 (P1):** build the rolling metrics store and wire it into
   the PSO objective.
7. **Phase 3 remainder:** validate the cold-start PromQL query against
   the deployed Knative metric schema.
8. **Phase 1 (P0):** define and implement the shared-layer runtime
   contract (sidecars, warm holders, or image prefetch).
9. **Phase 6 remainder:** run a W3 shadow experiment on a real KinD
   cluster, then one dry-run trial and one live trial.

The key milestone is not simply “the controller runs.” The target is
reached when the following statement is true:

> The simulator, telemetry adapter, optimizer, dependency graph, safety
> layer, and Kubernetes actuator describe and enforce the same
> allocation semantics.

## Completed work (as of this revision)

- `controller/contracts/` — typed telemetry, allocation, and decision
  models with validation.
- `controller/safety/feasibility.py` — hard feasibility gate; runs on
  both fuzzy and PSO paths.
- `controller/monitor/prometheus_client.py` — `probe()`,
  `force_mock_only()`, no silent fallback in `shadow` / `live`.
- `controller/main.py` — five operating modes, JSONL audit trail,
  bounded-delta fast loop, telemetry provenance tagging.
- `controller/granularity/tree.py` — non-allocatable node filtering,
  `parent_map` and `node_index` exposure.
- `controller/pso/pso_optimizer.py` — DAG-aware projection of particles
  onto the feasible subspace.
- `configs/dependencies.json` — `allocatable: false` on the structural
  root node.
- `tests/test_contracts.py`, `tests/test_feasibility.py` — new tests.
