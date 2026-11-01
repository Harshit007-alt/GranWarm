# Paper vs. Implementation Notes

This document records where the codebase and the accompanying research paper
draft (`docs/our-research-paper/granu-draft.tex`) diverge. The paper is a
draft, so these notes are a working checklist for reconciliation, not a final
review. They describe the **current** state of the repository.

The offline simulation path faithfully implements the paper's three core
mechanisms (Mamdani FIS, dependency-granularity tree, constrained discrete PSO)
and reproduces the statistical-significance claim. The items below are the
known divergences to reconcile.

---

## 1. Granularity-tree dimension: K = 19, not 20

The paper states K = 20 granularity-tree nodes. The config
(`configs/dependencies.json`) defines 20 nodes, but `root` is marked
`allocatable: false`, so `GranularityTree.get_total_nodes()` returns **19
allocatable** nodes and the PSO search dimension is 19.

`tests/test_pso.py` hardcodes dimension = 20 (with a 20-length memory array
including a zero for root), suggesting the K = 20 figure was assumed and the
non-allocatable root was an oversight.

Also, `shared_native_libs` is allocatable but no function's `dependency_path`
references it, so it always projects to 0.

**To reconcile:** either make `root` allocatable (and re-derive K = 20) or
update the paper/test to K = 19.

## 2. Memory budget: 8192 MB in code, 4096 MB in the paper

The paper fixes the hard memory budget at `M_budget = 4096 MB`. The code
defaults to **8192 MB** in:

- `simulator/run_sim.py` (`--budget` default)
- `controller/main.py` (`GranuWarmController` default)
- `experiments/run_experiment.py` (`--budget` default)

`configs/controller_light.yaml` comments indicate 4096 MB was the intended
full budget ("Reduced from 4096 to match 6 lightweight functions"). The
committed 150-run matrix was produced at 8192 MB.

**To reconcile:** set the default budget to 4096 MB and re-run the matrix, or
update the paper to report 8192 MB.

## 3. Headline numbers not exactly reproduced

The paper's headline figures for B6 — P95 ≈ 43.24 ms and average memory ≈
280.49 MB — do not match the committed results in `results/raw/`. For example,
the W1/B6 run shows P95 ≈ 55 ms and substantially higher average-memory figures.

The qualitative ordering (B6 best on composite `J`, then B2, then the
non-granular dynamic baselines) and the Wilcoxon significance **are**
reproducible. Only the specific table values differ, reflecting a different
configuration/normalization than the committed run set (budget, duration,
and/or memory-accounting differences).

**To reconcile:** identify which configuration produced the paper's table
numbers (likely 4096 MB budget + a specific duration) and reproduce that exact
run set, or update the paper tables to the committed results.

## 4. Dual-timescale 10 s / 60 s separation is live-only

The paper's dual-timescale control loop runs fuzzy inference every 10 s and PSO
every 60 s. In the **offline sim**, `simulator/run_sim.py` runs the active
policy's `compute_allocation` (including PSO for B4/B5/B6) on **every 10 s
control cycle** — there is no 60 s slow-loop cadence.

The 60 s slow-loop separation is only enforced in `controller/main.py`
(`GranuWarmController.run_loop`: PSO when `now - t_last_pso >= dt_slow`, else a
bounded ±1-per-node delta). That controller is the **live** path and is not
exercised by the offline results.

**To reconcile:** add a slow-loop gate to the offline sim so PSO runs every
60 s (with bounded fuzzy deltas in between), or document that the offline
results use a single-timescale 10 s loop.

## 5. "Greedy budget repair" is proportional shrink

The paper describes a deterministic greedy repair that prunes the node with the
highest `memory_mb / init_time_ms` ratio until the budget is met. In code this
is realized as a **proportional-shrink** repair in
`controller/safety/feasibility.py` (`FeasibilityService.repair`: scales all
over-budget capacities by `budget/est` over up to 20 attempts, then re-clamps
dependency constraints), plus greedy per-function packing in B2/B3/B5.

This is a reasonable but not strictly greedy interpretation.

**To reconcile:** implement the ratio-based greedy pruning described in the
paper, or update the paper to describe proportional-shrink repair.

## 6. Time-stepped, not a priority-queue event loop

`simulator/env.py`'s docstring calls it a "discrete-event simulation engine,"
but it is a **time-stepped** simulator: `run_sim.py` advances in fixed
`dt = 0.5 s` steps, generates Poisson arrivals per step
(`rng.poisson(rate * dt)`), scatters them uniformly within the interval, sorts
them chronologically, and dispatches each to `step_invoke`. There is no
`heapq` priority-queue event loop.

Arrival events are still processed chronologically within each step, so the
behavior approximates a discrete-event simulation at 0.5 s resolution.

**To reconcile:** either re-implement with a priority-queue event loop, or
update the docstring/paper wording to "time-stepped" / "discrete-time".

---

## What is faithful

For reference, the following match the paper:

- Mamdani FIS: 27 rules, `trimf`/`trapmf` membership functions, min-AND
  antecedents, max aggregation, centroid defuzzification
  (`controller/fuzzy/fuzzy_engine.py`, `configs/fuzzy_rules.json`).
- Granularity max-projection `P_k = max{ P_i : f_i depends on v_k }`
  (`controller/granularity/tree.py`).
- Constrained discrete PSO: S = 30 particles, 50 iterations, inertia decay
  0.7 → 0.4, c1 = c2 = 1.5, informed seeding from the fuzzy prior, Deb
  parameter-less constraint penalty, DAG projection
  (`controller/pso/pso_optimizer.py`).
- Six distinct ablation configurations B1–B6 (`baselines/`).
- Five workload regimes W1–W5 (`workload/profiles.py`).
- Twelve benchmark functions F01–F12 with dependency paths
  (`configs/dependencies.json`).
- Composite-fitness weights `w_L / w_C / w_M / w_S = 0.35 / 0.25 / 0.25 / 0.15`
  (`experiments/run_experiment.py`).
- Wilcoxon signed-rank `p = 0.00195` at N = 10 (seeds 42 & 123), matching the
  paper exactly (`results/stats_summary.txt`).
