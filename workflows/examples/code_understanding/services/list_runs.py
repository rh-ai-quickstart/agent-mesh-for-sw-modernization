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


def list_kfp_runs(page_size: int = 50) -> list[dict[str, Any]]:
    """Return KFP runs newest-first as a list of {name, status} dicts."""
    client = create_client()
    result = client.list_runs(page_size=page_size, sort_by="created_at desc")
    runs = getattr(result, "runs", None) or []
    return [
        {
            "name": getattr(r, "display_name", None) or getattr(r, "name", ""),
            "status": _normalize_state(r).capitalize(),
        }
        for r in runs
    ]
