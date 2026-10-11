<div align="center">

# 🔥 GranuWarm

**Adaptive Dependency-Aware Prewarming for Serverless Functions**
*Under Non-Stationary Workloads Using Fuzzy-Controlled Constrained Particle Swarm Optimization*

&nbsp;

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-v1.28-326CE5?style=for-the-badge&logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Knative](https://img.shields.io/badge/knative-v1.13-0865AD?style=for-the-badge&logo=knative&logoColor=white)](https://knative.dev/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=for-the-badge)](CONTRIBUTING.md)

&nbsp;

[📄 Abstract](#abstract) · [🏗️ Architecture](#architecture) · [👥 Team](#team) · [📁 Structure](#repository-structure) · [🚀 Quickstart](#getting-started) · [🤝 Contributing](#contributing--collaboration) · [📐 Math](#mathematical-foundation) · [🔬 RQs](#research-questions)

</div>

---

## Abstract

Serverless computing delivers elastic, event-driven execution but suffers from **cold starts** — latency incurred when containers must be provisioned and initialized. **GranuWarm** is a closed-loop adaptive prewarming framework that integrates three complementary mechanisms:

<table>
  <tr>
    <td align="center"><strong>🧮</strong></td>
    <td><strong>Mamdani Fuzzy Inference System</strong></td>
    <td>Maps real-time workload signals (invocation intensity, traffic trend, cold-start pressure, resource utilization) to per-function warm-capacity recommendations</td>
  </tr>
  <tr>
    <td align="center"><strong>🌳</strong></td>
    <td><strong>Dependency Granularity Tree</strong></td>
    <td>Decomposes function software stacks into hierarchical shareable layers (runtimes → libraries → function code) to exploit inter-function overlap</td>
  </tr>
  <tr>
    <td align="center"><strong>🎯</strong></td>
    <td><strong>Constrained Particle Swarm Optimizer</strong></td>
    <td>Globally optimizes warm-resource allocation across granularity-tree nodes under hard memory budgets</td>
  </tr>
</table>

> 💡 **Dual-Timescale Architecture:** Fast fuzzy loop (**Δt = 10s**) for rapid adaptation + slow PSO loop (**Δt = 60s**) for global re-optimization.

---

## Architecture

```
                     ┌─────────────────────────────────────────────────┐
                     │            GranuWarm Control Loop               │
                     │                                                 │
   Prometheus ──────►│   ┌───────────┐     ┌────────────────────────┐  │
   Metrics           │   │   Fuzzy   │────►│   Granularity Tree     │  │
   (Rᵢ, Tᵢ,         │   │   Engine  │     │   (Max-Projection)     │  │
    Cᵢ, M)           │   │   (10s)   │     └───────────┬────────────┘  │
                     │   └───────────┘                 │               │
                     │                                 ▼               │
                     │                 ┌────────────────────────────┐   │───► Knative
                     │                 │  Constrained PSO  (60s)   │   │     API
                     │                 │  Budget-aware global       │   │     Patches
                     │                 │  optimization              │   │
                     │                 └────────────────────────────┘   │
                     └─────────────────────────────────────────────────┘
```

---

## Team

<table>
  <tr>
    <th>Member</th>
    <th>Role</th>
    <th>Phases</th>
    <th>Key Deliverables</th>
  </tr>
  <tr>
    <td><strong>Harshit Arya</strong></td>
    <td>Lead Architect &amp; Constrained Optimization</td>
    <td align="center">10, 11</td>
    <td><code>controller/pso/</code>, <code>controller/main.py</code>, system integration</td>
  </tr>
  <tr>
    <td><strong>Tijil Gupta</strong></td>
    <td>Cloud Native Infrastructure &amp; Knative/Docker</td>
    <td align="center">0–4</td>
    <td><code>docker/</code>, <code>functions/F1–F12</code>, <code>configs/cluster_config.yaml</code></td>
  </tr>
  <tr>
    <td><strong>Ayush Rawat</strong></td>
    <td>Workload Profiling &amp; Simulation</td>
    <td align="center">5–7</td>
    <td><code>controller/monitor/</code>, <code>workload/</code>, <code>simulator/</code></td>
  </tr>
  <tr>
    <td><strong>Bhavya Yadav</strong></td>
    <td>Fuzzy Inference, Granularity Tree &amp; Evaluation</td>
    <td align="center">8, 9, 12–14</td>
    <td><code>controller/fuzzy/</code>, <code>controller/granularity/</code>, <code>experiments/</code></td>
  </tr>
</table>

### Phase Dependency Chain

```
Phase 0–4 (Tijil)  ───────┐
                           ├──► Phase 8–9 (Bhavya) ──► Phase 10 (Harshit)
Phase 5–7 (Ayush)  ───────┘                                    │
                                                                ▼
                                                       Phase 11 (Harshit)
                                                                │
                                                                ▼
                                                    Phase 12–14 (Bhavya + Harshit)
```

---

## Repository Structure

```
granuwarm/
│
├── 📄 README.md
├── 📄 requirements.txt
│
├── ⚙️ configs/
│   ├── cluster_config.yaml              # KinD multi-node cluster config
│   ├── fuzzy_rules.json                 # 27 Mamdani fuzzy rules (Table 2)
│   └── dependencies.json               # 12-function dependency hierarchy
│
├── 🐳 docker/
│   ├── base_python/Dockerfile           # Python 3.11-slim base
│   └── base_node/Dockerfile             # Node.js 20-slim base
│
├── ⚡ functions/                         # F1–F12 benchmark functions
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
│
├── 🧠 controller/
│   ├── main.py                          # Dual-timescale control loop
│   ├── monitor/
│   │   └── prometheus_client.py         # PromQL signal extraction
│   ├── fuzzy/
│   │   └── fuzzy_engine.py              # 27-rule Mamdani FIS
│   ├── granularity/
│   │   └── tree.py                      # 3-layer dependency DAG
│   ├── pso/
│   │   └── pso_optimizer.py             # Discrete constrained PSO
│   └── allocator/
│       └── knative_scaler.py            # K8s API patching + hysteresis
│
├── 🔄 simulator/
│   ├── env.py                           # Discrete-event FaaS simulation
│   └── run_sim.py                       # CLI runner
│
├── 📊 workload/
│   ├── profiles.py                      # W1–W5 rate functions
│   └── generator.py                     # Async HTTP generator
│
├── 📏 baselines/
│   ├── base_policy.py                   # Abstract interface
│   ├── b1_no_prewarm.py
│   ├── b2_fixed_prewarm.py
│   ├── b3_fuzzy_only.py
│   ├── b4_pso_only.py
│   ├── b5_fuzzy_pso_no_granularity.py
│   └── b6_granuwarm_full.py
│
├── 🧪 experiments/
│   └── run_experiment.py                # 150-run experiment matrix
│
├── 🛠️ scripts/
│   ├── setup_env.sh                     # KinD + Knative + Prometheus
│   ├── reset_cluster.py                 # Inter-run cleanup
│   └── plot_results.py                  # Publication figures + LaTeX
│
├── 📈 results/
│   ├── raw/                             # CSV experiment logs
│   ├── plots/                           # Generated figures
│   └── tables/                          # LaTeX tables
│
├── ✅ tests/
│   ├── test_fuzzy.py
│   ├── test_tree.py
│   └── test_pso.py
│
└── 📖 docs/
    └── phase_guides/
        ├── STAGE_1_INFRA_FUNCTIONS.md
        ├── STAGE_2_TELEMETRY_SIMULATOR.md
        ├── STAGE_3_INTELLIGENCE_CORE.md
        └── STAGE_4_CONTROLLER_EXPERIMENTS_PAPER.md
```

---

## Getting Started

### Prerequisites

<table>
  <tr>
    <th>Requirement</th>
    <th>Version</th>
  </tr>
  <tr><td>🖥️ OS</td><td>Ubuntu 22.04 LTS (native, dual-boot, or VM)</td></tr>
  <tr><td>⚙️ Hardware</td><td>≥ 8 CPU cores, ≥ 16 GB RAM</td></tr>
  <tr><td>🐳 Docker</td><td>v26+</td></tr>
  <tr><td>🐍 Python</td><td>3.11+</td></tr>
</table>

### Step 1 — Clone & Setup

```bash
git clone https://github.com/Harshit007-alt/GranWarm.git granuwarm && cd granuwarm
python3 -m venv venv && source venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt
```

### Step 2 — Create KinD Cluster

```bash
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind
kind create cluster --config configs/cluster_config.yaml --name granuwarm-local
```

### Step 3 — Install Knative + Prometheus

```bash
chmod +x scripts/setup_env.sh && ./scripts/setup_env.sh
```

### Step 4 — Build & Deploy Functions

```bash
for dir in functions/f*/; do
    fname=$(basename "$dir")
    docker build -t "granuwarm/${fname}:v1" "$dir"
    kind load docker-image "granuwarm/${fname}:v1" --name granuwarm-local
done

kubectl apply -f functions/
```

### Step 5 — Run Controller

```bash
python controller/main.py &
python workload/generator.py --profile W3 --duration 300 --seed 42
```

### Step 6 — Run Experiments

```bash
python experiments/run_experiment.py --full
python scripts/plot_results.py
```

---

## Contributing & Collaboration

We welcome contributions from team members, lab colleagues, and the broader research community.

<details>
<summary><strong>📥 1 · Fork & Clone</strong></summary>

&nbsp;

```bash
# Fork via GitHub UI → click "Fork" button (top-right)

# Clone YOUR fork
git clone https://github.com/<your-username>/granuwarm.git
cd granuwarm

# Add upstream remote
git remote add upstream https://github.com/Harshit007-alt/GranWarm.git

# Verify
git remote -v
```

</details>

<details>
<summary><strong>🔄 2 · Stay in Sync</strong></summary>

&nbsp;

Always pull upstream changes before starting new work:

```bash
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
```

</details>

<details>
<summary><strong>🌿 3 · Branch Naming</strong></summary>

&nbsp;

> ⚠️ **Never commit directly to `main`.**

| Prefix | Use Case | Example |
|:---|:---|:---|
| `feature/` | New features | `feature/phase8-fuzzy-engine` |
| `bugfix/` | Bug fixes | `bugfix/42-pso-convergence` |
| `docs/` | Documentation | `docs/add-api-reference` |
| `experiment/` | Experiment runs | `experiment/w4-burst-profile` |

```bash
git checkout -b feature/phase8-fuzzy-engine
```

</details>

<details>
<summary><strong>🔨 4 · Development Workflow</strong></summary>

&nbsp;

```bash
# Setup (first time)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Make changes, then test
python -m pytest tests/ -v

# Optional: validate with simulator
python simulator/run_sim.py --workload W1 --duration 300 --seed 42
```

</details>

<details>
<summary><strong>💬 5 · Commit Messages</strong></summary>

&nbsp;

We use **[Conventional Commits](https://www.conventionalcommits.org/)**:

```
<type>(<scope>): <short description>
```

| Type | When to Use |
|:---|:---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding/updating tests |
| `refactor` | Code change with no feature/fix |
| `perf` | Performance improvement |
| `experiment` | Experiment configs/results |

```bash
git commit -m "feat(fuzzy): implement 27-rule Mamdani FIS with centroid defuzzification"
git commit -m "fix(simulator): enforce memory budget cap in step_invoke"
git commit -m "experiment(matrix): add W4 burst-spike workload to run matrix"
```

> **Tips:** Keep commits atomic · Use imperative mood · Reference issues: `fix(pso): edge case (#17)`

</details>

<details>
<summary><strong>🚀 6 · Opening a Pull Request</strong></summary>

&nbsp;

```bash
git push origin feature/phase8-fuzzy-engine
```

Then open a PR on GitHub using this template:

```markdown
## Summary
Brief description of what this PR implements or fixes.

## Related Phase
Phase 8 — Fuzzy Inference System

## Changes
- [ ] Added `controller/fuzzy/fuzzy_engine.py` with 27 Mamdani rules
- [ ] Added `tests/test_fuzzy.py` with 8 unit tests
- [ ] Updated `configs/fuzzy_rules.json`

## Testing
- [ ] All existing tests pass (`python -m pytest tests/ -v`)
- [ ] New tests added and passing
- [ ] Simulator validation completed (if applicable)

## Verification Criteria
- [ ] FIS output is monotonic for increasing invocation rate
- [ ] Centroid defuzzification yields values in [0, 1]
```

</details>

<details>
<summary><strong>👀 7 · Code Review</strong></summary>

&nbsp;

All PRs require **at least one approving review** before merge.

| Step | Action | Owner |
|:---:|:---|:---|
| 1 | Open PR with description & linked issues | Author |
| 2 | Assign reviewer based on phase ownership | Author |
| 3 | Reviewer leaves inline comments or approves | Reviewer |
| 4 | Author addresses feedback, pushes fixes | Author |
| 5 | Reviewer re-reviews and approves | Reviewer |
| 6 | **Squash & merge** into `main` | Author / Lead |

**Reviewer assignments:**

| Changes in… | Reviewer |
|:---|:---|
| Phase 0–4 (infra, Docker, Knative) | **Tijil Gupta** |
| Phase 5–7 (workload, simulator) | **Ayush Rawat** |
| Phase 8–9, 12–14 (fuzzy, tree, experiments) | **Bhavya Yadav** |
| Phase 10–11 (PSO, controller) | **Harshit Arya** |
| Cross-phase | **Two reviewers** |

</details>

<details>
<summary><strong>🏷️ 8 · Issue Tracking</strong></summary>

&nbsp;

Use GitHub Issues with these labels:

| Label | Meaning |
|:---|:---|
| 🐛 `bug` | Something isn't working |
| ✨ `enhancement` | New feature or improvement |
| 📄 `documentation` | Docs updates |
| 🔬 `experiment` | Experiment design or execution |
| 🏗️ `infrastructure` | Docker, K8s, Knative setup |
| 🔴 `priority:high` | Blocking other work |
| 🟡 `priority:medium` | Important but not blocking |
| 🟢 `priority:low` | Nice to have |

**Issue title format:** `[Phase N] Short description`

</details>

<details>
<summary><strong>🔒 9 · Branch Protection</strong></summary>

&nbsp;

The `main` branch enforces:

- ✅ Pull request required before merging
- ✅ At least 1 approving review
- ✅ Status checks (unit tests) must pass
- ✅ Branch must be up-to-date before merge
- ❌ Direct pushes **blocked**

</details>

<details>
<summary><strong>💬 10 · Communication</strong></summary>

&nbsp;

| Channel | Purpose |
|:---|:---|
| **GitHub Issues** | Bug reports, feature requests, task tracking |
| **GitHub Discussions** | Design decisions, architecture Q&A |
| **PR Comments** | Code-level feedback |
| **Weekly Sync** | 30-min video call — progress + blockers |

> **Tips:** Tag teammates with `@username` · Use `WIP:` prefix for draft PRs · Post experiment plots in issue comments

</details>

### Quick Reference Scenarios

<details>
<summary>🐛 <strong>Fix a bug</strong></summary>

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
<summary>✨ <strong>Add a new workload profile</strong></summary>

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
<summary>📄 <strong>Improve documentation</strong></summary>

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
<summary>🔬 <strong>Run & submit experiment results</strong></summary>

```bash
git checkout main && git pull upstream main
git checkout -b experiment/run-w3-full-matrix
python experiments/run_experiment.py --workload W3 --policies all --runs 5
python scripts/plot_results.py
git add results/raw/ results/plots/ results/tables/
git commit -m "experiment(W3): complete 30-run matrix for W3 diurnal workload"
git push origin experiment/run-w3-full-matrix
# → Open PR with plot screenshots in the description
```

</details>

---

## Mathematical Foundation

### Composite Fitness Function (PSO Objective)

```
J(x) = w_L · L̄(x) + w_C · C̄(x) + w_M · M̂(x) + w_S · S̄(x)
     + ρ · max(0, Σ mᵥₖ · xₖ − M_budget)²
```

<table>
  <tr>
    <th>Weight</th>
    <th>Symbol</th>
    <th align="center">Default</th>
  </tr>
  <tr><td>Latency</td><td><code>w_L</code></td><td align="center">0.35</td></tr>
  <tr><td>Cold-Start Rate</td><td><code>w_C</code></td><td align="center">0.25</td></tr>
  <tr><td>Idle Memory</td><td><code>w_M</code></td><td align="center">0.25</td></tr>
  <tr><td>SLA Violations</td><td><code>w_S</code></td><td align="center">0.15</td></tr>
  <tr><td>Penalty Coefficient</td><td><code>ρ</code></td><td align="center">100</td></tr>
</table>

### PSO Hyperparameters

<table>
  <tr>
    <th>Parameter</th>
    <th align="center">Value</th>
  </tr>
  <tr><td>Swarm Size</td><td align="center">30</td></tr>
  <tr><td>Max Iterations</td><td align="center">50</td></tr>
  <tr><td>Inertia <code>ω</code></td><td align="center">0.7 → 0.4 (linear decay)</td></tr>
  <tr><td>Cognitive <code>c₁</code></td><td align="center">1.5</td></tr>
  <tr><td>Social <code>c₂</code></td><td align="center">1.5</td></tr>
</table>

### Control Loop Intervals

<table>
  <tr>
    <th>Loop</th>
    <th align="center">Interval</th>
    <th>Purpose</th>
  </tr>
  <tr><td>Fast (Fuzzy)</td><td align="center"><code>Δt = 10s</code></td><td>Rapid reactive adaptation</td></tr>
  <tr><td>Slow (PSO)</td><td align="center"><code>Δt = 60s</code></td><td>Global re-optimization</td></tr>
  <tr><td>Hysteresis</td><td align="center"><code>ε = 2</code></td><td>Flapping prevention</td></tr>
</table>

---

## Research Questions

> **RQ1** — Does workload-aware fuzzy control reduce cold-start frequency and latency compared to fixed/static prewarming?
>
> **RQ2** — Does constrained PSO optimization improve the latency–resource tradeoff beyond what either technique achieves independently?
>
> **RQ3** — Does incorporating dependency-granularity structure improve resource efficiency compared to function-level prewarming?

---

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

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ by the GranuWarm Research Team**

*Harshit Arya · Tijil Gupta · Ayush Rawat · Bhavya Yadav*

</div>
