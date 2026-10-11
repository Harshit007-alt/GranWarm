import json
from typing import Any, Dict, List, Optional, Set, Tuple


class GranularityTree:
    """Dependency Granularity DAG parser and max-projection engine.

    Translates per-function capacity recommendations into shareable node warm capacities.

    Nodes marked `allocatable: false` (e.g., the structural `root`) are parsed
    for graph traversal but excluded from the allocatable node list, the PSO
    dimension, and the memory accounting.
    """

    def __init__(self, config_path: str = "configs/dependencies.json"):
        self.config_path = config_path
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.functions: Dict[str, Dict[str, Any]] = {}
        self.node_ids: List[str] = []          # allocatable only
        self.all_node_ids: List[str] = []      # every node, allocatable or not
        self._node_to_functions: Dict[str, Set[str]] = {}
        self.parent_map: Dict[str, Optional[str]] = {}
        self.node_index: Dict[str, int] = {}   # allocatable index
        self._load_tree()

    # ------------------------------------------------------------------
    def _load_tree(self):
        with open(self.config_path, "r") as f:
            data = json.load(f)

        for n in data.get("nodes", []):
            nid = n["id"]
            self.nodes[nid] = n
            self.all_node_ids.append(nid)
            self._node_to_functions[nid] = set()
            self.parent_map[nid] = n.get("parent")

            # Only allocatable nodes participate in the optimization vector
            if n.get("allocatable", True):
                self.node_index[nid] = len(self.node_ids)
                self.node_ids.append(nid)

        for f in data.get("functions", []):
            fid = f["id"]
            self.functions[fid] = f
            path = f.get("dependency_path", [])
            for node_id in path:
                if node_id in self._node_to_functions:
                    self._node_to_functions[node_id].add(fid)

    # ------------------------------------------------------------------
    # Basic queries
    # ------------------------------------------------------------------
    def get_total_nodes(self) -> int:
        """Number of ALLOCATABLE nodes (PSO dimension)."""
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

    def is_allocatable(self, node_id: str) -> bool:
        return node_id in self.node_index

    # ------------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------------
    def project_capacities(
        self, func_recommendations: Dict[str, float],
    ) -> Dict[str, float]:
        """Max-Projection Algorithm.

        For each allocatable node v_k:
            P_k^tree = max { P_i : f_i depends on v_k }
        Non-allocatable nodes are returned as 0.0.
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
        self, node_allocation: Dict[str, int],
    ) -> Dict[str, int]:
        """Maps node warm counts to effective function warm counts."""
        func_allocation: Dict[str, int] = {}
        for fid, finfo in self.functions.items():
            leaf_id = finfo.get("leaf_node")
            func_allocation[fid] = node_allocation.get(leaf_id, 0)
        return func_allocation

    # ------------------------------------------------------------------
    # Shared-layer semantics
    # ------------------------------------------------------------------
    def is_shared_layer(self, node_id: str) -> bool:
        node = self.nodes.get(node_id, {})
        return int(node.get("layer", 2)) < 2

    def get_children(self, node_id: str) -> List[str]:
        return [k for k, v in self.nodes.items() if v.get("parent") == node_id]

    def get_ancestors(self, node_id: str) -> List[str]:
        path = []
        cur = self.nodes.get(node_id, {}).get("parent")
        while cur:
            path.append(cur)
            cur = self.nodes.get(cur, {}).get("parent")
        return path

    def validate_dependency_constraints(
        self, node_caps: Dict[str, int],
    ) -> Tuple[bool, str]:
        """Enforce: for every (child, parent) pair, child <= parent.

        Only allocatable nodes are checked; non-allocatable ancestors are
        ignored (they carry no capacity and are always effectively infinite).
        """
        for nid in self.node_ids:
            parent = self.parent_map.get(nid)
            if not parent or not self.is_allocatable(parent):
                continue
            if parent not in node_caps or nid not in node_caps:
                continue
            if node_caps[nid] > node_caps[parent]:
                return False, (
                    f"{nid}({node_caps[nid]}) > {parent}"
                    f"({node_caps[parent]})"
                )
        return True, ""

    def compute_shared_memory(self, node_caps: Dict[str, int]) -> float:
        """Shared layers counted ONCE per family."""
        total = 0.0
        for nid in self.node_ids:
            if not self.is_shared_layer(nid):
                continue
            caps_here = node_caps.get(nid, 0)
            if caps_here <= 0:
                continue
            effective = self._subtree_max(nid, node_caps)
            total += self.get_node_memory(nid) * effective
        return total

    def _subtree_max(self, nid: str, node_caps: Dict[str, int]) -> int:
        best = node_caps.get(nid, 0)
        for c in self.get_children(nid):
            best = max(best, self._subtree_max(c, node_caps))
        return best