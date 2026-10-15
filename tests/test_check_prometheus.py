from unittest.mock import Mock

from controller.monitor.prometheus_client import PrometheusMonitor
from scripts import check_prometheus


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {"status": "success", "data": {}}

    def json(self):
        return self.payload


class _Session:
    def __init__(self, *, empty_required_query=False, missing_metric=None):
        self.empty_required_query = empty_required_query
        self.missing_metric = missing_metric

    def get(self, url, params=None, timeout=None):
        if url.endswith("/-/ready"):
            return _Response()
        if url.endswith("/api/v1/label/__name__/values"):
            names = list(PrometheusMonitor.REQUIRED_BASE_METRICS)
            if self.missing_metric:
                names.remove(self.missing_metric)
            return _Response(payload={"status": "success", "data": names})
        query = params["query"]
        metric_by_signal = {
            "R_i": "revision_app_request_count",
            "cold_starts": "activator_request_count",
            "M": "container_memory_working_set_bytes",
        }
        signal = next(
            name for name, metric in metric_by_signal.items()
            if metric in query
        )
        if self.empty_required_query and signal == "R_i":
            result = []
        else:
            result = [{"value": [0, "0.25"]}]
        return _Response(payload={
            "status": "success",
            "data": {"result": result},
        })


def test_diagnostic_reports_readiness_metrics_and_all_queries(
    monkeypatch, capsys,
):
    monkeypatch.setattr(
        check_prometheus.requests, "Session", lambda: _Session(),
    )

    assert check_prometheus.check_prometheus(
        "http://127.0.0.1:9090", "f01-hello-world", "default",
    ) == 0

    output = capsys.readouterr().out
    assert "/-/ready: HTTP 200 (ready)" in output
    for metric in PrometheusMonitor.REQUIRED_BASE_METRICS:
        assert f"base metric {metric}: present" in output
    for signal in PrometheusMonitor.QUERY_SCHEMA:
        assert f"query {signal}:" in output


def test_diagnostic_fails_for_missing_required_metric_or_signal(
    monkeypatch, capsys,
):
    monkeypatch.setattr(
        check_prometheus.requests,
        "Session",
        lambda: _Session(
            empty_required_query=True,
            missing_metric="revision_app_request_count",
        ),
    )

    assert check_prometheus.check_prometheus(
        "http://127.0.0.1:9090", "f01-hello-world", "default",
    ) == 1

    output = capsys.readouterr().out
    assert "revision_app_request_count: MISSING" in output
    assert "query R_i: EMPTY" in output


def test_diagnostic_rejects_invalid_service_without_http(monkeypatch, capsys):
    session_factory = Mock()
    monkeypatch.setattr(
        check_prometheus.requests, "Session", session_factory,
    )

    assert check_prometheus.check_prometheus(
        "http://127.0.0.1:9090", "not a dns label", "default",
    ) == 1

    session_factory.assert_not_called()
    assert "invalid Kubernetes service DNS label" in capsys.readouterr().out


def test_diagnostic_fails_for_non_finite_required_value(monkeypatch, capsys):
    session = _Session()
    original_get = session.get

    def get_with_nan(url, params=None, timeout=None):
        response = original_get(url, params=params, timeout=timeout)
        if params and "revision_app_request_count" in params["query"]:
            return _Response(payload={
                "status": "success",
                "data": {"result": [{"value": [0, "NaN"]}]},
            })
        return response

    session.get = get_with_nan
    monkeypatch.setattr(
        check_prometheus.requests, "Session", lambda: session,
    )

    assert check_prometheus.check_prometheus(
        "http://127.0.0.1:9090", "f01-hello-world", "default",
    ) == 1
    assert "query R_i: ERROR (non-finite value)" in capsys.readouterr().out
