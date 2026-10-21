"""Check single- and multi-repo CLI pipelines and independently query the index.

These tests require an existing deployment and oc login. Pipeline tests also
require --run-pipelines (or make test-cli-e2e RUN_PIPELINES=true). The query test
uses the existing index. CLI_E2E_PIPELINE_TIMEOUT_SECONDS defaults to one hour;
CLI_E2E_COMMAND_TIMEOUT_SECONDS defaults to 30 minutes.
"""

import os
import re
import time
from pathlib import Path

import pytest
from kfp_server_api import ApiException
from urllib3.exceptions import HTTPError

from ui.catalog import git_slug

REPO = "https://github.com/agapebondservant/tic-tac-toe-sample"
BRANCH = "main"
QUESTION = "Which components should we investigate first, and why?"
GIT_SLUG = git_slug(REPO, BRANCH)
REPO_LIST = (
    Path(__file__).resolve().parents[3]
    / "workflows/examples/code_understanding/assets/repos/repo_list.json"
)


def _artifact_run(client, namespace, experiment_suffix, category, kfp_run_id, *, multi_repo=False):
    experiment_name = f"{namespace}/code-refactoring/assets/{experiment_suffix}"
    experiment = client.get_experiment_by_name(experiment_name)
    assert experiment is not None, f"Missing MLflow experiment: {experiment_name}"
    scope = "" if multi_repo else f" AND tags.git_slug = '{GIT_SLUG}'"
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=(
            "attributes.status = 'FINISHED'"
            f" AND tags.category = '{category}'"
            f"{scope}"
            f" AND tags.kfp_run_id = '{kfp_run_id}'"
        ),
        order_by=["attributes.start_time DESC"],
        max_results=100,
    )
    run = next(
        (
            run
            for run in runs
            if str(run.data.tags.get("multi_repo", "")).lower() == str(multi_repo).lower()
            and str(run.data.tags.get("adhoc_query", "")).lower() != "true"
        ),
        None,
    )
    assert (
        run is not None
    ), f"No completed {category} artifacts for KFP run {kfp_run_id} in {experiment_name}."
    return run.info.run_id


def _wait_for_run(client, run_id, timeout):
    """Poll KFP with a monotonic deadline and a separate connection-error budget."""
    deadline = time.monotonic() + timeout
    last_state = "UNKNOWN"
    consecutive_errors = 0
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            run = client.run_service_get_run(
                run_id=run_id, _request_timeout=(min(10, remaining), min(30, remaining))
            )
        except (HTTPError, ApiException) as exc:
            status = getattr(exc, "status", None)
            if isinstance(exc, ApiException) and status not in (0, 408, 429, 500, 502, 503, 504):
                pytest.fail(
                    f"Could not monitor KFP run {run_id}: API returned HTTP {status}. "
                    "Check route access and oc authentication; the pipeline may still be running."
                )
            consecutive_errors += 1
            if consecutive_errors >= 5:
                pytest.fail(
                    f"Could not monitor KFP run {run_id} after 5 consecutive request failures "
                    f"({type(exc).__name__}); last observed state: {last_state}. "
                    "The pipeline may still be running."
                )
            print(
                f"KFP run {run_id}: temporary monitoring error; retry {consecutive_errors}/5.",
                flush=True,
            )
        else:
            consecutive_errors = 0
            state = getattr(run, "state", None)
            last_state = str(getattr(state, "name", state) or "PENDING").upper()
            print(f"KFP run {run_id}: {last_state}", flush=True)
            if last_state == "SUCCEEDED":
                return
            if last_state in {"FAILED", "ERROR", "CANCELED", "CANCELLED", "SKIPPED"}:
                pytest.fail(f"KFP run {run_id} ended with state {last_state}.")
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    pytest.fail(
        f"KFP run {run_id} did not complete within {timeout}s; last observed state: {last_state}. "
        "This test timeout does not cancel the pipeline."
    )


def _submit_and_wait(run_cli, client, namespace, args, *, repo_list=None):
    command_timeout = int(os.environ.get("CLI_E2E_COMMAND_TIMEOUT_SECONDS", "1800"))
    pipeline_timeout = int(os.environ.get("CLI_E2E_PIPELINE_TIMEOUT_SECONDS", "3600"))

    command = ["make", "run-pipelines", f"ARGS={args}"]
    if repo_list is not None:
        run_cli(
            ["make", "apply-secrets", f"PIPELINE_GIT_REPO_LIST={repo_list}"],
            name="pipeline-repository-list",
            timeout=command_timeout,
        )
    else:
        command.extend([f"PIPELINE_GIT_REPO={REPO}", f"PIPELINE_GIT_BRANCH={BRANCH}"])
    run_cli(command, name="pipeline-submission", timeout=command_timeout)
    submission_log = run_cli(
        ["oc", "logs", "job/run-pipelines", "--namespace", namespace],
        name="pipeline-submission-logs",
        timeout=60,
    )
    run_ids = re.findall(r"Submitted run id:\s*(\S+)", submission_log)
    assert len(run_ids) == 1, f"Expected one submitted KFP run:\n{submission_log}"
    run_id = run_ids[0]

    _wait_for_run(client, run_id, pipeline_timeout)

    return run_id


def _assert_analysis_report(client, namespace, run_id, tmp_path, *, multi_repo=False):
    report_run_id = _artifact_run(
        client, namespace, "results", "analysis", run_id, multi_repo=multi_repo
    )
    report_path = "results/pipelines/multi-repo" if multi_repo else f"results/pipelines/{GIT_SLUG}"
    report_files = [
        artifact
        for artifact in client.list_artifacts(report_run_id, report_path)
        if not artifact.is_dir and artifact.path.endswith(".md")
    ]
    assert (
        len(report_files) == 1
    ), f"Expected one analysis report for KFP run {run_id}: {report_files}"
    report = Path(client.download_artifacts(report_run_id, report_files[0].path, str(tmp_path)))
    assert report.read_text(encoding="utf-8").strip(), f"Empty analysis report: {report}"


def _assert_index(client, namespace, run_id, tmp_path, *, multi_repo=False):
    index_run_id = _artifact_run(
        client, namespace, "result-directories", "indexing", run_id, multi_repo=multi_repo
    )
    index_path = (
        "results/datasets/repos/multi-repo" if multi_repo else f"results/datasets/repos/{GIT_SLUG}"
    )
    index_files = {
        artifact.path: artifact
        for artifact in client.list_artifacts(index_run_id, index_path)
        if not artifact.is_dir
    }
    import pyarrow.parquet as parquet

    for table in ("entities", "relationships", "text_units", "communities", "community_reports"):
        path = f"{index_path}/{table}.parquet"
        assert path in index_files, f"KFP run {run_id} produced no index table: {path}"
        local_path = client.download_artifacts(index_run_id, path, str(tmp_path))
        assert (
            parquet.ParquetFile(local_path).metadata.num_rows > 0
        ), f"KFP run {run_id} produced an empty index table: {path}"


def _assert_query_answer(output):
    # Ignore the wrapper's spinner and ANSI line-clearing sequences. Require an
    # answer after the results header, rather than accepting progress logs.
    output = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)
    result = re.search(r"^[^\n]*ADHOC RESULTS[^\n]*\n(.*)", output, flags=re.MULTILINE | re.DOTALL)
    assert result, f"Query returned no ADHOC RESULTS section:\n{output}"
    answer = result[1].strip()
    assert answer and answer.lower() not in {
        "none",
        "null",
    }, f"Query returned an empty answer:\n{output}"
    assert "Could not perform query:" not in answer, f"Query could not use its index:\n{answer}"
    assert "Traceback (most recent call last)" not in answer, answer


def test_adhoc_query_returns_answer(run_cli):
    command_timeout = int(os.environ.get("CLI_E2E_COMMAND_TIMEOUT_SECONDS", "1800"))
    output = run_cli(
        ["wrappers/adhoc.sh", QUESTION, "--git-repo", REPO, "--git-branch", BRANCH],
        name="adhoc-query",
        timeout=command_timeout,
    )
    _assert_query_answer(output)


@pytest.mark.pipeline
def test_analysis_only_pipeline_returns_report(
    run_cli, deployed_kfp_client, deployed_mlflow_client, deployed_namespace, tmp_path
):
    run_id = _submit_and_wait(
        run_cli, deployed_kfp_client, deployed_namespace, "--single-repo --analysis-only"
    )
    _assert_analysis_report(deployed_mlflow_client, deployed_namespace, run_id, tmp_path)


@pytest.mark.pipeline
def test_single_repo_pipeline_creates_report_and_index(
    run_cli, deployed_kfp_client, deployed_mlflow_client, deployed_namespace, tmp_path
):
    run_id = _submit_and_wait(run_cli, deployed_kfp_client, deployed_namespace, "--single-repo")
    client = deployed_mlflow_client
    _assert_analysis_report(client, deployed_namespace, run_id, tmp_path)

    _assert_index(client, deployed_namespace, run_id, tmp_path)


@pytest.mark.pipeline
def test_multi_repo_pipeline_creates_report_and_index(
    run_cli, deployed_kfp_client, deployed_mlflow_client, deployed_namespace, tmp_path
):
    run_id = _submit_and_wait(
        run_cli, deployed_kfp_client, deployed_namespace, "--multi-repo", repo_list=REPO_LIST
    )
    _assert_analysis_report(
        deployed_mlflow_client, deployed_namespace, run_id, tmp_path, multi_repo=True
    )
    _assert_index(deployed_mlflow_client, deployed_namespace, run_id, tmp_path, multi_repo=True)


@pytest.mark.pipeline
def test_multi_repo_combined_index_query_returns_answer(run_cli):
    command_timeout = int(os.environ.get("CLI_E2E_COMMAND_TIMEOUT_SECONDS", "1800"))
    output = run_cli(
        [
            "wrappers/adhoc.sh",
            "Which repositories share dependencies that affect migration order?",
        ],
        name="combined-index-query",
        timeout=command_timeout,
    )
    _assert_query_answer(output)
