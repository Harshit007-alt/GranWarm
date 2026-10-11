<![CDATA[# STAGE 3: Intelligence Core — Fuzzy, Granularity Tree & PSO

> **Assigned to: Member 4 (Phases 8–9) + Harshit Arya (Phase 10)**
> **Phases: 8 → 9 → 10**
> **Estimated Duration: 3 weeks**
> **Prerequisites: Stage 2 complete (Prometheus signals + simulator working)**

---

## Phase 8 — Mamdani Fuzzy Inference System

### 8.1 Learning Objectives
- Mamdani FIS theory: Fuzzification → Rule Evaluation → Aggregation → Defuzzification
- Membership functions: triangular `trimf(x; a,b,c)` and trapezoidal `trapmf(x; a,b,c,d)`
- Min-AND conjunction, max aggregation, centroid defuzzification
- Pure NumPy implementation (no heavy dependencies)

### 8.2 Input Membership Functions (from Paper Section 4.3.1)

#### Invocation Intensity R ∈ [0, 1]
| Term | Type | Parameters |
|:---|:---|:---|
| LOW | Trapezoidal | (0, 0, 0.15, 0.35) |
| MEDIUM | Triangular | (0.2, 0.5, 0.8) |
| HIGH | Trapezoidal | (0.65, 0.85, 1.0, 1.0) |

#### Traffic Trend T ∈ [-1, 1]
| Term | Type | Parameters |
|:---|:---|:---|
| FALLING | Trapezoidal | (-1, -1, -0.5, -0.1) |
| STABLE | Triangular | (-0.2, 0, 0.2) |
| RISING | Triangular | (0.1, 0.4, 0.7) |
| SURGING | Trapezoidal | (0.5, 0.8, 1, 1) |

#### Cold-Start Pressure C ∈ [0, 1]
| Term | Type | Parameters |
|:---|:---|:---|
| LOW | Trapezoidal | (0, 0, 0.1, 0.3) |
| MEDIUM | Triangular | (0.15, 0.4, 0.65) |
| HIGH | Trapezoidal | (0.5, 0.7, 1, 1) |

#### Resource Pressure M ∈ [0, 1]
| Term | Type | Parameters |
|:---|:---|:---|
| LOW | Trapezoidal | (0, 0, 0.3, 0.5) |
| MEDIUM | Triangular | (0.35, 0.55, 0.75) |
| HIGH | Trapezoidal | (0.65, 0.8, 1, 1) |

### 8.3 Output Membership Functions — Desired Warm Capacity P ∈ [0, 1]
| Term | Type | Parameters |
|:---|:---|:---|
| VERY_LOW | Trapezoidal | (0, 0, 0.05, 0.2) |
| LOW | Triangular | (0.1, 0.25, 0.4) |
| MEDIUM | Triangular | (0.3, 0.5, 0.7) |
| HIGH | Triangular | (0.6, 0.75, 0.9) |
| VERY_HIGH | Trapezoidal | (0.8, 0.95, 1, 1) |

### 8.4 Complete Rule Base — 27 Rules (Table 2)

**"—" = don't-care (rule fires regardless of that input's value, membership = 1.0)**

| # | Invocation (R) | Trend (T) | Cold-Start (C) | Memory (M) | → Output (P) |
|:---|:---|:---|:---|:---|:---|
| 1 | LOW | FALLING | LOW | — | VERY_LOW |
| 2 | LOW | STABLE | LOW | — | VERY_LOW |
| 3 | LOW | STABLE | MEDIUM | LOW | LOW |
| 4 | LOW | STABLE | MEDIUM | MEDIUM | VERY_LOW |
| 5 | LOW | RISING | LOW | LOW | LOW |
| 6 | LOW | RISING | MEDIUM | LOW | MEDIUM |
| 7 | LOW | RISING | HIGH | LOW | MEDIUM |
| 8 | LOW | SURGING | — | LOW | MEDIUM |
| 9 | LOW | SURGING | — | HIGH | LOW |
| 10 | MEDIUM | FALLING | LOW | — | LOW |
| 11 | MEDIUM | STABLE | LOW | LOW | MEDIUM |
| 12 | MEDIUM | STABLE | LOW | HIGH | LOW |
| 13 | MEDIUM | STABLE | MEDIUM | LOW | MEDIUM |
| 14 | MEDIUM | STABLE | HIGH | LOW | HIGH |
| 15 | MEDIUM | RISING | LOW | LOW | MEDIUM |
| 16 | MEDIUM | RISING | MEDIUM | LOW | HIGH |
| 17 | MEDIUM | RISING | HIGH | LOW | HIGH |
| 18 | MEDIUM | SURGING | — | LOW | HIGH |
| 19 | MEDIUM | SURGING | — | HIGH | MEDIUM |
| 20 | HIGH | FALLING | LOW | — | MEDIUM |
| 21 | HIGH | STABLE | LOW | LOW | HIGH |
| 22 | HIGH | STABLE | MEDIUM | LOW | HIGH |
| 23 | HIGH | STABLE | HIGH | LOW | VERY_HIGH |
| 24 | HIGH | RISING | — | LOW | VERY_HIGH |
| 25 | HIGH | RISING | — | HIGH | HIGH |
| 26 | HIGH | SURGING | — | LOW | VERY_HIGH |
| 27 | HIGH | SURGING | — | HIGH | HIGH |

### 8.5 Design Principles Encoded in Rules

1. **Load-proportional scaling**: LOW invocation → VERY_LOW/LOW capacity; HIGH → HIGH/VERY_HIGH
2. **Trend-anticipatory**: RISING/SURGING trends trigger proactive scaling (Rules 5–8, 15–18, 24–26)
3. **Cold-start feedback**: HIGH cold-start pressure increases capacity even at moderate load (Rules 14, 17, 23)
4. **Resource-constrained moderation**: HIGH memory pressure dampens recommendations (Rules 9, 12, 19, 25, 27)

### 8.6 Implementation Workflow

1. Create `configs/fuzzy_rules.json` — encode all 27 rules
2. Implement `controller/fuzzy/fuzzy_engine.py`:
   - `trimf(x, a, b, c)` — triangular membership
   - `trapmf(x, a, b, c, d)` — trapezoidal membership
   - `evaluate_rule(rule, inputs)` — min-AND antecedent firing
   - `aggregate_rules(fired_rules)` — max aggregation
   - `centroid_defuzzify(aggregated_output)` — centroid calculation
   - `evaluate(R, T, C, M) → P_fuzzy ∈ [0, 1]` — main interface
3. Scale output: `P_desired = x_min + P_fuzzy * (x_max - x_min)`

### 8.7 Unit Tests

```python
# tests/test_fuzzy.py

def test_low_traffic_falling():
    """Rule 1: LOW invocation + FALLING trend + LOW cold-start → VERY_LOW"""
    engine = FuzzyEngine("configs/fuzzy_rules.json")
    p = engine.evaluate(R=0.1, T=-0.7, C=0.05, M=0.3)
    assert p < 0.15  # Should be near VERY_LOW

def test_high_traffic_surging():
    """Rule 26: HIGH invocation + SURGING trend + LOW memory → VERY_HIGH"""
    engine = FuzzyEngine("configs/fuzzy_rules.json")
    p = engine.evaluate(R=0.9, T=0.9, C=0.3, M=0.2)
    assert p > 0.85  # Should be near VERY_HIGH

def test_memory_pressure_dampens():
    """Rule 27 vs 26: HIGH memory should reduce recommendation"""
    engine = FuzzyEngine("configs/fuzzy_rules.json")
    p_low_mem = engine.evaluate(R=0.9, T=0.9, C=0.3, M=0.2)
    p_high_mem = engine.evaluate(R=0.9, T=0.9, C=0.3, M=0.9)
    assert p_high_mem < p_low_mem  # Memory pressure dampens

def test_output_bounded():
    """All outputs must be in [0, 1]"""
    engine = FuzzyEngine("configs/fuzzy_rules.json")
    import numpy as np
    for _ in range(1000):
        R, T, C, M = np.random.rand(), np.random.rand()*2-1, np.random.rand(), np.random.rand()
        p = engine.evaluate(R=R, T=T, C=C, M=M)
        assert 0.0 <= p <= 1.0
```

### 8.8 Verification
- [ ] All 27 rules fire correctly under appropriate input combinations
- [ ] Output is always bounded to [0, 1]
- [ ] Don't-care conditions (—) correctly evaluate to membership = 1.0
- [ ] No divide-by-zero during defuzzification
- [ ] Edge cases: all inputs at 0.0, all at 1.0, mixed extremes

---

## Phase 9 — Dependency Granularity Tree

### 9.1 Learning Objectives
- DAG data structures in Python
- Dependency decomposition: Runtime → Shared Libraries → Unique Code
- Max-projection: P_k^tree = max_{f_i ∈ F(v_k)} P_i
- Jaccard similarity clustering

### 9.2 The Benchmark Granularity Tree (Paper Section 5.3)

```
Root
├── Python 3.11 Runtime (80 MB)
│   ├── numpy (25 MB)
│   │   ├── Pillow bundle [F3, F4, F5] (15 MB)
│   │   │   ├── F3-specific: image resize code (5 MB)
│   │   │   ├── F4-specific: scipy + filter code (60 MB)
│   │   │   └── F5-specific: thumbnail code (3 MB)
│   │   ├── pandas bundle [F6, F8, F9] (35 MB)
│   │   │   ├── F6-specific: scikit-learn + model (400 MB)
│   │   │   ├── F8-specific: aggregation code (5 MB)
│   │   │   └── F9-specific: parser code (3 MB)
│   │   └── (numpy-only: no direct leaf users)
│   ├── F7-specific: transformers + torch (1800 MB)
│   └── F11-specific: requests + sqlalchemy (30 MB)
│
└── Node.js 20 Runtime (40 MB)
    ├── F1-specific: minimal (1 MB)
    ├── F2-specific: lodash (5 MB)
    ├── F10-specific: jsonwebtoken + bcrypt (8 MB)
    └── F12-specific: firebase-admin (15 MB)
```

**Total granularity-tree nodes: K = 20**

### 9.3 Node Types

| Layer | Description | Example | Count |
|:---|:---|:---|:---|
| Layer 0 | Runtime | Python 3.11, Node.js 20 | 2 |
| Layer 1 | Shared library bundles | numpy, Pillow bundle, pandas bundle | 3 |
| Layer 2 | Function-specific | F1-code, F2-code, ..., F12-code | 12 |
| Internal | Non-leaf groupings | Root, runtime containers | 3 |

### 9.4 Max-Projection Algorithm

For each tree node v_k, compute:
```
P_k^tree = max { P_i : f_i depends on v_k }
```

**Example:** If Fuzzy recommends P_F3=0.6, P_F4=0.8, P_F5=0.3, then:
- Pillow bundle node: max(0.6, 0.8, 0.3) = 0.8
- numpy node: max(0.6, 0.8, 0.3, ...) (all numpy users)
- Python runtime: max of ALL Python function recommendations

### 9.5 Implementation: `configs/dependencies.json`

```json
{
    "nodes": [
        {"id": "python_311", "name": "Python 3.11 Runtime", "layer": 0, "memory_mb": 80, "init_time_ms": 200, "parent": null},
        {"id": "nodejs_20", "name": "Node.js 20 Runtime", "layer": 0, "memory_mb": 40, "init_time_ms": 100, "parent": null},
        {"id": "numpy", "name": "numpy", "layer": 1, "memory_mb": 25, "init_time_ms": 80, "parent": "python_311"},
        ...
    ],
    "functions": [
        {"id": "f01", "name": "helloWorld", "leaf_node": "f01_leaf", "dependency_path": ["nodejs_20", "f01_leaf"]},
        ...
    ]
}
```

### 9.6 Implementation: `controller/granularity/tree.py`

Core class interface:
```python
class GranularityTree:
    def __init__(self, config_path: str): ...
    def get_dependency_path(self, function_id: str) -> list[str]: ...
    def get_functions_for_node(self, node_id: str) -> list[str]: ...
    def project_capacities(self, func_recommendations: dict[str, float]) -> dict[str, float]: ...
    def get_node_memory(self, node_id: str) -> float: ...
    def get_total_nodes(self) -> int: ...
```

### 9.7 Unit Tests

```python
# tests/test_tree.py

def test_max_projection():
    tree = GranularityTree("configs/dependencies.json")
    recs = {"f03": 0.6, "f04": 0.8, "f05": 0.3}
    projected = tree.project_capacities(recs)
    assert projected["pillow_bundle"] == 0.8  # max(0.6, 0.8, 0.3)

def test_runtime_inherits_max():
    tree = GranularityTree("configs/dependencies.json")
    recs = {"f01": 0.2, "f03": 0.9}
    projected = tree.project_capacities(recs)
    assert projected["python_311"] >= 0.9
    assert projected["nodejs_20"] >= 0.2

def test_all_functions_have_paths():
    tree = GranularityTree("configs/dependencies.json")
    for fid in [f"f{i:02d}" for i in range(1, 13)]:
        path = tree.get_dependency_path(fid)
        assert len(path) >= 2  # At least runtime + leaf
```

### 9.8 Verification
- [ ] Tree has K=20 nodes (matching paper)
- [ ] Every function maps to a valid leaf node
- [ ] Max-projection propagates correctly up the tree
- [ ] No circular dependencies in DAG
- [ ] Memory values match Table 4 and Section 5.3

---

## Phase 10 — Constrained Discrete PSO Optimizer

> **Assigned to: Harshit Arya**

### 10.1 Learning Objectives
- PSO velocity/position update equations
- Inertia weight decay (ω: 0.7 → 0.4)
- Discrete (integer) search space with rounding + clamping
- Constraint handling via quadratic penalty function
- Intelligent swarm initialization from fuzzy prior

### 10.2 PSO Formulation

#### Particle Representation
```
x^(p) = [x_1^(p), x_2^(p), ..., x_K^(p)] ∈ ℤ≥0^K
```
Each x_k = number of warm instances for granularity-tree node v_k.

#### Fitness Function
```
J(x) = w_L·L̄(x) + w_C·C̄(x) + w_M·M̂(x) + w_S·S̄(x)
      + ρ · max(0, Σ m_vk·x_k − M_budget)²
```

| Component | Weight | Description |
|:---|:---|:---|
| L̄(x) | w_L = 0.35 | Normalized average latency |
| C̄(x) | w_C = 0.25 | Normalized cold-start rate |
| M̂(x) | w_M = 0.25 | Normalized idle memory |
| S̄(x) | w_S = 0.15 | Normalized SLA violation rate |
| Penalty | ρ = 100 | Quadratic memory budget violation |

#### Velocity Update
```
v_k^(p)(t+1) = ω·v_k^(p)(t) + c₁·r₁·(pbest_k^(p) − x_k^(p)(t)) + c₂·r₂·(gbest_k − x_k^(p)(t))
```

#### Position Update (with integer discretization)
```
x_k^(p)(t+1) = round(x_k^(p)(t) + v_k^(p)(t+1))
x_k^(p)(t+1) = clamp(x_k^(p)(t+1), x_k_min, x_k_max)
```

### 10.3 PSO Hyperparameters

| Parameter | Symbol | Value |
|:---|:---|:---|
| Swarm size | S | 30 |
| Max iterations | I_max | 50 |
| Inertia (start) | ω_start | 0.7 |
| Inertia (end) | ω_end | 0.4 |
| Cognitive coeff. | c₁ | 1.5 |
| Social coeff. | c₂ | 1.5 |
| Penalty coeff. | ρ | 100 |

### 10.4 Intelligent Initialization

| Particle | Initialization |
|:---|:---|
| 1 | Fuzzy projected recommendations P^tree |
| 2 | Current active allocation x^current |
| 3 | 0.5 × P^tree (conservative) |
| 4 | 0.75 × P^tree (moderate) |
| 5 | 1.25 × P^tree (aggressive) |
| 6–30 | Gaussian perturbation around P^tree |

### 10.5 Implementation: `controller/pso/pso_optimizer.py`

Key methods:
```python
class DiscreteConstrainedPSO:
    def __init__(self, swarm_size, max_iter, memory_budget, weights, ...): ...
    def _initialize_swarm(self, fuzzy_prior, current_allocation): ...
    def _compute_fitness(self, position, metrics): ...
    def _compute_penalty(self, position): ...
    def _update_velocities(self, iteration): ...
    def _update_positions(self): ...
    def optimize(self, fuzzy_prior, current_allocation, metrics) -> np.ndarray: ...
```

### 10.6 Unit Tests

```python
# tests/test_pso.py

def test_budget_constraint():
    """Optimal solution must not exceed memory budget"""
    pso = DiscreteConstrainedPSO(swarm_size=30, max_iter=50, memory_budget=4000)
    best_x = pso.optimize(fuzzy_prior=P_tree, current=x_curr, metrics=metrics)
    total_memory = sum(best_x[k] * node_memory[k] for k in range(K))
    assert total_memory <= 4000

def test_convergence():
    """Fitness should improve over iterations"""
    pso = DiscreteConstrainedPSO(swarm_size=30, max_iter=50, memory_budget=4000)
    best_x, history = pso.optimize(fuzzy_prior=P_tree, ..., return_history=True)
    assert history[-1] <= history[0]  # Final fitness ≤ initial

def test_integer_positions():
    """All positions must be non-negative integers"""
    pso = DiscreteConstrainedPSO(swarm_size=30, max_iter=50, memory_budget=4000)
    best_x = pso.optimize(...)
    assert all(isinstance(x, (int, np.integer)) and x >= 0 for x in best_x)
```

### 10.7 Verification
- [ ] PSO converges within 50 iterations (fitness monotonically improves for gbest)
- [ ] All final positions are non-negative integers
- [ ] Memory budget constraint satisfied in final solution
- [ ] Intelligent seeding (Particles 1–5) outperforms random initialization
- [ ] Execution time: < 500ms for K=20 nodes, S=30 particles, I=50 iterations

---

## Handoff to Stage 4

Once verified:
1. Fuzzy engine passes all 27-rule tests
2. Granularity tree correctly projects across K=20 nodes
3. PSO converges within budget constraints

→ **Harshit Arya** begins Phase 11 (integration of all components into dual-timescale controller).
]]>
