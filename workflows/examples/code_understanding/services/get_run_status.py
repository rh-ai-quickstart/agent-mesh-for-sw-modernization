"""Fetch and normalise the state of a KFP run."""

from __future__ import annotations

from utils.service_utils import create_client


def get_kfp_run_state(job_id: str, namespace: str | None = None) -> str:
    """Return the normalised uppercase state string for a KFP run."""
    client = create_client(namespace=namespace)
    try:
        run_detail = client.get_run(run_id=job_id)
    except Exception as exc:
        raise ValueError(f"KFP run '{job_id}' not found: {exc}") from exc

    run_obj = getattr(run_detail, "run", run_detail)
    state_raw = getattr(run_obj, "state", None) or getattr(run_obj, "runtime_state", None)
    state = str(getattr(state_raw, "name", state_raw) or "PENDING").upper()
    if not state or state in ("NONE", "RUNTIME_STATE_UNSPECIFIED"):
        state = "PENDING"
    return state
