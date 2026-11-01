#!/usr/bin/env python3
"""
GranuWarm One-Command Reproduction Script

Usage:
    # 1. Regenerate all publication figures, LaTeX tables, and Wilcoxon statistics from saved results:
    python reproduce.py

    # 2. Quick smoke-test simulation (runs mini matrix + plots):
    python reproduce.py --quick

    # 3. Full end-to-end simulation reproduction (runs all 150 experiments + plots):
    python reproduce.py --full

    # 4. Custom subset run:
    python reproduce.py --run --workloads W1 W3 --baselines B1 B2 B6 --seeds 42 123 --duration 300
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SUMMARY_FILE = REPO_ROOT / "results" / "raw" / "summary_experiment_matrix.csv"
STATS_FILE = REPO_ROOT / "results" / "stats_summary.txt"
PLOTS_DIR = REPO_ROOT / "results" / "plots"
TABLES_DIR = REPO_ROOT / "results" / "tables"


def run_cmd(cmd: list[str], description: str) -> None:
    print(f"\n>>> {description}...")
    print(f"    Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"ERROR: {description} failed with return code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        description="One-command reproduction for GranuWarm simulation experiments, figures, and statistical tests."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full 150-run simulation matrix (5 workloads x 6 baselines x 5 seeds) and generate all artifacts."
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick smoke-test simulation (mini matrix) and generate all artifacts."
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run simulation before generating plots/tables (uses existing settings or custom args)."
    )
    parser.add_argument(
        "--plots-only",
        action="store_true",
        help="Generate plots, tables, and statistics only without running simulations."
    )
    parser.add_argument("--workloads", nargs="+", default=None, help="Workloads: W1 W2 W3 W4 W5")
    parser.add_argument("--baselines", nargs="+", default=None, help="Baselines: B1 B2 B3 B4 B5 B6")
    parser.add_argument("--seeds", nargs="+", type=int, default=None, help="Random seeds (e.g. 42 123)")
    parser.add_argument("--duration", type=float, default=None, help="Simulation duration in seconds per run")

    args = parser.parse_args()

    python_bin = sys.executable

    # Determine whether simulation should run
    should_run_sim = args.full or args.quick or args.run
    if not should_run_sim and not args.plots_only:
        if not SUMMARY_FILE.exists() or SUMMARY_FILE.stat().st_size == 0:
            print(f"No existing summary matrix found at {SUMMARY_FILE}. Initiating simulation run...")
            should_run_sim = True

    if should_run_sim:
        sim_cmd = [python_bin, "-m", "experiments.run_experiment"]
        if args.full:
            sim_cmd.append("--full")
            if args.duration:
                sim_cmd.extend(["--duration", str(args.duration)])
        elif args.quick:
            sim_cmd.append("--mini-test")
        else:
            if args.workloads:
                sim_cmd.extend(["--workloads"] + args.workloads)
            if args.baselines:
                sim_cmd.extend(["--baselines"] + args.baselines)
            if args.seeds:
                sim_cmd.extend(["--seeds"] + [str(s) for s in args.seeds])
            if args.duration:
                sim_cmd.extend(["--duration", str(args.duration)])

        run_cmd(sim_cmd, "Running GranuWarm simulation experiments")

    # Generate publication figures, tables, and statistics
    plot_cmd = [python_bin, "scripts/plot_results.py"]
    run_cmd(plot_cmd, "Generating publication figures, LaTeX tables, and Wilcoxon statistics")

    # Print summary of results
    print("\n" + "=" * 76)
    print("REPRODUCTION COMPLETE")
    print("=" * 76)

    if STATS_FILE.exists():
        print("\nStatistical Significance Summary (from results/stats_summary.txt):")
        print("-" * 76)
        with open(STATS_FILE, "r") as f:
            print(f.read().strip())
        print("-" * 76)

    print("\nGenerated Artifacts:")
    print(f"  Plots:  {PLOTS_DIR}")
    if PLOTS_DIR.exists():
        for p in sorted(PLOTS_DIR.glob("*.png")):
            print(f"    - {p.name}")
    print(f"  Tables: {TABLES_DIR}")
    if TABLES_DIR.exists():
        for t in sorted(TABLES_DIR.glob("*.tex")):
            print(f"    - {t.name}")
    print(f"  Stats:  {STATS_FILE}")
    print(f"  Matrix: {SUMMARY_FILE}")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    main()
