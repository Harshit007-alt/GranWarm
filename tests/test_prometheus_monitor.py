import logging
from unittest.mock import Mock

import pytest

from controller.contracts import TelemetryError
from controller.monitor.prometheus_client import PrometheusMonitor


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {
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
    empty_result = _Response(
        payload={"status": "success", "data": {"result": []}},
    )
    monitor._session.get = Mock(side_effect=[
        _Response(), empty_result, empty_result, empty_result,
    ])

    with caplog.at_level(logging.WARNING):
        telemetry = monitor.fetch_function("f01", "f01-hello-world")

    assert telemetry.source == "mock"
    assert "service=f01-hello-world" in caplog.text
    assert "signals=['R_i', 'M']" in caplog.text


def test_non_finite_required_signal_raises_without_fallback():
    monitor = PrometheusMonitor()
    non_finite = _Response(payload={
        "status": "success",
        "data": {"result": [{"value": [0, "NaN"]}]},
    })
    monitor._session.get = Mock(side_effect=[_Response(), non_finite])

    with pytest.raises(TelemetryError, match="Required signal 'R_i' missing"):
        monitor.fetch_function("f01", "f01-hello-world")


def test_prometheus_down_raises_telemetry_error_without_fallback():
    monitor = PrometheusMonitor(enable_mock_fallback=False)
    monitor._session.get = Mock(side_effect=OSError("Prometheus down"))

    with pytest.raises(TelemetryError, match="scrape health unavailable"):
        monitor.fetch_function("f01", "f01-hello-world")


def test_queries_scope_memory_and_return_zero_when_idle():
    monitor = PrometheusMonitor(namespace="staging")

    assert "or vector(0)" in monitor.QUERY_SCHEMA["R_i"]
    assert "activator_request_count" in monitor.QUERY_SCHEMA["cold_starts"]
    assert "revision_app_request_latencies_count" not in (
        monitor.QUERY_SCHEMA["cold_starts"]
    )
    assert 'namespace="{namespace}"' in monitor.QUERY_SCHEMA["M"]
    assert 'pod=~"{svc}-.*"' in monitor.QUERY_SCHEMA["M"]
    assert 'resource="memory",unit="byte"' in monitor.QUERY_SCHEMA["M"]
    assert monitor.namespace == "staging"


def test_fetch_substitutes_validated_service_and_namespace():
    monitor = PrometheusMonitor(namespace="staging")
    monitor._session.get = Mock(side_effect=[
        _Response(),
        _Response(payload={
            "status": "success",
            "data": {"result": [{"value": [0, "0"]}]},
        }),
        _Response(payload={
            "status": "success",
            "data": {"result": [{"value": [0, "0.25"]}]},
        }),
        _Response(payload={
            "status": "success",
            "data": {"result": [{"value": [0, "0"]}]},
        }),
    ])

    telemetry = monitor.fetch_function("f01", "f01-hello-world")

    assert telemetry.R_i == 0
    assert telemetry.M == 0.25
    queries = [
        call.kwargs["params"]["query"]
        for call in monitor._session.get.call_args_list[1:]
    ]
    assert all("{svc}" not in query for query in queries)
    assert all("{namespace}" not in query for query in queries)
    assert all('service_name="f01-hello-world"' in query for query in queries
               if "service_name" in query)
    assert all('namespace="staging"' in query for query in queries
               if "namespace" in query)


def test_invalid_service_name_is_rejected_before_query():
    monitor = PrometheusMonitor()
    monitor._session.get = Mock()

    with pytest.raises(TelemetryError, match="Invalid Kubernetes service"):
        monitor.fetch_function("f01", "service-name OR vector(1)")

    monitor._session.get.assert_not_called()


def test_schema_validation_uses_metric_name_index():
    monitor = PrometheusMonitor()
    monitor._session.get = Mock(side_effect=[
        _Response(),
        _Response(payload={
            "status": "success",
            "data": list(monitor.REQUIRED_BASE_METRICS),
        }),
    ])

    monitor.validate_schema()

    assert monitor._session.get.call_args_list[1].args[0].endswith(
        "/api/v1/label/__name__/values"
    )


def test_schema_validation_rejects_missing_base_metric():
    monitor = PrometheusMonitor()
    monitor._session.get = Mock(side_effect=[
        _Response(),
        _Response(payload={"status": "success", "data": []}),
    ])

    with pytest.raises(TelemetryError, match="missing required base metrics"):
        monitor.validate_schema()
