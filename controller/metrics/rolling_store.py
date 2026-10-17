"""Rolling metrics window for observed latency, cold-starts, and SLA violations.

This module maintains a sliding time window of observed metrics per function,
enabling the PSO optimizer to make decisions based on real measured behavior
rather than analytic surrogates.
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Deque, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MetricWindow:
    """Observed metrics for a function within a time window.
    
    Attributes:
        latency_p50_ms: Median latency in milliseconds
        latency_p95_ms: 95th percentile latency in milliseconds
        latency_p99_ms: 99th percentile latency in milliseconds
        cold_start_count: Number of cold starts observed
        warm_start_count: Number of warm starts observed
        total_requests: Total number of requests
        sla_violations: Number of requests exceeding SLA threshold
        avg_memory_mb: Average memory usage in MB
    """
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    cold_start_count: int = 0
    warm_start_count: int = 0
    total_requests: int = 0
    sla_violations: int = 0
    avg_memory_mb: float = 0.0

    @property
    def cold_start_rate(self) -> float:
        """Calculate cold-start rate as fraction of total requests."""
        if self.total_requests == 0:
            return 0.0
        return self.cold_start_count / self.total_requests

    @property
    def sla_violation_rate(self) -> float:
        """Calculate SLA violation rate as fraction of total requests."""
        if self.total_requests == 0:
            return 0.0
        return self.sla_violations / self.total_requests


class RollingMetricsStore:
    """Maintains a sliding window of observed function metrics.
    
    This store keeps recent observations for each function in a time-based
    sliding window. Metrics can be recorded per control cycle and aggregated
    over the window for use in optimization.
    
    The store is used to:
    1. Replace analytic surrogates in PSO objective with real observations
    2. Detect trends (increasing latency, cold-start spikes)
    3. Validate that control decisions improve observed behavior
    
    Usage:
        store = RollingMetricsStore(window_seconds=300)  # 5-minute window
        
        # Record observations each cycle
        store.record("f01", latency_p50_ms=25.0, cold_start_count=2, ...)
        
        # Get aggregated metrics for optimization
        window = store.get_aggregated("f01")
        print(f"Avg latency: {window.latency_p50_ms:.1f}ms")
        print(f"Cold-start rate: {window.cold_start_rate:.2%}")
    """

    def __init__(self, window_seconds: int = 300):
        """Initialize rolling metrics store.
        
        Args:
            window_seconds: Size of sliding window in seconds (default: 300 = 5 minutes)
        """
        self.window_seconds = window_seconds
        self.window_delta = timedelta(seconds=window_seconds)
        
        # Per-function deques of (timestamp, MetricWindow) tuples
        # Using deque with maxlen ensures automatic eviction of old entries
        self._windows: Dict[str, Deque[Tuple[datetime, MetricWindow]]] = defaultdict(
            lambda: deque(maxlen=100)  # Max 100 observations per function
        )
        
        logger.info(
            f"RollingMetricsStore initialized with {window_seconds}s window"
        )

    def record(
        self,
        function_id: str,
        latency_p50_ms: float = 0.0,
        latency_p95_ms: float = 0.0,
        latency_p99_ms: float = 0.0,
        cold_start_count: int = 0,
        warm_start_count: int = 0,
        total_requests: int = 0,
        sla_violations: int = 0,
        avg_memory_mb: float = 0.0,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record observed metrics for a function at a point in time.
        
        Args:
            function_id: Function identifier (e.g., "f01", "f02")
            latency_p50_ms: Median latency in milliseconds
            latency_p95_ms: 95th percentile latency
            latency_p99_ms: 99th percentile latency
            cold_start_count: Number of cold starts observed
            warm_start_count: Number of warm starts observed
            total_requests: Total requests in this observation period
            sla_violations: Number of requests exceeding SLA
            avg_memory_mb: Average memory usage
            timestamp: Observation timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        metric = MetricWindow(
            latency_p50_ms=latency_p50_ms,
            latency_p95_ms=latency_p95_ms,
            latency_p99_ms=latency_p99_ms,
            cold_start_count=cold_start_count,
            warm_start_count=warm_start_count,
            total_requests=total_requests,
            sla_violations=sla_violations,
            avg_memory_mb=avg_memory_mb,
        )
        
        self._windows[function_id].append((timestamp, metric))
        
        logger.debug(
            f"Recorded metrics for {function_id}: "
            f"p50={latency_p50_ms:.1f}ms, cold_starts={cold_start_count}, "
            f"reqs={total_requests}"
        )

    def get_recent(
        self, function_id: str, max_age_seconds: Optional[int] = None
    ) -> List[Tuple[datetime, MetricWindow]]:
        """Get recent observations within the window.
        
        Args:
            function_id: Function identifier
            max_age_seconds: Max age in seconds (default: window_seconds)
            
        Returns:
            List of (timestamp, MetricWindow) tuples within the window
        """
        if max_age_seconds is None:
            max_age_seconds = self.window_seconds
        
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=max_age_seconds)
        
        window = self._windows.get(function_id, deque())
        recent = [(ts, m) for ts, m in window if ts >= cutoff]
        
        return recent

    def get_aggregated(self, function_id: str) -> MetricWindow:
        """Get aggregated metrics over the rolling window.
        
        Aggregation strategy:
        - Latencies: Mean of all observations
        - Counts: Sum of all observations
        - Memory: Mean of all observations
        
        Args:
            function_id: Function identifier
            
        Returns:
            MetricWindow with aggregated values, or zeros if no data
        """
        recent = self.get_recent(function_id)
        
        if not recent:
            return MetricWindow()  # Return zeros if no data
        
        # Extract metrics from recent observations
        metrics = [m for _, m in recent]
        
        # Aggregate latencies (mean)
        total_latency_p50 = sum(m.latency_p50_ms for m in metrics)
        total_latency_p95 = sum(m.latency_p95_ms for m in metrics)
        total_latency_p99 = sum(m.latency_p99_ms for m in metrics)
        
        # Aggregate counts (sum)
        total_cold_starts = sum(m.cold_start_count for m in metrics)
        total_warm_starts = sum(m.warm_start_count for m in metrics)
        total_reqs = sum(m.total_requests for m in metrics)
        total_sla_viol = sum(m.sla_violations for m in metrics)
        
        # Aggregate memory (mean)
        total_memory = sum(m.avg_memory_mb for m in metrics)
        
        n = len(metrics)
        return MetricWindow(
            latency_p50_ms=total_latency_p50 / n,
            latency_p95_ms=total_latency_p95 / n,
            latency_p99_ms=total_latency_p99 / n,
            cold_start_count=total_cold_starts,
            warm_start_count=total_warm_starts,
            total_requests=total_reqs,
            sla_violations=total_sla_viol,
            avg_memory_mb=total_memory / n,
        )

    def get_all_aggregated(self) -> Dict[str, MetricWindow]:
        """Get aggregated metrics for all functions.
        
        Returns:
            Dict mapping function_id to aggregated MetricWindow
        """
        return {
            fid: self.get_aggregated(fid)
            for fid in self._windows.keys()
        }

    def get_trend(
        self, function_id: str, metric_name: str = "latency_p50_ms"
    ) -> Optional[float]:
        """Calculate trend (slope) for a metric over the window.
        
        Uses simple linear regression to detect increasing/decreasing trends.
        
        Args:
            function_id: Function identifier
            metric_name: Name of metric field (e.g., "latency_p50_ms")
            
        Returns:
            Slope (change per second), or None if insufficient data
        """
        recent = self.get_recent(function_id)
        
        if len(recent) < 2:
            return None  # Need at least 2 points for trend
        
        # Extract times (seconds since first observation) and values
        first_ts = recent[0][0]
        times = [
            (ts - first_ts).total_seconds()
            for ts, _ in recent
        ]
        values = [
            getattr(m, metric_name)
            for _, m in recent
        ]
        
        # Simple linear regression: slope = covariance(x,y) / variance(x)
        n = len(times)
        mean_time = sum(times) / n
        mean_value = sum(values) / n
        
        covariance = sum(
            (t - mean_time) * (v - mean_value)
            for t, v in zip(times, values)
        )
        variance = sum((t - mean_time) ** 2 for t in times)
        
        if variance == 0:
            return 0.0  # All observations at same time
        
        slope = covariance / variance
        return slope

    def clear(self, function_id: Optional[str] = None) -> None:
        """Clear metrics for a function or all functions.
        
        Args:
            function_id: Function to clear, or None to clear all
        """
        if function_id is None:
            self._windows.clear()
            logger.info("Cleared all metrics")
        elif function_id in self._windows:
            del self._windows[function_id]
            logger.info(f"Cleared metrics for {function_id}")

    def get_window_summary(self) -> Dict[str, dict]:
        """Get summary statistics for all functions.
        
        Returns:
            Dict mapping function_id to summary dict with:
            - observation_count: Number of observations in window
            - window_age_seconds: Age of oldest observation
            - avg_latency_p50: Average p50 latency
            - cold_start_rate: Cold-start rate
            - sla_violation_rate: SLA violation rate
        """
        summary = {}
        now = datetime.now(timezone.utc)
        
        for fid in self._windows.keys():
            recent = self.get_recent(fid)
            aggregated = self.get_aggregated(fid)
            
            if recent:
                oldest_age = (now - recent[0][0]).total_seconds()
            else:
                oldest_age = 0.0
            
            summary[fid] = {
                "observation_count": len(recent),
                "window_age_seconds": oldest_age,
                "avg_latency_p50": aggregated.latency_p50_ms,
                "cold_start_rate": aggregated.cold_start_rate,
                "sla_violation_rate": aggregated.sla_violation_rate,
            }
        
        return summary
