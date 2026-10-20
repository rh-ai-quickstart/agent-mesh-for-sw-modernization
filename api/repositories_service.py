"""Repository list retrieval for the v2 API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_CU_ROOT = str(
    Path(__file__).resolve().parent.parent / "workflows" / "examples" / "code_understanding"
)
if _CU_ROOT not in sys.path:
    sys.path.insert(0, _CU_ROOT)


def get_run_repos(run_id: str, namespace: str | None = None) -> list[dict[str, Any]]:
    """Returns the repo list for a specific pipeline run.

    Delegates to ``load_run_repos`` on the configured asset loader, scoping the
    lookup by ``run_id``.

    Args:
        run_id: Pipeline run identifier to scope the repo list lookup. In KFP
            this is the ``ARGO_WORKFLOW_UID`` of the run.
        namespace: Optional MLflow/KFP namespace for the asset loader.

    Returns:
        List of ``{"git_repo": ..., "git_branch": ...}`` dicts.
    """
    from loaders.default_asset_loader import DefaultAssetLoader

    return DefaultAssetLoader(namespace=namespace).load_run_repos(run_id=run_id)


def get_catalog_repos(namespace: str | None = None) -> list[dict[str, Any]]:
    """Returns the full repo catalog from the asset store.

    Delegates to ``get_catalog_repos`` service which tries enrichments first
    and falls back to static assets.

    Args:
        namespace: Optional MLflow/KFP namespace for the asset loader.

    Returns:
        List of ``{"git_repo": ..., "git_branch": ...}`` dicts, or an empty list.
    """
    from services.get_catalog_repos import get_catalog_repos as _get_catalog_repos

    return _get_catalog_repos(namespace=namespace)
