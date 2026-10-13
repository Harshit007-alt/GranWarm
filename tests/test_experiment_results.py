import pytest

from experiments.run_experiment import REQUIRED_METRICS, _validate_metrics


def test_experiment_metrics_must_be_complete():
    with pytest.raises(ValueError, match="incomplete metrics"):
        _validate_metrics({"p95_latency_ms": 100.0})


def test_experiment_metrics_accept_all_recorded_fields():
    _validate_metrics({metric: 0.0 for metric in REQUIRED_METRICS})
