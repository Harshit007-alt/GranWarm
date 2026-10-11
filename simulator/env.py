import enum
import heapq
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class ContainerState(enum.Enum):
    COLD = 0
    WARM = 1
    BUSY = 2
    RECLAIMED = 3


@dataclass
class Container:
    container_id: int
    function_id: str
    state: ContainerState
    memory_mb: float
    last_active_time: float
    busy_until: float = 0.0


@dataclass
class FunctionSpec:
    id: str
    name: str
    service_name: str
    memory_mb: float
    cold_start_ms: float
    warm_start_ms: float
    execution_time_ms: float = 50.0
    sla_threshold_ms: float = 1000.0
    dependency_path: List[str] = field(default_factory=list)


@dataclass
class InvocationRecord:
    timestamp: float
    function_id: str
    latency_ms: float
    is_cold_start: bool
    is_sla_violation: bool
    memory_used_mb: float
    idle_memory_mb: float


class SimEnvironment:
    """High-performance discrete-event serverless simulation engine for GranuWarm evaluation.

    Models container states: Cold -> Warm -> Busy -> Warm -> Reclaim.
    Supports layer-sharing and granularity-tree dependency cache hits.
    """

    def __init__(
        self,
        config_path: str,
        memory_budget_mb: float = 4096.0,
        idle_timeout_sec: float = 60.0
    ):
        self.config_path = config_path
        self.memory_budget_mb = memory_budget_mb
        self.idle_timeout_sec = idle_timeout_sec

        self.functions: Dict[str, FunctionSpec] = {}
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self._load_config(config_path)

        # State tracking
        self.current_time: float = 0.0
        self._container_counter: int = 0
        self.warm_pools: Dict[str, List[Container]] = {fid: [] for fid in self.functions}
        self.busy_pools: Dict[str, List[Container]] = {fid: [] for fid in self.functions}
        
        # Granularity-tree node prewarmed capacities {node_id: warm_count}
        self.tree_prewarmed: Dict[str, int] = {}
        
        # Function-level prewarm target {function_id: min_scale}
        self.min_scale_targets: Dict[str, int] = {fid: 0 for fid in self.functions}

        self.records: List[InvocationRecord] = []

    def _load_config(self, config_path: str):
        with open(config_path, "r") as f:
            data = json.load(f)
        for n in data.get("nodes", []):
            self.nodes[n["id"]] = n
        for f in data.get("functions", []):
            spec = FunctionSpec(
                id=f["id"],
                name=f["name"],
                service_name=f.get("service_name", f["name"]),
                memory_mb=float(f.get("container_memory_mb", 256)),
                cold_start_ms=float(f.get("cold_start_ms", 500.0)),
                warm_start_ms=float(f.get("warm_start_ms", 5.0)),
                execution_time_ms=float(f.get("execution_time_ms", 40.0)),
                sla_threshold_ms=float(f.get("cold_start_ms", 500.0) * 1.2),
                dependency_path=f.get("dependency_path", [])
            )
            self.functions[spec.id] = spec

    def reset(self):
        self.current_time = 0.0
        self._container_counter = 0
        self.warm_pools = {fid: [] for fid in self.functions}
        self.busy_pools = {fid: [] for fid in self.functions}
        self.tree_prewarmed.clear()
        self.min_scale_targets = {fid: 0 for fid in self.functions}
        self.records.clear()

    def set_prewarm_policy(
        self,
        func_targets: Dict[str, int],
        tree_targets: Optional[Dict[str, int]] = None
    ):
        """Updates prewarming targets from controller or baseline policy."""
        self.min_scale_targets.update(func_targets)
        if tree_targets:
            self.tree_prewarmed = dict(tree_targets)
        else:
            self.tree_prewarmed.clear()
        self._reconcile_prewarmed_containers()

    def _reconcile_prewarmed_containers(self):
        """Ensures that the number of warm containers meets target min_scale."""
        for fid, target_count in self.min_scale_targets.items():
            current_count = len(self.warm_pools[fid]) + len(self.busy_pools[fid])
            spec = self.functions[fid]
            while current_count < target_count:
                # Spawn prewarmed container
                self._container_counter += 1
                c = Container(
                    container_id=self._container_counter,
                    function_id=fid,
                    state=ContainerState.WARM,
                    memory_mb=spec.memory_mb,
                    last_active_time=self.current_time,
                    busy_until=0.0
                )
                self.warm_pools[fid].append(c)
                current_count += 1

    def _free_busy_containers(self):
        """Transitions finished containers from busy back to warm."""
        for fid, busy_list in self.busy_pools.items():
            still_busy = []
            for c in busy_list:
                if c.busy_until <= self.current_time:
                    c.state = ContainerState.WARM
                    c.last_active_time = self.current_time
                    self.warm_pools[fid].append(c)
                else:
                    still_busy.append(c)
            self.busy_pools[fid] = still_busy

    def _reclaim_expired_idle(self):
        """Reclaims idle containers exceeding timeout and above min_scale target."""
        for fid, warm_list in self.warm_pools.items():
            target_min = self.min_scale_targets.get(fid, 0)
            retained = []
            for c in warm_list:
                idle_duration = self.current_time - c.last_active_time
                if idle_duration > self.idle_timeout_sec and (len(retained) + len(self.busy_pools[fid])) >= target_min:
                    c.state = ContainerState.RECLAIMED
                else:
                    retained.append(c)
            self.warm_pools[fid] = retained

    def calculate_memory_usage(self) -> Tuple[float, float]:
        """Returns (total_used_memory_mb, idle_memory_mb)."""
        used_mem = 0.0
        idle_mem = 0.0
        for fid, c_list in self.busy_pools.items():
            used_mem += sum(c.memory_mb for c in c_list)
        for fid, c_list in self.warm_pools.items():
            idle_mem += sum(c.memory_mb for c in c_list)
            used_mem += sum(c.memory_mb for c in c_list)
        return used_mem, idle_mem

    def _compute_granularity_cold_delay(self, spec: FunctionSpec) -> float:
        """Calculates effective cold-start delay factoring in prewarmed dependency nodes."""
        base_cold = spec.cold_start_ms
        if not self.tree_prewarmed:
            return base_cold

        # If shared nodes on dependency path are prewarmed, deduct their init times
        saved_ms = 0.0
        for node_id in spec.dependency_path:
            if self.tree_prewarmed.get(node_id, 0) > 0:
                node_info = self.nodes.get(node_id, {})
                saved_ms += float(node_info.get("init_time_ms", 0.0))

        effective_cold = max(base_cold - saved_ms, spec.warm_start_ms)
        return effective_cold

    def step_invoke(self, function_id: str, invocation_time: float) -> InvocationRecord:
        """Simulates single invocation arriving at invocation_time."""
        self.current_time = max(self.current_time, invocation_time)
        self._free_busy_containers()
        self._reclaim_expired_idle()

        spec = self.functions[function_id]
        warm_list = self.warm_pools[function_id]

        used_mem, _ = self.calculate_memory_usage()

        if len(warm_list) > 0:
            # WARM HIT: Fast execution from prewarmed/idle container
            container = warm_list.pop(0)
            is_cold = False
            latency = spec.warm_start_ms + spec.execution_time_ms
            container.state = ContainerState.BUSY
            container.busy_until = self.current_time + (latency / 1000.0)
            self.busy_pools[function_id].append(container)
        else:
            # COLD START: Must provision container or wait if memory budget exceeded
            is_cold = True
            effective_cold = self._compute_granularity_cold_delay(spec)

            # Check if spawning a new container would exceed memory budget
            if (used_mem + spec.memory_mb) > self.memory_budget_mb and self.busy_pools[function_id]:
                # Queue request on earliest completing container of this function
                earliest_busy = min(self.busy_pools[function_id], key=lambda c: c.busy_until)
                queue_wait_ms = max(0.0, (earliest_busy.busy_until - self.current_time) * 1000.0)
                latency = queue_wait_ms + spec.warm_start_ms + spec.execution_time_ms
                earliest_busy.busy_until += (spec.warm_start_ms + spec.execution_time_ms) / 1000.0
                is_cold = False  # Reused already-warm container after queuing
            else:
                self._container_counter += 1
                container = Container(
                    container_id=self._container_counter,
                    function_id=function_id,
                    state=ContainerState.BUSY,
                    memory_mb=spec.memory_mb,
                    last_active_time=self.current_time,
                    busy_until=self.current_time + ((effective_cold + spec.execution_time_ms) / 1000.0)
                )
                latency = effective_cold + spec.execution_time_ms
                self.busy_pools[function_id].append(container)

        used_mem, idle_mem = self.calculate_memory_usage()
        is_sla_violation = (latency > spec.sla_threshold_ms)

        record = InvocationRecord(
            timestamp=invocation_time,
            function_id=function_id,
            latency_ms=latency,
            is_cold_start=is_cold,
            is_sla_violation=is_sla_violation,
            memory_used_mb=used_mem,
            idle_memory_mb=idle_mem
        )
        self.records.append(record)
        return record

    def get_summary_metrics(self) -> Dict[str, float]:
        """Computes aggregate statistical metrics from recorded run."""
        if not self.records:
            return {}

        latencies = np.array([r.latency_ms for r in self.records])
        cold_flags = np.array([1.0 if r.is_cold_start else 0.0 for r in self.records])
        sla_flags = np.array([1.0 if r.is_sla_violation else 0.0 for r in self.records])
        mem_used = np.array([r.memory_used_mb for r in self.records])
        mem_idle = np.array([r.idle_memory_mb for r in self.records])

        return {
            "total_requests": float(len(self.records)),
            "mean_latency_ms": float(np.mean(latencies)),
            "median_latency_ms": float(np.median(latencies)),
            "p95_latency_ms": float(np.percentile(latencies, 95)),
            "p99_latency_ms": float(np.percentile(latencies, 99)),
            "cold_start_rate_pct": float(np.mean(cold_flags) * 100.0),
            "sla_violation_rate_pct": float(np.mean(sla_flags) * 100.0),
            "avg_memory_used_mb": float(np.mean(mem_used)),
            "avg_memory_idle_mb": float(np.mean(mem_idle)),
            "max_memory_mb": float(np.max(mem_used))
        }
