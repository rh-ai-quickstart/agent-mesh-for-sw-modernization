import os
import time

from .basic_token_logger import BasicTokenLogger


def get_mlflow_callback():
    if os.environ.get("RHOAI_MLFLOW_COST_MONITORING_ENABLED", "false").lower() != "true":
        return "mlflow"

    from litellm.integrations.mlflow import MlflowLogger

    class _CostAwareMlflowLogger(MlflowLogger):
        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            if not kwargs.get("response_cost"):
                cost = getattr(getattr(response_obj, "usage", None), "cost", None)
                if cost:
                    kwargs["response_cost"] = cost
            super().log_success_event(kwargs, response_obj, start_time, end_time)

        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            if not kwargs.get("response_cost"):
                cost = getattr(getattr(response_obj, "usage", None), "cost", None)
                if cost:
                    kwargs["response_cost"] = cost
            await super().async_log_success_event(kwargs, response_obj, start_time, end_time)

    return _CostAwareMlflowLogger()


class MlflowTokenLogger(BasicTokenLogger):
    """Token logger that persists cumulative token metrics to an MLflow run."""

    def __init__(self, experiment_name: str):
        super().__init__()
        self._experiment_name = experiment_name

    def log_tokens(self) -> None:
        from mlflow.entities import Metric
        from mlflow.tracking import MlflowClient

        if not self.totals:
            return

        client = MlflowClient()

        if not self.run_id:
            from utils.pipeline_utils import get_pipeline_run_id

            pipeline_run_id = get_pipeline_run_id()
            tags = {"mlflow.runName": "token_usage"}
            if pipeline_run_id:
                tags["pipeline_run_id"] = pipeline_run_id
            experiment = client.get_experiment_by_name(self._experiment_name)
            experiment_id = (
                experiment.experiment_id
                if experiment
                else client.create_experiment(self._experiment_name)
            )
            self.run_id = client.create_run(experiment_id=experiment_id, tags=tags).info.run_id

        client.log_batch(
            self.run_id,
            metrics=[
                Metric(key=k, value=float(v), timestamp=int(time.time() * 1000), step=self.step)
                for k, v in self.totals.items()
            ],
        )

    def finalize(self) -> None:
        if self.run_id:
            try:
                from mlflow.tracking import MlflowClient

                MlflowClient().set_terminated(self.run_id, "FINISHED")
            except Exception:
                pass
