from datetime import datetime, timezone

from .errors import ContractValidationError, TelemetryError


STALENESS_THRESHOLD_SEC = 30.0   # 3x the fast loop interval


def validate_unit(value: float, name: str, lo: float, hi: float) -> None:
    if not (lo <= value <= hi):
        raise ContractValidationError(
            f"{name}={value} outside domain [{lo}, {hi}]"
        )


def validate_function_telemetry(t, allow_stale: bool = False) -> None:
    validate_unit(t.R_i, "R_i", 0.0, 1.0)
    validate_unit(t.C_i, "C_i", 0.0, 1.0)
    validate_unit(t.M, "M", 0.0, 1.0)
    validate_unit(t.T_i, "T_i", -1.0, 1.0)
    validate_unit(t.S_i, "S_i", 0.0, 1.0)

    # Synthetic telemetry has no real-time contract — never stale.
    if t.source in ("mock", "replay", "simulator"):
        return

    age = (datetime.now(timezone.utc) - t.captured_at).total_seconds()
    if age > STALENESS_THRESHOLD_SEC and not allow_stale:
        raise TelemetryError(
            f"Telemetry for {t.function_id} is {age:.1f}s old "
            f"(threshold {STALENESS_THRESHOLD_SEC}s)"
        )


def validate_snapshot(snapshot, allow_stale: bool = False) -> None:
    if not snapshot.functions:
        raise TelemetryError("TelemetrySnapshot contains zero functions")
    for t in snapshot.functions.values():
        validate_function_telemetry(t, allow_stale=allow_stale)