"""Adhoc query execution for the v2 API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Make the code_understanding package importable.
_CU_ROOT = str(
    Path(__file__).resolve().parent.parent
    / "workflows" / "examples" / "code_understanding"
)
if _CU_ROOT not in sys.path:
    sys.path.insert(0, _CU_ROOT)

from services.run_adhoc_query import run_adhoc_query as _run_adhoc_query


def run_query(
    question: str,
    retry_count: int = 3,
    use_global: bool = True,
    git_repo: str = "",
    git_branch: str = "main",
    multi_repo: bool = False,
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("Question must not be empty.")
    result = _run_adhoc_query(
        question=question,
        retry_count=retry_count,
        use_global=use_global,
        git_repo=git_repo,
        git_branch=git_branch,
        multi_repo=multi_repo,
    )
    return {"result": result}
