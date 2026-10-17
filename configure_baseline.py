#!/usr/bin/env python3
"""
Configure Knative services for a specific baseline policy.
This script sets minScale annotations before running experiments.
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ConfigureBaseline")

# Baseline configurations
BASELINE_CONFIGS = {
    "B1": {
        "name": "No Prewarm",
        "description": "All services at minScale=0 (Knative default)",
        "min_scale": 0,
    },
    "B2": {
        "name": "Fixed Prewarm",
        "description": "All services at minScale=1 (simple prewarming)",
        "min_scale": 1,
    },
    "B3": {
        "name": "Fuzzy Only",
        "description": "Let controller use fuzzy logic (dynamic)",
        "min_scale": 0,  # Controller will set dynamically
        "use_controller": True,
    },
    "B4": {
        "name": "PSO Only",
        "description": "Let controller use PSO optimization (dynamic)",
        "min_scale": 0,
        "use_controller": True,
    },
    "B5": {
        "name": "Fuzzy+PSO No Granularity",
        "description": "Let controller use fuzzy+PSO (dynamic)",
        "min_scale": 0,
        "use_controller": True,
    },
    "B6": {
        "name": "GranuWarm Full",
        "description": "Let controller use full GranuWarm (dynamic)",
        "min_scale": 0,
        "use_controller": True,
    },
}


def reset_all_services(services: list):
    """Reset all services to minScale=0."""
    logger.info("Resetting all services to minScale=0...")
    for service_name in services:
        patch_cmd = [
            "kubectl", "patch", "ksvc", service_name,
            "-n", "default",
            "--type", "merge",
            "-p", '{"spec":{"template":{"metadata":{"annotations":{"autoscaling.knative.dev/min-scale":"0"}}}}}'
        ]
        try:
            subprocess.run(patch_cmd, check=True, capture_output=True)
            logger.debug(f"  Reset {service_name}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"  Failed to reset {service_name}: {e.stderr.decode()}")


def configure_baseline(baseline: str, services: list):
    """Configure services for a specific baseline."""
    config = BASELINE_CONFIGS.get(baseline.upper())
    
    if not config:
        logger.error(f"Unknown baseline: {baseline}")
        return False
    
    logger.info("=" * 72)
    logger.info(f"Configuring baseline: {baseline} - {config['name']}")
    logger.info(f"  {config['description']}")
    logger.info("=" * 72)
    
    if config.get("use_controller", False):
        logger.info("✓ This baseline uses dynamic controller decisions")
        logger.info("  Services will remain at minScale=0")
        logger.info("  Controller will adjust during experiment")
        reset_all_services(services)
        return True
    
    min_scale = config["min_scale"]
    logger.info(f"Setting all services to minScale={min_scale}...")
    
    success_count = 0
    for service_name in services:
        patch_cmd = [
            "kubectl", "patch", "ksvc", service_name,
            "-n", "default",
            "--type", "merge",
            "-p", f'{{"spec":{{"template":{{"metadata":{{"annotations":{{"autoscaling.knative.dev/min-scale":"{min_scale}"}}}}}}}}}}'
        ]
        try:
            subprocess.run(patch_cmd, check=True, capture_output=True)
            logger.info(f"  ✓ {service_name}: minScale={min_scale}")
            success_count += 1
        except subprocess.CalledProcessError as e:
            logger.error(f"  ✗ {service_name}: {e.stderr.decode()}")
    
    logger.info("")
    logger.info(f"Configured {success_count}/{len(services)} services")
    return success_count == len(services)


def main():
    parser = argparse.ArgumentParser(
        description="Configure Knative services for a baseline policy"
    )
    parser.add_argument(
        "--baseline",
        required=True,
        choices=["B1", "B2", "B3", "B4", "B5", "B6"],
        help="Baseline policy to configure"
    )
    parser.add_argument(
        "--config",
        default="configs/dependencies_light.json",
        help="Path to dependencies config"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available baselines and exit"
    )
    
    args = parser.parse_args()
    
    if args.list:
        print("\nAvailable Baselines:")
        print("=" * 72)
        for code, config in BASELINE_CONFIGS.items():
            print(f"{code}: {config['name']}")
            print(f"    {config['description']}")
            if config.get("use_controller"):
                print(f"    minScale: dynamic (controller decides)")
            else:
                print(f"    minScale: {config['min_scale']}")
            print()
        return 0
    
    # Load config to get service names
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return 1
    
    with open(config_path) as f:
        config_data = json.load(f)
    
    services = [func["service_name"] for func in config_data.get("functions", [])]
    
    if not services:
        logger.error("No services found in config")
        return 1
    
    logger.info(f"Found {len(services)} services: {', '.join(services)}")
    logger.info("")
    
    success = configure_baseline(args.baseline, services)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
