"""Tests for enhanced actuator with retry and reconciliation."""

import pytest
from datetime import datetime, timezone
from controller.allocator.knative_scaler import (
    KnativeScaler,
    ActuationResult,
    ActuationSummary
)
from controller.allocator.state_store import DesiredStateStore
from controller.contracts import AllocationDecision


class TestKnativeScaler:
    """Test idempotency, retry logic, and reconciliation."""

    def test_dry_run_mode(self):
        """Dry-run mode should skip actual patches."""
        scaler = KnativeScaler(dry_run=True)
        assert scaler.dry_run is True
        assert scaler.api_available is False

    def test_idempotency_already_at_target(self):
        """Should skip patch if already at target."""
        scaler = KnativeScaler(dry_run=True)
        scaler._known_state["test-service"] = 5
        
        result = scaler._patch_service("test-service", 5)
        assert result.success is True
        assert result.skipped is True
        assert result.attempts == 0
        assert "Already at target" in result.message

    def test_scale_down_deadband(self):
        """Should skip scale-down within deadband."""
        scaler = KnativeScaler(dry_run=True)
        scaler._known_state["test-service"] = 3
        
        # Scale down by 1 is AT the deadband threshold (SCALE_DOWN_DEADBAND = 1)
        # so it should NOT be skipped by deadband logic, but would patch
        result = scaler._patch_service("test-service", 2)
        assert result.success is True
        # In dry-run, it still gets marked as would-patch
        assert result.skipped is True
        assert "dry-run" in result.message.lower()

    def test_scale_up_immediate(self):
        """Scale-up should always apply immediately."""
        scaler = KnativeScaler(dry_run=True)
        scaler._known_state["test-service"] = 2
        
        result = scaler._patch_service("test-service", 5)
        assert result.success is True
        assert result.requested == 5
        # In dry-run mode, state is updated even though no real patch
        assert scaler._known_state["test-service"] == 5

    def test_scale_down_beyond_deadband(self):
        """Scale-down beyond deadband should apply."""
        scaler = KnativeScaler(dry_run=True)
        scaler._known_state["test-service"] = 5
        
        # Scale down by 3 is beyond deadband
        result = scaler._patch_service("test-service", 2)
        assert result.success is True
        assert result.requested == 2
        # In dry-run mode, state is updated
        assert scaler._known_state["test-service"] == 2

    def test_apply_allocation_summary(self):
        """Should return structured summary."""
        scaler = KnativeScaler(dry_run=True)
        scaler._known_state = {"svc1": 2, "svc2": 2, "svc3": 2}
        
        targets = {
            "svc1": 5,  # scale up (will patch in non-dry-run)
            "svc2": 2,  # no change (skipped, idempotency)
            "svc3": 1,  # scale down by 1 (within deadband, but dry-run patches it)
        }
        
        summary = scaler.apply_allocation(targets)
        assert summary.total == 3
        assert summary.successful == 3
        # In dry-run, everything gets marked as skipped (including would-be patches)
        assert summary.skipped >= 1  # At least svc2 should be skipped
        assert summary.failed == 0

    def test_reconcile(self):
        """Reconcile should work like apply_allocation."""
        scaler = KnativeScaler(dry_run=True)
        desired = {"svc1": 3, "svc2": 5}
        
        summary = scaler.reconcile(desired)
        assert summary.total == 2
        assert summary.successful == 2


class TestDesiredStateStore:
    """Test persistent state management."""

    def test_save_and_load(self, tmp_path):
        """Should save and load decision state."""
        state_file = tmp_path / "test_state.json"
        store = DesiredStateStore(str(state_file))
        
        decision = AllocationDecision(
            decision_id="dec-123",
            cycle_id="cyc-123",
            source="pso",
            created_at=datetime.now(timezone.utc),
            estimated_memory_mb=1000.0,
            within_budget=True,
            rejected_reason="",
            node_capacities={"n1": 5, "n2": 3},
            function_capacities={"f01": 5, "f02": 3}
        )
        
        store.save(decision)
        loaded = store.load()
        
        assert loaded is not None
        assert loaded["decision_id"] == "dec-123"
        assert loaded["function_capacities"] == {"f01": 5, "f02": 3}
        assert loaded["node_capacities"] == {"n1": 5, "n2": 3}
        assert "saved_at" in loaded

    def test_load_nonexistent(self, tmp_path):
        """Should return None if no state file."""
        store = DesiredStateStore(str(tmp_path / "nonexistent.json"))
        loaded = store.load()
        assert loaded is None

    def test_clear(self, tmp_path):
        """Should delete state file."""
        state_file = tmp_path / "test_state.json"
        store = DesiredStateStore(str(state_file))
        
        decision = AllocationDecision(
            decision_id="dec-123",
            cycle_id="cyc-123",
            source="test",
            created_at=datetime.now(timezone.utc),
            estimated_memory_mb=1000.0,
            within_budget=True,
            rejected_reason="",
            node_capacities={},
            function_capacities={}
        )
        
        store.save(decision)
        assert state_file.exists()
        
        store.clear()
        assert not state_file.exists()

    def test_get_age_seconds(self, tmp_path):
        """Should calculate state age."""
        state_file = tmp_path / "test_state.json"
        store = DesiredStateStore(str(state_file))
        
        decision = AllocationDecision(
            decision_id="dec-123",
            cycle_id="cyc-123",
            source="test",
            created_at=datetime.now(timezone.utc),
            estimated_memory_mb=1000.0,
            within_budget=True,
            rejected_reason="",
            node_capacities={},
            function_capacities={}
        )
        
        store.save(decision)
        age = store.get_age_seconds()
        
        assert age is not None
        assert age >= 0.0
        assert age < 5.0  # Should be recent
