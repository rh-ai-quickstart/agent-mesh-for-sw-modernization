"""KFP pipeline submission and status for the v2 API."""

from __future__ import annotations

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

# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


def submit_pipeline_run(
    repos: list[dict[str, str]],
    namespace: str | None = None,
    *,
    analysis_only: bool = False,
    multi_repo: bool = False,
) -> dict[str, Any]:
    if multi_repo and not analysis_only:
        raise ValueError("The multi_repo flag requires analysis_only=true.")
    if analysis_only:
        if multi_repo:
            if repos:
                raise ValueError("Combined-index analysis must not include repositories.")
        elif len(repos) != 1 or not repos[0].get("git_repo", "").strip():
            raise ValueError("Select one indexed repository or the combined multi-repo index.")
    elif not repos:
        raise ValueError("Select at least one repository.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    single = not multi_repo and len(repos) == 1
    git_repo = repos[0]["git_repo"] if single else ""
    git_branch = repos[0].get("git_branch", "main") if single else "main"
    pipeline_name = "single_repo" if single else "multi_repo"
    run_name = f"{pipeline_name}{'_analysis' if analysis_only else ''}_{timestamp}"
    mode = "single-repo" if single else "multi-repo"

    params: dict[str, Any] = {
        **({"git_repo": git_repo, "git_branch": git_branch} if single else {}),
        "parent_source_path": os.getenv("PARENT_SOURCE_PATH", "source"),
        "parent_target_path": os.getenv("PARENT_TARGET_PATH", "target"),
    }
    if analysis_only:
        params["analysis_only"] = True

    run = _trigger_run(
        pipeline_name,
        run_name,
        params,
        repos=None if single or analysis_only else repos,
        namespace=namespace,
    )
    return {"job_id": run.run_id, "mode": mode, "run_name": run_name}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def list_pipeline_runs(namespace: str | None = None) -> list[dict[str, Any]]:
    """Return all KFP runs newest-first with their current status."""
    return list_kfp_runs(namespace=namespace)


def get_run_status(job_id: str, namespace: str | None = None) -> dict[str, Any]:
    state = get_kfp_run_state(job_id, namespace=namespace)

    evaluation_report: str | None = None
    analysis_report: str | None = None
    if state in {"SUCCEEDED", "SKIPPED"}:
        git_slug, multi_repo = get_run_git_metadata(job_id, namespace=namespace)
        evaluation_report, analysis_report = _fetch_reports(git_slug, multi_repo, job_id)

    return {
        "status": state.lower(),
        "evaluation_report": evaluation_report,
        "analysis_report": analysis_report,
    }
