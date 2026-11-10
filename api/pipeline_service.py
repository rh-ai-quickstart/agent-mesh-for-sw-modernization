"""KFP pipeline submission and status for the v2 API."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the code_understanding package importable so we can reuse its loaders,
# artifact-path helpers, git-slug generation, and services.
_CU_ROOT = str(
    Path(__file__).resolve().parent.parent / "workflows" / "examples" / "code_understanding"
)
if _CU_ROOT not in sys.path:
    sys.path.insert(0, _CU_ROOT)

from services.fetch_reports import fetch_reports as _fetch_reports  # noqa: E402
from services.get_run_status import get_kfp_run_state  # noqa: E402
from services.list_runs import get_run_git_metadata, list_kfp_runs  # noqa: E402
from services.trigger_run import trigger_run as _trigger_run  # noqa: E402
from services.update_repos import log_repos  # noqa: E402


def submit_pipeline_run(
    repos: list[dict[str, str]], namespace: str | None = None, pipeline_run_id: str = ""
) -> dict[str, Any]:
    if not repos:
        raise ValueError("Select at least one repository.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    single = len(repos) == 1
    git_repo = repos[0]["git_repo"] if single else ""
    git_branch = repos[0].get("git_branch", "main") if single else "main"
    pipeline_name = "single_repo" if single else "multi_repo"
    run_name = f"{pipeline_name}_{timestamp}"
    mode = "single-repo" if single else "multi-repo"
    enable_caching = bool(pipeline_run_id)

    params: dict[str, Any] = {
        **({"git_repo": git_repo, "git_branch": git_branch} if single else {}),
        "runnable_repos": json.dumps(repos),
        "pipeline_run_id": pipeline_run_id,
        "parent_source_path": os.getenv("PARENT_SOURCE_PATH", "source"),
        "parent_target_path": os.getenv("PARENT_TARGET_PATH", "target"),
    }

    try:
        log_repos(repos, namespace)
    except Exception:
        logging.info("log_repos failed; continuing with pipeline submission.", exc_info=True)

    run = _trigger_run(
        pipeline_name,
        run_name,
        params,
        namespace=namespace,
        enable_caching=enable_caching,
    )
    return {"job_id": run.run_id, "mode": mode, "run_name": run_name}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def list_pipeline_runs(namespace: str | None = None) -> list[dict[str, Any]]:
    """Return all KFP runs newest-first, plus uploaded indexes as synthetic entries."""
    runs = list_kfp_runs(namespace=namespace)
    try:
        try:
            from ui.indexes import list_uploaded_indexes_as_runs
        except ImportError:
            from indexes import list_uploaded_indexes_as_runs

        runs.extend(list_uploaded_indexes_as_runs())
    except Exception:
        logging.debug("Uploaded-index discovery failed", exc_info=True)
    return runs


def get_run_status(job_id: str, namespace: str | None = None) -> dict[str, Any]:
    state = get_kfp_run_state(job_id, namespace=namespace)

    evaluation_report: str | None = None
    analysis_report: str | None = None
    evaluation_scores: dict[str, Any] | None = None
    if state in {"SUCCEEDED", "SKIPPED"}:
        git_slug, multi_repo = get_run_git_metadata(job_id, namespace=namespace)
        evaluation_report, analysis_report = _fetch_reports(job_id, git_slug, multi_repo)
        if evaluation_report:
            from utils.eval_utils import aggregate_evaluation_scores

            evaluation_scores = aggregate_evaluation_scores(evaluation_report)

    return {
        "status": state.lower(),
        "evaluation_report": evaluation_report,
        "analysis_report": analysis_report,
        "evaluation_scores": evaluation_scores,
    }
