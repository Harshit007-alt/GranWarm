"""
GranuWarm Controller — Algorithm 2: Dual-Timescale Closed-Loop Orchestrator.

Integrates:
  - Typed contracts (TelemetrySnapshot, AllocationRequest, AllocationDecision)
  - Production-safe Prometheus telemetry (no silent mock fallback in live modes)
  - Hard feasibility gate for BOTH fast (fuzzy) and slow (PSO) paths
  - Operating modes: simulation | replay | dry_run | shadow | live
  - Bounded-delta fast loop (hysteresis without extra machinery)
  - Auditable decision log (JSONL per day, includes telemetry provenance)

Author: GranuWarm Team
"""

import argparse
import asyncio
import json
import logging
import os
import pathlib
import signal
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from controller.contracts import (
    AllocationRequest,
    AllocationDecision,
    TelemetrySnapshot,
    TelemetryError,
    validate_snapshot,
)
from controller.contracts.allocation import _new_id
from controller.monitor.prometheus_client import PrometheusMonitor
from controller.fuzzy.fuzzy_engine import FuzzyEngine
from controller.granularity.tree import GranularityTree
from controller.pso.pso_optimizer import DiscreteConstrainedPSO
from controller.allocator.knative_scaler import KnativeScaler
from controller.allocator.state_store import DesiredStateStore
from controller.safety.feasibility import FeasibilityService
from controller.metrics import RollingMetricsStore, MetricWindow


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("GranuWarmController")


# ----------------------------------------------------------------------
# Operating modes
# ----------------------------------------------------------------------
class OperatingMode(str, Enum):
    """Target operating modes from the architecture README."""
    SIMULATION = "simulation"
    REPLAY = "replay"
    DRY_RUN = "dry_run"
    SHADOW = "shadow"
    LIVE = "live"


ACTUATING_MODES = {OperatingMode.LIVE}
MOCK_TELEMETRY_MODES = {
    OperatingMode.SIMULATION,
    OperatingMode.REPLAY,
}
SCHEMA_CHECK_MODES = {OperatingMode.SHADOW, OperatingMode.LIVE}

# Fast-loop knobs
FUZZY_CAPACITY_SCALE = 8.0     # maps fuzzy [0,1] -> ~[0,8] capacity
FAST_LOOP_MAX_DELTA = 1        # max change per node per fast cycle


# ----------------------------------------------------------------------
# Controller
# ----------------------------------------------------------------------
class GranuWarmController:
    """Dual-timescale closed-loop controller for GranuWarm."""

    def __init__(
        self,
        tree_config: str = "configs/dependencies.json",
        rules_config: str = "configs/fuzzy_rules.json",
        prometheus_url: str = "http://127.0.0.1:9090",
        memory_budget_mb: float = 4096.0,
        dt_fast_sec: float = 10.0,
        dt_slow_sec: float = 60.0,
        mode: OperatingMode = OperatingMode.DRY_RUN,
        audit_dir: str = "results/audit",
        stale_allow: bool = False,
        prometheus_namespace: str = "default",
        pso_swarm_size: int = 30,
        pso_max_iter: int = 50,
        skip_telemetry_validation: bool = False,
        policy: str = "B6",
    ):
        self.policy = policy.upper()
        self.dt_fast = float(dt_fast_sec)
        self.dt_slow = float(dt_slow_sec)
        self.memory_budget_mb = float(memory_budget_mb)
        self.mode = mode
        self.skip_telemetry_validation = skip_telemetry_validation
        self.stale_allow = stale_allow
        self.audit_dir = pathlib.Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        logger.info("=" * 72)
        logger.info(f"GranuWarm Controller starting in mode={self.mode.value} policy={self.policy}")
        logger.info(f"  budget={self.memory_budget_mb:.0f} MB  "
                    f"dt_fast={self.dt_fast:.1f}s  dt_slow={self.dt_slow:.1f}s")
        logger.info(f"  tree={tree_config}  rules={rules_config}")
        logger.info(
            f"  prometheus={prometheus_url} namespace={prometheus_namespace}"
        )
        logger.info(f"  audit_dir={self.audit_dir}")
        logger.info("=" * 72)

        # ---------------- Telemetry ----------------
        allow_mock = self.mode in MOCK_TELEMETRY_MODES
        self.monitor = PrometheusMonitor(
            prometheus_url=prometheus_url,
            namespace=prometheus_namespace,
            enable_mock_fallback=allow_mock,
        )

        if allow_mock:
            if self.monitor.probe():
                logger.info(f"  Prometheus probe: reachable at {prometheus_url}")
            else:
                logger.warning(
                    f"  Prometheus probe: UNREACHABLE at {prometheus_url} — "
                    f"switching to pure-mock mode (no HTTP)."
                )
                self.monitor.force_mock_only()

        # ---------------- Fuzzy ----------------
        self.fuzzy = FuzzyEngine(rules_config)

        # ---------------- Granularity DAG ----------------
        self.tree = GranularityTree(tree_config)
        self.K = self.tree.get_total_nodes()
        self.node_ids = list(self.tree.node_ids)
        self.node_memories = np.array(
            [self.tree.get_node_memory(nid) for nid in self.node_ids],
            dtype=float,
        )
        logger.info(
            f"  DAG: {len(self.tree.all_node_ids)} total nodes, "
            f"{self.K} allocatable (PSO dimension)"
        )

        self.svc_map: Dict[str, str] = {
            fid: f.get("service_name", f.get("name", fid))
            for fid, f in self.tree.functions.items()
        }

        # ---------------- PSO (DAG-aware) ----------------
        self.pso = DiscreteConstrainedPSO(
            dimension=self.K,
            swarm_size=pso_swarm_size,
            max_iter=pso_max_iter,
            memory_budget_mb=self.memory_budget_mb,
            node_memories=self.node_memories,
            node_ids=self.node_ids,
            parent_map=self.tree.parent_map,
        )
        logger.info(
            f"  PSO: {pso_swarm_size} particles, {pso_max_iter} iterations "
            f"({pso_swarm_size * pso_max_iter} total evaluations)"
        )

        # ---------------- Safety gate ----------------
        self.safety = FeasibilityService(
            tree=self.tree,
            budget_mb=self.memory_budget_mb,
            node_min_capacity={nid: 0 for nid in self.node_ids},
            node_max_capacity={nid: 10 for nid in self.node_ids},
        )

        # ---------------- Actuator ----------------
        dry_run = self.mode not in ACTUATING_MODES
        self.scaler = KnativeScaler(
            namespace=prometheus_namespace,
            dry_run=dry_run,
            max_retries=3,
            base_backoff_sec=1.0
        )
        logger.info(f"  actuator: KnativeScaler(dry_run={dry_run})")
        
        # ---------------- State store ----------------
        self.state_store = DesiredStateStore(
            state_file=str(self.audit_dir / "desired_state.json")
        )
        
        # ---------------- Metrics store ----------------
        self.metrics_store = RollingMetricsStore(
            window_seconds=300  # 5-minute rolling window
        )
        logger.info("  metrics: RollingMetricsStore(window=300s)")

        # ---------------- Startup schema check ----------------
        if self.skip_telemetry_validation:
            logger.info(
                "  schema check: skipped (--skip-telemetry-validation flag set)"
            )
        elif self.mode in SCHEMA_CHECK_MODES:
            try:
                self.monitor.validate_schema()
            except TelemetryError as e:
                logger.error(
                    f"Startup telemetry schema validation failed: {e}"
                )
                raise
        else:
            logger.info(
                f"  schema check: skipped (mode={self.mode.value} permits "
                f"offline operation)"
            )

        # ---------------- Runtime state ----------------
        self.current_alloc_vector = np.zeros(self.K, dtype=int)
        self.is_running = False
        
        # ---------------- Startup reconciliation ----------------
        if self.mode in ACTUATING_MODES:
            self._reconcile_startup()

    # ------------------------------------------------------------------
    # Metrics extraction
    # ------------------------------------------------------------------
    def _extract_and_record_metrics(self, snapshot: TelemetrySnapshot) -> None:
        """Extract metrics from telemetry and record to rolling store.
        
        Args:
            snapshot: TelemetrySnapshot with current function metrics
        """
        for fid, telemetry in snapshot.functions.items():
            # For now, derive metrics from telemetry signals
            # In a full implementation, these would come from detailed Prometheus queries
            
            # Estimate requests from rate
            requests = int(telemetry.R_i * 10)  # Rough estimate over 10s cycle
            
            # Estimate cold-starts from cold-start signal
            cold_starts = int(telemetry.C_i * requests)
            
            # Estimate latency from workload characteristics
            # This is a placeholder - real implementation would query actual latency metrics
            base_latency = 50.0  # Base latency in ms
            latency_p50 = base_latency * (1.0 + telemetry.C_i * 10)  # Higher if cold-starts
            
            self.metrics_store.record(
                function_id=fid,
                latency_p50_ms=latency_p50,
                latency_p95_ms=latency_p50 * 1.5,
                latency_p99_ms=latency_p50 * 2.0,
                cold_start_count=cold_starts,
                total_requests=requests,
                sla_violations=0,  # Would come from actual SLA threshold checks
            )
    
    def _build_observed_metrics_prior(self) -> Optional[Dict[str, float]]:
        """Build metrics dict from observed data for PSO.
        
        Returns:
            Dict with observed metrics, or None if insufficient data
        """
        all_metrics = self.metrics_store.get_all_aggregated()
        
        if not all_metrics:
            return None  # No observations yet, fall back to analytic
        
        # Aggregate across all functions
        total_latency = sum(m.latency_p50_ms for m in all_metrics.values())
        total_cold_starts = sum(m.cold_start_count for m in all_metrics.values())
        total_requests = sum(m.total_requests for m in all_metrics.values())
        total_sla_violations = sum(m.sla_violations for m in all_metrics.values())
        
        # Calculate average memory (would come from actual metrics in production)
        total_memory = sum(m.avg_memory_mb for m in all_metrics.values() if m.avg_memory_mb > 0)
        avg_memory = total_memory / len(all_metrics) if all_metrics else 1000.0
        
        return {
            "mode": "observed",
            "latency_total_ms": total_latency,
            "cold_start_total": float(total_cold_starts),
            "memory_used_mb": avg_memory * len(all_metrics),  # Rough estimate
            "sla_violations_total": float(total_sla_violations),
            "total_requests": float(total_requests),
        }

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------
    def _reconcile_startup(self) -> None:
        """Reconcile Kubernetes state to last desired state at startup.
        
        This method is called during __init__ when in an actuating mode.
        It loads the last saved desired state and attempts to converge
        the cluster to that state.
        """
        saved_state = self.state_store.load()
        if not saved_state:
            logger.info("No previous desired state to reconcile")
            return
        
        func_caps = saved_state.get("function_capacities", {})
        if not func_caps:
            logger.warning("Saved state has no function capacities, skip reconciliation")
            return
        
        # Convert function capacities to service targets
        svc_targets = {
            self.tree.functions[fid].get("service_name", fid): int(count)
            for fid, count in func_caps.items()
            if fid in self.tree.functions
        }
        
        if not svc_targets:
            logger.warning("No valid services to reconcile")
            return
        
        logger.info(f"Reconciling {len(svc_targets)} services to last desired state")
        summary = self.scaler.reconcile(svc_targets)
        
        if summary.failed > 0:
            logger.warning(
                f"Reconciliation completed with {summary.failed} failures"
            )
        else:
            logger.info(
                f"Reconciliation successful: {summary.successful} services converged"
            )

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def _audit(
        self,
        decision: AllocationDecision,
        telemetry_source: str = "unknown",
        extra: dict = None,
    ) -> None:
        """Append a validated or rejected decision to the daily audit log."""
        date = decision.created_at.strftime("%Y-%m-%d")
        path = self.audit_dir / f"{date}.jsonl"
        record = decision.to_audit_dict()
        record["telemetry_source"] = telemetry_source
        record["mode"] = self.mode.value
        if extra:
            record.update(extra)
        try:
            with open(path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write audit record: {e}")

    def _audit_telemetry_error(self, cycle_id: str, error: TelemetryError) -> None:
        """Record skipped cycles that could not obtain valid telemetry."""
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.audit_dir / f"{date}.jsonl"
        record = {
            "event": "telemetry_error",
            "cycle_id": cycle_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode.value,
            "telemetry_source": "unavailable",
            "error": str(error),
        }
        try:
            with open(path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write telemetry error audit record: {e}")

    # ------------------------------------------------------------------
    # Fast-loop helpers
    # ------------------------------------------------------------------
    def _build_fuzzy_prior(
        self, snapshot: TelemetrySnapshot,
    ) -> np.ndarray:
        """Run fuzzy inference per function, then project to DAG nodes."""
        func_recommendations: Dict[str, float] = {}
        for fid, t in snapshot.functions.items():
            p_fuzzy = self.fuzzy.evaluate(
                R=t.R_i, T=t.T_i, C=t.C_i, M=t.M,
            )
            func_recommendations[fid] = p_fuzzy

        projected = self.tree.project_capacities(func_recommendations)
        prior = np.array(
            [projected.get(nid, 0.0) * FUZZY_CAPACITY_SCALE
             for nid in self.node_ids],
            dtype=float,
        )
        return prior

    def _vector_to_caps(self, vector: np.ndarray) -> Dict[str, int]:
        return {nid: int(vector[i]) for i, nid in enumerate(self.node_ids)}

    def _bounded_delta(
        self, target: np.ndarray, max_delta: int = FAST_LOOP_MAX_DELTA,
    ) -> np.ndarray:
        """Move current_alloc_vector at most ±max_delta toward target per cycle.

        Provides natural hysteresis without a dedicated state machine.
        """
        delta = target.astype(int) - self.current_alloc_vector
        delta = np.clip(delta, -max_delta, +max_delta)
        new_alloc = np.clip(self.current_alloc_vector + delta, 0, 10)
        return new_alloc

    @staticmethod
    def _infer_telemetry_source(snapshot: TelemetrySnapshot) -> str:
        if not snapshot.functions:
            return "unknown"
        sources = {t.source for t in snapshot.functions.values()}
        if "prometheus" in sources:
            return "prometheus"
        if "mock" in sources:
            return "mock"
        if "replay" in sources:
            return "replay"
        if "simulator" in sources:
            return "simulator"
        return "unknown"

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    async def run_loop(self, max_cycles: int = 0):
        self.is_running = True
        t_last_pso = 0.0
        cycle_count = 0

        logger.info("Control loop online. Press Ctrl-C to stop.")
        while self.is_running:
            t_start = time.time()
            cycle_count += 1
            cycle_id = _new_id("cyc")

            try:
                # ------------------------------------------------------
                # 1. OBSERVE
                # ------------------------------------------------------
                try:
                    snapshot: TelemetrySnapshot = self.monitor.fetch_snapshot(
                        functions=self.svc_map,
                        cycle_id=cycle_id,
                    )
                    validate_snapshot(snapshot, allow_stale=self.stale_allow)
                    
                    # Record metrics to rolling store
                    self._extract_and_record_metrics(snapshot)
                    
                except TelemetryError as e:
                    logger.error(
                        f"[{cycle_id}] Telemetry error: {e}. Skipping cycle."
                    )
                    self._audit_telemetry_error(cycle_id, e)
                    await self._sleep_remaining(t_start)
                    if max_cycles > 0 and cycle_count >= max_cycles:
                        break
                    continue

                telemetry_source = self._infer_telemetry_source(snapshot)

                # ------------------------------------------------------
                # 2. REACT
                # ------------------------------------------------------
                fuzzy_prior = self._build_fuzzy_prior(snapshot)

                # ------------------------------------------------------
                # 3. OPTIMIZE — slow (PSO) or fast (bounded delta)
                # ------------------------------------------------------
                now = time.time()
                delta_info: dict = {}
                if (now - t_last_pso) >= self.dt_slow or t_last_pso == 0.0:
                    logger.info(f"[{cycle_id}] Slow loop: constrained PSO ...")
                    
                    # Try to use observed metrics, fall back to analytic
                    observed_metrics = self._build_observed_metrics_prior()
                    if observed_metrics:
                        logger.debug(
                            f"Using observed metrics: "
                            f"{observed_metrics['total_requests']:.0f} reqs, "
                            f"{observed_metrics['cold_start_total']:.0f} cold-starts"
                        )
                    
                    best_x = self.pso.optimize(
                        fuzzy_prior=fuzzy_prior,
                        current_allocation=self.current_alloc_vector,
                        metrics=observed_metrics,
                    )
                    raw_req = AllocationRequest(
                        node_capacities=self._vector_to_caps(best_x),
                        source="pso",
                        cycle_id=cycle_id,
                        requested_budget_mb=self.memory_budget_mb,
                    )
                    t_last_pso = now
                    delta_info["fuzzy_prior"] = fuzzy_prior.tolist()
                else:
                    # Bounded-delta fast loop — hysteresis for free
                    target = np.round(fuzzy_prior).astype(int)
                    new_alloc = self._bounded_delta(target)
                    raw_req = AllocationRequest(
                        node_capacities=self._vector_to_caps(new_alloc),
                        source="fuzzy+delta",
                        cycle_id=cycle_id,
                        requested_budget_mb=self.memory_budget_mb,
                    )
                    delta_info["fuzzy_prior"] = fuzzy_prior.tolist()
                    delta_info["fuzzy_target"] = target.tolist()
                    delta_info["delta_from_previous"] = (
                        new_alloc - self.current_alloc_vector
                    ).tolist()

                # ------------------------------------------------------
                # 4. VALIDATE
                # ------------------------------------------------------
                decision: AllocationDecision = self.safety.process(raw_req)

                if not decision.within_budget:
                    logger.error(
                        f"[{decision.decision_id}] REJECTED: "
                        f"{decision.rejected_reason}"
                    )
                    self._audit(decision, telemetry_source, extra=delta_info)
                    await self._sleep_remaining(t_start)
                    continue

                if decision.repair_notes:
                    logger.warning(
                        f"[{decision.decision_id}] Repaired: "
                        f"{len(decision.repair_notes)} change(s); "
                        f"first={decision.repair_notes[0]}"
                    )

                logger.info(
                    f"[{decision.decision_id}] source={decision.source} "
                    f"telemetry={telemetry_source} "
                    f"mem={decision.estimated_memory_mb:.0f}/"
                    f"{self.memory_budget_mb:.0f} MB  "
                    f"nodes_allocated="
                    f"{sum(1 for v in decision.node_capacities.values() if v > 0)}"
                )

                # ------------------------------------------------------
                # 5. AUDIT + ACTUATE
                # ------------------------------------------------------
                self._audit(decision, telemetry_source, extra=delta_info)

                self.current_alloc_vector = np.array(
                    [decision.node_capacities.get(nid, 0)
                     for nid in self.node_ids],
                    dtype=int,
                )

                if self.mode in ACTUATING_MODES:
                    svc_targets = {
                        self.tree.functions[fid].get("service_name", fid): int(count)
                        for fid, count in decision.function_capacities.items()
                    }
                    summary = self.scaler.apply_allocation(svc_targets)
                    
                    # Log per-service results
                    for svc, result in summary.results.items():
                        if result.success and not result.skipped:
                            logger.info(
                                f"  ✓ {svc}: {result.current} → {result.requested}"
                            )
                        elif result.skipped:
                            logger.debug(
                                f"  ⊙ {svc}: {result.message}"
                            )
                        else:
                            logger.error(
                                f"  ✗ {svc}: {result.message} (error: {result.error})"
                            )
                    
                    # Save successful decisions as desired state
                    if summary.failed == 0:
                        self.state_store.save(decision)
                    else:
                        logger.warning(
                            f"Not saving desired state due to {summary.failed} "
                            f"actuation failures"
                        )
                        
                elif self.mode == OperatingMode.DRY_RUN:
                    logger.info(
                        f"[{decision.decision_id}] DRY-RUN — no Kubernetes "
                        f"writes (would patch "
                        f"{len(decision.function_capacities)} services)."
                    )
                elif self.mode == OperatingMode.SHADOW:
                    logger.info(
                        f"[{decision.decision_id}] SHADOW — decision logged, "
                        f"no actuation."
                    )

            except Exception as e:
                logger.exception(f"[{cycle_id}] Unexpected error: {e}")

            if max_cycles > 0 and cycle_count >= max_cycles:
                logger.info(f"Reached target {max_cycles} cycles. Stopping.")
                break

            await self._sleep_remaining(t_start)

        logger.info("Control loop exited.")

    async def _sleep_remaining(self, t_start: float) -> None:
        elapsed = time.time() - t_start
        sleep_time = max(self.dt_fast - elapsed, 0.1)
        await asyncio.sleep(sleep_time)

    def stop(self):
        self.is_running = False
        logger.info("GranuWarm Controller stop requested.")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GranuWarm Dual-Timescale Controller",
    )
    parser.add_argument(
        "--profile",
        choices=["default", "light", "minimal"],
        default=None,
        help=(
            "Resource profile: default (4GB+ cluster), light (laptop 4GB), "
            "minimal (2GB). Overrides individual parameters."
        )
    )
    parser.add_argument("--config", type=str, default="configs/dependencies.json")
    parser.add_argument("--rules", type=str, default="configs/fuzzy_rules.json")
    parser.add_argument(
        "--prometheus-config", type=str, default="configs/prometheus.json",
    )
    parser.add_argument("--prometheus-url", type=str)
    parser.add_argument("--prometheus-namespace", type=str)
    parser.add_argument("--budget", type=float, default=None)
    parser.add_argument("--dt-fast", type=float, default=None)
    parser.add_argument("--dt-slow", type=float, default=None)
    parser.add_argument(
        "--mode",
        choices=[m.value for m in OperatingMode],
        default=OperatingMode.DRY_RUN.value,
        help=(
            "simulation | replay | dry_run | shadow | live. "
            "Only 'live' performs Kubernetes writes."
        ),
    )
    parser.add_argument("--cycles", type=int, default=0)
    parser.add_argument("--audit-dir", type=str, default="results/audit")
    parser.add_argument("--allow-stale", action="store_true")
    parser.add_argument(
        "--pso-swarm-size", type=int, default=None,
        help="PSO swarm size (default: 30, light: 15, minimal: 10)"
    )
    parser.add_argument(
        "--pso-max-iter", type=int, default=None,
        help="PSO max iterations (default: 50, light: 30, minimal: 20)"
    )
    parser.add_argument(
        "--skip-telemetry-validation", action="store_true",
        help="Skip Prometheus schema validation (useful for offline testing)"
    )
    parser.add_argument(
        "--baseline", type=str, default="B6",
        choices=["B1", "B2", "B3", "B4", "B5", "B6"],
        help="Baseline policy: B1=no_prewarm, B2=fixed_prewarm, B3=fuzzy_only, B4=pso_only, B5=fuzzy_pso_no_granularity, B6=granuwarm_full (default: B6)"
    )
    return parser


def main():
    args = build_arg_parser().parse_args()
    mode = OperatingMode(args.mode)
    
    # Apply profile defaults
    profile_configs = {
        "default": {
            "config": "configs/dependencies.json",
            "budget": 4096.0,
            "dt_fast": 10.0,
            "dt_slow": 60.0,
            "pso_swarm_size": 30,
            "pso_max_iter": 50,
        },
        "light": {
            "config": "configs/dependencies_light.json",
            "budget": 1500.0,
            "dt_fast": 15.0,
            "dt_slow": 90.0,
            "pso_swarm_size": 15,
            "pso_max_iter": 30,
        },
        "minimal": {
            "config": "configs/dependencies_light.json",
            "budget": 1000.0,
            "dt_fast": 30.0,
            "dt_slow": 120.0,
            "pso_swarm_size": 10,
            "pso_max_iter": 20,
        },
    }
    
    # Select profile
    if args.profile:
        profile = profile_configs[args.profile]
        logger.info(f"Using '{args.profile}' profile")
    else:
        profile = profile_configs["default"]
    
    # Override with explicit args
    config = args.config if args.config != "configs/dependencies.json" else profile["config"]
    budget = args.budget if args.budget is not None else profile["budget"]
    dt_fast = args.dt_fast if args.dt_fast is not None else profile["dt_fast"]
    dt_slow = args.dt_slow if args.dt_slow is not None else profile["dt_slow"]
    pso_swarm_size = args.pso_swarm_size if args.pso_swarm_size is not None else profile["pso_swarm_size"]
    pso_max_iter = args.pso_max_iter if args.pso_max_iter is not None else profile["pso_max_iter"]
    
    with open(args.prometheus_config, encoding="utf-8") as config_file:
        prometheus_config = json.load(config_file)
    if not isinstance(prometheus_config, dict):
        raise ValueError("Prometheus config must be a JSON object")
    prometheus_url = args.prometheus_url or prometheus_config["url"]
    prometheus_namespace = (
        args.prometheus_namespace or prometheus_config["namespace"]
    )

    controller = GranuWarmController(
        tree_config=config,
        rules_config=args.rules,
        prometheus_url=prometheus_url,
        prometheus_namespace=prometheus_namespace,
        memory_budget_mb=budget,
        dt_fast_sec=dt_fast,
        dt_slow_sec=dt_slow,
        mode=mode,
        audit_dir=args.audit_dir,
        stale_allow=args.allow_stale,
        pso_swarm_size=pso_swarm_size,
        pso_max_iter=pso_max_iter,
        skip_telemetry_validation=args.skip_telemetry_validation,
        policy=args.baseline,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(signum, frame):
        logger.info(f"Signal {signum} received.")
        controller.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(controller.run_loop(max_cycles=args.cycles))
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        loop.close()
        logger.info("Controller shut down cleanly.")


if __name__ == "__main__":
    main()