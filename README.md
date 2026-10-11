<![CDATA[# GranuWarm: Adaptive Dependency-Aware Prewarming for Serverless Functions

> **Under Non-Stationary Workloads Using Fuzzy-Controlled Constrained Particle Swarm Optimization**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-v1.28-326CE5.svg)](https://kubernetes.io/)
[![Knative](https://img.shields.io/badge/knative-v1.13-0865AD.svg)](https://knative.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Abstract

Serverless computing delivers elastic, event-driven execution but suffers from **cold starts**—latency incurred when containers must be provisioned and initialized. GranuWarm is a closed-loop adaptive prewarming framework that integrates three complementary mechanisms:

1. **Mamdani Fuzzy Inference System** — Maps real-time workload signals (invocation intensity, traffic trend, cold-start pressure, resource utilization) to per-function warm-capacity recommendations
2. **Dependency Granularity Tree** — Decomposes function software stacks into hierarchical shareable layers (runtimes → libraries → function code) to exploit inter-function overlap
3. **Constrained Particle Swarm Optimizer** — Globally optimizes warm-resource allocation across granularity-tree nodes under hard memory budgets

GranuWarm uses a **dual-timescale architecture**: fast fuzzy loop (10s) for rapid adaptation + slow PSO loop (60s) for global re-optimization.

---

## Team Responsibility Matrix

| Member | Role | Roadmap Phases | Primary Deliverables | Verification Milestone |
|:---|:---|:---|:---|:---|
| **Tijil Gupta** | Cloud Native Infrastructure & Knative/Docker Lead | **Phase 0–4** | `docker/`, `functions/F1–F12`, `configs/cluster_config.yaml`, `scripts/setup_env.sh`, Knative Service YAMLs | All 12 functions deploy to Knative, respond to HTTP, auto-scale to zero |
| **Ayush Rawat** | Workload Profiling, Prometheus Signals & Simulation Lead | **Phase 5–7** | `controller/monitor/`, `workload/`, `simulator/` | Prometheus scraping live metrics; W1–W5 visible in dashboards; simulator runs 1000s in <3s |
| **Bhavya Yadav** | Fuzzy Inference, Granularity Tree & Empirical Evaluation Lead | **Phase 8, 9, 12, 13, 14** | `controller/fuzzy/`, `controller/granularity/`, `configs/fuzzy_rules.json`, `configs/dependencies.json`, `baselines/`, `experiments/`, `scripts/plot_results.py` | 27 fuzzy rules pass unit tests; tree projection correct; 150-run experiment matrix completes |
| **Harshit Arya** | Lead Architect & Constrained Optimization Lead | **Phase 10, 11 + Integration** | `controller/pso/`, `controller/main.py`, `controller/allocator/`, system integration | PSO converges within budget; dual-timescale controller runs 30+ min without flapping |

### Dependency Chain Between Phases

```
Phase 0–4 (Tijil) ─────────────────┐
                                     ├──► Phase 8–9 (Bhavya Yadav
                                     ) ──► Phase 10 (Harshit)
Phase 5–7 (Ayush) ──────────────────┘                                    │
                                                                         ▼
                                                               Phase 11 (Harshit)
                                                                         │
                                                                         ▼
                                                          Phase 12–14 (Bhavya Yadav
                                                           + Harshit)
```

---

## Repository Directory Layout

```
granuwarm/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── configs/
│   ├── cluster_config.yaml            # KinD multi-node cluster configuration
│   ├── fuzzy_rules.json               # 27 Mamdani fuzzy rules (Table 2)
│   └── dependencies.json              # 12-function dependency hierarchy
├── docker/
│   ├── base_python/Dockerfile         # Python 3.11-slim base image
│   └── base_node/Dockerfile           # Node.js 20-slim base image
├── functions/                         # F1–F12 benchmark function source + service.yaml
│   ├── f01_hello_world/
│   ├── f02_json_transform/
│   ├── f03_image_resize/
│   ├── f04_image_filter/
│   ├── f05_thumbnail_gen/
│   ├── f06_ml_inference/
│   ├── f07_sentiment_analysis/
│   ├── f08_data_aggregate/
│   ├── f09_csv_parser/
│   ├── f10_auth_service/
│   ├── f11_order_process/
│   └── f12_notification/
├── controller/
│   ├── __init__.py
│   ├── monitor/
│   │   ├── __init__.py
│   │   └── prometheus_client.py       # PromQL signal extraction (R_i, T_i, C_i, M)
│   ├── fuzzy/
│   │   ├── __init__.py
│   │   └── fuzzy_engine.py            # 27-rule Mamdani FIS (trimf, trapmf, centroid)
│   ├── granularity/
│   │   ├── __init__.py
│   │   └── tree.py                    # 3-layer dependency DAG + max-projection
│   ├── pso/
│   │   ├── __init__.py
│   │   └── pso_optimizer.py           # Vectorized discrete constrained PSO
│   ├── allocator/
│   │   ├── __init__.py
│   │   └── knative_scaler.py          # Kubernetes API patching with hysteresis
│   └── main.py                        # Dual-timescale control loop orchestrator
├── simulator/
│   ├── __init__.py
│   ├── env.py                         # Discrete-event FaaS simulation engine
│   └── run_sim.py                     # CLI runner for offline simulation
├── workload/
│   ├── __init__.py
│   ├── profiles.py                    # W1–W5 mathematical rate functions
│   └── generator.py                   # Async HTTP workload generator
├── baselines/
│   ├── __init__.py
│   ├── base_policy.py                 # Abstract BasePolicy interface
│   ├── b1_no_prewarm.py
│   ├── b2_fixed_prewarm.py
│   ├── b3_fuzzy_only.py
│   ├── b4_pso_only.py
│   ├── b5_fuzzy_pso_no_granularity.py
│   └── b6_granuwarm_full.py
├── experiments/
│   └── run_experiment.py              # 150-run automated experiment matrix
├── scripts/
│   ├── setup_env.sh                   # KinD + Knative + Prometheus setup
│   ├── reset_cluster.py               # Inter-run cluster cleanup
│   └── plot_results.py                # Publication-quality figures + LaTeX tables
├── results/
│   ├── raw/                           # CSV experiment logs
│   ├── plots/                         # Generated figures (PDF/PNG)
│   └── tables/                        # LaTeX table output
├── tests/
│   ├── test_fuzzy.py
│   ├── test_tree.py
│   └── test_pso.py
└── docs/
    └── phase_guides/
        ├── STAGE_1_INFRA_FUNCTIONS.md
        ├── STAGE_2_TELEMETRY_SIMULATOR.md
        ├── STAGE_3_INTELLIGENCE_CORE.md
        └── STAGE_4_CONTROLLER_EXPERIMENTS_PAPER.md
```

---

## Environment Setup & Quickstart

### Prerequisites

- Ubuntu 22.04 LTS (native, dual-boot, or VM: ≥8 CPU cores, ≥16 GB RAM)
- Docker Engine v26+
- Python 3.11+

### Step 1: Clone & Setup Virtual Environment

```bash
git clone <repository-url> granuwarm && cd granuwarm
python3 -m venv venv && source venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt
```

### Step 2: Install KinD & Create Cluster

```bash
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind
kind create cluster --config configs/cluster_config.yaml --name granuwarm-local
```

### Step 3: Install Knative Serving v1.13 + Kourier + Prometheus

```bash
chmod +x scripts/setup_env.sh && ./scripts/setup_env.sh
```

### Step 4: Build & Deploy Functions

```bash
# Build all 12 function images
for dir in functions/f*/; do
    fname=$(basename "$dir")
    docker build -t "granuwarm/${fname}:v1" "$dir"
    kind load docker-image "granuwarm/${fname}:v1" --name granuwarm-local
done

# Deploy to Knative
kubectl apply -f functions/
```

### Step 5: Run GranuWarm Controller

```bash
python controller/main.py &
python workload/generator.py --profile W3 --duration 300 --seed 42
```

### Step 6: Run Full Experiment Matrix

```bash
python experiments/run_experiment.py --full
python scripts/plot_results.py
```

---

## Contributing & Collaboration Guide

We welcome contributions from team members, lab colleagues, and the broader research community. Follow this step-by-step guide to collaborate on the GranuWarm repository.

### 1. Fork & Clone the Repository

```bash
# 1a. Click the "Fork" button on the GitHub repo page (top-right corner)
#     This creates your personal copy at github.com/<your-username>/granuwarm

# 1b. Clone YOUR fork locally
git clone https://github.com/<your-username>/granuwarm.git
cd granuwarm

# 1c. Add the original repository as an "upstream" remote
git remote add upstream https://github.com/Harshit007-alt/GranWarm.git

# 1d. Verify your remotes
git remote -v
# origin    https://github.com/<your-username>/granuwarm.git (fetch)
# origin    https://github.com/<your-username>/granuwarm.git (push)
# upstream  https://github.com/Harshit007-alt/GranWarm.git  (fetch)
# upstream  https://github.com/Harshit007-alt/GranWarm.git  (push)
```

### 2. Keep Your Fork in Sync

Before starting any new work, always sync with the latest upstream changes:

```bash
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
```

### 3. Create a Feature Branch

**Never work directly on `main`.** Create a descriptive branch for each task:

```bash
# Branch naming convention:
#   feature/<phase>-<short-description>   — for new features
#   bugfix/<issue-number>-<description>   — for bug fixes
#   docs/<description>                    — for documentation changes
#   experiment/<description>              — for experiment scripts/configs

# Examples:
git checkout -b feature/phase8-fuzzy-engine
git checkout -b bugfix/42-pso-convergence-fix
git checkout -b docs/add-api-reference
git checkout -b experiment/w4-burst-profile
```

### 4. Development Workflow

```bash
# 4a. Set up the virtual environment (first time only)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 4b. Make your changes — edit files, add new modules, write tests

# 4c. Run the test suite before committing
python -m pytest tests/ -v

# 4d. (Optional) Run the simulator to verify behavior
python simulator/run_sim.py --workload W1 --duration 300 --seed 42
```

### 5. Commit Guidelines

Follow clear, conventional commit messages:

```bash
# Format: <type>(<scope>): <short description>
#
# Types: feat, fix, docs, test, refactor, perf, chore, experiment
# Scope: fuzzy, pso, tree, controller, simulator, infra, baselines, etc.

# Examples:
git add controller/fuzzy/fuzzy_engine.py tests/test_fuzzy.py
git commit -m "feat(fuzzy): implement 27-rule Mamdani FIS with centroid defuzzification"

git add simulator/env.py
git commit -m "fix(simulator): enforce memory budget cap in step_invoke"

git add docs/phase_guides/STAGE_3_INTELLIGENCE_CORE.md
git commit -m "docs(phase-guide): add verification checklist for Phase 8–10"

git add experiments/run_experiment.py
git commit -m "experiment(matrix): add W4 burst-spike workload to experiment matrix"
```

**Commit best practices:**
- Keep commits atomic — one logical change per commit
- Write commits in imperative mood ("add feature" not "added feature")
- Reference issue numbers when applicable: `fix(pso): handle edge case (#17)`

### 6. Push & Open a Pull Request (PR)

```bash
# 6a. Push your feature branch to YOUR fork
git push origin feature/phase8-fuzzy-engine

# 6b. Go to the upstream repository on GitHub
#     GitHub will show a "Compare & pull request" banner — click it

# 6c. Fill out the PR template:
```

**PR Title:** `feat(fuzzy): implement 27-rule Mamdani FIS`

**PR Description Template:**

```markdown
## Summary
Brief description of what this PR implements/fixes.

## Related Phase
Phase 8 — Fuzzy Inference System

## Changes Made
- [ ] Added `controller/fuzzy/fuzzy_engine.py` with 27 Mamdani rules
- [ ] Added `tests/test_fuzzy.py` with 8 unit tests
- [ ] Updated `configs/fuzzy_rules.json` with rule definitions

## Testing
- [ ] All existing tests pass (`python -m pytest tests/ -v`)
- [ ] New unit tests added and passing
- [ ] Simulator validation run completed (if applicable)

## Verification Criteria (from Phase Guide)
- [ ] FIS produces monotonic output for increasing invocation rate
- [ ] Centroid defuzzification yields values in [0, 1]

## Screenshots / Logs
(Attach relevant output, plots, or terminal logs)
```

### 7. Code Review Process

All PRs require at least **one approving review** before merge:

| Step | Action | Who |
|:---|:---|:---|
| 1 | Open PR with description & linked issues | Author |
| 2 | Auto-assign reviewers based on phase ownership (see Team Matrix above) | GitHub / Author |
| 3 | Reviewer leaves inline comments or approves | Reviewer |
| 4 | Author addresses feedback, pushes fixes | Author |
| 5 | Reviewer re-reviews and approves | Reviewer |
| 6 | **Squash & merge** into `main` | Author or Lead |

**Review assignment guidelines:**
- Phase 0–4 changes → **Tijil Gupta** reviews
- Phase 5–7 changes → **Ayush Rawat** reviews
- Phase 8–9, 12–14 changes → **Bhavya Yadav** reviews
- Phase 10–11, integration changes → **Harshit Arya** reviews
- Cross-phase changes → require **two** reviewers

### 8. Issue Tracking & Project Board

Use GitHub Issues to track bugs, feature requests, and tasks:

```markdown
# Creating an Issue — use these labels:

Labels:
  🐛 bug              — Something isn't working
  ✨ enhancement       — New feature or improvement
  📄 documentation     — Documentation updates
  🔬 experiment        — Experiment design or execution
  🏗️ infrastructure   — Docker, K8s, Knative setup
  ❓ question          — Discussion or clarification needed
  🔴 priority:high     — Blocking other work
  🟡 priority:medium   — Important but not blocking
  🟢 priority:low      — Nice to have

# Issue title examples:
  "[Phase 8] FIS output is non-monotonic for edge-case input"
  "[Phase 11] Controller flaps when memory budget is near capacity"
  "[Experiment] Add W4 burst-spike workload profile"
```

**GitHub Projects Board** — We use a Kanban board with columns:
| Column | Description |
|:---|:---|
| **Backlog** | Planned tasks not yet started |
| **In Progress** | Actively being worked on |
| **In Review** | PR open, awaiting review |
| **Done** | Merged to `main` and verified |

### 9. Branch Protection Rules

The `main` branch has the following protections:

- ✅ Require pull request before merging
- ✅ Require at least 1 approving review
- ✅ Require status checks to pass (unit tests)
- ✅ Require branches to be up to date before merging
- ❌ No direct pushes to `main`

### 10. Communication & Coordination

| Channel | Purpose |
|:---|:---|
| **GitHub Issues** | Bug reports, feature requests, task tracking |
| **GitHub Discussions** | Design decisions, architecture questions, research ideas |
| **PR Comments** | Code-level feedback and review |
| **Weekly Sync** | 30-min video call — progress updates, blocker resolution |

**Coordination rules:**
- Tag teammates with `@username` in issues/PRs when their input is needed
- Use `WIP:` prefix in PR titles for work-in-progress (draft PRs)
- Post experiment results as GitHub Issue comments with attached plots
- Document all design decisions in `docs/` for future reference

### 11. Quick Reference: Common Contribution Scenarios

<details>
<summary><strong>Scenario A: "I want to fix a bug I found"</strong></summary>

```bash
git checkout main && git pull upstream main
git checkout -b bugfix/42-memory-leak-in-simulator
# ... make fix ...
python -m pytest tests/ -v
git add -A && git commit -m "fix(simulator): patch memory leak in step_invoke (#42)"
git push origin bugfix/42-memory-leak-in-simulator
# → Open PR on GitHub
```
</details>

<details>
<summary><strong>Scenario B: "I want to add a new workload profile (W6)"</strong></summary>

```bash
git checkout main && git pull upstream main
git checkout -b feature/w6-periodic-burst
# Edit workload/profiles.py — add W6 function
# Edit workload/generator.py — register W6
# Add test in tests/test_workload.py
python -m pytest tests/ -v
git add -A && git commit -m "feat(workload): add W6 periodic-burst profile"
git push origin feature/w6-periodic-burst
# → Open PR on GitHub
```
</details>

<details>
<summary><strong>Scenario C: "I want to improve documentation"</strong></summary>

```bash
git checkout main && git pull upstream main
git checkout -b docs/improve-phase-guide-stage3
# Edit docs/phase_guides/STAGE_3_INTELLIGENCE_CORE.md
git add -A && git commit -m "docs(phase-guide): clarify PSO convergence criteria"
git push origin docs/improve-phase-guide-stage3
# → Open PR on GitHub
```
</details>

<details>
<summary><strong>Scenario D: "I want to run and submit experiment results"</strong></summary>

```bash
git checkout main && git pull upstream main
git checkout -b experiment/run-w3-full-matrix
# Run the experiment
python experiments/run_experiment.py --workload W3 --policies all --runs 5
# Generate plots
python scripts/plot_results.py
# Commit ONLY results (not code changes)
git add results/raw/ results/plots/ results/tables/
git commit -m "experiment(W3): complete 30-run matrix for W3 diurnal workload"
git push origin experiment/run-w3-full-matrix
# → Open PR on GitHub with plot screenshots in the description
```
</details>

---

## Mathematical Foundation

### Composite Fitness Function (PSO Objective)

```
J(x) = w_L · L̄(x) + w_C · C̄(x) + w_M · M̂(x) + w_S · S̄(x)
      + ρ · max(0, Σ m_vk · x_k − M_budget)²
```

| Weight | Symbol | Default |
|:---|:---|:---|
| Latency | w_L | 0.35 |
| Cold-Start Rate | w_C | 0.25 |
| Idle Memory | w_M | 0.25 |
| SLA Violations | w_S | 0.15 |
| Penalty Coeff. | ρ | 100 |

### PSO Hyperparameters

| Parameter | Value |
|:---|:---|
| Swarm Size | 30 |
| Max Iterations | 50 |
| Inertia ω | 0.7 → 0.4 (linear decay) |
| Cognitive c₁ | 1.5 |
| Social c₂ | 1.5 |

### Control Loop Intervals

| Loop | Interval | Purpose |
|:---|:---|:---|
| Fast (Fuzzy) | Δt_fast = 10s | Rapid reactive adaptation |
| Slow (PSO) | Δt_slow = 60s | Global re-optimization |
| Hysteresis | ε_reclaim = 2 | Flapping prevention |

---

## Research Questions

- **RQ1**: Does workload-aware fuzzy control reduce cold-start frequency and latency compared to fixed/static prewarming?
- **RQ2**: Does constrained PSO optimization improve the latency–resource tradeoff beyond what either technique achieves independently?
- **RQ3**: Does incorporating dependency-granularity structure improve resource efficiency compared to function-level prewarming?

---

## Citation

```bibtex
@article{granuwarm2026,
  title={GranuWarm: Adaptive Dependency-Aware Prewarming for Serverless Functions Under Non-Stationary Workloads Using Fuzzy-Controlled Constrained Particle Swarm Optimization},
  author={Arya, Harshit and Gupta, Tijil and Rawat, Ayush},
  year={2026}
}
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
]]>
