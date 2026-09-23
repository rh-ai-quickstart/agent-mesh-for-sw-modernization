import os
import time

from .basic_token_logger import BasicTokenLogger


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
            kfp_run_id = os.environ.get("KFP_RUN_ID", "").strip()
            tags = {"mlflow.runName": "token_usage"}
            if kfp_run_id:
                tags["kfp_run_id"] = kfp_run_id
            experiment = client.get_experiment_by_name(self._experiment_name)
            experiment_id = (
                experiment.experiment_id
                if experiment
                else client.create_experiment(self._experiment_name)
            )
            self.run_id = client.create_run(
                experiment_id=experiment_id, tags=tags
            ).info.run_id

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
