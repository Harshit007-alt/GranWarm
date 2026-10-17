"""Persistent desired-state store for reconciliation after restarts.

The state store maintains the last successfully applied allocation decision,
enabling the controller to reconcile observed state with desired state after
restarts, crashes, or transient failures.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from controller.contracts import AllocationDecision

logger = logging.getLogger(__name__)


class DesiredStateStore:
    """Persists the last successful allocation decision for reconciliation.
    
    The store writes to a single JSON file that is atomically updated on each
    successful allocation. This enables:
    
    1. Startup reconciliation: Load last desired state and converge to it
    2. Failure recovery: Resume from last known-good allocation
    3. Audit trail: Track when state was last successfully applied
    
    Thread-safety: Not thread-safe. Designed for single-threaded controller.
    """

    def __init__(self, state_file: str = "results/controller_state.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"DesiredStateStore initialized: {self.state_file}")

    def save(self, decision: AllocationDecision) -> None:
        """Save a validated decision as the new desired state.
        
        Args:
            decision: A validated AllocationDecision that passed the safety gate
                     and was successfully applied to Kubernetes.
        
        The saved state includes:
        - decision_id: Unique identifier for audit correlation
        - created_at: When the decision was made
        - saved_at: When it was persisted (now)
        - function_capacities: Map of function_id -> instance count
        - node_capacities: Map of node_id -> capacity
        - estimated_memory_mb: Total memory budget used
        - source: Decision source (pso, fuzzy+delta)
        """
        state = {
            "decision_id": decision.decision_id,
            "created_at": decision.created_at.isoformat(),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "function_capacities": decision.function_capacities,
            "node_capacities": decision.node_capacities,
            "estimated_memory_mb": decision.estimated_memory_mb,
            "source": decision.source,
        }
        try:
            # Atomic write: write to temp file, then rename
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)
            temp_file.replace(self.state_file)
            logger.debug(f"Saved desired state: {decision.decision_id}")
        except Exception as e:
            logger.error(f"Failed to save desired state: {e}")

    def load(self) -> Optional[Dict]:
        """Load the last desired state, if it exists.
        
        Returns:
            Dict with function_capacities, node_capacities, metadata, or None
            if no state file exists or loading fails.
        """
        if not self.state_file.exists():
            logger.info("No previous desired state found")
            return None
        
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
            
            saved_at = state.get('saved_at', 'unknown')
            decision_id = state.get('decision_id', 'unknown')
            logger.info(
                f"Loaded desired state: {decision_id} saved at {saved_at}"
            )
            return state
        except Exception as e:
            logger.error(f"Failed to load desired state: {e}")
            return None

    def clear(self) -> None:
        """Clear the desired state (e.g., on manual intervention or reset).
        
        Use this when:
        - Manually scaling functions outside the controller
        - Resetting the controller to a clean slate
        - Debugging or testing scenarios
        """
        if self.state_file.exists():
            try:
                self.state_file.unlink()
                logger.info("Cleared desired state")
            except Exception as e:
                logger.error(f"Failed to clear desired state: {e}")
        else:
            logger.debug("No desired state to clear")

    def get_age_seconds(self) -> Optional[float]:
        """Get the age of the saved state in seconds.
        
        Returns:
            Age in seconds, or None if no state exists or saved_at is missing.
        """
        state = self.load()
        if not state or 'saved_at' not in state:
            return None
        
        try:
            saved_at = datetime.fromisoformat(state['saved_at'])
            age = (datetime.now(timezone.utc) - saved_at).total_seconds()
            return age
        except Exception as e:
            logger.error(f"Failed to calculate state age: {e}")
            return None
