"""List all KFP pipeline runs."""

from __future__ import annotations

from typing import Any

from utils.service_utils import create_client


def _normalize_state(run_obj: Any) -> str:
    state_raw = getattr(run_obj, "state", None) or getattr(run_obj, "runtime_state", None)
    state = str(getattr(state_raw, "name", state_raw) or "PENDING").upper()
    if not state or state in ("NONE", "RUNTIME_STATE_UNSPECIFIED"):
        state = "PENDING"
    return state


def _get_git_slug(run_obj: Any) -> str | None:
    """Derive a git slug from the run's runtime_config parameters, if present.

    Returns None for multi-repo runs, which do not include git_repo in their params.
    """
    try:
        params = getattr(getattr(run_obj, "runtime_config", None), "parameters", None) or {}
        git_repo = params.get("git_repo") or ""
        git_branch = params.get("git_branch") or ""
        if not git_repo:
            return None
        from pipelines.base.data_generation import generate_git_slug
        return generate_git_slug(git_repo, git_branch)
    except Exception:
        return None


def _get_run_start_date_time(run_obj: Any) -> str | None:
    start_raw = getattr(run_obj, "created_at", None) or getattr(run_obj, "scheduled_at", None)
    if start_raw is None:
        return None
    return start_raw.isoformat() if hasattr(start_raw, "isoformat") else str(start_raw)


def list_kfp_runs(page_size: int = 50) -> list[dict[str, Any]]:
    """Return KFP runs newest-first as a list of {run_id, name, status, start_time} dicts."""
    client = create_client()
    result = client.list_runs(page_size=page_size, sort_by="created_at desc")
    runs = getattr(result, "runs", None) or []
    out = []
    for r in runs:
        params = getattr(getattr(r, "runtime_config", None), "parameters", None) or {}
        git_repo = params.get("git_repo") or ""
        git_branch = params.get("git_branch") or ""
        out.append({
            "run_id": getattr(r, "run_id", None) or getattr(r, "id", ""),
            "name": getattr(r, "display_name", None) or getattr(r, "name", ""),
            "status": _normalize_state(r).capitalize(),
            "start_time": _get_run_start_date_time(r),
            "git_slug": _get_git_slug(r),
            "git_repo": git_repo or None,
            "git_branch": git_branch or None,
        })
    return out
