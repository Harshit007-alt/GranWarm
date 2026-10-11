# GranuWarm

**Adaptive dependency-aware prewarming for serverless functions under
non-stationary workloads**

GranuWarm is a closed-loop serverless resource-management architecture that
combines workload telemetry, fuzzy control, dependency-aware warm layers, and
constrained particle swarm optimization (PSO) to reduce cold-start latency
under a cluster memory budget.

This README describes the **target architecture**: the end-state system that
the project is designed to implement. The implementation inventory and the
steps required to reach this design are documented separately:

- [Current architecture](docs/architecture/current-architecture.md)
- [Architecture gap analysis and roadmap](docs/architecture/gap-analysis-and-roadmap.md)

## Target architecture at a glance

```text
                         +-----------------------------+
                         |        Workload sources     |
                         |  clients, traces, profiles  |
                         +--------------+--------------+
                                        |
                                        v
                         +-----------------------------+
                         |   Serverless runtime plane  |
                         |  Knative services/functions |
                         +--------------+--------------+
                                        |
                 metrics                 | requests / latency
                                        v
 +------------------+       +-----------------------------+
 | Prometheus        |------>| Telemetry and feature       |
 | metrics store     |       | extraction                 |
 +------------------+       | rate, trend, cold starts,  |
                            | memory, SLA pressure        |
                            +--------------+--------------+
                                           |
                                           v
                            +-----------------------------+
                            | Fast control loop            |
                            | Fuzzy inference              |
                            | every 10 seconds             |
                            +--------------+--------------+
                                           |
                                           v
                            +-----------------------------+
                            | Dependency-granularity       |
                            | graph / shared warm-layer    |
                            | projection                  |
                            +--------------+--------------+
                                           |
                         fuzzy prior       v
                            +-----------------------------+
                            | Slow global optimizer        |
                            | constrained discrete PSO    |
                            | every 60 seconds             |
                            +--------------+--------------+
                                           |
                                           v
                            +-----------------------------+
                            | Policy and safety layer      |
                            | hard memory budget           |
                            | bounds, validation,          |
                            | hysteresis, reconciliation   |
                            +--------------+--------------+
                                           |
                                           v
                            +-----------------------------+
                            | Allocation actuator          |
                            | shared layers + function     |
                            | warm capacity                |
                            +--------------+--------------+
                                           |
                                           v
                         +-----------------------------+
                         | Knative/Kubernetes runtime   |
                         | deploy, prewarm, scale,       |
                         | observe, reconcile            |
                         +-----------------------------+
```

## Target design principles

1. **Closed loop:** every allocation decision is based on observed workload
   and runtime state.
2. **Two timescales:** fuzzy control reacts quickly; PSO performs slower global
   re-optimization.
3. **Dependency awareness:** shared runtimes and libraries are represented as
   reusable warm layers rather than treating every function as unrelated.
4. **Budget safety:** no allocation may violate the configured memory budget.
5. **Safe actuation:** changes are bounded, hysteresis-protected,
   idempotent, observable, and reconciled after failures.
6. **Simulation/live parity:** the simulator and the live controller use the
   same telemetry, allocation, memory-accounting, and dependency semantics.
7. **Reproducibility:** every experiment records configuration, code revision,
   dependency versions, workload profile, and random seeds.

## Target components

### 1. Runtime plane

The runtime plane hosts heterogeneous Python and Node.js functions as Knative
Services on Kubernetes. Each function has:

- an immutable image and version;
- a service identity;
- runtime and dependency metadata;
- memory and startup-cost estimates;
- an allocation target that can be reconciled by the controller.

The target design introduces a runtime abstraction for shared warm layers.
Layer nodes may represent a runtime, shared library bundle, native library
bundle, or function-specific code. The actuator must translate layer
allocations into real runtime resources or an explicitly supported equivalent.

### 2. Telemetry plane

Prometheus collects the signals needed by the controller. For each function
and shared layer, the telemetry adapter produces a typed feature record:

| Signal | Meaning | Domain |
| --- | --- | --- |
| `R_i` | Invocation intensity | `[0, 1]` |
| `T_i` | Traffic trend | `[-1, 1]` |
| `C_i` | Cold-start pressure | `[0, 1]` |
| `M` | Memory pressure | `[0, 1]` |
| `L_i` | Observed latency features | milliseconds / quantiles |
| `S_i` | SLA pressure | `[0, 1]` |

Missing or stale required metrics are explicit controller errors. Synthetic
fallback values are allowed only in simulator and test modes.

### 3. Fast fuzzy controller

Every 10 seconds, the controller:

1. reads a consistent telemetry snapshot;
2. evaluates the 27-rule Mamdani fuzzy system;
3. produces a normalized warm-capacity recommendation per function;
4. projects those recommendations over the dependency graph; and
5. submits a bounded allocation prior to the policy layer.

### 4. Dependency-granularity graph

The dependency graph contains parent-child relationships between shared
layers and function leaves. A function can depend on multiple reusable layers.
The graph is responsible for:

- determining which functions benefit from a warm layer;
- calculating shared memory contribution;
- calculating startup-time savings;
- projecting function demand to layer demand; and
- mapping a valid layer allocation back to executable function capacity.

The simulator and live runtime must use the same graph semantics.

### 5. Slow constrained PSO optimizer

Every 60 seconds, PSO searches an integer allocation vector:

```text
x = [x_root, x_runtime, x_library, ..., x_function]
```

The target objective combines:

```text
latency + cold-start cost + idle-memory cost + SLA cost
```

subject to:

```text
total shared and function memory <= configured budget
allocation bounds and dependency constraints
```

Infeasible candidates are rejected or repaired before actuation. Penalties may
shape optimization, but they do not replace hard feasibility checks.

### 6. Safety and actuation layer

Before a change reaches Kubernetes, the policy layer must:

- validate the complete allocation;
- enforce minimum and maximum capacity;
- enforce the memory budget;
- reject stale decisions;
- apply hysteresis to scale-down;
- rate-limit changes;
- emit an auditable decision record; and
- reconcile desired state with observed state.

The actuator then applies changes to shared warm-layer resources and Knative
function services through an idempotent Kubernetes adapter.

## Target control loop

```text
1. Observe
   Prometheus -> typed telemetry snapshot

2. React
   telemetry -> fuzzy recommendation per function

3. Project
   function recommendations -> dependency-layer priorities

4. Optimize
   priorities + measured metrics -> feasible PSO allocation

5. Validate
   budget, bounds, freshness, hysteresis, safety policy

6. Actuate
   desired allocation -> Kubernetes/Knative resources

7. Reconcile
   observed state and metrics -> next control cycle
```

## Target operating modes

| Mode | Purpose |
| --- | --- |
| Simulation | Fast, deterministic evaluation with the same policy interfaces |
| Shadow | Read telemetry and calculate decisions without changing Kubernetes |
| Dry run | Emit validated actuator operations without applying them |
| Live | Apply decisions with retries, reconciliation, and audit logs |
| Replay | Re-run a recorded telemetry trace for regression testing |

## Target evaluation

The target evaluation compares:

- no prewarming;
- fixed prewarming;
- fuzzy-only control;
- PSO-only control;
- fuzzy + PSO without dependency granularity; and
- the complete GranuWarm architecture.

Each experiment should report latency quantiles, cold-start rate, SLA
violations, used memory, idle memory, controller overhead, allocation changes,
and budget violations. Results must be reproducible across W1–W5 workload
profiles and fixed random seeds.

## Repository orientation

| Area | Target responsibility |
| --- | --- |
| `controller/` | Telemetry, fuzzy inference, graph projection, optimization, actuation |
| `configs/` | Function metadata, dependency graph, fuzzy rules, cluster settings |
| `simulator/` | Offline implementation of the target control semantics |
| `baselines/` | Ablation and comparison policies |
| `workload/` | Workload profiles and live traffic generation |
| `experiments/` | Matrix execution and result collection |
| `functions/` | Heterogeneous serverless workloads |
| `scripts/` | Cluster setup, cleanup, plotting, and reporting |
| `docs/architecture/` | Target design, current implementation, and migration plan |

## Getting started

The simulator is the first target-compatible execution environment:

```bash
python -m pytest tests -q
python simulator/run_sim.py \
  --workload W3 \
  --policy granuwarm \
  --duration 300 \
  --seed 42
```

For the live Kubernetes path, see the implementation and migration documents
before enabling actuation:

- [Current architecture](docs/architecture/current-architecture.md)
- [Architecture gap analysis and roadmap](docs/architecture/gap-analysis-and-roadmap.md)

## Research questions

1. Does workload-aware fuzzy control reduce cold-start frequency and latency
   compared with no or fixed prewarming?
2. Does constrained PSO improve the latency/resource trade-off beyond fuzzy
   control alone?
3. Does dependency-granularity modeling improve resource efficiency compared
   with function-level prewarming?

## Citation

```bibtex
@article{granuwarm2026,
  title   = {GranuWarm: Adaptive Dependency-Aware Prewarming for Serverless
             Functions Under Non-Stationary Workloads Using Fuzzy-Controlled
             Constrained Particle Swarm Optimization},
  author  = {Arya, Harshit and Gupta, Tijil and Rawat, Ayush and Yadav, Bhavya},
  year    = {2026}
}
```
