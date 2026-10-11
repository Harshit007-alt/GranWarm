import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List
import httpx
import numpy as np

from workload.profiles import get_profile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WorkloadGenerator")


async def invoke_worker(
    client: httpx.AsyncClient,
    base_url: str,
    func_info: Dict[str, Any],
    log_file_handle=None,
    lock=None
):
    service_name = func_info["service_name"]
    host_header = f"{service_name}.default.127.0.0.1.sslip.io"
    t_req = time.time()
    try:
        resp = await client.get(
            f"{base_url}/",
            headers={"Host": host_header},
            timeout=15.0
        )
        latency_ms = (time.time() - t_req) * 1000.0
        status = resp.status_code
    except Exception as e:
        latency_ms = (time.time() - t_req) * 1000.0
        status = 500

    if log_file_handle and lock:
        async with lock:
            log_file_handle.write(
                f"{t_req:.4f},{func_info['id']},{func_info['service_name']},{latency_ms:.2f},{status}\n"
            )


async def run_workload(
    profile_name: str,
    duration: float,
    seed: int,
    base_url: str,
    config_path: str,
    output_path: str = None
):
    logger.info(f"Starting workload generator: profile={profile_name}, duration={duration}s, seed={seed}")
    rng = np.random.default_rng(seed)

    with open(config_path, "r") as f:
        config_data = json.load(f)
    functions: List[Dict[str, Any]] = config_data.get("functions", [])

    profile = get_profile(profile_name, switch_time=duration / 2.0)

    log_file = None
    lock = asyncio.Lock()
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        log_file = open(output_path, "w", buffering=1)
        log_file.write("timestamp,function_id,service_name,latency_ms,status_code\n")

    t_start = time.monotonic()
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=200, max_keepalive_connections=50)) as client:
        active_tasks = set()
        while True:
            elapsed = time.monotonic() - t_start
            if elapsed >= duration:
                break

            for idx, func in enumerate(functions):
                rate = profile.get_rate(elapsed, func.get("base_rate", 5.0), idx, len(functions))
                # Poisson inter-arrival time: wait ~ Exp(lambda)
                wait_time = rng.exponential(1.0 / max(rate, 0.01))
                if wait_time < 0.05:
                    task = asyncio.create_task(
                        invoke_worker(client, base_url, func, log_file, lock)
                    )
                    active_tasks.add(task)
                    task.add_done_callback(active_tasks.discard)

            await asyncio.sleep(0.1)

        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)

    if log_file:
        log_file.close()
    logger.info(f"Workload generation finished successfully.")


def main():
    parser = argparse.ArgumentParser(description="GranuWarm Async HTTP Workload Generator")
    parser.add_argument("--profile", type=str, default="W1", help="Workload profile: W1, W2, W3, W4, W5")
    parser.add_argument("--duration", type=float, default=60.0, help="Duration in seconds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--base-url", type=str, default="http://localhost:80", help="Knative ingress base URL")
    parser.add_argument("--config", type=str, default="configs/dependencies.json", help="Path to dependencies.json")
    parser.add_argument("--output", type=str, default=None, help="Output CSV path")

    args = parser.parse_args()
    asyncio.run(
        run_workload(
            profile_name=args.profile,
            duration=args.duration,
            seed=args.seed,
            base_url=args.base_url,
            config_path=args.config,
            output_path=args.output
        )
    )


if __name__ == "__main__":
    main()
