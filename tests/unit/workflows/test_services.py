from types import SimpleNamespace

import services.trigger_run as trigger_run_service


def _make_fake_client():
    class FakeClient:
        last_call: dict

        def create_experiment(self, *, name):
            assert name == "Default"
            return SimpleNamespace(experiment_id="experiment-1")

        def run_pipeline(self, **kwargs):
            self.last_call = kwargs
            return SimpleNamespace(run_id="run-123")

    return FakeClient()


def _patch_trigger_run(monkeypatch, client, namespaces=None):
    seen = namespaces if namespaces is not None else []
    monkeypatch.setattr(
        trigger_run_service,
        "create_client",
        lambda namespace=None: seen.append(namespace) or client,
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
    return seen


def test_trigger_run_submits_pipeline_with_params(monkeypatch):
    client = _make_fake_client()
    namespaces = _patch_trigger_run(monkeypatch, client)

    run = trigger_run_service.trigger_run(
        pipeline_name="single_repo",
        run_name="single_repo_test",
        params={"git_repo": "https://github.com/example/repo", "parent_source_path": "src"},
        namespace="test-namespace",
    )

    assert run.run_id == "run-123"
    assert namespaces == ["test-namespace"]
    assert client.last_call == {
        "experiment_id": "experiment-1",
        "job_name": "single_repo_test",
        "pipeline_id": "pipeline-1",
        "version_id": "version-2",
        "params": {"git_repo": "https://github.com/example/repo", "parent_source_path": "src"},
        "enable_caching": False,
    }


def test_trigger_run_passes_enable_caching(monkeypatch):
    client = _make_fake_client()
    _patch_trigger_run(monkeypatch, client)

    trigger_run_service.trigger_run(
        pipeline_name="single_repo",
        run_name="single_repo_cache_test",
        params={"pipeline_run_id": "prev-run"},
        enable_caching=True,
    )

    assert client.last_call["enable_caching"] is True
    assert client.last_call["params"] == {"pipeline_run_id": "prev-run"}
