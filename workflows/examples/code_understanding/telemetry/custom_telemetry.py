from abc import ABC, abstractmethod


class CustomTelemetry(ABC):
    """Abstract base class for telemetry providers."""

    @abstractmethod
    def track(self):
        """Enable telemetry instrumentation for LLM calls."""

    @staticmethod
    @abstractmethod
    def get_token_usage(kfp_run_id: str) -> dict:
        """Return aggregated token usage for a KFP run."""
