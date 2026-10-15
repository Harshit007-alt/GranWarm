import argparse
import csv
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from simulator.env import SimEnvironment
from workload.profiles import get_profile
from baselines.b1_no_prewarm import B1NoPrewarmPolicy
from baselines.b2_fixed_prewarm import B2FixedPrewarmPolicy
from baselines.b3_fuzzy_only import B3FuzzyOnlyPolicy
from baselines.b4_pso_only import B4PSOOnlyPolicy
from baselines.b5_fuzzy_pso_no_granularity import B5FuzzyPSONoGranularityPolicy
from baselines.b6_granuwarm_full import B6GranuWarmFullPolicy

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SimulatorCLI")


def instantiate_policy(policy_name: str, config_path: str, memory_budget_mb: float):
    with open(config_path, "r") as f:
        data = json.load(f)
    fids = [f["id"] for f in data.get("functions", [])]
    fmems = {f["id"]: float(f.get("container_memory_mb", 256)) for f in data.get("functions", [])}

    p = policy_name.lower().replace("-", "_")
    if p in ["b1", "none", "no_prewarm"]:
        return B1NoPrewarmPolicy(fids)
    elif p in ["b2", "fixed", "fixed_prewarm"]:
        return B2FixedPrewarmPolicy(fids, fixed_count=2, function_memories=fmems, memory_budget_mb=memory_budget_mb)
    elif p in ["b3", "fuzzy", "fuzzy_only"]:
        return B3FuzzyOnlyPolicy(fids, fmems, memory_budget_mb=memory_budget_mb)
    elif p in ["b4", "pso", "pso_only"]:
        return B4PSOOnlyPolicy(fids, fmems, memory_budget_mb=memory_budget_mb)
    elif p in ["b5", "fuzzy_pso", "no_granularity"]:
        return B5FuzzyPSONoGranularityPolicy(fids, fmems, memory_budget_mb=memory_budget_mb)
    elif p in ["b6", "granuwarm", "full"]:
        return B6GranuWarmFullPolicy(tree_config=config_path, memory_budget_mb=memory_budget_mb)
    else:
        raise ValueError(f"Unknown policy name: {policy_name}")


def run_simulation(
    workload_name: str,
    policy_name: str,
    duration: float,
    seed: int,
    config_path: str,
    memory_budget_mb: float,
    output_csv: Optional[str] = None
):
    t_wall_start = time.time()
    rng = np.random.default_rng(seed)

    env = SimEnvironment(config_path, memory_budget_mb=memory_budget_mb)
    policy = instantiate_policy(policy_name, config_path, memory_budget_mb)
    profile = get_profile(workload_name, switch_time=duration / 2.0)

    with open(config_path, "r") as f:
        config_data = json.load(f)
    functions = config_data.get("functions", [])
    total_funcs = len(functions)

    # Pre-generate arrivals via non-homogeneous Poisson process or step-based simulation
    dt_step = 0.5  # 500ms time step
    steps = int(duration / dt_step)

    last_control_cycle = -100.0
    control_interval = 10.0  # evaluate controller every 10 simulated seconds

    logger.info(f"Running simulation: Workload={workload_name}, Policy={policy.name}, Duration={duration}s, Seed={seed}")

    for step_idx in range(steps):
        sim_time = step_idx * dt_step

        # Periodic control loop invocation
        if (sim_time - last_control_cycle) >= control_interval:
            last_control_cycle = sim_time
            # Formulate simulated telemetry signals from recent activity
            mock_metrics = {}
            for idx, func in enumerate(functions):
                fid = func["id"]
                rate = profile.get_rate(sim_time, func.get("base_rate", 5.0), idx, total_funcs)
                # Normalized invocation intensity
                r_norm = min(rate / 50.0, 1.0)
                # Traffic trend
                prev_rate = profile.get_rate(max(sim_time - control_interval, 0), func.get("base_rate", 5.0), idx, total_funcs)
                t_norm = min(max((rate - prev_rate) / 20.0, -1.0), 1.0)
                # Memory pressure
                used_m, _ = env.calculate_memory_usage()
                m_norm = min(used_m / memory_budget_mb, 1.0)

                mock_metrics[fid] = {
                    "R_i": r_norm,
                    "T_i": t_norm,
                    "C_i": 0.2 if r_norm > 0.4 else 0.05,
                    "M": m_norm
                }

            func_alloc, tree_alloc = policy.compute_allocation(mock_metrics)
            env.set_prewarm_policy(func_alloc, tree_alloc)

        # Generate and chronologically sort invocations for this discrete interval
        interval_events = []
        for idx, func in enumerate(functions):
            fid = func["id"]
            rate = profile.get_rate(sim_time, func.get("base_rate", 5.0), idx, total_funcs)
            expected_arrivals = rate * dt_step
            num_arrivals = rng.poisson(expected_arrivals)
            for _ in range(num_arrivals):
                inv_time = sim_time + rng.uniform(0.0, dt_step)
                interval_events.append((inv_time, fid))

        interval_events.sort(key=lambda x: x[0])
        for inv_time, fid in interval_events:
            env.step_invoke(fid, inv_time)

    wall_duration = time.time() - t_wall_start
    summary = env.get_summary_metrics()

    logger.info(f"Simulation completed in {wall_duration:.2f} real seconds!")
    logger.info(f"Summary: Total Reqs={summary.get('total_requests', 0):.0f}, "
                f"P95 Latency={summary.get('p95_latency_ms', 0):.1f}ms, "
                f"Cold Start Rate={summary.get('cold_start_rate_pct', 0):.2f}%, "
                f"Avg Memory={summary.get('avg_memory_used_mb', 0):.1f}MB")

    if output_csv:
        os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "seed", "workload_id", "baseline_id",
                "function_id", "latency_ms", "is_cold_start",
                "is_sla_violation", "memory_used_mb", "idle_memory_mb"
            ])
            for r in env.records:
                writer.writerow([
                    f"{r.timestamp:.3f}", seed, workload_name, policy.name,
                    r.function_id, f"{r.latency_ms:.2f}",
                    int(r.is_cold_start), int(r.is_sla_violation),
                    f"{r.memory_used_mb:.1f}", f"{r.idle_memory_mb:.1f}"
                ])
        logger.info(f"Saved trace log to {output_csv}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="GranuWarm Discrete-Event Simulator CLI")
    parser.add_argument("--workload", type=str, default="W3", help="Workload: W1, W2, W3, W4, W5")
    parser.add_argument("--policy", type=str, default="granuwarm", help="Policy: b1..b6 or none, fixed, fuzzy, pso, granuwarm")
    parser.add_argument("--duration", type=float, default=1000.0, help="Simulated seconds (default: 1000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--config", type=str, default="configs/dependencies.json", help="Path to dependencies.json")
    parser.add_argument("--budget", type=float, default=4096.0, help="Cluster memory budget in MB")
    parser.add_argument("--output", type=str, default=None, help="Output CSV filepath")

    args = parser.parse_args()
    run_simulation(
        workload_name=args.workload,
        policy_name=args.policy,
        duration=args.duration,
        seed=args.seed,
        config_path=args.config,
        memory_budget_mb=args.budget,
        output_csv=args.output
    )


if __name__ == "__main__":
    main()
