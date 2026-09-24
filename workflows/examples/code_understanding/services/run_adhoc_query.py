"""Run a GraphRAG adhoc query using the analysis pipeline."""

from __future__ import annotations


def run_adhoc_query(
    question: str,
    retry_count: int = 3,
    use_global: bool = True,
    git_repo: str = "",
    git_branch: str = "main",
    multi_repo: bool = False,
) -> str:
    """Query the GraphRAG index with an LLM and return the result."""
    from pipelines.base.analysis import run_adhoc_query_pipeline

    return run_adhoc_query_pipeline(
        question=question,
        retry_count=retry_count,
        use_global=use_global,
        git_repo=git_repo,
        git_branch=git_branch,
        multi_repo=multi_repo,
    )
