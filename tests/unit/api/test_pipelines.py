"""Console pipeline routing without submitting cluster runs."""

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
    "body, pipeline_name, expected_repo_list, analysis_only",
    [
        ({"repos": [REPO]}, "single_repo", None, False),
        ({"repos": [REPO, SECOND_REPO]}, "multi_repo", [REPO, SECOND_REPO], False),
        ({"repos": [REPO], "analysis_only": True}, "single_repo", None, True),
        ({"analysis_only": True, "multi_repo": True}, "multi_repo", None, True),
    ],
)
def test_pipeline_requests_route_to_existing_pipelines(
    client, monkeypatch, body, pipeline_name, expected_repo_list, analysis_only
):
    calls = []
    monkeypatch.setenv("PARENT_SOURCE_PATH", "sources")
    monkeypatch.setenv("PARENT_TARGET_PATH", "targets")

    def trigger(name, run_name, params, *, repos, namespace):
        calls.append((name, run_name, params, repos, namespace))
        return SimpleNamespace(run_id="new-run")

    monkeypatch.setattr(pipeline_service, "_trigger_run", trigger)

    response = client.post("/api/v2/pipelines", json=body)

    assert response.status_code == 200
    name, run_name, params, repo_list, namespace = calls[0]
    assert name == pipeline_name
    assert repo_list == expected_repo_list
    assert namespace == "selected-namespace"
    expected_params = {"parent_source_path": "sources", "parent_target_path": "targets"}
    if pipeline_name == "single_repo":
        expected_params.update(REPO)
    if analysis_only:
        expected_params["analysis_only"] = True
        assert params["analysis_only"] is True
        assert run_name.startswith(f"{pipeline_name}_analysis_")
    else:
        assert run_name.startswith(f"{pipeline_name}_")
        assert "_analysis_" not in run_name
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
        {"multi_repo": True, "repos": [REPO, SECOND_REPO]},
        {"analysis_only": True},
        {"analysis_only": True, "repos": [REPO, SECOND_REPO]},
        {"analysis_only": True, "repos": [{"git_repo": ""}]},
        {"analysis_only": True, "repos": [{"git_repo": "   "}]},
        {"analysis_only": True, "multi_repo": True, "repos": [REPO]},
    ],
)
def test_invalid_pipeline_requests_are_rejected_before_submission(client, monkeypatch, body):
    def unexpected_submission(*args, **kwargs):
        pytest.fail("Invalid requests must not submit a KFP run")

    monkeypatch.setattr(pipeline_service, "_trigger_run", unexpected_submission)

    response = client.post("/api/v2/pipelines", json=body)

    assert response.status_code == 400
    assert response.json()["detail"]


def test_analysis_submission_failure_returns_error(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("Pipeline service unavailable")

    monkeypatch.setattr(pipeline_service, "_trigger_run", unavailable)

    response = client.post("/api/v2/pipelines", json={"repos": [REPO], "analysis_only": True})

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
        lambda git_slug, multi_repo, kfp_run_id: seen.append(kfp_run_id) or (None, "report"),
    )

    status = pipeline_service.get_run_status("selected-kfp")

    assert seen == ["selected-kfp"]
    assert status["analysis_report"] == "report"
