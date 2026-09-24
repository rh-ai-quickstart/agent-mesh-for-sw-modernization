"""Adhoc query execution for the v2 API."""

from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

# Make the code_understanding package importable.
_CU_ROOT = str(
    Path(__file__).resolve().parent.parent / "workflows" / "examples" / "code_understanding"
)
if _CU_ROOT not in sys.path:
    sys.path.insert(0, _CU_ROOT)

# Self-signed certificate bypass.
# GRAPHRAG_LOCAL_QUERY_SKIP_TLS_VERIFY: patches ssl.create_default_context at import
#   time in graphrag_utils.py (covers stdlib/urllib3 paths).
# SSL_VERIFY: litellm 1.x reads this via get_ssl_verify() and passes verify=False
#   directly to httpx.Client (covers the litellm/openai embedding path).
os.environ.setdefault("GRAPHRAG_LOCAL_QUERY_SKIP_TLS_VERIFY", "true")
os.environ.setdefault("SSL_VERIFY", "false")

# graspologic -> hyppo -> numba: Numba cannot resolve a cache path when site-packages
# is accessed through the lib64 -> lib symlink on RHEL/OpenShift containers.
# Redirect the cache to a writable temp directory before numba is imported.
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_cache")

import services  # noqa: E402

_jobs: dict[str, dict[str, Any]] = {}

_TERMINAL = {"succeeded", "failed"}


def submit_query(
    question: str,
    retry_count: int = 3,
    use_global: bool = True,
    git_repo: str = "",
    git_branch: str = "main",
    multi_repo: bool = False,
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("Question must not be empty.")
    query_id = str(uuid.uuid4())
    _jobs[query_id] = {"status": "running", "result": None, "error": None}

    def _run():
        try:
            result = services.run_adhoc_query(
                question=question,
                retry_count=retry_count,
                use_global=use_global,
                git_repo=git_repo,
                git_branch=git_branch,
                multi_repo=multi_repo,
            )
            _jobs[query_id] = {"status": "succeeded", "result": result, "error": None}
        except Exception as exc:
            _jobs[query_id] = {"status": "failed", "result": None, "error": str(exc)}

    threading.Thread(target=_run, daemon=True).start()
    return {"query_id": query_id}


def get_query_status(query_id: str) -> dict[str, Any]:
    job = _jobs.get(query_id)
    if not job:
        raise ValueError(f"Query job {query_id!r} not found.")
    if job["status"] in _TERMINAL:
        del _jobs[query_id]
    return job
