#!/usr/bin/env python3
"""
Run a single baseline experiment (one workload × one baseline × one seed).
This script handles baseline-specific initialization and runs live traffic.
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BaselineExperiment")


def run_experiment(
    baseline: str,
    workload: str,
    seed: int,
    config: str,
    prewarm_time: int,
    traffic_duration: int,
    cooldown_time: int,
    base_url: str,
    results_dir: str,
):
    """Run one baseline experiment with live traffic."""
    
    baseline_upper = baseline.upper()
    workload_upper = workload.upper()
    
    # Output paths
    traffic_csv = Path(results_dir) / f"{workload_upper}_{baseline_upper}_seed{seed}_traffic.csv"
    audit_dir = Path(results_dir) / f"{workload_upper}_{baseline_upper}_seed{seed}_audit"
    
    logger.info("=" * 72)
    logger.info(f"Starting experiment: {workload_upper}_{baseline_upper}_seed{seed}")
    logger.info(f"  Baseline:  {baseline_upper}")
    logger.info(f"  Workload:  {workload_upper}")
    logger.info(f"  Seed:      {seed}")
    logger.info(f"  Config:    {config}")
    logger.info("=" * 72)
    
    # Step 0: Check prerequisites
    logger.info("[0/5] Checking prerequisites...")
    
    # Test port-forward connectivity
    logger.info("  Testing connectivity to Knative ingress...")
    test_url = f"{base_url}/"
    test_host = "f01-hello-world.default.127.0.0.1.sslip.io"
    
    try:
        import httpx
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(test_url, headers={"Host": test_host})
            logger.info(f"  ✓ Port-forward is working (status: {resp.status_code})")
    except Exception as e:
        logger.error("  ✗ Cannot connect to Knative ingress!")
        logger.error(f"    Error: {e}")
        logger.error("")
        logger.error("  SOLUTION:")
        logger.error("    1. Open PowerShell in a separate window")
        logger.error("    2. Run: kubectl port-forward -n kourier-system svc/kourier 8080:80")
        logger.error("    3. Keep it running during experiments")
        logger.error("")
        logger.error("  See LIVE_EXPERIMENTS_PREREQUISITES.md for details")
        return False
    
    # Warn about baseline configuration
    logger.info("")
    logger.info(f"  ⚠️  IMPORTANT: Configure baseline {baseline_upper} BEFORE running")
    logger.info("")
    if baseline_upper == "B1":
        logger.info("  In PowerShell, run:")
        logger.info("    $services = @('f01-hello-world', 'f02-json-transform', 'f03-image-resize', 'f04-image-filter', 'f05-thumbnail-gen', 'f08-data-aggregate', 'f09-csv-parser', 'f10-auth-service', 'f11-order-process', 'f12-notification')")
        logger.info("    foreach ($svc in $services) { kubectl patch ksvc $svc -n default --type merge -p '{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"autoscaling.knative.dev/min-scale\":\"0\"}}}}}' }")
    elif baseline_upper == "B2":
        logger.info("  In PowerShell, run:")
        logger.info("    $services = @('f01-hello-world', 'f02-json-transform', 'f03-image-resize', 'f04-image-filter', 'f05-thumbnail-gen', 'f08-data-aggregate', 'f09-csv-parser', 'f10-auth-service', 'f11-order-process', 'f12-notification')")
        logger.info("    foreach ($svc in $services) { kubectl patch ksvc $svc -n default --type merge -p '{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"autoscaling.knative.dev/min-scale\":\"1\"}}}}}' }")
    else:
        logger.info("  In PowerShell, run:")
        logger.info("    $services = @('f01-hello-world', 'f02-json-transform', 'f03-image-resize', 'f04-image-filter', 'f05-thumbnail-gen', 'f08-data-aggregate', 'f09-csv-parser', 'f10-auth-service', 'f11-order-process', 'f12-notification')")
        logger.info("    foreach ($svc in $services) { kubectl patch ksvc $svc -n default --type merge -p '{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"autoscaling.knative.dev/min-scale\":\"0\"}}}}}' }")
    
    logger.info("")
    input("Press ENTER when baseline is configured and ready to continue...")
    logger.info("")
    
    # Step 1: Start controller (only for dynamic baselines B3-B6)
    controller_proc = None
    
    if baseline_upper in ["B3", "B4", "B5", "B6"]:
        logger.info("[1/5] Starting controller...")
        
        controller_cmd = [
            sys.executable, "-m", "controller.main",
            "--config", config,
            "--mode", "live",
            "--baseline", baseline_upper,
            "--cycles", "40",
            "--dt-fast", "15",
            "--dt-slow", "90",
            "--budget", "1500",
            "--audit-dir", str(audit_dir),
            "--skip-telemetry-validation",
        ]
        
        controller_proc = subprocess.Popen(
            controller_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        logger.info(f"  Controller PID: {controller_proc.pid}")
    else:
        logger.info("[1/5] Skipping controller (static baseline)")
        logger.info(f"  {baseline_upper} uses fixed minScale configuration")
    
    # Step 2: Pre-warm (for dynamic baselines) or stabilize (for static)
    if controller_proc:
        logger.info(f"[2/5] Pre-warming for {prewarm_time}s...")
        logger.info("  Controller makes decisions and pods start...")
    else:
        # For B1/B2, give pods time to start based on initial minScale
        logger.info(f"[2/5] Stabilizing for {prewarm_time}s...")
        logger.info("  Waiting for pods to reach target minScale...")
    
    time.sleep(prewarm_time)
    
    # Step 3: Generate traffic
    logger.info(f"[3/5] Generating {traffic_duration}s of {workload_upper} traffic...")
    
    traffic_cmd = [
        sys.executable, "-m", "workload.generator",
        "--profile", workload_upper,
        "--duration", str(traffic_duration),
        "--seed", str(seed),
        "--base-url", base_url,
        "--config", config,
        "--output", str(traffic_csv),
    ]
    
    try:
        subprocess.run(traffic_cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Traffic generation failed: {e}")
        controller_proc.terminate()
        controller_proc.wait(timeout=10)
        return False
    
    # Step 4: Cooldown and stop controller
    logger.info(f"[4/5] Cooldown for {cooldown_time}s...")
    time.sleep(cooldown_time)
    
    if controller_proc:
        logger.info("  Stopping controller...")
        controller_proc.terminate()
        try:
            controller_proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("  Controller did not stop gracefully, killing...")
            controller_proc.kill()
            controller_proc.wait()
    else:
        logger.info("  No controller to stop (static baseline)")
    
    # Step 5: Summarize results
    logger.info("[5/5] Summarizing results...")
    if traffic_csv.exists():
        with open(traffic_csv, 'r') as f:
            total = sum(1 for _ in f) - 1  # Exclude header
        
        with open(traffic_csv, 'r') as f:
            success = sum(1 for line in f if ',200,' in line)
        
        success_rate = (success / total * 100) if total > 0 else 0.0
        
        logger.info("")
        logger.info("✓ Experiment complete!")
        logger.info(f"  Traffic CSV:  {traffic_csv}")
        logger.info(f"  Audit dir:    {audit_dir}")
        logger.info(f"  Requests:     {total}")
        logger.info(f"  Successful:   {success} ({success_rate:.1f}%)")
        
        return True
    else:
        logger.error("✗ Traffic CSV not found!")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run a single baseline × workload live experiment"
    )
    parser.add_argument("--baseline", required=True, choices=["B1", "B2", "B3", "B4", "B5", "B6"])
    parser.add_argument("--workload", required=True, choices=["W1", "W2", "W3", "W4", "W5"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", default="configs/dependencies_light.json")
    parser.add_argument("--prewarm-time", type=int, default=120)
    parser.add_argument("--traffic-duration", type=int, default=300)
    parser.add_argument("--cooldown-time", type=int, default=60)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--results-dir", default="results/live_experiments")
    
    args = parser.parse_args()
    
    success = run_experiment(
        baseline=args.baseline,
        workload=args.workload,
        seed=args.seed,
        config=args.config,
        prewarm_time=args.prewarm_time,
        traffic_duration=args.traffic_duration,
        cooldown_time=args.cooldown_time,
        base_url=args.base_url,
        results_dir=args.results_dir,
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
