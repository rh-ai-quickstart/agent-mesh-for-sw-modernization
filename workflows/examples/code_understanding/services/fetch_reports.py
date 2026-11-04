"""Download evaluation and analysis reports from MLflow."""

from __future__ import annotations

import logging
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient


def fetch_reports(
    git_slug: str | None, multi_repo: bool, kfp_run_id: str
) -> tuple[str | None, str | None]:
    """Return reports belonging to the selected KFP run."""
    if not multi_repo and not git_slug:
        return None, None

    from loaders.asset_loader import AssetLoader
    from loaders.mlflow_asset_loader import MlFlowAssetLoader

    try:
        loader = MlFlowAssetLoader()
        client = MlflowClient()
        experiment = client.get_experiment_by_name(loader.RESULT_ASSET_EXPERIMENT)
    except Exception:
        logging.exception("Could not connect to MLflow to fetch reports")
        return None, None
    if experiment is None:
        logging.error(
            "MLflow results experiment '%s' was not found",
            loader.RESULT_ASSET_EXPERIMENT,
        )
        return None, None

    base_tags = {"multi_repo": True} if multi_repo else {"git_slug": git_slug}

    def _get(prefix: str, category: str, suffix: str) -> str | None:
        artifact_path = AssetLoader.get_log_results_artifact_path(
            prefix, git_slug=git_slug, multi_repo=multi_repo
        )
        tags = {**base_tags, "category": category, "kfp_run_id": kfp_run_id}
        filter_string = " AND ".join(f"tags.\"{key}\" = '{value}'" for key, value in tags.items())
        try:
            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                filter_string=filter_string,
                order_by=["attributes.start_time DESC"],
                max_results=100,
            )
            # Query results share the "analysis" tag but have no pipeline report.
            run = next(
                (r for r in runs if str(r.data.tags.get("adhoc_query", "")).lower() != "true"),
                None,
            )
            if run is None:
                logging.warning(
                    "No %s MLflow report run found for KFP run %s", category, kfp_run_id
                )
                return None

            files = client.list_artifacts(run.info.run_id, artifact_path)
            report_files = [f for f in files if not f.is_dir and f.path.endswith(suffix)]
            if len(report_files) != 1:
                logging.error(
                    "Expected one %s report in MLflow run %s at %s; found %s",
                    category,
                    run.info.run_id,
                    artifact_path,
                    [f.path for f in files],
                )
                return None

            report_path = report_files[0].path
            local_path = mlflow.artifacts.download_artifacts(
                run_id=run.info.run_id, artifact_path=report_path
            )
            logging.info(
                "Downloaded %s report from MLflow run %s, artifact %s",
                category,
                run.info.run_id,
                report_path,
            )
            return Path(local_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            logging.exception(
                "Could not download %s report from %s",
                category,
                artifact_path,
            )
            return None

    return (
        _get(AssetLoader.RESULTS_PATH_PREFIX_EVAL, "evaluation", ".csv"),
        _get(AssetLoader.RESULTS_PATH_PREFIX_PIPELINES, "analysis", ".md"),
    )
