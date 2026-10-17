"""Enhanced Knative scaler with retry, reconciliation, and idempotency.

This module provides production-ready Kubernetes actuation with:
- Idempotent patch generation (only patch if current ≠ desired)
- Exponential backoff retry (max 3 attempts)
- 409 Conflict handling (refetch resource version and retry)
- Structured actuation results for observability
- Startup reconciliation to converge to desired state
- Hysteresis deadband to prevent oscillation
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ActuationResult:
    """Structured result of an actuation attempt.
    
    Attributes:
        success: True if the service was successfully patched or already at target
        service: Service name
        requested: The requested min-scale value
        current: The current min-scale value before patching (None if unknown)
        message: Human-readable message describing the outcome
        attempts: Number of patch attempts made (0 if skipped)
        skipped: True if patch was skipped due to idempotency or deadband
        error: Exception message if failed, None otherwise
    """
    success: bool
    service: str
    requested: int
    current: Optional[int] = None
    message: str = ""
    attempts: int = 1
    skipped: bool = False
    error: Optional[str] = None


@dataclass
class ActuationSummary:
    """Summary of a batch actuation operation.
    
    Attributes:
        total: Total number of services in the request
        successful: Number of successfully applied patches
        skipped: Number of patches skipped (idempotency or deadband)
        failed: Number of failed patches
        results: Dict mapping service name to ActuationResult
    """
    total: int = 0
    successful: int = 0
    skipped: int = 0
    failed: int = 0
    results: Dict[str, ActuationResult] = field(default_factory=dict)


class KnativeScaler:
    """Idempotent, retrying Knative Service scaler with reconciliation.
    
    This scaler provides production-ready actuation with:
    
    1. **Idempotency**: Only patches if current state ≠ desired state
    2. **Retry logic**: Exponential backoff with configurable max retries
    3. **Conflict handling**: Refetch resource version on 409 and retry
    4. **Hysteresis**: Scale-down deadband to prevent oscillation
    5. **Reconciliation**: Can reconcile to desired state at startup
    6. **Observability**: Structured results with success/failure/skip counts
    
    Usage:
        scaler = KnativeScaler(dry_run=False, max_retries=3)
        results = scaler.apply_allocation({"f01-hello-world": 5})
        
        # At startup
        results = scaler.reconcile(desired_state["function_capacities"])
    """

    SCALE_DOWN_DEADBAND = 1  # Minimum delta before scale-down

    def __init__(
        self,
        namespace: str = "default",
        dry_run: bool = False,
        max_retries: int = 3,
        base_backoff_sec: float = 1.0,
    ):
        """Initialize the Knative scaler.
        
        Args:
            namespace: Kubernetes namespace for Knative services
            dry_run: If True, log operations but don't apply to cluster
            max_retries: Maximum number of retry attempts per service
            base_backoff_sec: Base backoff for exponential retry (1.0s default)
        """
        self.namespace = namespace
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.api_available = False
        self.api = None
        
        # Track current known state for idempotency checks
        self._known_state: Dict[str, int] = {}
        
        self._init_k8s_client()

    def _init_k8s_client(self):
        """Initialize Kubernetes API client.
        
        Attempts in-cluster config first, then falls back to kubeconfig.
        If neither works and not in dry-run mode, switches to dry-run.
        """
        if self.dry_run:
            logger.info(
                "KnativeScaler initialized in DRY RUN mode "
                "(no K8s cluster calls)."
            )
            return

        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes configuration")
            except Exception:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig context")
            
            self.api = client.CustomObjectsApi()
            self.api_available = True
            logger.info("Kubernetes API initialized successfully")
        except Exception as e:
            logger.warning(
                f"Failed to initialize Kubernetes API: {e}. "
                f"Switching to dry-run mode."
            )
            self.dry_run = True
            self.api_available = False

    def get_current_min_scale(self, service_name: str) -> Optional[int]:
        """Fetch current min-scale annotation from a Knative Service.
        
        Args:
            service_name: Name of the Knative Service
            
        Returns:
            Current min-scale value, or None if service not found or fetch failed
        """
        if self.dry_run or not self.api_available:
            # Return cached value if in dry-run
            return self._known_state.get(service_name)

        try:
            svc = self.api.get_namespaced_custom_object(
                group="serving.knative.dev",
                version="v1",
                namespace=self.namespace,
                plural="services",
                name=service_name
            )
            annotations = (
                svc.get("spec", {})
                .get("template", {})
                .get("metadata", {})
                .get("annotations", {})
            )
            min_scale_str = annotations.get(
                "autoscaling.knative.dev/min-scale", "0"
            )
            current = int(min_scale_str)
            
            # Cache the current state
            self._known_state[service_name] = current
            return current
            
        except Exception as e:
            if "404" in str(e):
                logger.warning(f"Service {service_name} not found")
            else:
                logger.error(
                    f"Failed to get current min-scale for {service_name}: {e}"
                )
            return None

    def _needs_update(
        self, service_name: str, current: Optional[int], target: int
    ) -> bool:
        """Check if a patch is needed (idempotency + hysteresis check).
        
        Args:
            service_name: Name of the service
            current: Current min-scale value (None if unknown)
            target: Desired min-scale value
            
        Returns:
            True if a patch should be applied, False if skipped
        """
        if current is None:
            # Unknown current state, assume patch needed
            return True

        if target == current:
            # Already at target
            logger.debug(
                f"{service_name}: already at target ({current}), skip"
            )
            return False

        # Scale-up: always apply
        if target > current:
            return True

        # Scale-down: apply only if beyond deadband
        if target < current:
            delta = current - target
            if delta < self.SCALE_DOWN_DEADBAND:
                logger.debug(
                    f"{service_name}: scale-down {current} → {target} "
                    f"within deadband ({delta} < {self.SCALE_DOWN_DEADBAND}), skip"
                )
                return False
            return True

        return True

    def _patch_service(
        self, service_name: str, target: int
    ) -> ActuationResult:
        """Attempt to patch a service with retry logic.
        
        Args:
            service_name: Name of the Knative Service
            target: Desired min-scale value
            
        Returns:
            ActuationResult with success/failure details
        """
        # Fetch current state
        current = self.get_current_min_scale(service_name)

        # Idempotency + hysteresis check
        if not self._needs_update(service_name, current, target):
            return ActuationResult(
                success=True,
                service=service_name,
                requested=target,
                current=current,
                message=f"Already at target or within deadband (current={current})",
                attempts=0,
                skipped=True
            )

        # Dry-run mode
        if self.dry_run:
            self._known_state[service_name] = target
            return ActuationResult(
                success=True,
                service=service_name,
                requested=target,
                current=current,
                message=f"DRY-RUN: would patch {current} → {target}",
                attempts=0,
                skipped=True
            )

        # Retry loop with exponential backoff
        last_error = None
        for retry in range(self.max_retries):
            try:
                body = {
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "autoscaling.knative.dev/min-scale": str(target)
                                }
                            }
                        }
                    }
                }

                self.api.patch_namespaced_custom_object(
                    group="serving.knative.dev",
                    version="v1",
                    namespace=self.namespace,
                    plural="services",
                    name=service_name,
                    body=body
                )

                # Success!
                self._known_state[service_name] = target
                logger.info(f"✓ Patched {service_name}: {current} → {target}")
                return ActuationResult(
                    success=True,
                    service=service_name,
                    requested=target,
                    current=current,
                    message="Patched successfully",
                    attempts=retry + 1
                )

            except Exception as e:
                last_error = str(e)
                
                # Handle 409 Conflict (resource version changed)
                if "409" in last_error:
                    logger.warning(
                        f"Conflict patching {service_name}, refetch and retry "
                        f"{retry+1}/{self.max_retries}"
                    )
                    current = self.get_current_min_scale(service_name)
                    
                # Handle 404 Not Found
                elif "404" in last_error:
                    logger.error(f"Service {service_name} not found")
                    return ActuationResult(
                        success=False,
                        service=service_name,
                        requested=target,
                        current=None,
                        message="Service not found (404)",
                        attempts=retry + 1,
                        error=last_error
                    )
                
                # Other errors
                else:
                    logger.error(f"API error patching {service_name}: {e}")

                # Exponential backoff before retry
                if retry < self.max_retries - 1:
                    backoff = self.base_backoff_sec * (2 ** retry)
                    logger.debug(f"Backing off {backoff:.1f}s before retry")
                    time.sleep(backoff)

        # All retries exhausted
        return ActuationResult(
            success=False,
            service=service_name,
            requested=target,
            current=current,
            message=f"Failed after {self.max_retries} attempts",
            attempts=self.max_retries,
            error=last_error
        )

    def apply_allocation(
        self, targets: Dict[str, int]
    ) -> ActuationSummary:
        """Apply allocation with retry and idempotency.
        
        Args:
            targets: Dict mapping service name to desired min-scale
            
        Returns:
            ActuationSummary with results for each service
        """
        summary = ActuationSummary(total=len(targets))
        
        for service, target in targets.items():
            result = self._patch_service(service, target)
            summary.results[service] = result
            
            if result.success:
                summary.successful += 1
                if result.skipped:
                    summary.skipped += 1
            else:
                summary.failed += 1

        # Log summary
        logger.info(
            f"Actuation complete: {summary.successful}/{summary.total} successful "
            f"({summary.skipped} skipped, {summary.failed} failed)"
        )
        
        return summary

    def reconcile(
        self, desired_state: Dict[str, int]
    ) -> ActuationSummary:
        """Reconcile current state with desired state (called at startup).
        
        This method is typically called at controller startup to ensure the
        cluster state matches the last known desired state. It's identical to
        apply_allocation but logs differently for clarity.
        
        Args:
            desired_state: Dict mapping service name to desired min-scale
            
        Returns:
            ActuationSummary with reconciliation results
        """
        logger.info(
            f"Reconciling {len(desired_state)} services to desired state"
        )
        return self.apply_allocation(desired_state)

    def get_summary_message(self, summary: ActuationSummary) -> str:
        """Get a human-readable summary message.
        
        Args:
            summary: ActuationSummary from apply_allocation or reconcile
            
        Returns:
            Multi-line string with summary and per-service details
        """
        lines = [
            f"Actuation summary: {summary.successful}/{summary.total} successful",
            f"  Skipped: {summary.skipped}",
            f"  Failed: {summary.failed}",
        ]
        
        if summary.failed > 0:
            lines.append("Failed services:")
            for svc, result in summary.results.items():
                if not result.success:
                    lines.append(f"  ✗ {svc}: {result.message}")
        
        return "\n".join(lines)
