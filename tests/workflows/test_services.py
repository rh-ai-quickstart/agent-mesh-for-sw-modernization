import json
import sys
from types import ModuleType, SimpleNamespace

import services.get_repo_list as repo_list_service
import services.trigger_run as trigger_run_service


def test_trigger_run_submits_latest_version_and_uploads_repo_list(monkeypatch):
    run_calls = []
    namespaces = []
    uploads = []

    class FakeClient:
        def create_experiment(self, *, name):
            assert name == "Default"
            return SimpleNamespace(experiment_id="experiment-1")

        def run_pipeline(self, **kwargs):
            run_calls.append(kwargs)
            return SimpleNamespace(run_id="run-123")

    client = FakeClient()
    monkeypatch.setattr(
        trigger_run_service,
        "create_client",
        lambda namespace=None: namespaces.append(namespace) or client,
    )
    monkeypatch.setattr(
        trigger_run_service,
        "find_pipeline_id",
        lambda actual_client, name: "pipeline-1",
    )
    monkeypatch.setattr(
        trigger_run_service,
        "latest_version_id",
        lambda actual_client, pipeline_id: "version-2",
    )

    loader_module = ModuleType("loaders.default_asset_loader")

    class FakeLoader:
        def log_static_asset(self, *args, **kwargs):
            uploads.append((args, kwargs))

    loader_module.DefaultAssetLoader = FakeLoader
    monkeypatch.setitem(sys.modules, "loaders.default_asset_loader", loader_module)

    run = trigger_run_service.trigger_run(
        pipeline_name="multi_repo",
        run_name="multi_repo_test",
        params={"parent_target_path": "target"},
        repos=[
            {"git_repo": "https://github.com/example/one", "git_branch": "dev"},
            {"git_repo": "https://github.com/example/two"},
        ],
        namespace="test-namespace",
    )

    assert run.run_id == "run-123"
    assert namespaces == ["test-namespace"]
    assert run_calls == [
        {
            "experiment_id": "experiment-1",
            "job_name": "multi_repo_test",
            "pipeline_id": "pipeline-1",
            "version_id": "version-2",
            "params": {"parent_target_path": "target"},
            "enable_caching": False,
        }
    ]
    assert uploads[0][0] == ("repo_list.json",)
    assert json.loads(uploads[0][1]["content"]) == [
        {"git_repo": "https://github.com/example/one", "git_branch": "dev"},
        {"git_repo": "https://github.com/example/two", "git_branch": "main"},
    ]
    assert uploads[0][1]["artifact_path"] == "repos"
    assert uploads[0][1]["tags"] == {"kfp_run_id": "run-123"}


def test_get_multi_repo_list_retries_with_run_tag(monkeypatch):
    attempts = []
    sleeps = []
    loader_module = ModuleType("loaders.default_asset_loader")

    class FakeLoader:
        def download(self, path, **kwargs):
            attempts.append((path, kwargs))
            if len(attempts) < 3:
                raise FileNotFoundError("repo list is not available yet")
            return [{"git_repo": "https://github.com/example/repo", "git_branch": "main"}]

    loader_module.DefaultAssetLoader = FakeLoader
    monkeypatch.setitem(sys.modules, "loaders.default_asset_loader", loader_module)
    monkeypatch.setattr(repo_list_service.time, "sleep", sleeps.append)

    repos = repo_list_service.get_multi_repo_list(
        "run-123",
        max_attempts=3,
        retry_delay=2,
    )

    assert repos == [{"git_repo": "https://github.com/example/repo", "git_branch": "main"}]
    assert attempts == [
        ("repos/repo_list.json", {"asset_tags": {"kfp_run_id": "run-123"}}),
        ("repos/repo_list.json", {"asset_tags": {"kfp_run_id": "run-123"}}),
        ("repos/repo_list.json", {"asset_tags": {"kfp_run_id": "run-123"}}),
    ]
    assert sleeps == [2, 2]
