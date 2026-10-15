from typing import Dict, Optional, Tuple
from .base_policy import BasePolicy


class B2FixedPrewarmPolicy(BasePolicy):
    """B2: Static prewarming with fixed N warm containers per function, scaled to budget."""

    def __init__(
        self,
        function_ids: list[str],
        fixed_count: int = 2,
        function_memories: Optional[Dict[str, float]] = None,
        memory_budget_mb: float = 4096.0
    ):
        self.function_ids = function_ids
        self.fixed_count = fixed_count
        self.function_memories = function_memories or {}
        self.memory_budget_mb = memory_budget_mb

    @property
    def name(self) -> str:
        return f"B2_Fixed_Prewarm_N{self.fixed_count}"

    def compute_allocation(
        self,
        metrics: Dict[str, Dict[str, float]],
        cluster_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, int], Dict[str, int]]:
        if self.function_memories:
            total_req = sum(self.fixed_count * self.function_memories.get(fid, 256.0) for fid in self.function_ids)
            if total_req > self.memory_budget_mb:
                ratio = self.memory_budget_mb / max(total_req, 1.0)
                func_alloc = {fid: max(0, int(self.fixed_count * ratio)) for fid in self.function_ids}
            else:
                func_alloc = {fid: self.fixed_count for fid in self.function_ids}
        else:
            func_alloc = {fid: self.fixed_count for fid in self.function_ids}
        return func_alloc, {}

    def reset(self):
        pass

