from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class BasePolicy(ABC):
    """Abstract base interface for all comparative prewarming policies (B1–B6)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable policy identifier."""
        pass

    @abstractmethod
    def compute_allocation(
        self,
        metrics: Dict[str, Dict[str, float]],
        cluster_metrics: Optional[Dict[str, float]] = None
    ) -> Tuple[Dict[str, int], Dict[str, int]]:
        """Computes warm capacity allocation.

        Returns:
            (func_allocation, tree_allocation):
                func_allocation: {function_id: min_scale_int}
                tree_allocation: {node_id: warm_count_int} (empty if not granularity-aware)
        """
        pass

    @abstractmethod
    def reset(self):
        """Resets all internal history and state between experimental runs."""
        pass
