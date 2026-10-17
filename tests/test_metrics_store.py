"""Tests for rolling metrics store."""

import pytest
from datetime import datetime, timedelta, timezone
from controller.metrics import RollingMetricsStore, MetricWindow


class TestMetricWindow:
    """Test MetricWindow dataclass properties."""

    def test_cold_start_rate(self):
        """Should calculate cold-start rate correctly."""
        window = MetricWindow(
            cold_start_count=5,
            total_requests=100,
        )
        assert window.cold_start_rate == 0.05

    def test_cold_start_rate_zero_requests(self):
        """Should handle zero requests gracefully."""
        window = MetricWindow(cold_start_count=5, total_requests=0)
        assert window.cold_start_rate == 0.0

    def test_sla_violation_rate(self):
        """Should calculate SLA violation rate correctly."""
        window = MetricWindow(
            sla_violations=3,
            total_requests=100,
        )
        assert window.sla_violation_rate == 0.03


class TestRollingMetricsStore:
    """Test rolling metrics store functionality."""

    def test_initialization(self):
        """Should initialize with correct window size."""
        store = RollingMetricsStore(window_seconds=300)
        assert store.window_seconds == 300

    def test_record_and_retrieve(self):
        """Should record and retrieve metrics."""
        store = RollingMetricsStore(window_seconds=300)
        
        store.record(
            function_id="f01",
            latency_p50_ms=25.0,
            cold_start_count=2,
            total_requests=100,
        )
        
        recent = store.get_recent("f01")
        assert len(recent) == 1
        
        ts, metric = recent[0]
        assert metric.latency_p50_ms == 25.0
        assert metric.cold_start_count == 2
        assert metric.total_requests == 100

    def test_aggregation_single_observation(self):
        """Should aggregate single observation correctly."""
        store = RollingMetricsStore(window_seconds=300)
        
        store.record(
            function_id="f01",
            latency_p50_ms=50.0,
            latency_p95_ms=100.0,
            cold_start_count=5,
            total_requests=100,
        )
        
        aggregated = store.get_aggregated("f01")
        assert aggregated.latency_p50_ms == 50.0
        assert aggregated.latency_p95_ms == 100.0
        assert aggregated.cold_start_count == 5
        assert aggregated.total_requests == 100

    def test_aggregation_multiple_observations(self):
        """Should aggregate multiple observations correctly."""
        store = RollingMetricsStore(window_seconds=300)
        
        # Record 3 observations
        for i in range(3):
            store.record(
                function_id="f01",
                latency_p50_ms=50.0 + i * 10,  # 50, 60, 70
                cold_start_count=5 + i,        # 5, 6, 7
                total_requests=100,
            )
        
        aggregated = store.get_aggregated("f01")
        
        # Latencies are averaged: (50 + 60 + 70) / 3 = 60
        assert aggregated.latency_p50_ms == 60.0
        
        # Counts are summed: 5 + 6 + 7 = 18
        assert aggregated.cold_start_count == 18
        
        # Total requests: 100 + 100 + 100 = 300
        assert aggregated.total_requests == 300

    def test_window_expiration(self):
        """Should exclude observations outside window."""
        store = RollingMetricsStore(window_seconds=60)  # 1-minute window
        
        now = datetime.now(timezone.utc)
        
        # Record old observation (2 minutes ago)
        store.record(
            function_id="f01",
            latency_p50_ms=100.0,
            cold_start_count=10,
            total_requests=100,
            timestamp=now - timedelta(seconds=120)
        )
        
        # Record recent observation (30 seconds ago)
        store.record(
            function_id="f01",
            latency_p50_ms=50.0,
            cold_start_count=5,
            total_requests=100,
            timestamp=now - timedelta(seconds=30)
        )
        
        # Should only include recent observation
        recent = store.get_recent("f01")
        assert len(recent) == 1
        assert recent[0][1].latency_p50_ms == 50.0

    def test_get_all_aggregated(self):
        """Should return aggregated metrics for all functions."""
        store = RollingMetricsStore(window_seconds=300)
        
        store.record("f01", latency_p50_ms=50.0, total_requests=100)
        store.record("f02", latency_p50_ms=75.0, total_requests=150)
        
        all_metrics = store.get_all_aggregated()
        
        assert "f01" in all_metrics
        assert "f02" in all_metrics
        assert all_metrics["f01"].latency_p50_ms == 50.0
        assert all_metrics["f02"].latency_p50_ms == 75.0

    def test_trend_calculation(self):
        """Should calculate trend (increasing/decreasing)."""
        store = RollingMetricsStore(window_seconds=300)
        
        now = datetime.now(timezone.utc)
        
        # Record increasing latency trend
        for i in range(5):
            store.record(
                function_id="f01",
                latency_p50_ms=50.0 + i * 10,  # 50, 60, 70, 80, 90
                timestamp=now + timedelta(seconds=i * 10)
            )
        
        trend = store.get_trend("f01", "latency_p50_ms")
        
        # Trend should be positive (increasing)
        assert trend is not None
        assert trend > 0

    def test_clear_single_function(self):
        """Should clear metrics for a single function."""
        store = RollingMetricsStore(window_seconds=300)
        
        store.record("f01", latency_p50_ms=50.0)
        store.record("f02", latency_p50_ms=75.0)
        
        store.clear("f01")
        
        assert len(store.get_recent("f01")) == 0
        assert len(store.get_recent("f02")) == 1

    def test_clear_all(self):
        """Should clear all metrics."""
        store = RollingMetricsStore(window_seconds=300)
        
        store.record("f01", latency_p50_ms=50.0)
        store.record("f02", latency_p50_ms=75.0)
        
        store.clear()
        
        assert len(store.get_recent("f01")) == 0
        assert len(store.get_recent("f02")) == 0

    def test_window_summary(self):
        """Should provide summary statistics."""
        store = RollingMetricsStore(window_seconds=300)
        
        store.record(
            "f01",
            latency_p50_ms=50.0,
            cold_start_count=5,
            total_requests=100,
            sla_violations=2,
        )
        
        summary = store.get_window_summary()
        
        assert "f01" in summary
        assert summary["f01"]["observation_count"] == 1
        assert summary["f01"]["avg_latency_p50"] == 50.0
        assert summary["f01"]["cold_start_rate"] == 0.05
        assert summary["f01"]["sla_violation_rate"] == 0.02

    def test_empty_function_returns_zeros(self):
        """Should return zero metrics for unknown function."""
        store = RollingMetricsStore(window_seconds=300)
        
        aggregated = store.get_aggregated("unknown")
        
        assert aggregated.latency_p50_ms == 0.0
        assert aggregated.cold_start_count == 0
        assert aggregated.total_requests == 0
