import pytest
from datetime import datetime, timezone, timedelta
from controller.contracts import (
    FunctionTelemetry, ContractValidationError, TelemetryError,
    validate_function_telemetry, STALENESS_THRESHOLD_SEC,
)


def _ft(**overrides):
    defaults = dict(
        function_id="f01", service_name="f01-hello-world",
        captured_at=datetime.now(timezone.utc),
        R_i=0.5, T_i=0.1, C_i=0.2, M=0.4,
    )
    defaults.update(overrides)
    return FunctionTelemetry(**defaults)


def test_valid_telemetry_passes():
    validate_function_telemetry(_ft())


def test_out_of_range_raises():
    with pytest.raises(ContractValidationError):
        validate_function_telemetry(_ft(R_i=1.5))


def test_stale_raises():
    old = datetime.now(timezone.utc) - timedelta(seconds=STALENESS_THRESHOLD_SEC + 5)
    with pytest.raises(TelemetryError):
        validate_function_telemetry(_ft(captured_at=old))


def test_allow_stale_flag():
    old = datetime.now(timezone.utc) - timedelta(seconds=STALENESS_THRESHOLD_SEC + 5)
    validate_function_telemetry(_ft(captured_at=old), allow_stale=True)