from typing import Dict, Optional, Tuple
import numpy as np
from controller.pso.pso_optimizer import DiscreteConstrainedPSO
from .base_policy import BasePolicy


class B4PSOOnlyPolicy(BasePolicy):
    """B4: Constrained PSO only with random/uniform initialization, per-function search space."""

    def __init__(
        self,
        function_ids: list[str],
        function_memories: Dict[str, float],
        memory_budget_mb: float = 4096.0,
        swarm_size: int = 30,
        max_iter: int = 40
    ):
        self.function_ids = function_ids
        self.N = len(function_ids)
        self.mem_array = np.array([function_memories.get(fid, 256.0) for fid in function_ids])
        self.memory_budget_mb = memory_budget_mb
        self.pso = DiscreteConstrainedPSO(
            dimension=self.N,
            swarm_size=swarm_size,
            max_iter=max_iter,
            memory_budget_mb=memory_budget_mb,
            node_memories=self.mem_array
        )
        self.current_x = np.zeros(self.N, dtype=int)

    @property
    def name(self) -> str:
        return "B4_PSO_Only"

    def compute_allocation(
        self,
        metrics: Dict[str, Dict[str, float]],
        cluster_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, int], Dict[str, int]]:
        # Uniform prior (no fuzzy intelligence)
        uniform_prior = np.ones(self.N) * 1.5
        best_x = self.pso.optimize(
            fuzzy_prior=uniform_prior,
            current_allocation=self.current_x,
            metrics=cluster_metrics
        )
        self.current_x = np.copy(best_x)
        total_mem = sum(int(best_x[i]) * self.mem_array[i] for i in range(self.N))
        if total_mem > self.memory_budget_mb:
            ratio = self.memory_budget_mb / max(total_mem, 1.0)
            func_alloc = {fid: int(int(best_x[i]) * ratio) for i, fid in enumerate(self.function_ids)}
        else:
            func_alloc = {fid: int(best_x[i]) for i, fid in enumerate(self.function_ids)}
        return func_alloc, {}

    def reset(self):
        self.current_x = np.zeros(self.N, dtype=int)
