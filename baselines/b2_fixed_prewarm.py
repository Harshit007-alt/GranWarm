from typing import Dict, Optional, Tuple
from .base_policy import BasePolicy


class B2FixedPrewarmPolicy(BasePolicy):
    """B2: Static prewarming with fixed N warm containers per function."""

    def __init__(self, function_ids: list[str], fixed_count: int = 2):
        self.function_ids = function_ids
        self.fixed_count = fixed_count

    @property
    def name(self) -> str:
        return f"B2_Fixed_Prewarm_N{self.fixed_count}"

    def compute_allocation(
        self,
        metrics: Dict[str, Dict[str, float]],
        cluster_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, int], Dict[str, int]]:
        func_alloc = {fid: self.fixed_count for fid in self.function_ids}
        return func_alloc, {}

    def reset(self):
        pass
