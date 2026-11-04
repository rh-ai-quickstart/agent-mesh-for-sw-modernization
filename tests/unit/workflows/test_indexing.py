import json
import sys
from types import ModuleType

import pytest
from pipelines.base import indexing


def test_indexing_runs_generation_and_evaluation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        indexing,
        "generate_graphrag_index",
        lambda **kwargs: calls.append(("generate", kwargs)),
    )
    monkeypatch.setattr(
        indexing,
        "evaluate_graphrag_index",
        lambda **kwargs: calls.append(("evaluate", kwargs)),
    )

    result = indexing.IndexingPipeline().run(
        codebase_path="target/repo",
        graphrag_source_path="graph/source",
        git_repo="https://github.com/example/repo",
        git_branch="main",
    )

    assert result["status"] == "success"
    assert [name for name, _ in calls] == ["generate", "evaluate"]


def test_indexing_returns_failure_when_generation_fails(monkeypatch):
    evaluated = []

    def fail_generation(**kwargs):
        raise RuntimeError("index failed")

    monkeypatch.setattr(indexing, "generate_graphrag_index", fail_generation)
    monkeypatch.setattr(
        indexing,
        "evaluate_graphrag_index",
        lambda **kwargs: evaluated.append(kwargs),
    )

    result = indexing.IndexingPipeline().run(
        codebase_path="target/repo",
        graphrag_source_path="graph/source",
        git_repo="https://github.com/example/repo",
        git_branch="main",
    )

    assert result["status"] == "fail"
    assert "index failed" in result["fail_message"]
    assert evaluated == []


def test_indexing_evaluation_failure_is_nonfatal(monkeypatch):
    monkeypatch.setattr(indexing, "generate_graphrag_index", lambda **kwargs: None)

    def fail_evaluation(**kwargs):
        raise RuntimeError("evaluation failed")

    monkeypatch.setattr(indexing, "evaluate_graphrag_index", fail_evaluation)

    result = indexing.IndexingPipeline().run(
        codebase_path="target/repo",
        graphrag_source_path="graph/source",
        git_repo="https://github.com/example/repo",
        git_branch="main",
    )

    assert result["status"] == "success"


def test_multi_repo_indexing_skips_evaluation(monkeypatch):
    evaluations = []
    monkeypatch.setattr(indexing, "generate_graphrag_index", lambda **kwargs: None)
    monkeypatch.setattr(
        indexing,
        "evaluate_graphrag_index",
        lambda **kwargs: evaluations.append(kwargs),
    )

    result = indexing.IndexingPipeline().run(
        codebase_path="targets",
        graphrag_source_path="graph/source",
        git_repo="",
        git_branch="",
        multi_repo=True,
    )

    assert result["status"] == "success"
    assert evaluations == []


def test_multi_repo_indexing_uses_selected_repositories_for_current_run(monkeypatch, tmp_path):
    selected = [
        {"git_repo": "https://github.com/example/one", "git_branch": "develop"},
        {"git_repo": "https://github.com/example/two", "git_branch": "release"},
    ]
    defaults = [
        {"git_repo": "https://github.com/kfrankli/northpolesouthern-train", "git_branch": "main"},
        {
            "git_repo": "https://github.com/kfrankli/northpolesouthern-timetable",
            "git_branch": "main",
        },
    ]
    monkeypatch.setenv("KFP_RUN_ID", "selected-run")
    monkeypatch.setenv("GIT_REPO_LIST_CONTENTS", json.dumps(defaults))
    loader_module = ModuleType("loaders.default_asset_loader")

    class FakeLoader:
        def download(self, path, *, asset_tags):
            assert path == "repos/repo_list.json"
            assert asset_tags == {"kfp_run_id": "selected-run"}
            return selected

    loader_module.DefaultAssetLoader = FakeLoader
    monkeypatch.setitem(sys.modules, "loaders.default_asset_loader", loader_module)

    from utils import loader_utils

    downloads = []
    monkeypatch.setattr(
        loader_utils,
        "download_code_metadata_directories",
        lambda repos, target: downloads.append((repos, target)),
    )
    monkeypatch.setattr(
        indexing.IndexingPipeline, "run", lambda self, **kwargs: {"status": "success"}
    )

    indexing.IndexingPipeline().run_multi_repo(str(tmp_path), "graph/source")

    assert downloads == [(selected, str(tmp_path))]


def test_local_multi_repo_indexing_uses_environment_repositories(monkeypatch, tmp_path):
    from utils import loader_utils

    repos = [{"git_repo": "https://github.com/example/local", "git_branch": "develop"}]
    monkeypatch.delenv("KFP_RUN_ID", raising=False)
    monkeypatch.setenv("GIT_REPO_LIST_CONTENTS", json.dumps(repos))
    downloads = []
    monkeypatch.setattr(
        loader_utils,
        "download_code_metadata_directories",
        lambda actual_repos, target: downloads.append((actual_repos, target)),
    )
    monkeypatch.setattr(
        indexing.IndexingPipeline, "run", lambda self, **kwargs: {"status": "success"}
    )

    indexing.IndexingPipeline().run_multi_repo(str(tmp_path), "graph/source")

    assert downloads == [(repos, str(tmp_path))]


def test_multi_repo_indexing_does_not_fall_back_when_run_selection_is_unavailable(monkeypatch):
    from services import get_repo_list
    from utils import loader_utils

    monkeypatch.setenv("KFP_RUN_ID", "missing-selection-run")
    monkeypatch.setenv(
        "GIT_REPO_LIST_CONTENTS",
        json.dumps([{"git_repo": "https://github.com/example/default", "git_branch": "main"}]),
    )

    def unavailable(run_id):
        assert run_id == "missing-selection-run"
        raise FileNotFoundError("Run selection unavailable")

    def unexpected_download(*args, **kwargs):
        pytest.fail("A missing run selection must not index the environment defaults")

    monkeypatch.setattr(get_repo_list, "get_multi_repo_list", unavailable)
    monkeypatch.setattr(loader_utils, "download_code_metadata_directories", unexpected_download)

    with pytest.raises(FileNotFoundError, match="Run selection unavailable"):
        indexing.IndexingPipeline().run_multi_repo("target", "graph/source")
