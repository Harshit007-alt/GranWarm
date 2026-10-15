import argparse
import csv
import logging
import os
import sys
import time
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.run_sim import run_simulation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ExperimentHarness")

WORKLOADS = ["W1", "W2", "W3", "W4", "W5"]
BASELINES = ["B1", "B2", "B3", "B4", "B5", "B6"]
SEEDS = [42, 123, 456, 789, 1024]


def run_experiment_matrix(
    workloads: List[str],
    baselines: List[str],
    seeds: List[int],
    duration: float = 1000.0,
    config_path: str = "configs/dependencies.json",
    memory_budget_mb: float = 4096.0,
    raw_dir: str = "results/raw"
):
    os.makedirs(raw_dir, exist_ok=True)
    summary_path = os.path.join(raw_dir, "summary_experiment_matrix.csv")

    summary_rows = []
    total_runs = len(workloads) * len(baselines) * len(seeds)
    current_run = 0

    logger.info(f"Starting Experiment Matrix: {len(workloads)} Workloads x {len(baselines)} Baselines x {len(seeds)} Seeds = {total_runs} Total Runs")
    t0_all = time.time()

    for w in workloads:
        for b in baselines:
            for s in seeds:
                current_run += 1
                logger.info(f"[{current_run}/{total_runs}] Running {w} | {b} | Seed {s}")
                csv_path = os.path.join(raw_dir, f"{w}_{b}_seed{s}.csv")

                metrics = run_simulation(
                    workload_name=w,
                    policy_name=b,
                    duration=duration,
                    seed=s,
                    config_path=config_path,
                    memory_budget_mb=memory_budget_mb,
                    output_csv=csv_path
                )

                # Composite cost J surrogate for Wilcoxon significance testing
                # J = 0.35 * (L/1000) + 0.25 * (CSR/100) + 0.25 * (Mem/Budget) + 0.15 * (SVR/100)
                norm_L = metrics.get("p95_latency_ms", 50.0) / 1000.0
                norm_C = metrics.get("cold_start_rate_pct", 0.0) / 100.0
                norm_M = metrics.get("avg_memory_used_mb", 1000.0) / max(memory_budget_mb, 1.0)
                norm_S = metrics.get("sla_violation_rate_pct", 0.0) / 100.0
                comp_cost = 0.35 * norm_L + 0.25 * norm_C + 0.25 * norm_M + 0.15 * norm_S

                row = {
                    "workload": w,
                    "baseline": b,
                    "seed": s,
                    "total_requests": metrics.get("total_requests", 0),
                    "mean_latency_ms": metrics.get("mean_latency_ms", 0.0),
                    "median_latency_ms": metrics.get("median_latency_ms", 0.0),
                    "p95_latency_ms": metrics.get("p95_latency_ms", 0.0),
                    "p99_latency_ms": metrics.get("p99_latency_ms", 0.0),
                    "cold_start_rate_pct": metrics.get("cold_start_rate_pct", 0.0),
                    "sla_violation_rate_pct": metrics.get("sla_violation_rate_pct", 0.0),
                    "avg_memory_used_mb": metrics.get("avg_memory_used_mb", 0.0),
                    "avg_memory_idle_mb": metrics.get("avg_memory_idle_mb", 0.0),
                    "composite_cost": comp_cost
                }
                summary_rows.append(row)

    # Write or merge summary CSV
    if summary_rows:
        existing_rows_dict = {}
        if os.path.exists(summary_path):
            with open(summary_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    key = (r.get("workload"), r.get("baseline"), str(r.get("seed")))
                    existing_rows_dict[key] = r

        for r in summary_rows:
            key = (r.get("workload"), r.get("baseline"), str(r.get("seed")))
            existing_rows_dict[key] = r

        all_rows = list(existing_rows_dict.values())
        fieldnames = list(summary_rows[0].keys())
        with open(summary_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

    total_time = time.time() - t0_all
    logger.info(f"Experiment matrix finished in {total_time:.2f}s! Summary written to {summary_path}")


def main():
    parser = argparse.ArgumentParser(description="GranuWarm Automated Experiment Runner")
    parser.add_argument("--mini-test", action="store_true", help="Quick verification test (4 runs)")
    parser.add_argument("--full", action="store_true", help="Run full 150-run matrix")
    parser.add_argument("--workloads", nargs="+", default=None, help="Workloads to run (e.g. W1 W2 W3 W4 W5)")
    parser.add_argument("--baselines", nargs="+", default=None, help="Baselines to run (e.g. B1 B2 B3 B4 B5 B6)")
    parser.add_argument("--seeds", nargs="+", type=int, default=None, help="Seeds to run (e.g. 42 123 456)")
    parser.add_argument("--duration", type=float, default=600.0, help="Duration per run in seconds")
    parser.add_argument("--budget", type=float, default=4096.0, help="Memory budget in MB")
    parser.add_argument("--config", type=str, default="configs/dependencies.json")
    parser.add_argument("--output-dir", type=str, default="results/raw")

    args = parser.parse_args()

    if args.mini_test:
        workloads = ["W3"]
        baselines = ["B1", "B6"]
        seeds = [42, 123]
        duration = 200.0
    elif args.full:
        workloads = WORKLOADS
        baselines = BASELINES
        seeds = SEEDS
        duration = args.duration
    else:
        # Default test matrix: all 6 baselines across W1 and W3
        workloads = ["W1", "W3"]
        baselines = ["B1", "B2", "B3", "B4", "B5", "B6"]
        seeds = [42, 123]
        duration = 300.0

    if args.workloads:
        workloads = args.workloads
    if args.baselines:
        baselines = args.baselines
    if args.seeds:
        seeds = args.seeds

    run_experiment_matrix(
        workloads=workloads,
        baselines=baselines,
        seeds=seeds,
        duration=duration,
        config_path=args.config,
        memory_budget_mb=args.budget,
        raw_dir=args.output_dir
    )


if __name__ == "__main__":
    main()
