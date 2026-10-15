import pandas as pd
import pytest

from scripts import plot_results


def test_load_summary_requires_real_results(monkeypatch, tmp_path):
    monkeypatch.setattr(plot_results, "RAW_DIR", str(tmp_path))

    with pytest.raises(FileNotFoundError, match="Run the experiment matrix"):
        plot_results.load_summary_data()


def test_load_summary_uses_recorded_results(monkeypatch, tmp_path):
    monkeypatch.setattr(plot_results, "RAW_DIR", str(tmp_path))
    expected = pd.DataFrame([{
        "workload": "W1",
        "baseline": "B1",
        "seed": 42,
        "p95_latency_ms": 100.0,
        "cold_start_rate_pct": 1.0,
        "avg_memory_used_mb": 250.0,
        "sla_violation_rate_pct": 0.0,
        "composite_cost": 0.1,
    }])
    expected.to_csv(tmp_path / "summary_experiment_matrix.csv", index=False)

    actual = plot_results.load_summary_data()

    pd.testing.assert_frame_equal(actual, expected)


def test_load_summary_rejects_missing_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(plot_results, "RAW_DIR", str(tmp_path))
    pd.DataFrame([{"workload": "W1"}]).to_csv(
        tmp_path / "summary_experiment_matrix.csv",
        index=False,
    )

    with pytest.raises(ValueError, match="missing required columns"):
        plot_results.load_summary_data()
