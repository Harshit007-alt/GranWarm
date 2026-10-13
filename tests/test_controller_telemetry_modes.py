import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

from controller.contracts import TelemetryError
from controller.main import GranuWarmController, OperatingMode
from controller.monitor.prometheus_client import PrometheusMonitor


class _MonitorStub:
    def __init__(self, **kwargs):
        self.enable_mock_fallback = kwargs["enable_mock_fallback"]
        self.probe_called = False
        self.forced_mock_only = False

    def probe(self):
        self.probe_called = True
        return False

    def force_mock_only(self):
        self.forced_mock_only = True

    def validate_schema(self):
        pass


def _controller(monkeypatch, mode, tmp_path):
    monitors = []

    def create_monitor(**kwargs):
        monitor = _MonitorStub(**kwargs)
        monitors.append(monitor)
        return monitor

    monkeypatch.setattr("controller.main.PrometheusMonitor", create_monitor)
    controller = GranuWarmController(mode=mode, audit_dir=str(tmp_path))
    return controller, monitors[0]


def test_live_mode_disables_mock_fallback_and_mock_only(monkeypatch, tmp_path):
    _, monitor = _controller(monkeypatch, OperatingMode.LIVE, tmp_path)

    assert monitor.enable_mock_fallback is False
    assert monitor.probe_called is False
    assert monitor.forced_mock_only is False


def test_shadow_mode_disables_mock_fallback(monkeypatch, tmp_path):
    _, monitor = _controller(monkeypatch, OperatingMode.SHADOW, tmp_path)

    assert monitor.enable_mock_fallback is False
    assert monitor.probe_called is False
    assert monitor.forced_mock_only is False


def test_simulation_mode_allows_mock_only_fallback(monkeypatch, tmp_path):
    _, monitor = _controller(monkeypatch, OperatingMode.SIMULATION, tmp_path)

    assert monitor.enable_mock_fallback is True
    assert monitor.probe_called is True
    assert monitor.forced_mock_only is True


def test_live_monitor_rejects_missing_telemetry_without_mock():
    monitor = PrometheusMonitor(enable_mock_fallback=False)
    monitor._session.get = Mock(side_effect=OSError("Prometheus down"))

    try:
        monitor.fetch_function("f01", "f01-hello-world")
    except TelemetryError as error:
        assert "Required signal 'R_i' missing" in str(error)
    else:
        raise AssertionError("missing live telemetry must raise TelemetryError")


def test_telemetry_failure_is_audited_and_cycle_is_skipped(tmp_path):
    controller = object.__new__(GranuWarmController)
    controller.is_running = True
    controller.dt_fast = 0
    controller.mode = OperatingMode.LIVE
    controller.audit_dir = Path(tmp_path)
    controller.stale_allow = False
    controller.svc_map = {}
    controller.monitor = Mock()
    controller.monitor.fetch_snapshot.side_effect = TelemetryError(
        "Prometheus down"
    )

    asyncio.run(controller.run_loop(max_cycles=1))

    audit_files = list(Path(tmp_path).glob("*.jsonl"))
    assert len(audit_files) == 1
    record = json.loads(audit_files[0].read_text(encoding="utf-8"))
    assert record["event"] == "telemetry_error"
    assert record["mode"] == "live"
    assert record["telemetry_source"] == "unavailable"
    assert record["error"] == "Prometheus down"
