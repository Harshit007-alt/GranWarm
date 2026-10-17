#!/usr/bin/env python3
"""
Convert live experiment data to unified raw format matching simulation output.

Input:  results/live_experiments/W*_B*_seed*_traffic.csv + audit logs
Output: results/raw/W*_B*_seed*.csv (same format as simulation)

Format: timestamp,seed,workload_id,baseline_id,function_id,latency_ms,is_cold_start,is_sla_violation,memory_used_mb,idle_memory_mb
"""

import argparse
import csv
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LiveToRaw")

# SLA thresholds (ms) per function type
SLA_THRESHOLDS = {
    "f01": 100,  # Node.js
    "f02": 150,  # Node.js
    "f03": 1500, # Python/Pillow
    "f04": 1600, # Python/scipy
    "f05": 1200, # Python/Pillow
    "f08": 1700, # Python/pandas
    "f09": 1300, # Python/pandas
    "f10": 400,  # Node.js/auth
    "f11": 1000, # Python/sqlalchemy
    "f12": 450,  # Node.js/firebase
}

# Container memory per function (MB)
FUNCTION_MEMORY = {
    "f01": 128,
    "f02": 128,
    "f03": 512,
    "f04": 512,
    "f05": 256,
    "f08": 512,
    "f09": 256,
    "f10": 256,
    "f11": 256,
    "f12": 256,
}


def load_audit_allocations(audit_dir: Path) -> List[Dict]:
    """Load all allocation decisions from audit logs."""
    decisions = []
    
    if not audit_dir.exists():
        logger.warning(f"Audit directory not found: {audit_dir}")
        return decisions
    
    for audit_file in sorted(audit_dir.glob("*.jsonl")):
        with open(audit_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if record.get("event") != "telemetry_error":
                        decisions.append(record)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping invalid JSON line in {audit_file}: {e}")
    
    return decisions


def get_memory_at_time(decisions: List[Dict], timestamp: float) -> Tuple[float, float]:
    """Get memory allocation at a specific timestamp.
    
    Returns:
        (memory_used_mb, idle_memory_mb)
    """
    # Find the most recent decision before this timestamp
    relevant_decision = None
    for decision in decisions:
        decision_time = float(decision.get("captured_at", "0"))
        if decision_time <= timestamp:
            relevant_decision = decision
        else:
            break
    
    if not relevant_decision:
        return 0.0, 0.0
    
    function_capacities = relevant_decision.get("function_capacities", {})
    
    # Calculate used memory (allocated pods × memory)
    memory_used = sum(
        count * FUNCTION_MEMORY.get(fid, 256)
        for fid, count in function_capacities.items()
    )
    
    # For live experiments, idle memory is harder to calculate
    # Use a simple estimate: allocated but not serving traffic
    # For now, assume 30% of allocated is idle (rough estimate)
    idle_memory = memory_used * 0.3
    
    return memory_used, idle_memory


def detect_cold_start(latency_ms: float, function_id: str, status_code: int) -> bool:
    """Heuristic cold-start detection based on latency threshold.
    
    Args:
        latency_ms: Request latency in milliseconds
        function_id: Function identifier
        status_code: HTTP status code
        
    Returns:
        True if likely a cold-start
    """
    if status_code != 200:
        return False  # Failed requests aren't cold-starts
    
    # Cold-start threshold: 2x the normal (warm) latency
    threshold = SLA_THRESHOLDS.get(function_id, 500) * 2
    return latency_ms > threshold


def is_sla_violation(latency_ms: float, function_id: str, status_code: int) -> bool:
    """Check if request violates SLA."""
    if status_code != 200:
        return True  # Failed requests are SLA violations
    
    threshold = SLA_THRESHOLDS.get(function_id, 500)
    return latency_ms > threshold


def convert_traffic_to_raw(
    traffic_csv: Path,
    audit_dir: Path,
    output_csv: Path,
    seed: int,
    workload: str,
    baseline: str,
):
    """Convert one traffic CSV + audit logs to raw format."""
    
    logger.info(f"Converting: {traffic_csv.name}")
    logger.info(f"  Workload: {workload}, Baseline: {baseline}, Seed: {seed}")
    
    # Load audit decisions for memory tracking
    decisions = load_audit_allocations(audit_dir)
    logger.info(f"  Loaded {len(decisions)} allocation decisions from audit")
    
    # Sort decisions by timestamp for efficient lookup
    decisions.sort(key=lambda d: float(d.get("captured_at", "0")))
    
    # Read traffic CSV and convert to raw format
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    with open(traffic_csv, 'r', newline='') as infile, open(output_csv, 'w', newline='') as outfile:
        reader = csv.DictReader(infile)
        writer = csv.writer(outfile)
        
        # Write header
        writer.writerow([
            "timestamp", "seed", "workload_id", "baseline_id",
            "function_id", "latency_ms", "is_cold_start",
            "is_sla_violation", "memory_used_mb", "idle_memory_mb"
        ])
        
        row_count = 0
        for row in reader:
            timestamp = row["timestamp"]
            function_id = row["function_id"]
            latency_ms = float(row["latency_ms"])
            status_code = int(row["status_code"]) if row["status_code"] else 0
            
            # Get container memory from CSV if available, otherwise from lookup
            container_memory = float(row.get("memory_mb", FUNCTION_MEMORY.get(function_id, 256)))
            
            # Detect cold-starts and SLA violations
            cold_start = detect_cold_start(latency_ms, function_id, status_code)
            sla_violation = is_sla_violation(latency_ms, function_id, status_code)
            
            # Get memory allocation at this timestamp from audit logs
            memory_used, idle_memory = get_memory_at_time(decisions, float(timestamp))
            
            # If we don't have audit data, use container memory as allocated
            if memory_used == 0:
                memory_used = container_memory
                idle_memory = 0
            
            writer.writerow([
                timestamp,
                seed,
                workload,
                baseline,
                function_id,
                f"{latency_ms:.2f}",
                1 if cold_start else 0,
                1 if sla_violation else 0,
                f"{memory_used:.1f}",
                f"{idle_memory:.1f}",
            ])
            
            row_count += 1
    
    logger.info(f"  ✓ Wrote {row_count} rows to {output_csv}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert live experiment traffic CSVs to unified raw format"
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="results/live_experiments",
        help="Directory containing traffic CSVs and audit logs"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results/raw",
        help="Output directory for raw CSVs"
    )
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    
    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        return 1
    
    # Find all traffic CSVs
    traffic_files = list(input_dir.glob("*_traffic.csv"))
    
    if not traffic_files:
        logger.error(f"No traffic CSVs found in {input_dir}")
        return 1
    
    logger.info(f"Found {len(traffic_files)} traffic CSVs to convert")
    logger.info("")
    
    converted = 0
    failed = 0
    
    for traffic_csv in sorted(traffic_files):
        # Parse filename: W1_B6_seed42_traffic.csv
        parts = traffic_csv.stem.split("_")
        if len(parts) < 4:
            logger.warning(f"Skipping file with unexpected name format: {traffic_csv.name}")
            failed += 1
            continue
        
        workload = parts[0]  # W1
        baseline = parts[1]  # B6
        seed_str = parts[2] # seed42
        
        try:
            seed = int(seed_str.replace("seed", ""))
        except ValueError:
            logger.warning(f"Could not parse seed from {traffic_csv.name}")
            failed += 1
            continue
        
        # Find corresponding audit directory
        audit_dir = input_dir / f"{workload}_{baseline}_seed{seed}_audit"
        
        # Output path
        output_csv = output_dir / f"{workload}_{baseline}_{seed_str}.csv"
        
        try:
            convert_traffic_to_raw(
                traffic_csv=traffic_csv,
                audit_dir=audit_dir,
                output_csv=output_csv,
                seed=seed,
                workload=workload,
                baseline=baseline,
            )
            converted += 1
        except Exception as e:
            logger.error(f"Failed to convert {traffic_csv.name}: {e}")
            failed += 1
        
        logger.info("")
    
    logger.info("=" * 72)
    logger.info(f"Conversion complete!")
    logger.info(f"  Converted: {converted}")
    logger.info(f"  Failed:    {failed}")
    logger.info(f"  Output:    {output_dir}")
    logger.info("=" * 72)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
