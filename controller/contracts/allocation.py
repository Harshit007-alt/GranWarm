from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List
import uuid


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class AllocationRequest:
    """Proposed allocation before validation."""

    node_capacities: Dict[str, int]
    source: str                       # "fuzzy" | "pso" | "proportional"
    cycle_id: str = field(default_factory=lambda: _new_id("cyc"))
    requested_budget_mb: float = 4096.0


@dataclass(frozen=True)
class AllocationDecision:
    """Validated allocation, ready for actuation."""

    decision_id: str
    cycle_id: str
    source: str
    node_capacities: Dict[str, int]
    function_capacities: Dict[str, int]
    estimated_memory_mb: float
    within_budget: bool
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    rejected_reason: str = ""
    repair_notes: List[str] = field(default_factory=list)
    telemetry_source: str = "unknown"   # "prometheus" | "mock" | "replay" | ...

    def to_audit_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "cycle_id": self.cycle_id,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "estimated_memory_mb": self.estimated_memory_mb,
            "within_budget": self.within_budget,
            "rejected_reason": self.rejected_reason,
            "repair_notes": self.repair_notes,
            "telemetry_source": self.telemetry_source,
            "node_capacities": self.node_capacities,
            "function_capacities": self.function_capacities,
        }