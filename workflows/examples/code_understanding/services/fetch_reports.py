"""Download evaluation and analysis reports from MLflow."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
import traceback  # noqa: E402


def _read_dir_contents(path: str) -> str | None:
    p = Path(path)
    if not p.is_dir():
        return None
    parts = [
        f.read_text(encoding="utf-8", errors="replace")
        for f in sorted(p.rglob("*"))
        if f.is_file()
    ]
    return "\n".join(parts) or None


def fetch_reports(git_slug: str | None, multi_repo: bool) -> tuple[str | None, str | None]:
    """Return (evaluation_report, analysis_report) downloaded from MLflow."""
    if not multi_repo and not git_slug:
        return None, None
    try:
        from loaders.asset_loader import AssetLoader
        from loaders.mlflow_asset_loader import MlFlowAssetLoader

        loader = MlFlowAssetLoader()
        base_tags: dict[str, Any] = (
            {"multi_repo": True} if multi_repo else ({"git_slug": git_slug} if git_slug else {})
        )

        def _get(prefix: str, category: str) -> str | None:
            artifact_path = AssetLoader.get_log_results_artifact_path(
                prefix, git_slug=git_slug, multi_repo=multi_repo
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    loader.download_dir(
                        artifact_path,
                        download_dir=tmpdir,
                        experiment_name=loader.RESULT_ASSET_EXPERIMENT,
                        asset_tags={**base_tags, "category": category},
                    )
                    content = _read_dir_contents(tmpdir)
                    logging.info(
                        f"Downloaded {category} report from artifact '{artifact_path}', "
                        f"git_slug='{git_slug}', multi_repo='{multi_repo}'"
                    )
                    logging.debug(f"Contents: {content}")
                    return content
                except Exception:
                    logging.error(
                        f"Error: Could not download {category} report"
                        f" from artifact '{artifact_path}', "
                        f"tags: {base_tags}, experiment: {loader.RESULT_ASSET_EXPERIMENT}"
                    )
                    logging.error(traceback.format_exc())
                    return None

        return (
            _get(AssetLoader.RESULTS_PATH_PREFIX_EVAL, "evaluation"),
            _get(AssetLoader.RESULTS_PATH_PREFIX_PIPELINES, "analysis"),
        )
    except Exception:
        logging.error(
            f"Could not fetch reports for git_slug='{git_slug}', multi_repo='{multi_repo}':"
        )
        logging.error(traceback.format_exc())
        return None, None
