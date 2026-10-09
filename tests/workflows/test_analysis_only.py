"""Existing-index loading contracts without GraphRAG or MLflow services."""

import importlib.util
import inspect
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from conftest import WORKFLOW_ROOT
from utils.kubeflow_utils import read_from_input_artifact


@pytest.fixture
def existing_index_loader(monkeypatch):
    # Only stub the optional query dependencies; execute the real download logic.
    for name in ("graphrag", "graphrag.api", "graphrag.config", "pandas"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    config = ModuleType("graphrag.config.load_config")
    config.load_config = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, config.__name__, config)

    loader = ModuleType("loaders.default_asset_loader")

    class FakeLoader:
        RESULTS_PATH_PREFIX_REPO_DATASETS = "datasets"

        def download(self, path):
            return json.loads((WORKFLOW_ROOT / "assets" / path).read_text())

    loader.DefaultAssetLoader = FakeLoader
    monkeypatch.setitem(sys.modules, loader.__name__, loader)

    spec = importlib.util.spec_from_file_location(
        "utils.graphrag_utils", WORKFLOW_ROOT / "utils" / "graphrag_utils.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        path = Path(kwargs["download_dir"])
        path.mkdir(parents=True)
        (path / "entities.parquet").write_bytes(b"existing index")

    from utils import loader_utils

    monkeypatch.setattr(loader_utils, "download_result_directory", download)
    monkeypatch.setattr(
        module.DependencyAnalyzer,
        "prepare_settings",
        lambda template_dir, output_dir: (Path(output_dir) / "settings.yaml").write_text(
            "existing settings"
        ),
    )
    # Keep the real slug calculation while isolating its import-time asset loader.
    import utils

    code_spec = importlib.util.spec_from_file_location(
        "utils.code_utils", WORKFLOW_ROOT / "utils" / "code_utils.py"
    )
    code_module = importlib.util.module_from_spec(code_spec)
    monkeypatch.setitem(sys.modules, code_spec.name, code_module)
    monkeypatch.setattr(utils, "code_utils", code_module, raising=False)
    code_spec.loader.exec_module(code_module)

    from pipelines.kubeflow.analysis import load_existing_index_op

    return inspect.unwrap(load_existing_index_op).python_func, calls


@pytest.mark.parametrize(
    "multi_repo, git_repo, expected_slug",
    [
        (False, "https://github.com/example/repo.git", "example-repo-develop"),
        (True, "", ""),
    ],
)
def test_existing_index_lookup_uses_repository_scope_and_packages_artifact(
    existing_index_loader, tmp_path, multi_repo, git_repo, expected_slug
):
    load_index, calls = existing_index_loader
    artifact = SimpleNamespace(path=str(tmp_path / "index.tar.gz"))

    load_index(
        graphrag_dir=artifact,
        git_repo=git_repo,
        git_branch="develop",
        multi_repo=multi_repo,
    )

    assert len(calls) == 1
    assert calls[0] == {
        "git_slug": expected_slug,
        "download_dir": calls[0]["download_dir"],
        "results_prefix": "datasets",
        "multi_repo": multi_repo,
        "asset_tags": {
            "git_slug": expected_slug,
            "multi_repo": multi_repo,
            "category": "indexing",
        },
        "namespace": None,
    }
    assert Path(calls[0]["download_dir"]).name == "output"
    with read_from_input_artifact(artifact) as directory:
        assert (Path(directory) / "output" / "entities.parquet").read_bytes() == b"existing index"
        assert (Path(directory) / "settings.yaml").read_text() == "existing settings"


def test_existing_single_repo_index_requires_repository(existing_index_loader, tmp_path):
    load_index, calls = existing_index_loader
    with pytest.raises(ValueError, match="git_repo is required"):
        load_index(graphrag_dir=SimpleNamespace(path=str(tmp_path / "index.tar.gz")))
    assert calls == []


@pytest.mark.parametrize(
    "multi_repo, git_repo, label",
    [
        (False, "https://github.com/example/repo", "https://github.com/example/repo @ develop"),
        (True, "", "combined multi-repository"),
    ],
)
def test_missing_existing_index_reports_scope(
    existing_index_loader, monkeypatch, tmp_path, multi_repo, git_repo, label
):
    load_index, _ = existing_index_loader
    from utils import loader_utils

    def missing_index(**kwargs):
        raise FileNotFoundError("no matching index")

    monkeypatch.setattr(loader_utils, "download_result_directory", missing_index)
    artifact = SimpleNamespace(path=str(tmp_path / "index.tar.gz"))
    with pytest.raises(RuntimeError) as error:
        load_index(
            graphrag_dir=artifact, git_repo=git_repo, git_branch="develop", multi_repo=multi_repo
        )
    assert str(error.value) == f"Could not load the existing index for {label}"
    assert isinstance(error.value.__cause__, FileNotFoundError)
    assert not Path(artifact.path).exists()
