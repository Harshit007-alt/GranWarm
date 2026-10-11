import pytest
from controller.granularity.tree import GranularityTree
from controller.safety.feasibility import FeasibilityService
from controller.contracts import AllocationRequest


@pytest.fixture
def tree():
    return GranularityTree("configs/dependencies.json")


def test_budget_violation_repaired(tree):
    svc = FeasibilityService(tree=tree, budget_mb=500.0)
    req = AllocationRequest(
        node_capacities={nid: 5 for nid in tree.node_ids},
        source="test",
    )
    decision = svc.process(req)
    assert decision.within_budget
    assert decision.estimated_memory_mb <= 500.0
    assert decision.repair_notes  # something changed


def test_zero_budget_infeasible(tree):
    svc = FeasibilityService(tree=tree, budget_mb=0.0)
    req = AllocationRequest(
        node_capacities={nid: 3 for nid in tree.node_ids}, source="test",
    )
    decision = svc.process(req)
    # Either repaired to zero (feasible) or rejected
    assert decision.within_budget or decision.rejected_reason


def test_dependency_violation_detected(tree):
    svc = FeasibilityService(tree=tree, budget_mb=1e6)
    caps = {nid: 2 for nid in tree.node_ids}
    caps["f03_leaf"] = 5      # child > parent (pillow_bundle)
    req = AllocationRequest(node_capacities=caps, source="test")
    decision = svc.process(req)
    # Should have been repaired
    assert decision.node_capacities["f03_leaf"] <= decision.node_capacities["pillow_bundle"]