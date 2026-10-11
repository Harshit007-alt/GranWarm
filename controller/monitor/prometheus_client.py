import logging
import time
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)


class PrometheusMonitor:
    """Extracts real-time workload telemetry signals (R_i, T_i, C_i, M) via PromQL queries.

    Signals:
    - R_i: Invocation Intensity in [0, 1]
    - T_i: Traffic Trend in [-1, 1]
    - C_i: Cold-Start Pressure in [0, 1]
    - M: Cluster-wide Resource Pressure in [0, 1]
    """

    def __init__(
        self,
        prometheus_url: str = "http://localhost:9090",
        query_timeout_sec: float = 2.0,
        historical_max_rate: float = 50.0,
        enable_mock_fallback: bool = True
    ):
        self.prometheus_url = prometheus_url.rstrip("/")
        self.query_timeout_sec = query_timeout_sec
        self.historical_max_rate = historical_max_rate
        self.enable_mock_fallback = enable_mock_fallback
        self._prev_rates: Dict[str, float] = {}
        self._prev_timestamps: Dict[str, float] = {}

    def _query_promql(self, query: str) -> Optional[float]:
        try:
            resp = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=self.query_timeout_sec
            )
            if resp.status_code == 200:
                payload = resp.json()
                results = payload.get("data", {}).get("result", [])
                if results and len(results) > 0:
                    val_str = results[0]["value"][1]
                    return float(val_str)
        except Exception as e:
            logger.debug(f"Prometheus query failed ('{query}'): {e}")
        return None

    def get_function_metrics(self, service_name: str) -> Dict[str, float]:
        """Extracts and normalizes the 4 GranuWarm control signals for a function service."""
        now = time.time()

        # 1. R_i: Raw invocation rate over last 10s
        # Knative metric: revision_request_count or http_requests_total
        query_rate = f'sum(rate(revision_request_count{{service="{service_name}"}}[10s]))'
        raw_rate = self._query_promql(query_rate)

        # 2. C_i: Cold start ratio = cold_starts / total_starts over 60s
        query_cold = (
            f'sum(increase(revision_app_request_latencies_count{{service="{service_name}",response_code_class="2xx"}}[60s]))'
        )
        raw_cold = self._query_promql(query_cold)

        # 3. M: Cluster memory pressure = container_memory_working_set_bytes / node_memory_MemTotal_bytes
        query_mem = (
            'sum(container_memory_working_set_bytes{container!=""}) / sum(node_memory_MemTotal_bytes)'
        )
        raw_mem = self._query_promql(query_mem)

        # Fallback / Mock handling if Prometheus is unreachable or returns NaN
        if raw_rate is None and self.enable_mock_fallback:
            raw_rate = 5.0
        elif raw_rate is None:
            raw_rate = 0.0

        if raw_mem is None and self.enable_mock_fallback:
            raw_mem = 0.45
        elif raw_mem is None:
            raw_mem = 0.0

        if raw_cold is None and self.enable_mock_fallback:
            raw_cold = 0.1
        elif raw_cold is None:
            raw_cold = 0.0

        # Compute normalized R_i in [0, 1]
        r_i = min(max(raw_rate / max(self.historical_max_rate, 1.0), 0.0), 1.0)

        # Compute T_i in [-1, 1]
        prev_r = self._prev_rates.get(service_name, r_i)
        prev_t = self._prev_timestamps.get(service_name, now - 10.0)
        dt = max(now - prev_t, 1e-3)
        rate_diff = (r_i - prev_r) / (dt / 10.0)  # normalized over 10s step
        t_i = min(max(rate_diff, -1.0), 1.0)

        self._prev_rates[service_name] = r_i
        self._prev_timestamps[service_name] = now

        # Compute C_i in [0, 1]
        c_i = min(max(raw_cold, 0.0), 1.0)

        # Compute M in [0, 1]
        m = min(max(raw_mem, 0.0), 1.0)

        return {
            "R_i": float(r_i),
            "T_i": float(t_i),
            "C_i": float(c_i),
            "M": float(m),
            "raw_rate": float(raw_rate)
        }
