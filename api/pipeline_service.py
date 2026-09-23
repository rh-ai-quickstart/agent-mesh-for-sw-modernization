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
    Path(__file__).resolve().parent.parent
    / "workflows" / "examples" / "code_understanding"
)
if _CU_ROOT not in sys.path:
    sys.path.insert(0, _CU_ROOT)

from services.trigger_run import trigger_run as _trigger_run
from services.fetch_reports import fetch_reports as _fetch_reports
from services.get_run_status import get_kfp_run_state
from services.list_runs import list_kfp_runs, get_run_git_metadata
from telemetry.default_custom_telemetry import DefaultCustomTelemetry


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def submit_pipeline_run(repos: list[dict[str, str]]) -> dict[str, Any]:
    if not repos:
        raise ValueError("Select at least one repository.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    single = len(repos) == 1
    git_repo = repos[0]["git_repo"] if single else ""
    git_branch = repos[0].get("git_branch", "main") if single else "main"
    pipeline_name = "single_repo" if single else "multi_repo"
    run_name = f"{pipeline_name}_{timestamp}"
    mode = "single-repo" if single else "multi-repo"

    params: dict[str, str] = {
        **({"git_repo": git_repo, "git_branch": git_branch} if single else {}),
        "parent_source_path": os.getenv("PARENT_SOURCE_PATH", "source"),
        "parent_target_path": os.getenv("PARENT_TARGET_PATH", "target"),
    }

    run = _trigger_run(pipeline_name, run_name, params, repos=None if single else repos)
    return {"job_id": run.run_id, "mode": mode, "run_name": run_name}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def list_pipeline_runs() -> list[dict[str, Any]]:
    """Return all KFP runs newest-first with their current status."""
    return list_kfp_runs()


def get_run_status(job_id: str) -> dict[str, Any]:
    state = get_kfp_run_state(job_id)

    evaluation_report: str | None = None
    analysis_report: str | None = None
    if state in {"SUCCEEDED", "SKIPPED"}:
        git_slug, multi_repo = get_run_git_metadata(job_id)
        evaluation_report, analysis_report = _fetch_reports(git_slug, multi_repo)

    return {
        "status": state.lower(),
        "evaluation_report": evaluation_report,
        "analysis_report": analysis_report,
        "token_usage": DefaultCustomTelemetry.get_token_usage(job_id) if state in {"SUCCEEDED", "SKIPPED"} else {},
    }
