import logging
from unittest.mock import Mock

import pytest

from controller.contracts import TelemetryError
from controller.monitor.prometheus_client import PrometheusMonitor


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {
            "status": "success",
            "data": {"result": [{"value": [0, "1"]}]},
        }

    def json(self):
        return self._payload


@pytest.mark.parametrize(
    ("response", "expected_log"),
    [
        (_Response(503), "HTTP status=503"),
        (_Response(payload={"status": "error"}), "status='error'"),
        (_Response(payload={"status": "success", "data": {"result": []}}),
         "empty result"),
        (_Response(payload={
            "status": "success",
            "data": {"result": [{"value": [0, "NaN"]}]},
        }), "non-finite"),
        (_Response(payload={
            "status": "success",
            "data": {"result": [{"value": [0, "Infinity"]}]},
        }), "non-finite"),
    ],
)
def test_query_failures_are_warned_and_return_none(
    response, expected_log, caplog,
):
    monitor = PrometheusMonitor()
    monitor._session.get = Mock(return_value=response)

    with caplog.at_level(logging.WARNING):
        assert monitor._query_promql("up") is None

    assert expected_log in caplog.text
    assert "query='up'" in caplog.text


def test_query_exception_is_warned_with_query(caplog):
    monitor = PrometheusMonitor()
    monitor._session.get = Mock(side_effect=OSError("connection refused"))

    with caplog.at_level(logging.WARNING):
        assert monitor._query_promql("up") is None

    assert "HTTP status=unavailable" in caplog.text
    assert "query='up'" in caplog.text
    assert "connection refused" in caplog.text


def test_mock_fallback_logs_all_mocked_signals(caplog):
    monitor = PrometheusMonitor(enable_mock_fallback=True)
    monitor._session.get = Mock(return_value=_Response(
        payload={"status": "success", "data": {"result": []}},
    ))

    with caplog.at_level(logging.WARNING):
        telemetry = monitor.fetch_function("f01", "f01-hello-world")

    assert telemetry.source == "mock"
    assert "service=f01-hello-world" in caplog.text
    assert "signals=['R_i', 'M']" in caplog.text


def test_non_finite_required_signal_raises_without_fallback():
    monitor = PrometheusMonitor()
    monitor._session.get = Mock(return_value=_Response(payload={
        "status": "success",
        "data": {"result": [{"value": [0, "NaN"]}]},
    }))

    with pytest.raises(TelemetryError, match="Required signal 'R_i' missing"):
        monitor.fetch_function("f01", "f01-hello-world")
