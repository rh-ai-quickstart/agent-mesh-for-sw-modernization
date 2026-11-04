"""Regression checks for external CLI E2E monitoring, without submitting pipelines."""

import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kfp_server_api import ApiException
from urllib3.exceptions import NewConnectionError

CLI_TESTS = Path(__file__).resolve().parents[2] / "e2e" / "cli"
WAIT = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))["_wait_for_run"]


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()
    monkeypatch.setitem(WAIT.__globals__, "time", clock)
    return clock


def test_wait_recovers_from_connection_loss_and_gateway_error(clock):
    client = Mock()
    client.run_service_get_run.side_effect = [
        NewConnectionError(None, "connection lost"),
        ApiException(status=503),
        SimpleNamespace(state="RUNNING"),
        SimpleNamespace(state="SUCCEEDED"),
    ]

    WAIT(client, "selected-run", 120)

    assert client.run_service_get_run.call_count == 4
    assert clock.now == 45
    for call in client.run_service_get_run.call_args_list:
        assert call.kwargs == {"run_id": "selected-run", "_request_timeout": (10, 30)}


def test_wait_distinguishes_monitoring_failure_from_pipeline_failure(clock):
    client = Mock()
    client.run_service_get_run.side_effect = NewConnectionError(None, "connection lost")

    with pytest.raises(pytest.fail.Exception, match="pipeline may still be running"):
        WAIT(client, "selected-run", 120)

    assert client.run_service_get_run.call_count == 5


@pytest.mark.parametrize("state", ["FAILED", "ERROR", "CANCELED", "CANCELLED", "SKIPPED"])
def test_wait_stops_on_terminal_failure(clock, state):
    client = Mock()
    client.run_service_get_run.return_value = SimpleNamespace(state=state)

    with pytest.raises(pytest.fail.Exception, match=f"ended with state {state}"):
        WAIT(client, "selected-run", 120)

    assert client.run_service_get_run.call_count == 1


def test_wait_uses_elapsed_time_and_reports_last_state(clock):
    client = Mock()
    client.run_service_get_run.return_value = SimpleNamespace(state="RUNNING")

    with pytest.raises(pytest.fail.Exception, match="within 31s; last observed state: RUNNING"):
        WAIT(client, "selected-run", 31)

    assert clock.now == 31
    assert client.run_service_get_run.call_args.kwargs["_request_timeout"] == (1, 1)


def test_wait_fails_immediately_on_authentication_error(clock):
    client = Mock()
    client.run_service_get_run.side_effect = ApiException(status=401)

    with pytest.raises(pytest.fail.Exception, match="oc authentication"):
        WAIT(client, "selected-run", 120)

    assert client.run_service_get_run.call_count == 1


def test_kfp_fixture_discovers_authenticated_route_without_port_forward(monkeypatch):
    fixture = runpy.run_path(str(CLI_TESTS / "conftest.py"))["deployed_kfp_client"].__wrapped__
    monkeypatch.setitem(fixture.__globals__, "get_token", lambda: "test-token")
    run_cli = Mock(return_value="pipelines.example.test\n")
    monkeypatch.delenv("CLI_E2E_KFP_HOST", raising=False)
    generator = fixture("test-namespace", run_cli)
    try:
        api = next(generator)
        assert api.api_client.configuration.host == "https://pipelines.example.test"
        assert api.api_client.default_headers["Authorization"] == "Bearer test-token"
        assert "ds-pipeline-dspa" in run_cli.call_args.args[0]
        assert "port-forward" not in run_cli.call_args.args[0]
    finally:
        generator.close()


@pytest.mark.parametrize("multi_repo", [False, True])
def test_pipeline_artifact_checks_use_run_and_repository_scope(tmp_path, multi_repo):
    import pyarrow as arrow
    import pyarrow.parquet as parquet

    helpers = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
    slug = helpers["GIT_SLUG"]
    scope = "multi-repo" if multi_repo else slug
    report_path = f"results/pipelines/{scope}/migration_report.md"
    report = tmp_path / "report.md"
    report.write_text("# Migration report", encoding="utf-8")
    table = tmp_path / "table.parquet"
    parquet.write_table(arrow.table({"id": ["example"]}), table)
    client = Mock()
    client.get_experiment_by_name.return_value = SimpleNamespace(experiment_id="1")

    def search_runs(**kwargs):
        filters = kwargs["filter_string"]
        assert "tags.kfp_run_id = 'selected-run'" in filters
        assert ("tags.git_slug" in filters) is not multi_repo
        return [
            SimpleNamespace(
                info=SimpleNamespace(run_id="wrong-scope"),
                data=SimpleNamespace(tags={"multi_repo": str(not multi_repo)}),
            ),
            SimpleNamespace(
                info=SimpleNamespace(run_id="query"),
                data=SimpleNamespace(tags={"multi_repo": str(multi_repo), "adhoc_query": "true"}),
            ),
            SimpleNamespace(
                info=SimpleNamespace(run_id="matching-artifacts"),
                data=SimpleNamespace(tags={"multi_repo": str(multi_repo)}),
            ),
        ]

    def list_artifacts(run_id, path):
        assert run_id == "matching-artifacts"
        if path == f"results/pipelines/{scope}":
            return [SimpleNamespace(path=report_path, is_dir=False)]
        assert path == f"results/datasets/repos/{scope}"
        return [
            SimpleNamespace(path=f"{path}/{name}.parquet", is_dir=False)
            for name in (
                "entities",
                "relationships",
                "text_units",
                "communities",
                "community_reports",
            )
        ]

    client.search_runs.side_effect = search_runs
    client.list_artifacts.side_effect = list_artifacts
    client.download_artifacts.side_effect = lambda run, path, dst: (
        str(report) if path.endswith(".md") else str(table)
    )

    helpers["_assert_analysis_report"](
        client, "namespace", "selected-run", tmp_path, multi_repo=multi_repo
    )
    helpers["_assert_index"](client, "namespace", "selected-run", tmp_path, multi_repo=multi_repo)

    assert client.download_artifacts.call_count == 6


def test_multi_repo_submission_applies_readme_list_before_submitting(monkeypatch):
    helpers = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
    submit = helpers["_submit_and_wait"]
    waiter = Mock()
    monkeypatch.setitem(submit.__globals__, "_wait_for_run", waiter)
    run_cli = Mock(side_effect=["", "", "Submitted run id: selected-run\n"])
    client = Mock()

    assert (
        submit(run_cli, client, "namespace", "--multi-repo", repo_list=helpers["REPO_LIST"])
        == "selected-run"
    )

    commands = [call.args[0] for call in run_cli.call_args_list]
    assert commands[0] == [
        "make",
        "apply-secrets",
        f"PIPELINE_GIT_REPO_LIST={helpers['REPO_LIST']}",
    ]
    assert commands[1] == ["make", "run-pipelines", "ARGS=--multi-repo"]
    assert commands[2] == ["oc", "logs", "job/run-pipelines", "--namespace", "namespace"]
    waiter.assert_called_once()
    assert waiter.call_args.args[:2] == (client, "selected-run")


@pytest.mark.parametrize(
    "output",
    [
        "progress only",
        "ADHOC RESULTS\n",
        "ADHOC RESULTS\nNone",
        "ADHOC RESULTS\nnull",
        "ADHOC RESULTS\nCould not perform query: missing index",
        "ADHOC RESULTS\nTraceback (most recent call last)",
    ],
)
def test_query_check_rejects_missing_answers_and_query_errors(output):
    helpers = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
    with pytest.raises(AssertionError):
        helpers["_assert_query_answer"](output)


def test_combined_query_uses_wrapper_without_repository_flags():
    helpers = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
    run_cli = Mock(
        return_value=(
            "\r⠋ Querying...\r\x1b[K##################ADHOC RESULTS##################\n"
            "Train and timetable share dependencies.\n"
        )
    )

    helpers["test_multi_repo_combined_index_query_returns_answer"](run_cli)

    run_cli.assert_called_once()
    assert run_cli.call_args.args[0] == [
        "wrappers/adhoc.sh",
        "Which repositories share dependencies that affect migration order?",
    ]
    assert run_cli.call_args.kwargs["name"] == "combined-index-query"
