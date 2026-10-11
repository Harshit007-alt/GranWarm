import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class KnativeScaler:
    """Manages Knative Service min-scale annotations with hysteresis deadband logic."""

    def __init__(
        self,
        namespace: str = "default",
        epsilon_reclaim: int = 2,
        dry_run: bool = False
    ):
        self.namespace = namespace
        self.epsilon_reclaim = epsilon_reclaim
        self.dry_run = dry_run
        self.current_allocations: Dict[str, int] = {}
        self.api = None
        self._init_k8s_client()

    def _init_k8s_client(self):
        if self.dry_run:
            logger.info("KnativeScaler initialized in DRY RUN mode (no K8s cluster calls).")
            return
        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes configuration.")
            except Exception:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig context.")
            self.api = client.CustomObjectsApi()
        except Exception as e:
            logger.warning(f"Could not connect to Kubernetes API ({e}). Falling back to dry-run mode.")
            self.dry_run = True

    def _patch_min_scale(self, service_name: str, min_scale: int):
        """Patches autoscaling.knative.dev/min-scale annotation on Knative Service."""
        logger.info(f"[Scaler] Patching service '{service_name}' min-scale -> {min_scale}")
        if self.dry_run or not self.api:
            return

        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "autoscaling.knative.dev/min-scale": str(min_scale)
                        }
                    }
                }
            }
        }
        try:
            self.api.patch_namespaced_custom_object(
                group="serving.knative.dev",
                version="v1",
                namespace=self.namespace,
                plural="services",
                name=service_name,
                body=body
            )
        except Exception as e:
            logger.error(f"Failed to patch Knative service '{service_name}': {e}")

    def apply_allocation(self, desired_allocations: Dict[str, int]):
        """Applies desired allocations with hysteresis to prevent oscillation / flapping.

        Rule:
        - Scale-UP: applied immediately if desired > current.
        - Scale-DOWN: applied only if (desired - current) < -epsilon_reclaim.
        """
        for service_name, desired in desired_allocations.items():
            curr = self.current_allocations.get(service_name, 0)
            diff = desired - curr

            if diff > 0:
                # Proactive scale-up
                self._patch_min_scale(service_name, desired)
                self.current_allocations[service_name] = desired
            elif diff < -self.epsilon_reclaim:
                # Conservative hysteresis scale-down
                self._patch_min_scale(service_name, desired)
                self.current_allocations[service_name] = desired
            else:
                # Within hysteresis deadband -> hold current state to prevent flapping
                logger.debug(
                    f"[Scaler] Deadband hold for '{service_name}': curr={curr}, desired={desired}, diff={diff}"
                )
