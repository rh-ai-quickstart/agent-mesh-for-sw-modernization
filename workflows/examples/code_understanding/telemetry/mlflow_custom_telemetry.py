import atexit
import logging
import os

import mlflow

from .custom_telemetry import CustomTelemetry

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())


class MlFlowCustomTelemetry(CustomTelemetry):
    """MLflow telemetry provider. Enables LiteLLM autologging for token counts and latency."""

    _DEFAULT_EXPERIMENT_NAME = None

    def _get_default_experiment_name(self) -> str:
        """Returns the experiment name from the MLFLOW_EXPERIMENT_NAME env var."""
        return os.environ.get("MLFLOW_EXPERIMENT_NAME", "AIP-default")

    def __init__(self):
        if not MlFlowCustomTelemetry._DEFAULT_EXPERIMENT_NAME:
            MlFlowCustomTelemetry._DEFAULT_EXPERIMENT_NAME = self._get_default_experiment_name()

        logging.info(
            "MlFlowCustomTelemetry: default experiment resolved to "
            f"'{self._DEFAULT_EXPERIMENT_NAME}'"
        )

    def track(self):
        import litellm

        from .telemetry_litellm.mlflow_token_logger import MlflowTokenLogger, get_mlflow_callback

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")

        logging.debug(f"MlFlowCustomTelemetry.track() called. MLFLOW_TRACKING_URI={tracking_uri}")

        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)

        mlflow.set_experiment(self._DEFAULT_EXPERIMENT_NAME)

        counter = MlflowTokenLogger(self._DEFAULT_EXPERIMENT_NAME)
        litellm.callbacks = [counter, get_mlflow_callback()]

        atexit.register(counter.finalize)

    @staticmethod
    def get_token_usage(kfp_run_id: str) -> dict:
        from mlflow.tracking import MlflowClient

        try:
            client = MlflowClient()
            experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "AIP-default")
            experiment = client.get_experiment_by_name(experiment_name)
            if not experiment:
                return {}
            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                filter_string=f"tags.kfp_run_id = '{kfp_run_id}'",
            )
            totals: dict[str, int] = {}
            for run in runs:
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    val = run.data.metrics.get(key)
                    if val is not None:
                        totals[key] = totals.get(key, 0) + int(val)
                cost = run.data.metrics.get("cost_usd")
                if cost is not None:
                    totals["cost_usd"] = totals.get("cost_usd", 0.0) + cost
            return totals
        except Exception:
            return {}
