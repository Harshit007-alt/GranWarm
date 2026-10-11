import logging
from typing import Dict, List, Tuple

from controller.contracts import (
    AllocationRequest, AllocationDecision,
    InfeasibleAllocationError,
)
from controller.contracts.allocation import _new_id

logger = logging.getLogger(__name__)


class FeasibilityService:
    """Hard safety gate for all allocation decisions.

    Responsibilities:
      - Validate: every node known, bounds respected, dependency DAG satisfied
      - Compute memory: shared layers counted ONCE
      - Repair: proportionally shrink until feasible, respecting min bounds
      - Reject: if repair cannot fit within budget, return infeasible decision
    """

    def __init__(
        self,
        tree,                              # GranularityTree
        budget_mb: float,
        node_min_capacity: Dict[str, int] = None,
        node_max_capacity: Dict[str, int] = None,
    ):
        self.tree = tree
        self.budget_mb = float(budget_mb)
        self.node_ids = list(tree.node_ids)
        self.node_memories = {
            nid: float(tree.get_node_memory(nid)) for nid in self.node_ids
        }
        self.node_min = node_min_capacity or {nid: 0 for nid in self.node_ids}
        self.node_max = node_max_capacity or {nid: 10 for nid in self.node_ids}

    # ------------------------------------------------------------------
    # Memory accounting: shared layers counted ONCE
    # ------------------------------------------------------------------
    def estimate_memory_mb(self, node_caps: Dict[str, int]) -> float:
        """Sum (memory_mb * max_capacity_over_subtree) for shared layers,
        plus per-instance memory for function leaves.

        For a shared layer, we count its memory * maximum capacity among
        children that depend on it — because a single warm runtime can
        serve many concurrent functions.
        """
        total = 0.0
        for nid in self.node_ids:
            caps = node_caps.get(nid, 0)
            if caps <= 0:
                continue
            mem = self.node_memories[nid]
            if self._is_shared(nid):
                # Count once per "family" — determine effective demand
                effective = self._subtree_max_capacity(nid, node_caps)
                total += mem * effective
            else:
                total += mem * caps
        return total

    def _is_shared(self, nid: str) -> bool:
        node = self.tree.nodes.get(nid, {})
        return int(node.get("layer", 2)) < 2

    def _subtree_max_capacity(self, nid: str, node_caps: Dict[str, int]) -> int:
        """Max capacity among the layer itself and all descendants."""
        best = node_caps.get(nid, 0)
        for child in self._children_of(nid):
            best = max(best, self._subtree_max_capacity(child, node_caps))
        return best

    def _children_of(self, nid: str) -> List[str]:
        return [k for k, v in self.tree.nodes.items() if v.get("parent") == nid]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self, req: AllocationRequest) -> Tuple[bool, str]:
        # 1. All nodes known
        for nid in req.node_capacities:
            if nid not in self.node_memories:
                return False, f"Unknown node: {nid}"

        # 2. Bounds
        for nid, cap in req.node_capacities.items():
            if cap < self.node_min.get(nid, 0):
                return False, f"Node {nid} capacity {cap} < min {self.node_min[nid]}"
            if cap > self.node_max.get(nid, 10):
                return False, f"Node {nid} capacity {cap} > max {self.node_max[nid]}"

        # 3. Dependency constraint: parent >= child
        for nid, node in self.tree.nodes.items():
            parent = node.get("parent")
            if parent and parent in req.node_capacities:
                if req.node_capacities[nid] > req.node_capacities[parent]:
                    return False, (
                        f"Dependency violation: {nid}={req.node_capacities[nid]} "
                        f"> parent {parent}={req.node_capacities[parent]}"
                    )

        # 4. Budget
        est = self.estimate_memory_mb(req.node_capacities)
        if est > self.budget_mb:
            return False, f"Memory {est:.1f} MB > budget {self.budget_mb:.1f} MB"

        return True, ""

    # ------------------------------------------------------------------
    # Repair
    # ------------------------------------------------------------------
    def repair(self, req: AllocationRequest) -> Tuple[AllocationRequest, List[str]]:
        notes: List[str] = []
        caps = dict(req.node_capacities)

        # Fix bounds first
        for nid in self.node_ids:
            c = caps.get(nid, 0)
            if c < self.node_min.get(nid, 0):
                caps[nid] = self.node_min[nid]
            elif c > self.node_max.get(nid, 10):
                caps[nid] = self.node_max[nid]

        # Fix dependency violations bottom-up
        for nid, node in self.tree.nodes.items():
            parent = node.get("parent")
            if parent and parent in caps:
                if caps[nid] > caps[parent]:
                    old = caps[nid]
                    caps[nid] = caps[parent]
                    notes.append(f"Child {nid} {old}->{caps[nid]} (parent clamp)")

        # Scale down proportionally until budget met
        for _ in range(20):  # bounded attempts
            est = self.estimate_memory_mb(caps)
            if est <= self.budget_mb:
                break
            ratio = self.budget_mb / max(est, 1.0)
            changed = False
            for nid in self.node_ids:
                if caps.get(nid, 0) > self.node_min.get(nid, 0):
                    new_c = max(
                        self.node_min.get(nid, 0),
                        int(caps[nid] * ratio)
                    )
                    if new_c != caps[nid]:
                        notes.append(f"Scale {nid} {caps[nid]}->{new_c}")
                        caps[nid] = new_c
                        changed = True
            if not changed:
                break

        # Re-check dependency constraint after scaling
        for nid, node in self.tree.nodes.items():
            parent = node.get("parent")
            if parent and parent in caps:
                if caps[nid] > caps[parent]:
                    caps[nid] = caps[parent]

        return AllocationRequest(
            node_capacities=caps,
            source=req.source + "+repaired",
            cycle_id=req.cycle_id,
            requested_budget_mb=req.requested_budget_mb,
        ), notes

    # ------------------------------------------------------------------
    # Full pipeline: validate -> repair -> validate -> decide
    # ------------------------------------------------------------------
    def process(self, req: AllocationRequest) -> AllocationDecision:
        ok, reason = self.validate(req)
        repair_notes: List[str] = []

        if not ok:
            logger.info(f"Request invalid ({reason}); attempting repair")
            req, repair_notes = self.repair(req)
            ok, reason = self.validate(req)
            if not ok:
                # Cannot repair — emit rejected decision
                logger.error(f"Repair failed: {reason}")
                func_caps = self.tree.map_tree_allocation_to_functions(
                    req.node_capacities
                )
                return AllocationDecision(
                    decision_id=_new_id("dec"),
                    cycle_id=req.cycle_id,
                    source=req.source,
                    node_capacities=req.node_capacities,
                    function_capacities=func_caps,
                    estimated_memory_mb=self.estimate_memory_mb(req.node_capacities),
                    within_budget=False,
                    rejected_reason=reason,
                    repair_notes=repair_notes,
                )

        est = self.estimate_memory_mb(req.node_capacities)
        func_caps = self.tree.map_tree_allocation_to_functions(req.node_capacities)
        return AllocationDecision(
            decision_id=_new_id("dec"),
            cycle_id=req.cycle_id,
            source=req.source,
            node_capacities=req.node_capacities,
            function_capacities=func_caps,
            estimated_memory_mb=est,
            within_budget=True,
            repair_notes=repair_notes,
        )