import json
import sys
from types import ModuleType

import pandas as pd
import utils
from pipelines.base import data_generation


def test_data_generation_runs_code_and_config_passes(monkeypatch):
    calls = []

    monkeypatch.setattr(
        data_generation,
        "generate_git_slug",
        lambda repo, branch: "example-repo-main",
    )
    monkeypatch.setattr(data_generation, "prepare_environment", lambda **kwargs: None)
    monkeypatch.setattr(
        data_generation,
        "run_preflight",
        lambda source, slug, **kwargs: data_generation.PreflightResult(
            languages=["python"], external_metadata=[]
        ),
    )
    monkeypatch.setattr(
        data_generation,
        "generate_code_and_meta",
        lambda **kwargs: calls.append(kwargs),
    )

    result = data_generation.DataGenerationPipeline().run(
        git_repo="https://github.com/example/repo",
        git_branch="main",
        source_path="source",
        target_path="target",
    )

    assert result == {
        "git_slug": "example-repo-main",
        "status": "complete",
        "fail_message": "",
    }
    assert len(calls) == 1
    assert calls[0]["languages"] == ["python"]


def test_data_generation_cleans_up_after_failure(monkeypatch):
    cleanups = []

    monkeypatch.setattr(
        data_generation,
        "generate_git_slug",
        lambda repo, branch: "example-repo-main",
    )

    def fail_to_prepare(**kwargs):
        raise RuntimeError("clone failed")

    monkeypatch.setattr(data_generation, "prepare_environment", fail_to_prepare)
    monkeypatch.setattr(
        data_generation,
        "reset_environment",
        lambda source, target: cleanups.append((source, target)),
    )

    result = data_generation.DataGenerationPipeline().run(
        git_repo="https://github.com/example/repo",
        git_branch="main",
        source_path="source",
        target_path="target",
    )

    assert result["git_slug"] == "example-repo-main"
    assert result["status"] == "error"
    assert "clone failed" in result["fail_message"]
    assert cleanups == [("source", "target")]


def test_multi_repo_uses_isolated_paths_and_preserves_results(monkeypatch):
    from loaders.default_asset_loader import DefaultAssetLoader

    calls = []
    code_utils = ModuleType("utils.code_utils")
    code_utils.generate_slug_from_repo = lambda repo, branch: f"{repo.rsplit('/', 1)[-1]}-{branch}"
    monkeypatch.setitem(sys.modules, "utils.code_utils", code_utils)
    monkeypatch.setattr(utils, "code_utils", code_utils, raising=False)
    monkeypatch.setattr(DefaultAssetLoader, "log_repos", lambda self, repos: None)
    monkeypatch.setenv("PARENT_SOURCE_PATH", "sources")
    monkeypatch.setenv("PARENT_TARGET_PATH", "targets")

    def fake_run(self, **kwargs):
        calls.append(kwargs)
        return {
            "git_slug": kwargs["source_path"].removeprefix("sources/"),
            "status": "error" if kwargs["git_repo"].endswith("two") else "complete",
        }

    monkeypatch.setattr(data_generation.DataGenerationPipeline, "run", fake_run)

    results = data_generation.DataGenerationPipeline().run_multi_repo(
        [
            {"git_repo": "https://github.com/example/one", "git_branch": "main"},
            {"git_repo": "https://github.com/example/two", "git_branch": "dev"},
        ]
    )

    assert [call["source_path"] for call in calls] == [
        "sources/one-main",
        "sources/two-dev",
    ]
    assert [call["target_path"] for call in calls] == [
        "targets/one-main",
        "targets/two-dev",
    ]
    assert all(call["multi_repo"] for call in calls)
    assert [result["status"] for result in results] == ["complete", "error"]


def test_save_code_and_metadata_merges_multiple_external_metadata(monkeypatch, tmp_path):
    from loaders.default_asset_loader import DefaultAssetLoader

    df = pd.DataFrame(
        [
            {
                "file_path": "src/app.py",
                "code": "print('hello')",
                "extracted_data": json.dumps({"language": "python", "functions": []}),
            }
        ]
    )

    external_metadata = [
        {
            "runtime_stack": ["python3.11"],
            "libraries": ["flask"],
            "repo_packages": ["mylib"],
        },
        {
            "runtime_stack": ["python3.12"],
            "libraries": ["requests"],
            "repo_packages": ["otherlib"],
        },
    ]

    monkeypatch.setattr(DefaultAssetLoader, "download", lambda self, path: {})

    saved_records = []

    def capture_save(metadata, target_path, rel_file_path, **kwargs):
        saved_records.append(kwargs.get("external_metadata", {}))

    monkeypatch.setattr(data_generation, "save_metadata_file", capture_save)
    monkeypatch.setattr(data_generation, "generate_code_comment", lambda **kwargs: "")

    data_generation.save_code_and_metadata_files(
        df=df,
        target_path=str(tmp_path),
        git_repo="https://github.com/example/repo",
        git_slug="example-repo-main",
        language="python",
        config=False,
        external_metadata=external_metadata,
    )

    assert len(saved_records) == 1
    record = saved_records[0]

    assert "python3.11" in record["runtime_stack"]
    assert "python3.12" in record["runtime_stack"]
    assert "flask" in record["libraries"]
    assert "requests" in record["libraries"]
    assert "mylib" in record["repo_packages"]
    assert "otherlib" in record["repo_packages"]
