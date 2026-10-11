class GranuWarmError(Exception):
    """Base exception for all GranuWarm errors."""

class TelemetryError(GranuWarmError):
    """Raised when required telemetry is missing, stale, or invalid."""

class ContractValidationError(GranuWarmError):
    """Raised when a contract object fails validation."""

class InfeasibleAllocationError(GranuWarmError):
    """Raised when an allocation cannot be repaired to fit the budget."""

class ActuationError(GranuWarmError):
    """Raised when the actuator cannot apply a decision."""