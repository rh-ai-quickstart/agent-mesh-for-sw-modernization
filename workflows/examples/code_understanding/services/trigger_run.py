"""Submit a KFP pipeline run by name."""

from __future__ import annotations

from typing import Any

from utils.service_utils import create_client, find_pipeline_id, latest_version_id


def trigger_run(pipeline_name: str, run_name: str, params: dict[str, str]) -> Any:
    """Look up a pipeline, resolve its latest version, and submit a run."""
    client = create_client()
    pipeline_id = find_pipeline_id(client, pipeline_name)
    version_id = latest_version_id(client, pipeline_id)
    experiment = client.create_experiment(name="Default")
    return client.run_pipeline(
        experiment_id=experiment.experiment_id,
        job_name=run_name,
        pipeline_id=pipeline_id,
        version_id=version_id,
        params=params,
        enable_caching=False,
    )
