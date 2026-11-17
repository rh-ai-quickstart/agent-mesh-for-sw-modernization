"""Tests for pipeline_service.list_pipeline_runs uploaded-index merging."""

from __future__ import annotations

from unittest.mock import patch

from api import pipeline_service


def _kfp_run(run_id, name="run", status="Succeeded"):
    return {
        "run_id": run_id,
        "name": name,
        "status": status,
        "start_time": "2025-01-01T00:00:00+00:00",
        "git_slug": "repo-main",
        "git_repo": "https://example.com/repo",
        "git_branch": "main",
    }


def _uploaded_index(git_slug="repo-main", kfp_run_id="uploaded-123", multi_repo=False):
    return {
        "git_slug": git_slug,
        "multi_repo": multi_repo,
        "uploaded": True,
        "run_id": "mlflow-run-id",
        "kfp_run_id": kfp_run_id,
        "indexed_at": "2025-01-02T00:00:00+00:00",
    }


def test_uploaded_indexes_appended_as_synthetic_entries():
    kfp_runs = [_kfp_run("kfp-1")]
    index_data = {
        "ok": True,
        "indexes": [_uploaded_index(kfp_run_id="uploaded-123")],
    }
    with (
        patch.object(pipeline_service, "list_kfp_runs", return_value=kfp_runs),
        patch("ui.indexes.list_indexed_repos", return_value=index_data),
    ):
        runs = pipeline_service.list_pipeline_runs()

    assert len(runs) == 2
    synthetic = runs[1]
    assert synthetic["run_id"] == "uploaded-123"
    assert synthetic["name"] == "Uploaded index: repo-main"
    assert synthetic["status"] == "Succeeded"
    assert synthetic["uploaded"] is True
    assert synthetic["git_repo"] is None
    assert synthetic["git_branch"] is None


def test_non_uploaded_indexes_are_skipped():
    kfp_runs = []
    index_data = {
        "ok": True,
        "indexes": [
            {
                "git_slug": "repo-main",
                "multi_repo": False,
                "uploaded": False,
                "run_id": "mlflow-run-id",
                "kfp_run_id": "kfp-123",
                "indexed_at": "2025-01-01T00:00:00+00:00",
            }
        ],
    }
    with (
        patch.object(pipeline_service, "list_kfp_runs", return_value=kfp_runs),
        patch("ui.indexes.list_indexed_repos", return_value=index_data),
    ):
        runs = pipeline_service.list_pipeline_runs()

    assert len(runs) == 0


def test_multi_repo_uploaded_index_has_repos_key():
    kfp_runs = []
    index_data = {
        "ok": True,
        "indexes": [_uploaded_index(multi_repo=True)],
    }
    with (
        patch.object(pipeline_service, "list_kfp_runs", return_value=kfp_runs),
        patch("ui.indexes.list_indexed_repos", return_value=index_data),
    ):
        runs = pipeline_service.list_pipeline_runs()

    assert len(runs) == 1
    assert runs[0]["repos"] == []
    assert runs[0]["git_slug"] is None


def test_index_discovery_failure_does_not_break_kfp_runs():
    kfp_runs = [_kfp_run("kfp-1")]
    with (
        patch.object(pipeline_service, "list_kfp_runs", return_value=kfp_runs),
        patch("ui.indexes.list_indexed_repos", side_effect=RuntimeError("MLflow down")),
    ):
        runs = pipeline_service.list_pipeline_runs()

    assert len(runs) == 1
    assert runs[0]["run_id"] == "kfp-1"
