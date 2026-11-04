import sys
from types import ModuleType

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
    monkeypatch.setattr(data_generation, "detect_languages", lambda path: ["python"])
    monkeypatch.setattr(data_generation, "load_external_data", lambda path: {})
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
    assert [call["config"] for call in calls] == [False, True]


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
    calls = []
    code_utils = ModuleType("utils.code_utils")
    code_utils.generate_slug_from_repo = lambda repo, branch: f"{repo.rsplit('/', 1)[-1]}-{branch}"
    monkeypatch.setitem(sys.modules, "utils.code_utils", code_utils)
    monkeypatch.setattr(utils, "code_utils", code_utils, raising=False)
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
