import json
from typing import Any, Dict, List, Set


class GranularityTree:
    """Dependency Granularity DAG parser and max-projection engine.

    Translates per-function capacity recommendations into shareable node warm capacities.
    """

    def __init__(self, config_path: str = "configs/dependencies.json"):
        self.config_path = config_path
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.functions: Dict[str, Dict[str, Any]] = {}
        self.node_ids: List[str] = []
        self._node_to_functions: Dict[str, Set[str]] = {}
        self._load_tree()

    def _load_tree(self):
        with open(self.config_path, "r") as f:
            data = json.load(f)

        for n in data.get("nodes", []):
            nid = n["id"]
            self.nodes[nid] = n
            self.node_ids.append(nid)
            self._node_to_functions[nid] = set()

        for f in data.get("functions", []):
            fid = f["id"]
            self.functions[fid] = f
            path = f.get("dependency_path", [])
            for node_id in path:
                if node_id in self._node_to_functions:
                    self._node_to_functions[node_id].add(fid)

    def get_total_nodes(self) -> int:
        return len(self.node_ids)

    def get_dependency_path(self, function_id: str) -> List[str]:
        func = self.functions.get(function_id)
        if not func:
            return []
        return list(func.get("dependency_path", []))

    def get_functions_for_node(self, node_id: str) -> List[str]:
        return list(self._node_to_functions.get(node_id, set()))

    def get_node_memory(self, node_id: str) -> float:
        node = self.nodes.get(node_id, {})
        return float(node.get("memory_mb", 0.0))

    def project_capacities(self, func_recommendations: Dict[str, float]) -> Dict[str, float]:
        """Max-Projection Algorithm:

        For each node v_k in the granularity DAG:
            P_k^tree = max { P_i : f_i depends on v_k }
        """
        projected: Dict[str, float] = {}
        for nid in self.node_ids:
            dependent_funcs = self._node_to_functions.get(nid, set())
            if not dependent_funcs:
                projected[nid] = 0.0
            else:
                max_val = 0.0
                for fid in dependent_funcs:
                    val = func_recommendations.get(fid, 0.0)
                    if val > max_val:
                        max_val = val
                projected[nid] = max_val
        return projected

    def map_tree_allocation_to_functions(
        self,
        node_allocation: Dict[str, int]
    ) -> Dict[str, int]:
        """Maps node warm counts to effective function warm counts."""
        func_allocation: Dict[str, int] = {}
        for fid, finfo in self.functions.items():
            leaf_id = finfo.get("leaf_node")
            func_allocation[fid] = node_allocation.get(leaf_id, 0)
        return func_allocation
