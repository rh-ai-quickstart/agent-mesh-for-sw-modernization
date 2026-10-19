"""Update the repository list in the asset store."""

from __future__ import annotations


def log_repos(repos: list[dict[str, str]], namespace: str | None = None) -> None:
    """Logs repos to the asset store via the configured loader.

    The loader's ``log_repos`` implementation writes repos as an enrichment
    (``repos/repo_list.json``) and under ``category: repositories``.

    Args:
        repos: List of ``{"git_repo": ..., "git_branch": ...}`` dicts.
        namespace: Optional MLflow/KFP namespace for the asset loader.
    """
    from loaders.default_asset_loader import DefaultAssetLoader

    DefaultAssetLoader(namespace=namespace).log_repos(repos)
