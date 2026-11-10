"""Regression checks for external CLI E2E monitoring, without submitting pipelines."""

import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kfp_server_api import ApiException
from urllib3.exceptions import NewConnectionError

CLI_TESTS = Path(__file__).resolve().parents[2] / "e2e" / "cli"
HELPERS = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
WAIT = HELPERS["_wait_for_run"]
SUBMIT = HELPERS["_submit_and_wait"]


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


@pytest.fixture
def submit_run():
    def submit(client, pipeline_timeout=31):
        run_cli = Mock(side_effect=["", "Submitted run id: owned-run\n"])
        return SUBMIT(
            run_cli,
            client,
            "namespace",
            "--single-repo --analysis-only",
            pipeline_timeout=pipeline_timeout,
            pipeline_run_id="shared-prebuilt-index",
        )

    return submit


def test_submission_cancels_only_owned_run_on_timeout(clock, submit_run):
    client = Mock()
    client.run_service_get_run.side_effect = [
        SimpleNamespace(state=state)
        for state in ("RUNNING", "RUNNING", "RUNNING", "RUNNING", "CANCELING", "CANCELED")
    ]

    with pytest.raises(pytest.fail.Exception, match="within 31s; last observed state: RUNNING"):
        submit_run(client)

    client.run_service_terminate_run.assert_called_once()
    assert client.run_service_terminate_run.call_args.kwargs["run_id"] == "owned-run"
    assert all(
        call.kwargs["run_id"] == "owned-run" for call in client.run_service_get_run.call_args_list
    )
    assert clock.now == 35


def test_submission_cancels_on_monitoring_failure(clock, submit_run):
    client = Mock()
    client.run_service_get_run.side_effect = [
        *[ApiException(status=503) for _ in range(5)],
        SimpleNamespace(state="RUNNING"),
        SimpleNamespace(state="CANCELED"),
    ]

    with pytest.raises(pytest.fail.Exception, match="5 consecutive request failures"):
        submit_run(client, pipeline_timeout=120)

    client.run_service_terminate_run.assert_called_once()
    assert client.run_service_terminate_run.call_args.kwargs["run_id"] == "owned-run"


@pytest.mark.parametrize("state", ["SUCCEEDED", "FAILED", "ERROR", "CANCELED"])
def test_submission_leaves_terminal_runs_alone(clock, submit_run, state):
    client = Mock()
    client.run_service_get_run.return_value = SimpleNamespace(state=state)

    if state == "SUCCEEDED":
        assert submit_run(client) == "owned-run"
    else:
        with pytest.raises(pytest.fail.Exception, match=f"ended with state {state}"):
            submit_run(client)

    client.run_service_terminate_run.assert_not_called()
    assert clock.now == 0


@pytest.mark.parametrize("termination_error", [None, ApiException(status=503)])
def test_submission_stops_session_if_cleanup_unconfirmed(clock, submit_run, termination_error):
    client = Mock()
    client.run_service_get_run.return_value = SimpleNamespace(state="RUNNING")
    client.run_service_terminate_run.side_effect = termination_error

    with pytest.raises(pytest.exit.Exception) as failure:
        submit_run(client)

    assert failure.value.returncode == 1
    message = str(failure.value)
    assert "within 31s; last observed state: RUNNING" in message
    assert "Could not confirm termination of test-owned KFP run owned-run" in message
    assert clock.now == 91
    assert client.run_service_terminate_run.called
    assert all(
        call.kwargs["run_id"] == "owned-run" and sum(call.kwargs["_request_timeout"]) <= 60
        for call in client.run_service_terminate_run.call_args_list
    )


def test_submission_confirms_completion_after_termination_race(clock, submit_run):
    client = Mock()
    client.run_service_get_run.side_effect = [
        SimpleNamespace(state=state)
        for state in ("RUNNING", "RUNNING", "RUNNING", "RUNNING", "SUCCEEDED")
    ]
    client.run_service_terminate_run.side_effect = ApiException(status=409)

    with pytest.raises(pytest.fail.Exception, match="within 31s"):
        submit_run(client)

    assert clock.now == 33


def test_submission_retries_cleanup_after_transient_api_errors(clock, submit_run):
    client = Mock()
    client.run_service_get_run.side_effect = [
        *[SimpleNamespace(state="RUNNING") for _ in range(3)],
        NewConnectionError(None, "connection lost during cleanup"),
        SimpleNamespace(state="RUNNING"),
        SimpleNamespace(state="CANCELED"),
    ]
    client.run_service_terminate_run.side_effect = [ApiException(status=503), None]

    with pytest.raises(pytest.fail.Exception, match="within 31s"):
        submit_run(client)

    assert client.run_service_terminate_run.call_count == 2
    assert all(
        call.kwargs["run_id"] == "owned-run"
        for call in client.run_service_terminate_run.call_args_list
    )
    assert clock.now == 35


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
        assert "tags.pipeline_run_id = 'selected-run'" in filters
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


@pytest.mark.parametrize("creates_index", [False, True])
def test_analysis_only_reuses_prebuilt_index_and_checks_new_run(
    monkeypatch, tmp_path, creates_index
):
    helpers = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
    test = helpers["test_analysis_only_pipeline_returns_report"]
    waiter = Mock()
    monkeypatch.setitem(test.__globals__, "_wait_for_run", waiter)
    client = Mock()
    client.get_experiment_by_name.return_value = SimpleNamespace(experiment_id="1")
    report = tmp_path / "report.md"
    report.write_text("# Analysis from the prebuilt index", encoding="utf-8")
    report_path = f"results/pipelines/{helpers['GIT_SLUG']}/migration_report.md"
    client.list_artifacts.return_value = [SimpleNamespace(path=report_path, is_dir=False)]
    client.download_artifacts.return_value = str(report)

    def search_runs(**kwargs):
        filters = kwargs["filter_string"]
        assert "tags.pipeline_run_id = 'new-analysis-run'" in filters
        assert "8e71296d-5458-4433-a7b5-48aea9caf346" not in filters
        if "tags.category = 'analysis'" in filters:
            return [
                SimpleNamespace(
                    info=SimpleNamespace(run_id="analysis-artifacts"),
                    data=SimpleNamespace(tags={"multi_repo": "False"}),
                )
            ]
        assert "tags.category = 'indexing'" in filters
        return (
            [SimpleNamespace(info=SimpleNamespace(run_id="unexpected-index"))]
            if creates_index
            else []
        )

    client.search_runs.side_effect = search_runs

    def run_cli(command, **kwargs):
        if command[0] == "make":
            assert "ARGS=--single-repo --analysis-only" in command
            assert "PIPELINE_RUN_ID=8e71296d-5458-4433-a7b5-48aea9caf346" in command
            return ""
        assert command[:3] == ["oc", "logs", "job/run-pipelines"]
        return "Submitted run id: new-analysis-run\n"

    kfp = Mock()
    if creates_index:
        with pytest.raises(AssertionError, match="created.*index"):
            test(run_cli, kfp, client, "namespace", tmp_path)
    else:
        test(run_cli, kfp, client, "namespace", tmp_path)
        assert client.search_runs.call_count == 2
    waiter.assert_called_once_with(kfp, "new-analysis-run", 40 * 60)


def test_multi_repo_submission_applies_readme_list_before_submitting(monkeypatch):
    helpers = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
    submit = helpers["_submit_and_wait"]
    waiter = Mock()
    monkeypatch.setitem(submit.__globals__, "_wait_for_run", waiter)
    run_cli = Mock(side_effect=["", "", "Submitted run id: selected-run\n"])
    client = Mock()

    assert (
        submit(
            run_cli,
            client,
            "namespace",
            "--multi-repo",
            pipeline_timeout=4 * 60 * 60,
            repo_list=helpers["REPO_LIST"],
        )
        == "selected-run"
    )

    commands = [call.args[0] for call in run_cli.call_args_list]
    assert commands[0] == [
        "make",
        "apply-secrets",
        f"PIPELINE_GIT_REPO_LIST={helpers['REPO_LIST']}",
    ]
    assert commands[1] == ["make", "run-pipelines", "ARGS=--multi-repo"]
    assert commands[2] == [
        "oc",
        "logs",
        "job/run-pipelines",
        "--namespace",
        "namespace",
    ]
    waiter.assert_called_once_with(client, "selected-run", 4 * 60 * 60)
    assert run_cli.call_args_list[0].kwargs["timeout"] == 500
    assert run_cli.call_args_list[1].kwargs["timeout"] == 500


@pytest.mark.parametrize(
    "test_name, timeout",
    [
        ("test_single_repo_pipeline_creates_report_and_index", 3 * 60 * 60),
        ("test_multi_repo_pipeline_creates_report_and_index", 4 * 60 * 60),
    ],
)
def test_full_pipeline_waits_use_individual_timeouts(monkeypatch, tmp_path, test_name, timeout):
    helpers = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
    test = helpers[test_name]
    waiter = Mock()
    monkeypatch.setitem(test.__globals__, "_wait_for_run", waiter)
    monkeypatch.setitem(test.__globals__, "_assert_analysis_report", Mock())
    monkeypatch.setitem(test.__globals__, "_assert_index", Mock())
    run_cli = Mock(return_value="Submitted run id: owned-run\n")
    client = Mock()

    test(run_cli, client, Mock(), "namespace", tmp_path)

    waiter.assert_called_once_with(client, "owned-run", timeout)


@pytest.mark.parametrize(
    "test_name",
    ["test_adhoc_query_returns_answer", "test_multi_repo_combined_index_query_returns_answer"],
)
def test_queries_allow_ten_minutes(test_name):
    helpers = runpy.run_path(str(CLI_TESTS / "test_cli_pipelines.py"))
    run_cli = Mock(return_value="ADHOC RESULTS\nA useful answer.\n")

    helpers[test_name](run_cli)

    assert run_cli.call_args.kwargs["timeout"] == 10 * 60


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
