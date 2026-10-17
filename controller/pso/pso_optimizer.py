import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class DiscreteConstrainedPSO:
    """Vectorized Discrete Constrained Particle Swarm Optimizer for GranuWarm.

    Optimizes warm instance allocation vector x in Z_>=0^K under strict memory budget.

    When `node_ids` and `parent_map` are provided, positions are projected onto
    the dependency-feasible subspace after every update:
        child_capacity <= parent_capacity  for every parent-child pair.
    This makes the search space feasible-by-construction, so the downstream
    FeasibilityService almost never has to repair the PSO output.
    """

    def __init__(
        self,
        dimension: int = 20,
        swarm_size: int = 30,
        max_iter: int = 50,
        memory_budget_mb: float = 4096.0,
        node_memories: Optional[np.ndarray] = None,
        node_ids: Optional[List[str]] = None,
        parent_map: Optional[Dict[str, Optional[str]]] = None,
        w_L: float = 0.35,
        w_C: float = 0.25,
        w_M: float = 0.25,
        w_S: float = 0.15,
        rho_penalty: float = 100.0,
        omega_start: float = 0.7,
        omega_end: float = 0.4,
        c1: float = 1.5,
        c2: float = 1.5,
        x_max: int = 10,
        v_max: float = 3.0,
        seed: Optional[int] = None,
    ):
        self.K = dimension
        self.S = swarm_size
        self.max_iter = max_iter
        self.M_budget = memory_budget_mb
        self.node_memories = (
            node_memories if node_memories is not None
            else np.ones(self.K) * 50.0
        )
        self.w_L = w_L
        self.w_C = w_C
        self.w_M = w_M
        self.w_S = w_S
        self.rho = rho_penalty
        self.omega_start = omega_start
        self.omega_end = omega_end
        self.c1 = c1
        self.c2 = c2
        self.x_max = x_max
        self.v_max = v_max
        self.rng = np.random.default_rng(seed)

        # Build (child_idx, parent_idx) pairs for DAG projection.
        # Only pairs where BOTH endpoints are in the allocatable vector
        # contribute constraints.
        self._dag_pairs: List[Tuple[int, int]] = []
        if node_ids and parent_map:
            index_of = {nid: i for i, nid in enumerate(node_ids)}
            for nid, parent in parent_map.items():
                if parent is None:
                    continue
                if nid in index_of and parent in index_of:
                    self._dag_pairs.append(
                        (index_of[nid], index_of[parent])
                    )
            if self._dag_pairs:
                logger.info(
                    f"PSO DAG projection enabled: {len(self._dag_pairs)} "
                    f"parent-child constraints"
                )

    # ------------------------------------------------------------------
    def _enforce_dag(self, positions: np.ndarray) -> np.ndarray:
        """Clamp each child's capacity to its parent's. In-place, idempotent.

        Repeated 3x to handle cascading violations (grandchild > child > parent).
        """
        if not self._dag_pairs:
            return positions
        for _ in range(3):
            changed = False
            for child_idx, parent_idx in self._dag_pairs:
                over = positions[:, child_idx] > positions[:, parent_idx]
                if np.any(over):
                    positions[over, child_idx] = positions[over, parent_idx]
                    changed = True
            if not changed:
                break
        return positions

    # ------------------------------------------------------------------
    def _initialize_swarm(
        self,
        fuzzy_prior: Optional[np.ndarray],
        current_allocation: Optional[np.ndarray],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Intelligent swarm seeding from fuzzy prior and current state."""
        positions = np.zeros((self.S, self.K), dtype=int)
        velocities = self.rng.uniform(-1.0, 1.0, size=(self.S, self.K))

        if fuzzy_prior is None:
            fuzzy_prior = np.ones(self.K) * 2.0
        if current_allocation is None:
            current_allocation = np.zeros(self.K, dtype=int)

        scaled_prior = np.round(fuzzy_prior).astype(int)

        positions[0] = np.clip(scaled_prior, 0, self.x_max)
        positions[1] = np.clip(current_allocation, 0, self.x_max)
        positions[2] = np.clip(
            np.round(scaled_prior * 0.5).astype(int), 0, self.x_max
        )
        positions[3] = np.clip(
            np.round(scaled_prior * 0.75).astype(int), 0, self.x_max
        )
        positions[4] = np.clip(
            np.round(scaled_prior * 1.25).astype(int), 0, self.x_max
        )

        for p in range(5, self.S):
            noise = self.rng.normal(0.0, 1.0, size=self.K)
            pos = np.round(scaled_prior + noise).astype(int)
            positions[p] = np.clip(pos, 0, self.x_max)

        # Project every seed onto the feasible subspace
        self._enforce_dag(positions)
        return positions, velocities

    # ------------------------------------------------------------------
    def _compute_fitness_vector(
        self,
        positions: np.ndarray,
        metrics_prior: Optional[Dict[str, float]],
    ) -> np.ndarray:
        """Evaluates composite objective J(x) for all particles.
        
        If metrics_prior is provided and contains observed metrics, uses those.
        Otherwise falls back to analytic surrogates.
        
        Args:
            positions: Particle positions (S x K)
            metrics_prior: Optional dict with observed metrics:
                - "mode": "observed" or "analytic"
                - "latency": observed latencies per function
                - "cold_starts": observed cold-start counts
                - "memory": observed memory usage
                - "sla_violations": observed SLA violations
                
        Returns:
            Fitness vector (S,) - lower is better
        """
        # Check if we have observed metrics
        if metrics_prior and metrics_prior.get("mode") == "observed":
            return self._compute_fitness_observed(positions, metrics_prior)
        else:
            return self._compute_fitness_analytic(positions)
    
    def _compute_fitness_analytic(self, positions: np.ndarray) -> np.ndarray:
        """Original analytic surrogate fitness (used when no observed metrics).
        
        This is the fallback when we don't have real observations yet,
        or in simulation mode.
        """
        mem_used = np.dot(positions, self.node_memories)

        violation = np.maximum(0.0, mem_used - self.M_budget)
        penalty = self.rho * (violation / max(self.M_budget, 1.0)) ** 2

        effective_alloc = np.maximum(positions, 0.1)
        L_bar = np.mean(1.0 / effective_alloc, axis=1)
        L_bar_norm = L_bar / np.max(L_bar + 1e-6)

        C_bar = np.exp(-0.4 * np.mean(positions, axis=1))
        M_hat = mem_used / max(self.M_budget, 1.0)
        S_bar = np.maximum(0.0, C_bar - 0.2)

        J = (
            self.w_L * L_bar_norm
            + self.w_C * C_bar
            + self.w_M * M_hat
            + self.w_S * S_bar
            + penalty
        )
        return J
    
    def _compute_fitness_observed(
        self, positions: np.ndarray, metrics: Dict[str, float]
    ) -> np.ndarray:
        """Compute fitness from observed metrics (used when available).
        
        Uses real observed latency, cold-starts, memory, and SLA violations
        instead of analytic surrogates.
        
        Args:
            positions: Particle positions (S x K)
            metrics: Dict with observed metrics:
                - "latency_total_ms": total observed latency across functions
                - "cold_start_total": total cold-starts observed
                - "memory_used_mb": total memory used
                - "sla_violations_total": total SLA violations
                
        Returns:
            Fitness vector (S,) - lower is better
        """
        # Extract observed metrics with defaults
        latency_total = metrics.get("latency_total_ms", 100.0)
        cold_start_total = metrics.get("cold_start_total", 5.0)
        memory_used_mb = metrics.get("memory_used_mb", 1000.0)
        sla_violations = metrics.get("sla_violations_total", 0.0)
        
        # Normalize latency (lower is better)
        # Assume baseline latency scales inversely with allocation
        L_bar = latency_total / (np.mean(positions, axis=1) + 1.0)
        L_bar_norm = L_bar / np.max(L_bar + 1e-6)
        
        # Cold-start cost (lower is better)
        # More allocation = fewer cold-starts
        C_bar = cold_start_total / (np.mean(positions, axis=1) + 1.0)
        C_bar_norm = C_bar / np.max(C_bar + 1e-6)
        
        # Memory pressure (lower is better)
        mem_used = np.dot(positions, self.node_memories)
        M_hat = mem_used / max(self.M_budget, 1.0)
        
        # SLA violations (lower is better)
        S_bar = sla_violations / (np.mean(positions, axis=1) + 1.0)
        S_bar_norm = S_bar / np.max(S_bar + 1e-6)
        
        # Budget violation penalty (hard constraint)
        violation = np.maximum(0.0, mem_used - self.M_budget)
        penalty = self.rho * (violation / max(self.M_budget, 1.0)) ** 2
        
        # Composite objective
        J = (
            self.w_L * L_bar_norm
            + self.w_C * C_bar_norm
            + self.w_M * M_hat
            + self.w_S * S_bar_norm
            + penalty
        )
        return J

    # ------------------------------------------------------------------
    def optimize(
        self,
        fuzzy_prior: Optional[np.ndarray] = None,
        current_allocation: Optional[np.ndarray] = None,
        metrics: Optional[Dict[str, float]] = None,
        return_history: bool = False,
    ):
        """Runs vectorized discrete PSO loop."""
        positions, velocities = self._initialize_swarm(
            fuzzy_prior, current_allocation
        )

        pbest_positions = np.copy(positions)
        pbest_fitness = self._compute_fitness_vector(positions, metrics)

        gbest_idx = int(np.argmin(pbest_fitness))
        gbest_pos = np.copy(pbest_positions[gbest_idx])
        gbest_fit = float(pbest_fitness[gbest_idx])

        history = [gbest_fit]

        for it in range(self.max_iter):
            omega = self.omega_start - (it / float(self.max_iter)) * (
                self.omega_start - self.omega_end
            )

            r1 = self.rng.uniform(0.0, 1.0, size=(self.S, self.K))
            r2 = self.rng.uniform(0.0, 1.0, size=(self.S, self.K))

            cognitive = self.c1 * r1 * (pbest_positions - positions)
            social = self.c2 * r2 * (gbest_pos - positions)
            velocities = omega * velocities + cognitive + social
            velocities = np.clip(velocities, -self.v_max, self.v_max)

            positions_continuous = positions.astype(float) + velocities
            positions = np.clip(
                np.round(positions_continuous).astype(int), 0, self.x_max
            )

            # Project onto the DAG-feasible subspace
            self._enforce_dag(positions)

            current_fitness = self._compute_fitness_vector(positions, metrics)

            improved = current_fitness < pbest_fitness
            pbest_positions[improved] = positions[improved]
            pbest_fitness[improved] = current_fitness[improved]

            current_min_idx = int(np.argmin(pbest_fitness))
            if pbest_fitness[current_min_idx] < gbest_fit:
                gbest_fit = float(pbest_fitness[current_min_idx])
                gbest_pos = np.copy(pbest_positions[current_min_idx])

            history.append(gbest_fit)

        if return_history:
            return gbest_pos, history
        return gbest_pos