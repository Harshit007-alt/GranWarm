import json
import logging
import subprocess
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ClusterReset")


def run_cmd(cmd: str):
    logger.info(f"Running: {cmd}")
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        logger.warning(f"Command '{cmd}' returned non-zero exit code: {e}")


def reset_cluster(config_path: str = "configs/dependencies.json"):
    logger.info("=== Starting Cluster Reset ===")

    # 1. Reset min-scale annotations to 0 for all Knative services
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        for func in data.get("functions", []):
            svc_name = func.get("service_name", func["name"])
            patch_json = '{"spec":{"template":{"metadata":{"annotations":{"autoscaling.knative.dev/min-scale":"0"}}}}}'
            run_cmd(f"kubectl patch ksvc {svc_name} --type merge -p '{patch_json}'")
    except Exception as e:
        logger.warning(f"Could not patch services: {e}")

    # 2. Delete all running function pods in default namespace
    run_cmd("kubectl delete pods -l 'serving.knative.dev/service' --grace-period=0 --force")

    # 3. Wait for pod termination
    logger.info("Waiting 15s for cluster stabilization...")
    time.sleep(15)
    logger.info("=== Cluster Reset Complete ===")


if __name__ == "__main__":
    reset_cluster()
