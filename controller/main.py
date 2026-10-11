import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from controller.monitor.prometheus_client import PrometheusMonitor
from controller.fuzzy.fuzzy_engine import FuzzyEngine
from controller.granularity.tree import GranularityTree
from controller.pso.pso_optimizer import DiscreteConstrainedPSO
from controller.allocator.knative_scaler import KnativeScaler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("GranuWarmController")


class GranuWarmController:
    """Algorithm 2: Dual-Timescale Closed-Loop Controller Orchestrator."""

    def __init__(
        self,
        tree_config: str = "configs/dependencies.json",
        rules_config: str = "configs/fuzzy_rules.json",
        prometheus_url: str = "http://localhost:9090",
        memory_budget_mb: float = 4096.0,
        dt_fast_sec: float = 10.0,
        dt_slow_sec: float = 60.0,
        dry_run: bool = False
    ):
        self.dt_fast = dt_fast_sec
        self.dt_slow = dt_slow_sec
        self.memory_budget_mb = memory_budget_mb
        self.dry_run = dry_run

        logger.info("Initializing GranuWarm Core Intelligence Modules...")
        self.monitor = PrometheusMonitor(prometheus_url=prometheus_url)
        self.fuzzy = FuzzyEngine(rules_config)
        self.tree = GranularityTree(tree_config)

        self.K = self.tree.get_total_nodes()
        self.node_ids = self.tree.node_ids
        self.node_memories = np.array([self.tree.get_node_memory(nid) for nid in self.node_ids])

        self.pso = DiscreteConstrainedPSO(
            dimension=self.K,
            swarm_size=30,
            max_iter=50,
            memory_budget_mb=self.memory_budget_mb,
            node_memories=self.node_memories
        )

        self.scaler = KnativeScaler(dry_run=dry_run)
        self.current_alloc_vector = np.zeros(self.K, dtype=int)
        self.is_running = False

    async def run_loop(self, max_cycles: int = 0):
        """Executes the dual-timescale control loop."""
        self.is_running = True
        t_last_pso = 0.0
        cycle_count = 0

        logger.info(f"GranuWarm Controller online. Fast loop: {self.dt_fast}s, Slow loop: {self.dt_slow}s.")

        while self.is_running:
            t_start = time.time()
            cycle_count += 1

            # ---------------------------------------------------------
            # 1. FAST LOOP (every 10s): Signal Collection & Fuzzy FIS
            # ---------------------------------------------------------
            func_recommendations: Dict[str, float] = {}
            for fid, func_data in self.tree.functions.items():
                svc_name = func_data.get("service_name", func_data["name"])
                telemetry = self.monitor.get_function_metrics(svc_name)
                p_fuzzy = self.fuzzy.evaluate(
                    R=telemetry["R_i"],
                    T=telemetry["T_i"],
                    C=telemetry["C_i"],
                    M=telemetry["M"]
                )
                func_recommendations[fid] = p_fuzzy

            # Granularity Tree Max-Projection
            projected_tree_p = self.tree.project_capacities(func_recommendations)
            fuzzy_prior_vector = np.array([projected_tree_p.get(nid, 0.0) * 8.0 for nid in self.node_ids])

            # ---------------------------------------------------------
            # 2. SLOW LOOP (every 60s): Constrained PSO Optimization
            # ---------------------------------------------------------
            now = time.time()
            if (now - t_last_pso) >= self.dt_slow:
                logger.info("Executing slow global re-optimization loop (Constrained PSO)...")
                best_x = self.pso.optimize(
                    fuzzy_prior=fuzzy_prior_vector,
                    current_allocation=self.current_alloc_vector
                )
                self.current_alloc_vector = np.copy(best_x)
                t_last_pso = now
            else:
                # Approximate fast-loop budget scaling
                raw_scaled = np.round(fuzzy_prior_vector).astype(int)
                used_mem = np.dot(raw_scaled, self.node_memories)
                if used_mem > self.memory_budget_mb:
                    ratio = self.memory_budget_mb / max(used_mem, 1.0)
                    self.current_alloc_vector = np.round(raw_scaled * ratio).astype(int)
                else:
                    self.current_alloc_vector = raw_scaled

            # ---------------------------------------------------------
            # 3. Knative Actuation with Hysteresis
            # ---------------------------------------------------------
            tree_alloc_map = {nid: int(self.current_alloc_vector[i]) for i, nid in enumerate(self.node_ids)}
            func_alloc_map = self.tree.map_tree_allocation_to_functions(tree_alloc_map)

            svc_targets: Dict[str, int] = {}
            for fid, count in func_alloc_map.items():
                svc = self.tree.functions[fid].get("service_name", fid)
                svc_targets[svc] = count

            self.scaler.apply_allocation(svc_targets)

            if max_cycles > 0 and cycle_count >= max_cycles:
                logger.info(f"Reached target {max_cycles} cycles. Stopping.")
                break

            elapsed = time.time() - t_start
            sleep_time = max(self.dt_fast - elapsed, 0.1)
            await asyncio.sleep(sleep_time)

    def stop(self):
        self.is_running = False
        logger.info("GranuWarm Controller stop requested.")


def main():
    parser = argparse.ArgumentParser(description="GranuWarm Dual-Timescale Controller")
    parser.add_argument("--config", type=str, default="configs/dependencies.json")
    parser.add_argument("--rules", type=str, default="configs/fuzzy_rules.json")
    parser.add_argument("--prometheus-url", type=str, default="http://localhost:9090")
    parser.add_argument("--budget", type=float, default=4096.0, help="Memory budget in MB")
    parser.add_argument("--dt-fast", type=float, default=10.0, help="Fast loop interval in seconds")
    parser.add_argument("--dt-slow", type=float, default=60.0, help="Slow loop interval in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Run without live Kubernetes cluster")
    parser.add_argument("--cycles", type=int, default=0, help="Max cycles to run (0 for infinite)")

    args = parser.parse_args()
    controller = GranuWarmController(
        tree_config=args.config,
        rules_config=args.rules,
        prometheus_url=args.prometheus_url,
        memory_budget_mb=args.budget,
        dt_fast_sec=args.dt_fast,
        dt_slow_sec=args.dt_slow,
        dry_run=args.dry_run
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(signum, frame):
        controller.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(controller.run_loop(max_cycles=args.cycles))
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
