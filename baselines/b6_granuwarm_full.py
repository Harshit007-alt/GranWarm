from typing import Dict, Optional, Tuple
import numpy as np
from controller.fuzzy.fuzzy_engine import FuzzyEngine
from controller.granularity.tree import GranularityTree
from controller.pso.pso_optimizer import DiscreteConstrainedPSO
from .base_policy import BasePolicy


class B6GranuWarmFullPolicy(BasePolicy):
    """B6: Complete GranuWarm Framework (Fuzzy FIS + Granularity Tree Projection + Constrained PSO)."""

    def __init__(
        self,
        tree_config: str = "configs/dependencies.json",
        rules_config: str = "configs/fuzzy_rules.json",
        memory_budget_mb: float = 4096.0,
        swarm_size: int = 30,
        max_iter: int = 50
    ):
        self.tree = GranularityTree(tree_config)
        self.engine = FuzzyEngine(rules_config)
        self.memory_budget_mb = memory_budget_mb

        self.K = self.tree.get_total_nodes()
        self.node_ids = self.tree.node_ids
        self.node_memories = np.array([self.tree.get_node_memory(nid) for nid in self.node_ids])

        self.pso = DiscreteConstrainedPSO(
            dimension=self.K,
            swarm_size=swarm_size,
            max_iter=max_iter,
            memory_budget_mb=memory_budget_mb,
            node_memories=self.node_memories
        )
        self.current_x = np.zeros(self.K, dtype=int)

    @property
    def name(self) -> str:
        return "B6_GranuWarm_Full"

    def compute_allocation(
        self,
        metrics: Dict[str, Dict[str, float]],
        cluster_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, int], Dict[str, int]]:
        # 1. Fuzzy Inference Loop
        func_recs: Dict[str, float] = {}
        for fid in self.tree.functions:
            m = metrics.get(fid, {"R_i": 0.2, "T_i": 0.0, "C_i": 0.1, "M": 0.3})
            p = self.engine.evaluate(m["R_i"], m["T_i"], m["C_i"], m["M"])
            func_recs[fid] = p

        # 2. Granularity Tree Max-Projection
        projected_recs = self.tree.project_capacities(func_recs)
        fuzzy_prior_vector = np.array([projected_recs.get(nid, 0.0) * 8.0 for nid in self.node_ids])

        # 3. Constrained Discrete PSO Optimization
        best_x = self.pso.optimize(
            fuzzy_prior=fuzzy_prior_vector,
            current_allocation=self.current_x,
            metrics=cluster_metrics
        )
        self.current_x = np.copy(best_x)

        # 4. Map allocations
        tree_alloc = {nid: int(best_x[i]) for i, nid in enumerate(self.node_ids)}
        func_alloc = self.tree.map_tree_allocation_to_functions(tree_alloc)

        return func_alloc, tree_alloc

    def reset(self):
        self.current_x = np.zeros(self.K, dtype=int)
