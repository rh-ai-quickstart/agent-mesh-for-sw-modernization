"""Index discovery keeps indexed repositories available to analysis and chat."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import indexes


def make_run(
    run_id: str = "run-1",
    *,
    git_slug: str = "acme-widget-main",
    multi_repo: str = "false",
    uploaded: str = "false",
    start_time: int = 1_700_000_000_000,
):
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, start_time=start_time),
        data=SimpleNamespace(
            tags={"git_slug": git_slug, "multi_repo": multi_repo, "uploaded": uploaded}
        ),
    )


@pytest.fixture
def discovered_runs(monkeypatch):
    runs = []

    class DiscoveryClient:
        def get_experiment_by_name(self, name):
            assert name == "workspace/code-refactoring/assets/result-directories"
            return SimpleNamespace(experiment_id="7")

        def search_runs(self, **kwargs):
            assert kwargs["experiment_ids"] == ["7"]
            assert kwargs["filter_string"] == 'tags.category = "indexing"'
            assert kwargs["order_by"] == ["attributes.start_time DESC"]
            return runs

    monkeypatch.setenv("ASSET_LOADER", "mlflow")
    monkeypatch.setenv("MLFLOW_WORKSPACE", "workspace")
    monkeypatch.setattr(indexes, "create_mlflow_client", DiscoveryClient)
    return runs


def test_discovery_keeps_newest_run_for_slug(discovered_runs):
    discovered_runs.extend(
        [
            make_run("new", uploaded="true", start_time=1_700_000_001_000),
            make_run("old", start_time=1_700_000_000_000),
        ]
    )

    data = indexes.list_indexed_repos()

    assert data["ok"] is True
    assert data["indexes"] == [
        {
            "run_id": "new",
            "git_slug": "acme-widget-main",
            "multi_repo": False,
            "indexed_at": "2023-11-14T22:13:21+00:00",
        }
    ]


@pytest.mark.parametrize("slug", ["", ".", "..", "../outside", "nested/path", "nested\\path"])
def test_discovery_skips_invalid_single_repository_slugs(discovered_runs, slug):
    discovered_runs.extend([make_run("invalid", git_slug=slug), make_run("valid")])

    data = indexes.list_indexed_repos()

    assert data["ok"] is True
    assert [item["run_id"] for item in data["indexes"]] == ["valid"]


def test_discovered_indexes_remain_available_to_analysis_and_chat(discovered_runs):
    discovered_runs.extend(
        [make_run(uploaded="true"), make_run("combined", git_slug="", multi_repo="true")]
    )
    repo = {"git_repo": "https://github.com/acme/widget", "git_branch": "main"}
    unindexed_repo = {"git_repo": "https://github.com/acme/other", "git_branch": "main"}

    data = indexes.list_indexed_repos()
    options = indexes.queryable_repos(data["indexes"], [repo, unindexed_repo])

    assert [item["run_id"] for item in data["indexes"]] == ["run-1", "combined"]
    assert options == [
        {**repo, "label": "widget @ main", "key": f"{repo['git_repo']}|main", "use_global": False},
        {
            "git_repo": "",
            "git_branch": "main",
            "label": "Combined multi-repo index",
            "key": "__multi_repo__",
            "use_global": True,
        },
    ]
