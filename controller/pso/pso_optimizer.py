import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class DiscreteConstrainedPSO:
    """Vectorized Discrete Constrained Particle Swarm Optimizer for GranuWarm.

    Optimizes warm instance allocation vector x in Z_>=0^K under strict memory budget.
    """

    def __init__(
        self,
        dimension: int = 20,
        swarm_size: int = 30,
        max_iter: int = 50,
        memory_budget_mb: float = 4096.0,
        node_memories: Optional[np.ndarray] = None,
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
        seed: Optional[int] = None
    ):
        self.K = dimension
        self.S = swarm_size
        self.max_iter = max_iter
        self.M_budget = memory_budget_mb
        self.node_memories = node_memories if node_memories is not None else np.ones(self.K) * 50.0
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

    def _initialize_swarm(
        self,
        fuzzy_prior: Optional[np.ndarray],
        current_allocation: Optional[np.ndarray]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Intelligent swarm seeding from fuzzy prior and current state."""
        positions = np.zeros((self.S, self.K), dtype=int)
        velocities = self.rng.uniform(-1.0, 1.0, size=(self.S, self.K))

        if fuzzy_prior is None:
            fuzzy_prior = np.ones(self.K) * 2.0
        if current_allocation is None:
            current_allocation = np.zeros(self.K, dtype=int)

        scaled_prior = np.round(fuzzy_prior).astype(int)

        # Particle 1: Fuzzy prior
        positions[0] = np.clip(scaled_prior, 0, self.x_max)
        # Particle 2: Current allocation
        positions[1] = np.clip(current_allocation, 0, self.x_max)
        # Particle 3: 0.5x Conservative
        positions[2] = np.clip(np.round(scaled_prior * 0.5).astype(int), 0, self.x_max)
        # Particle 4: 0.75x Moderate
        positions[3] = np.clip(np.round(scaled_prior * 0.75).astype(int), 0, self.x_max)
        # Particle 5: 1.25x Aggressive
        positions[4] = np.clip(np.round(scaled_prior * 1.25).astype(int), 0, self.x_max)

        # Remaining particles: Gaussian perturbation around fuzzy prior
        for p in range(5, self.S):
            noise = self.rng.normal(0.0, 1.0, size=self.K)
            pos = np.round(scaled_prior + noise).astype(int)
            positions[p] = np.clip(pos, 0, self.x_max)

        return positions, velocities

    def _compute_fitness_vector(self, positions: np.ndarray, metrics_prior: Optional[Dict[str, float]]) -> np.ndarray:
        """Evaluates composite objective J(x) for all particles."""
        # positions: shape (S, K)
        # Memory consumption per particle: (S,)
        mem_used = np.dot(positions, self.node_memories)

        # Memory violation penalty: rho * max(0, mem - M_budget)^2
        violation = np.maximum(0.0, mem_used - self.M_budget)
        penalty = self.rho * (violation / max(self.M_budget, 1.0)) ** 2

        # Latency surrogate L_bar: higher allocation reduces expected queuing/cold start latency
        # Model: L(x) decays inversely with warm instances
        effective_alloc = np.maximum(positions, 0.1)
        L_bar = np.mean(1.0 / effective_alloc, axis=1)
        L_bar_norm = L_bar / np.max(L_bar + 1e-6)

        # Cold start rate surrogate C_bar
        C_bar = np.exp(-0.4 * np.mean(positions, axis=1))

        # Idle memory ratio surrogate M_hat
        M_hat = mem_used / max(self.M_budget, 1.0)

        # SLA violation surrogate S_bar
        S_bar = np.maximum(0.0, C_bar - 0.2)

        # Composite Fitness J(x)
        J = (
            self.w_L * L_bar_norm
            + self.w_C * C_bar
            + self.w_M * M_hat
            + self.w_S * S_bar
            + penalty
        )
        return J

    def optimize(
        self,
        fuzzy_prior: Optional[np.ndarray] = None,
        current_allocation: Optional[np.ndarray] = None,
        metrics: Optional[Dict[str, float]] = None,
        return_history: bool = False
    ):
        """Runs vectorized discrete PSO loop.

        Returns:
            best_position: np.ndarray of shape (K,), integer warm capacities.
            fitness_history (optional): list of float gbest fitness values.
        """
        positions, velocities = self._initialize_swarm(fuzzy_prior, current_allocation)

        pbest_positions = np.copy(positions)
        pbest_fitness = self._compute_fitness_vector(positions, metrics)

        gbest_idx = int(np.argmin(pbest_fitness))
        gbest_pos = np.copy(pbest_positions[gbest_idx])
        gbest_fit = float(pbest_fitness[gbest_idx])

        history = [gbest_fit]

        for it in range(self.max_iter):
            # Linearly decaying inertia weight
            omega = self.omega_start - (it / float(self.max_iter)) * (self.omega_start - self.omega_end)

            r1 = self.rng.uniform(0.0, 1.0, size=(self.S, self.K))
            r2 = self.rng.uniform(0.0, 1.0, size=(self.S, self.K))

            # Velocity update
            cognitive = self.c1 * r1 * (pbest_positions - positions)
            social = self.c2 * r2 * (gbest_pos - positions)
            velocities = omega * velocities + cognitive + social
            velocities = np.clip(velocities, -self.v_max, self.v_max)

            # Position update with integer discretization
            positions_continuous = positions.astype(float) + velocities
            positions = np.clip(np.round(positions_continuous).astype(int), 0, self.x_max)

            # Evaluate fitness
            current_fitness = self._compute_fitness_vector(positions, metrics)

            # Update pbest
            improved = current_fitness < pbest_fitness
            pbest_positions[improved] = positions[improved]
            pbest_fitness[improved] = current_fitness[improved]

            # Update gbest
            current_min_idx = int(np.argmin(pbest_fitness))
            if pbest_fitness[current_min_idx] < gbest_fit:
                gbest_fit = float(pbest_fitness[current_min_idx])
                gbest_pos = np.copy(pbest_positions[current_min_idx])

            history.append(gbest_fit)

        if return_history:
            return gbest_pos, history
        return gbest_pos
