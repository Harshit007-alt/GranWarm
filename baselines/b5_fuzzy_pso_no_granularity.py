from typing import Dict, Optional, Tuple
import numpy as np
from controller.fuzzy.fuzzy_engine import FuzzyEngine
from controller.pso.pso_optimizer import DiscreteConstrainedPSO
from .base_policy import BasePolicy


class B5FuzzyPSONoGranularityPolicy(BasePolicy):
    """B5: Fuzzy-seeded PSO optimizer running strictly in per-function search space (no Granularity Tree)."""

    def __init__(
        self,
        function_ids: list[str],
        function_memories: Dict[str, float],
        memory_budget_mb: float = 4096.0,
        rules_config: str = "configs/fuzzy_rules.json",
        swarm_size: int = 30,
        max_iter: int = 40
    ):
        self.function_ids = function_ids
        self.N = len(function_ids)
        self.memory_budget_mb = memory_budget_mb
        self.engine = FuzzyEngine(rules_config)
        self.mem_array = np.array([function_memories.get(fid, 256.0) for fid in function_ids])
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
        return "B5_Fuzzy_PSO_No_Granularity"

    def compute_allocation(
        self,
        metrics: Dict[str, Dict[str, float]],
        cluster_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, int], Dict[str, int]]:
        # Compute fuzzy recommendations per function
        fuzzy_recs = []
        for fid in self.function_ids:
            m = metrics.get(fid, {"R_i": 0.2, "T_i": 0.0, "C_i": 0.1, "M": 0.3})
            p = self.engine.evaluate(m["R_i"], m["T_i"], m["C_i"], m["M"])
            fuzzy_recs.append(p * 8.0)  # scale to approximate capacity

        fuzzy_prior = np.array(fuzzy_recs)
        best_x = self.pso.optimize(
            fuzzy_prior=fuzzy_prior,
            current_allocation=self.current_x,
            metrics=cluster_metrics
        )
        self.current_x = np.copy(best_x)
        total_mem = sum(int(best_x[i]) * self.mem_array[i] for i in range(self.N))
        if total_mem > self.memory_budget_mb:
            func_alloc = {fid: 0 for fid in self.function_ids}
            allocated_mem = 0.0
            # Prioritize functions with highest fuzzy demand and positive PSO proposal
            priorities = [int(best_x[i]) * (fuzzy_prior[i] + 0.1) for i in range(self.N)]
            order = np.argsort(-np.array(priorities))
            for idx in order:
                fid = self.function_ids[idx]
                req_count = int(best_x[idx])
                mem_each = self.mem_array[idx]
                if req_count > 0:
                    max_can_fit = int((self.memory_budget_mb - allocated_mem) // max(mem_each, 1.0))
                    count = min(req_count, max_can_fit)
                    if count > 0:
                        func_alloc[fid] = count
                        allocated_mem += count * mem_each
        else:
            func_alloc = {fid: int(best_x[i]) for i, fid in enumerate(self.function_ids)}
        return func_alloc, {}

    def reset(self):
        self.current_x = np.zeros(self.N, dtype=int)
