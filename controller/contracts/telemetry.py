from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional
import json


@dataclass(frozen=True)
class FunctionTelemetry:
    """Typed telemetry for one function in one cycle."""
    function_id: str
    service_name: str
    captured_at: datetime
    R_i: float           # [0, 1] invocation intensity
    T_i: float           # [-1, 1] traffic trend
    C_i: float           # [0, 1] cold-start pressure
    M: float             # [0, 1] memory pressure
    L_p50_ms: float = 0.0
    L_p99_ms: float = 0.0
    S_i: float = 0.0     # [0, 1] SLA pressure
    is_stale: bool = False
    source: str = "prometheus"  # or "simulator" / "replay" / "mock"

    def to_dict(self) -> dict:
        return {
            "function_id": self.function_id,
            "service_name": self.service_name,
            "captured_at": self.captured_at.isoformat(),
            "R_i": self.R_i, "T_i": self.T_i, "C_i": self.C_i, "M": self.M,
            "L_p50_ms": self.L_p50_ms, "L_p99_ms": self.L_p99_ms,
            "S_i": self.S_i, "is_stale": self.is_stale, "source": self.source,
        }


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Consistent point-in-time snapshot for a controller cycle."""
    cycle_id: str
    captured_at: datetime
    functions: Dict[str, FunctionTelemetry]  # keyed by function_id
    schema_version: str = "1.0"

    def max_age_sec(self) -> float:
        if not self.functions:
            return 0.0
        now = datetime.now(timezone.utc)
        return max((now - t.captured_at).total_seconds() for t in self.functions.values())

    def to_json(self) -> str:
        return json.dumps({
            "cycle_id": self.cycle_id,
            "captured_at": self.captured_at.isoformat(),
            "schema_version": self.schema_version,
            "functions": {fid: t.to_dict() for fid, t in self.functions.items()},
        }, indent=2)