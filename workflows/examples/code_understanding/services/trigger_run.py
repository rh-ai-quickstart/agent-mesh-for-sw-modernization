"""Submit a KFP pipeline run by name."""

from __future__ import annotations

import json
import logging
from typing import Any

from utils.service_utils import create_client, find_pipeline_id, latest_version_id


def trigger_run(
    pipeline_name: str,
    run_name: str,
    params: dict[str, str],
    repos: list[dict[str, str]] | None = None,
    namespace: str | None = None,
) -> Any:
    """Look up a pipeline, resolve its latest version, and submit a run.

    If ``repos`` is provided the list is uploaded to the asset store tagged
    with the KFP run ID so that ``get_repo_list_op`` can retrieve it via
    ``asset_tags={"kfp_run_id": ...}``.
    """
    client = create_client(namespace=namespace)
    pipeline_id = find_pipeline_id(client, pipeline_name)
    version_id = latest_version_id(client, pipeline_id)
    experiment = client.create_experiment(name="Default")
    run = client.run_pipeline(
        experiment_id=experiment.experiment_id,
        job_name=run_name,
        pipeline_id=pipeline_id,
        version_id=version_id,
        params=params,
        enable_caching=False,
    )

    if repos is not None:
        try:
            from loaders.default_asset_loader import DefaultAssetLoader

            DefaultAssetLoader().log_static_asset(
                "repo_list.json",
                artifact_path="repos",
                content=json.dumps(
                    [
                        {"git_repo": r["git_repo"], "git_branch": r.get("git_branch", "main")}
                        for r in repos
                    ]
                ),
                tags={"kfp_run_id": run.run_id},
            )
        except Exception:
            logging.exception(
                "Pipeline run %s was submitted but the repo list could not be uploaded. "
                "The multi-repo pipeline will fail to retrieve its repo list.",
                run.run_id,
            )

    return run
