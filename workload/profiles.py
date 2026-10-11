import math
from abc import ABC, abstractmethod
from typing import Dict


class WorkloadProfile(ABC):
    """Abstract base class for benchmark workload arrival rate models W1–W5."""

    @abstractmethod
    def get_rate(self, t: float, base_rate: float, func_index: int = 0, total_funcs: int = 12) -> float:
        """Returns instantaneous target request rate (req/s) at time t."""
        pass


class W1StableProfile(WorkloadProfile):
    """W1: Constant-rate stationary Poisson process."""

    def get_rate(self, t: float, base_rate: float, func_index: int = 0, total_funcs: int = 12) -> float:
        return max(base_rate, 0.01)


class W2GradualGrowthProfile(WorkloadProfile):
    """W2: Linearly increasing workload stress test (ramp-up)."""

    def __init__(self, growth_slope: float = 0.002):
        self.growth_slope = growth_slope

    def get_rate(self, t: float, base_rate: float, func_index: int = 0, total_funcs: int = 12) -> float:
        rate = base_rate * (1.0 + self.growth_slope * t)
        return max(rate, 0.01)


class W3BurstyProfile(WorkloadProfile):
    """W3: Bursty traffic with periodic 10x flash crowd spikes lasting 60s every 300s."""

    def __init__(self, burst_multiplier: float = 10.0, burst_duration: float = 60.0, burst_interval: float = 300.0):
        self.burst_multiplier = burst_multiplier
        self.burst_duration = burst_duration
        self.burst_interval = burst_interval

    def get_rate(self, t: float, base_rate: float, func_index: int = 0, total_funcs: int = 12) -> float:
        cycle_pos = t % self.burst_interval
        if cycle_pos < self.burst_duration:
            return base_rate * self.burst_multiplier
        return max(base_rate, 0.01)


class W4PeriodicProfile(WorkloadProfile):
    """W4: Sinusoidal diurnal / cyclic workload pattern."""

    def __init__(self, period: float = 600.0, amplitude: float = 0.8):
        self.period = period
        self.amplitude = amplitude

    def get_rate(self, t: float, base_rate: float, func_index: int = 0, total_funcs: int = 12) -> float:
        modulation = 1.0 + self.amplitude * math.sin(2.0 * math.pi * t / self.period)
        return max(base_rate * modulation, 0.01)


class W5NonStationaryProfile(WorkloadProfile):
    """W5: Abrupt regime change at t = duration/2 with popularity inversion."""

    def __init__(self, switch_time: float = 900.0):
        self.switch_time = switch_time

    def get_rate(self, t: float, base_rate: float, func_index: int = 0, total_funcs: int = 12) -> float:
        if t < self.switch_time:
            # Baseline phase
            return max(base_rate, 0.01)
        else:
            # Inversion phase: reverse function popularity weighting
            inverted_factor = (total_funcs - func_index) / max(func_index + 1, 1)
            return max(base_rate * 1.5 * inverted_factor, 0.01)


def get_profile(name: str, **kwargs) -> WorkloadProfile:
    name_upper = name.strip().upper()
    if name_upper == "W1":
        return W1StableProfile()
    elif name_upper == "W2":
        slope = kwargs.get("growth_slope", 0.002)
        return W2GradualGrowthProfile(growth_slope=slope)
    elif name_upper == "W3":
        mult = kwargs.get("burst_multiplier", 10.0)
        dur = kwargs.get("burst_duration", 60.0)
        inv = kwargs.get("burst_interval", 300.0)
        return W3BurstyProfile(burst_multiplier=mult, burst_duration=dur, burst_interval=inv)
    elif name_upper == "W4":
        period = kwargs.get("period", 600.0)
        amp = kwargs.get("amplitude", 0.8)
        return W4PeriodicProfile(period=period, amplitude=amp)
    elif name_upper == "W5":
        sw = kwargs.get("switch_time", 900.0)
        return W5NonStationaryProfile(switch_time=sw)
    else:
        raise ValueError(f"Unknown workload profile: {name}. Supported: W1, W2, W3, W4, W5")
