from typing import Dict, Optional, Tuple
from .base_policy import BasePolicy


class B1NoPrewarmPolicy(BasePolicy):
    """B1: Default Knative scale-to-zero baseline (min-scale = 0)."""

    def __init__(self, function_ids: list[str]):
        self.function_ids = function_ids

    @property
    def name(self) -> str:
        return "B1_No_Prewarm"

    def compute_allocation(
        self,
        metrics: Dict[str, Dict[str, float]],
        cluster_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, int], Dict[str, int]]:
        func_alloc = {fid: 0 for fid in self.function_ids}
        return func_alloc, {}

    def reset(self):
        pass
