from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class FunctionSpec:
    function_id: str
    service_name: str
    runtime: str                     # "python" | "nodejs"
    container_memory_mb: int
    leaf_node: str
    dependencies: List[str]          # node IDs
    cold_start_ms: float
    warm_start_ms: float
    min_capacity: int = 0
    max_capacity: int = 10


@dataclass(frozen=True)
class LayerSpec:
    layer_id: str
    name: str
    layer_depth: int                 # -1 for root, 0 runtime, 1 library, 2 function
    parent_id: Optional[str]
    memory_mb: float
    init_time_ms: float
    is_shared: bool                  # True for depth < 2