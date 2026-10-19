"""Fetch the repository catalog from the asset store."""

from __future__ import annotations


def get_catalog_repos(namespace: str | None = None) -> list:
    """Returns the full repo catalog via ``load_catalog_repos`` on the configured loader.

    Resolution order (MLflow mode):
    1. Enrichments in ``RESULT_DIRECTORY_ASSET_EXPERIMENT`` — written by ``log_repos``.
    2. Static asset in ``STATIC_ASSET_EXPERIMENT`` — fallback.

    Args:
        namespace: Optional MLflow/KFP namespace for the asset loader.

    Returns:
        List of ``{"git_repo": ..., "git_branch": ...}`` dicts, or an empty list.
    """
    from loaders.default_asset_loader import DefaultAssetLoader

    return DefaultAssetLoader(namespace=namespace).load_catalog_repos()
