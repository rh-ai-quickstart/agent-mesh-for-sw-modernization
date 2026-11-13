"""Discover GraphRAG indexes stored via the configured asset loader."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

RESULT_DIRECTORY_EXPERIMENT_SUFFIX = "/code-refactoring/assets/result-directories"


def result_directory_experiment_name(workspace: str | None = None) -> str:
    """Return the MLflow experiment that stores result-directory artifacts."""
    selected_workspace = (
        workspace or os.getenv("MLFLOW_WORKSPACE") or os.getenv("KFP_NAMESPACE") or "demo"
    ).strip()
    return f"{selected_workspace}{RESULT_DIRECTORY_EXPERIMENT_SUFFIX}"


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _valid_slug(slug: str) -> bool:
    """Return True when *slug* is a safe, single path component."""
    if not slug:
        return False
    if slug in {".", ".."}:
        return False
    if "/" in slug or "\\" in slug:
        return False
    return True


def _run_index_metadata(run: Any) -> dict[str, Any]:
    """Build index metadata from an MLflow run object."""
    tags = getattr(getattr(run, "data", None), "tags", None) or {}
    slug = str(tags.get("git_slug") or "")
    multi = _as_bool(tags.get("multi_repo"))
    uploaded = _as_bool(tags.get("uploaded"))
    kfp_run_id = str(tags.get("pipeline_run_id") or "")

    if not multi and not _valid_slug(slug):
        raise ValueError(f"invalid or missing git_slug for single-repository index: {slug!r}")

    run_info = getattr(run, "info", None)
    started = getattr(run_info, "start_time", None)
    return {
        "git_slug": slug,
        "multi_repo": multi,
        "uploaded": uploaded,
        "run_id": str(getattr(run_info, "run_id", "")),
        "kfp_run_id": kfp_run_id,
        "indexed_at": (
            datetime.fromtimestamp(started / 1000, tz=timezone.utc).isoformat() if started else ""
        ),
    }


def create_mlflow_client() -> Any:
    """Create an MLflow client authenticated with the pod service account."""
    from pathlib import Path

    from mlflow.tracking import MlflowClient

    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    if not os.environ.get("MLFLOW_TRACKING_TOKEN") and os.path.isfile(token_path):
        os.environ["MLFLOW_TRACKING_TOKEN"] = Path(token_path).read_text(encoding="utf-8").strip()

    return MlflowClient()


def list_indexed_repos() -> dict[str, Any]:
    """Return indexed repositories discovered from MLflow artifact runs."""
    if os.getenv("ASSET_LOADER", "local").strip().lower() != "mlflow":
        return {
            "ok": True,
            "source": "local",
            "indexes": [],
            "message": "Index discovery requires ASSET_LOADER=mlflow in code-understanding-env.",
        }

    try:
        client = create_mlflow_client()
        experiment_name = result_directory_experiment_name()
        experiment = client.get_experiment_by_name(experiment_name)
        if experiment is None:
            return {
                "ok": True,
                "source": "mlflow",
                "indexes": [],
                "message": f"No MLflow experiment yet: {experiment_name}",
            }

        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string='tags.category = "indexing"',
            order_by=["attributes.start_time DESC"],
            max_results=200,
        )
        seen: set[tuple[str, bool]] = set()
        indexes: list[dict[str, Any]] = []
        for run in runs:
            try:
                metadata = _run_index_metadata(run)
            except ValueError:
                continue
            key = (metadata["git_slug"], metadata["multi_repo"], metadata["uploaded"])
            if key in seen:
                continue
            seen.add(key)
            indexes.append(metadata)
        return {"ok": True, "source": "mlflow", "indexes": indexes, "message": ""}
    except Exception as exc:
        return {"ok": False, "source": "mlflow", "indexes": [], "message": str(exc)}


def list_uploaded_indexes_as_runs() -> list[dict[str, Any]]:
    """Return uploaded indexes as synthetic run entries for the UI runs list."""
    data = list_indexed_repos()
    runs: list[dict[str, Any]] = []
    for idx in data.get("indexes") or []:
        if not idx.get("uploaded"):
            continue
        kfp_run_id = idx.get("kfp_run_id", "")
        slug = idx.get("git_slug", "")
        runs.append(
            {
                "run_id": kfp_run_id or idx.get("run_id", ""),
                "name": f"Uploaded index: {slug}" if slug else "Uploaded index",
                "status": "Succeeded",
                "start_time": idx.get("indexed_at"),
                "git_slug": slug if not idx.get("multi_repo") else None,
                "git_repo": None,
                "git_branch": None,
                "uploaded": True,
                **({"repos": []} if idx.get("multi_repo") else {}),
            }
        )
    return runs


def index_lookup(indexes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map git_slug -> single-repo index metadata (multi_repo entries excluded)."""
    return {
        item["git_slug"]: item
        for item in indexes
        if item.get("git_slug") and not item.get("multi_repo")
    }


def repo_is_indexed(git_repo: str, git_branch: str, indexes: list[dict[str, Any]]) -> bool:
    from utils.code_utils import generate_slug_from_repo

    slug = generate_slug_from_repo(git_repo, git_branch)
    return any(item.get("git_slug") == slug and not item.get("multi_repo") for item in indexes)


def multi_repo_indexed(indexes: list[dict[str, Any]]) -> bool:
    return any(item.get("multi_repo") for item in indexes)


def queryable_repos(
    indexes: list[dict[str, Any]],
    catalog: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Catalog entries that have a GraphRAG index, plus optional multi-repo index."""
    from utils.code_utils import generate_slug_from_repo

    lkp = index_lookup(indexes)
    options: list[dict[str, Any]] = []
    for item in catalog:
        slug = generate_slug_from_repo(item["git_repo"], item["git_branch"])
        idx_meta = lkp.get(slug)
        if not idx_meta:
            continue
        short = item["git_repo"].rsplit("/", 1)[-1]
        options.append(
            {
                **item,
                "git_slug": slug,
                "label": f"{short} @ {item['git_branch']}",
                "key": f"{item['git_repo']}|{item['git_branch']}",
                "use_global": False,
                "kfp_run_id": idx_meta.get("kfp_run_id", ""),
            }
        )
    if multi_repo_indexed(indexes):
        multi_meta = next((i for i in indexes if i.get("multi_repo")), {})
        options.append(
            {
                "git_repo": "",
                "git_branch": "main",
                "label": "Combined multi-repo index",
                "key": "__multi_repo__",
                "use_global": True,
                "kfp_run_id": multi_meta.get("kfp_run_id", ""),
            }
        )
    return options


def default_query_key(options: list[dict[str, Any]]) -> str | None:
    for option in options:
        if "tic-tac-toe" in option.get("git_repo", ""):
            return option["key"]
    return options[0]["key"] if options else None
