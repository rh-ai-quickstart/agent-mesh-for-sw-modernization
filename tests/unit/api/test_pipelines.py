"""Console pipeline routing without submitting cluster runs."""

import json
from types import SimpleNamespace

import pytest
from api import pipeline_service, pipelines
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO = {"git_repo": "https://github.com/example/one", "git_branch": "develop"}
SECOND_REPO = {"git_repo": "https://github.com/example/two", "git_branch": "main"}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(pipelines.router, prefix="/api/v2")
    with TestClient(app) as client:
        client.cookies.set("cu_namespace", "selected-namespace")
        yield client


@pytest.mark.parametrize(
    "body, pipeline_name, pipeline_run_id",
    [
        ({"repos": [REPO]}, "single_repo", ""),
        ({"repos": [REPO, SECOND_REPO]}, "multi_repo", ""),
        ({"repos": [REPO], "pipeline_run_id": "prev-run"}, "single_repo", "prev-run"),
        ({"repos": [REPO, SECOND_REPO], "pipeline_run_id": "prev-run"}, "multi_repo", "prev-run"),
    ],
)
def test_pipeline_requests_route_to_existing_pipelines(
    client, monkeypatch, body, pipeline_name, pipeline_run_id
):
    calls = []
    monkeypatch.setenv("PARENT_SOURCE_PATH", "sources")
    monkeypatch.setenv("PARENT_TARGET_PATH", "targets")

    def trigger(name, run_name, params, *, namespace, enable_caching):
        calls.append((name, run_name, params, namespace, enable_caching))
        return SimpleNamespace(run_id="new-run")

    monkeypatch.setattr(pipeline_service, "_trigger_run", trigger)

    response = client.post("/api/v2/pipelines", json=body)

    assert response.status_code == 200
    name, run_name, params, namespace, enable_caching = calls[0]
    assert name == pipeline_name
    assert namespace == "selected-namespace"
    assert enable_caching == bool(pipeline_run_id)
    assert run_name.startswith(f"{pipeline_name}_")

    expected_params = {
        "pipeline_run_id": pipeline_run_id,
        "parent_source_path": "sources",
        "parent_target_path": "targets",
        "runnable_repos": json.dumps(body["repos"]),
    }
    if pipeline_name == "single_repo":
        expected_params.update(REPO)

    assert params == expected_params
    assert response.json() == {
        "job_id": "new-run",
        "mode": pipeline_name.replace("_", "-"),
        "run_name": run_name,
    }


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"repos": []},
        {"pipeline_run_id": "some-run"},
    ],
)
def test_invalid_pipeline_requests_are_rejected_before_submission(client, monkeypatch, body):
    def unexpected_submission(*args, **kwargs):
        pytest.fail("Invalid requests must not submit a KFP run")

    monkeypatch.setattr(pipeline_service, "_trigger_run", unexpected_submission)

    response = client.post("/api/v2/pipelines", json=body)

    assert response.status_code == 400
    assert response.json()["detail"]


def test_pipeline_submission_failure_returns_error(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("Pipeline service unavailable")

    monkeypatch.setattr(pipeline_service, "_trigger_run", unavailable)

    response = client.post("/api/v2/pipelines", json={"repos": [REPO]})

    assert response.status_code == 500
    assert response.json()["detail"] == "Pipeline service unavailable"


def test_pipeline_status_passes_selected_run_id_to_report_lookup(monkeypatch):
    seen = []
    monkeypatch.setattr(
        pipeline_service,
        "get_kfp_run_state",
        lambda run_id, namespace=None: "SUCCEEDED",
    )
    monkeypatch.setattr(
        pipeline_service,
        "get_run_git_metadata",
        lambda run_id, namespace=None: ("repo-main", False),
    )
    monkeypatch.setattr(
        pipeline_service,
        "_fetch_reports",
        lambda job_id, git_slug, multi_repo: seen.append(job_id) or (None, "report", None),
    )

    status = pipeline_service.get_run_status("selected-kfp")

    assert seen == ["selected-kfp"]
    assert status["analysis_report"] == "report"
