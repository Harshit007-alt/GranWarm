from typing import Dict, Optional, Tuple
from controller.fuzzy.fuzzy_engine import FuzzyEngine
from .base_policy import BasePolicy


class B3FuzzyOnlyPolicy(BasePolicy):
    """B3: Fuzzy Inference only with proportional budget scaling, without PSO or Granularity Tree."""

    def __init__(
        self,
        function_ids: list[str],
        function_memories: Dict[str, float],
        memory_budget_mb: float = 4096.0,
        rules_config: str = "configs/fuzzy_rules.json"
    ):
        self.function_ids = function_ids
        self.function_memories = function_memories
        self.memory_budget_mb = memory_budget_mb
        self.engine = FuzzyEngine(rules_config)

    @property
    def name(self) -> str:
        return "B3_Fuzzy_Only"

    def compute_allocation(
        self,
        metrics: Dict[str, Dict[str, float]],
        cluster_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, int], Dict[str, int]]:
        raw_alloc: Dict[str, int] = {}
        total_requested_mem = 0.0

        for fid in self.function_ids:
            m = metrics.get(fid, {"R_i": 0.2, "T_i": 0.0, "C_i": 0.1, "M": 0.3})
            p = self.engine.evaluate(m["R_i"], m["T_i"], m["C_i"], m["M"])
            count = self.engine.scale_to_instances(p, min_inst=0, max_inst=8)
            raw_alloc[fid] = count
            total_requested_mem += count * self.function_memories.get(fid, 256.0)

        # Proportional budget scaling if exceeding memory budget
        func_alloc: Dict[str, int] = {}
        if total_requested_mem > self.memory_budget_mb:
            ratio = self.memory_budget_mb / max(total_requested_mem, 1.0)
            for fid, c in raw_alloc.items():
                func_alloc[fid] = int(c * ratio)
        else:
            func_alloc = raw_alloc

        return func_alloc, {}

    def reset(self):
        pass
