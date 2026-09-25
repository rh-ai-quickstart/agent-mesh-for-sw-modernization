"""Retrieve the per-run repo list uploaded by trigger_run."""

from __future__ import annotations

import time


def get_multi_repo_list(kfp_run_id: str, max_attempts: int = 10, retry_delay: int = 5) -> list:
    """Download the repo list for a multi-repo KFP run from the asset store.

    trigger_run uploads ``repos/repo_list.json`` tagged with ``kfp_run_id``
    immediately after submitting the pipeline run.  This function polls with
    retries to tolerate the brief window between pipeline submission and the
    first KFP component executing.

    Args:
        kfp_run_id: The KFP run ID used as the asset tag.
        max_attempts: Number of download attempts before raising.
        retry_delay: Seconds to wait between attempts.

    Returns:
        List of ``{"git_repo": ..., "git_branch": ...}`` dicts.
    """
    from loaders.default_asset_loader import DefaultAssetLoader

    loader = DefaultAssetLoader()
    for attempt in range(max_attempts):
        try:
            return loader.download(
                "repos/repo_list.json",
                asset_tags={"kfp_run_id": kfp_run_id},
            )
        except Exception:
            if attempt == max_attempts - 1:
                raise
            time.sleep(retry_delay)
