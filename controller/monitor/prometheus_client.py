import logging
import math
import time
from datetime import datetime, timezone
from typing import Dict, Optional, List

import requests
from requests.adapters import HTTPAdapter

from controller.contracts import (
    FunctionTelemetry, TelemetrySnapshot, TelemetryError,
    validate_function_telemetry,
)

logger = logging.getLogger(__name__)


class PrometheusMonitor:
    """Production-safe Prometheus telemetry adapter.

    Key behaviors:
      - Mock fallback is OPT-IN (default: disabled).
      - probe() does a one-shot reachability check with a short timeout.
      - force_mock_only() disables all HTTP; every fetch returns mock data.
      - Missing required signals raise TelemetryError (unless mock mode).
      - Returns typed TelemetrySnapshot, not dicts.
    """

    # Documented PromQL schema — see docs/architecture/prometheus-schema.md
    # Placeholder `{svc}` is substituted via .replace(); PromQL braces are literal.
    QUERY_SCHEMA = {
        "R_i": 'sum(rate(revision_app_request_count{service_name="{svc}"}[1m]))',
        "cold_starts": (
            'sum(increase(revision_app_request_latencies_count'
            '{service_name="{svc}",response_code_class="2xx"}[60s]))'
        ),
        "M": (
            'sum(container_memory_working_set_bytes{container!=""}) '
            '/ sum(node_memory_MemTotal_bytes)'
        ),
    }

    # Short connect timeout so a down Prometheus does not block the loop.
    # (connect_sec, read_sec) tuple passed to requests.
    CONNECT_TIMEOUT_SEC = 0.5

    def __init__(
        self,
        prometheus_url: str = "http://localhost:9090",
        query_timeout_sec: float = 2.0,
        historical_max_rate: float = 50.0,
        enable_mock_fallback: bool = False,
        required_signals: Optional[List[str]] = None,
    ):
        self.prometheus_url = prometheus_url.rstrip("/")
        self.query_timeout_sec = query_timeout_sec
        self.historical_max_rate = historical_max_rate
        self.enable_mock_fallback = enable_mock_fallback
        self.required_signals = required_signals or ["R_i", "M"]
        self._prev_rates: Dict[str, float] = {}
        self._prev_timestamps: Dict[str, float] = {}
        self._mock_only = False  # set True by force_mock_only()

        # Reuse one session with a short connect timeout baked in.
        # max_retries=0 so a down Prometheus fails immediately, not 3x later.
        self._session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=8,
            pool_maxsize=16,
            max_retries=0,
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    # ------------------------------------------------------------------
    # Reachability + mock-only mode
    # ------------------------------------------------------------------
    def probe(self, timeout_sec: float = 0.5) -> bool:
        """One-shot reachability check. Returns True if Prometheus answers."""
        try:
            r = self._session.get(
                f"{self.prometheus_url}/-/ready",
                timeout=(self.CONNECT_TIMEOUT_SEC, timeout_sec),
            )
            return r.status_code == 200
        except Exception:
            return False

    def force_mock_only(self) -> None:
        """Disable all HTTP calls; every fetch returns mock values."""
        if not self.enable_mock_fallback:
            raise RuntimeError(
                "force_mock_only() called but enable_mock_fallback=False"
            )
        self._mock_only = True
        logger.warning(
            "PrometheusMonitor forced to MOCK-ONLY mode. "
            "No HTTP calls will be made."
        )

    @property
    def is_mock_only(self) -> bool:
        return self._mock_only

    # ------------------------------------------------------------------
    # PromQL
    # ------------------------------------------------------------------
    def _query_promql(self, query: str) -> Optional[float]:
        if self._mock_only:
            return None  # never called in mock-only mode, but be defensive
        status_code = "unavailable"
        try:
            resp = self._session.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=(self.CONNECT_TIMEOUT_SEC, self.query_timeout_sec),
            )
            status_code = resp.status_code
            if resp.status_code != 200:
                logger.warning(
                    "PromQL request failed: HTTP status=%s query=%r",
                    status_code, query,
                )
                return None
            payload = resp.json()
            if payload.get("status") != "success":
                logger.warning(
                    "PromQL returned status=%r: HTTP status=%s query=%r",
                    payload.get("status"), status_code, query,
                )
                return None
            results = payload.get("data", {}).get("result", [])
            if results:
                value = float(results[0]["value"][1])
                if math.isfinite(value):
                    return value
                logger.warning(
                    "PromQL returned a non-finite value %r: "
                    "HTTP status=%s query=%r",
                    value, status_code, query,
                )
                return None
            logger.warning(
                "PromQL returned an empty result: HTTP status=%s query=%r",
                status_code, query,
            )
        except Exception as e:
            logger.warning(
                "PromQL request failed: HTTP status=%s query=%r error=%s",
                status_code, query, e,
            )
        return None

    def _mock(self, key: str) -> float:
        return {"R_i": 5.0, "M": 0.45, "cold_starts": 0.1}[key]

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------
    def fetch_function(
        self, function_id: str, service_name: str,
    ) -> FunctionTelemetry:
        now_dt = datetime.now(timezone.utc)
        now = time.time()

        if self._mock_only:
            # Fast path — no HTTP at all
            raw = {
                "R_i": self._mock("R_i"),
                "M": self._mock("M"),
                "cold_starts": self._mock("cold_starts"),
            }
            mocked_signals = ["R_i", "M", "cold_starts"]
        else:
            raw = {}
            for signal in self.required_signals + ["cold_starts"]:
                query = self.QUERY_SCHEMA[signal].replace("{svc}", service_name)
                raw[signal] = self._query_promql(query)

            mocked_signals = []
            for signal in self.required_signals:
                if raw[signal] is None:
                    if self.enable_mock_fallback:
                        raw[signal] = self._mock(signal)
                        mocked_signals.append(signal)
                    else:
                        raise TelemetryError(
                            f"Required signal '{signal}' missing for "
                            f"{service_name} "
                            f"(query={self.QUERY_SCHEMA[signal]})"
                        )
            if raw.get("cold_starts") is None:
                raw["cold_starts"] = 0.0

        if mocked_signals:
            logger.warning(
                "Mock telemetry used for service=%s signals=%s",
                service_name, mocked_signals,
            )

        # Normalization
        r_i = min(max(raw["R_i"] / max(self.historical_max_rate, 1.0), 0.0), 1.0)
        m = min(max(raw.get("M") or 0.0, 0.0), 1.0)
        c_i = min(max(raw.get("cold_starts") or 0.0, 0.0), 1.0)

        # Trend
        prev_r = self._prev_rates.get(service_name, r_i)
        prev_t = self._prev_timestamps.get(service_name, now - 10.0)
        dt = max(now - prev_t, 1e-3)
        t_i = min(max((r_i - prev_r) / (dt / 10.0), -1.0), 1.0)

        self._prev_rates[service_name] = r_i
        self._prev_timestamps[service_name] = now

        if mocked_signals:
            source = "mock"
        else:
            source = "prometheus"

        ft = FunctionTelemetry(
            function_id=function_id,
            service_name=service_name,
            captured_at=now_dt,
            R_i=float(r_i), T_i=float(t_i), C_i=float(c_i), M=float(m),
            S_i=0.0, source=source,
        )
        validate_function_telemetry(ft, allow_stale=False)
        return ft

    def fetch_snapshot(
        self,
        functions: Dict[str, str],
        cycle_id: str,
    ) -> TelemetrySnapshot:
        """Fetch a consistent snapshot for all functions."""
        funcs: Dict[str, FunctionTelemetry] = {}
        for fid, svc in functions.items():
            funcs[fid] = self.fetch_function(fid, svc)
        return TelemetrySnapshot(
            cycle_id=cycle_id,
            captured_at=datetime.now(timezone.utc),
            functions=funcs,
        )

    # ------------------------------------------------------------------
    def validate_schema(self) -> None:
        """Startup check: verify Prometheus reachable and queries parse."""
        for signal, tmpl in self.QUERY_SCHEMA.items():
            q = tmpl.replace("{svc}", "__schema_check__")
            try:
                r = self._session.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": q},
                    timeout=(self.CONNECT_TIMEOUT_SEC, self.query_timeout_sec),
                )
                if r.status_code != 200:
                    raise TelemetryError(
                        f"Schema check failed for '{signal}': "
                        f"HTTP {r.status_code}"
                    )
            except requests.RequestException as e:
                raise TelemetryError(
                    f"Prometheus unreachable at {self.prometheus_url}: {e}"
                )
        logger.info("Prometheus schema validation passed.")

    # ------------------------------------------------------------------
    def get_function_metrics(self, service_name: str) -> Dict[str, float]:
        """Legacy dict interface (deprecated — use fetch_snapshot)."""
        ft = self.fetch_function(service_name, service_name)
        return {"R_i": ft.R_i, "T_i": ft.T_i, "C_i": ft.C_i, "M": ft.M}