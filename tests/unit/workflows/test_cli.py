import json
import os
import re
import subprocess

import pytest
from conftest import WORKFLOW_ROOT

SCRIPT = WORKFLOW_ROOT / "scripts" / "run_pipelines.sh"


def run_script(*args, env=None):
    process_env = os.environ.copy()
    process_env.pop("GIT_REPO", None)
    process_env.pop("KFP_NAMESPACE", None)
    process_env.update(env or {})
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_help_succeeds_without_contacting_kfp():
    result = run_script("--help", env={"KFP_NAMESPACE": "test"})

    assert result.returncode == 0
    assert "Usage:" in result.stderr


def test_missing_namespace_fails_clearly():
    result = run_script("--multi-repo")

    assert result.returncode == 1
    assert "KFP_NAMESPACE must be set" in result.stderr


def test_single_repo_requires_repository_url():
    result = run_script("--single-repo", env={"KFP_NAMESPACE": "test"})

    assert result.returncode == 1
    assert "GIT_REPO must be set" in result.stderr


def test_unknown_argument_fails_clearly():
    result = run_script("--unknown", env={"KFP_NAMESPACE": "test"})

    assert result.returncode == 1
    assert "Unknown argument: --unknown" in result.stderr


@pytest.fixture
def capture_submission(tmp_path):
    """Run the real shell and embedded Python, replacing only the KFP service."""
    capture = tmp_path / "submission.json"
    (tmp_path / "sitecustomize.py").write_text(
        "import json, os, sys\n"
        "from types import ModuleType, SimpleNamespace\n"
        "service = ModuleType('services.trigger_run')\n"
        "def trigger_run(pipeline_name, run_name, params, *, enable_caching=False):\n"
        "    with open(os.environ['TEST_SUBMISSION'], 'w') as output:\n"
        "        json.dump(dict(pipeline_name=pipeline_name, run_name=run_name, "
        "params=params, enable_caching=enable_caching), output)\n"
        "    return SimpleNamespace(run_id='mock-run-123')\n"
        "service.trigger_run = trigger_run\n"
        "sys.modules['services.trigger_run'] = service\n"
    )
    return capture, {
        "PYTHONPATH": str(tmp_path),
        "TEST_SUBMISSION": str(capture),
        "KFP_NAMESPACE": "test",
        "GIT_REPO": "https://github.com/example/repo",
        "GIT_BRANCH": "develop",
        "PARENT_SOURCE_PATH": "custom/source",
        "PARENT_TARGET_PATH": "custom/target",
    }


@pytest.mark.parametrize("mode", ["single", "multi"])
@pytest.mark.parametrize("analysis_only", [False, True])
def test_successful_invocation_passes_parameters_and_repos(
    capture_submission, mode, analysis_only
):
    capture, env = capture_submission
    if analysis_only:
        env["PIPELINE_RUN_ID"] = "prev-run"
    args = [f"--{mode}-repo"]
    if analysis_only:
        args.append("--analysis-only")

    result = run_script(*args, env=env)

    assert result.returncode == 0, result.stderr
    assert "Submitted run id: mock-run-123" in result.stdout
    submission = json.loads(capture.read_text())
    assert submission["pipeline_name"] == f"{mode}_repo"
    assert re.fullmatch(f"{mode}_repo_" + r"\d{8}_\d{6}", submission["run_name"])
    expected_params = {
        "parent_source_path": "custom/source",
        "parent_target_path": "custom/target",
        "pipeline_run_id": "prev-run" if analysis_only else "",
    }
    if mode == "single":
        expected_params.update(git_repo=env["GIT_REPO"], git_branch="develop")
    assert submission["params"] == expected_params
    assert submission["enable_caching"] is analysis_only


def test_analysis_only_requires_pipeline_run_id(capture_submission):
    capture, env = capture_submission
    env.pop("PIPELINE_RUN_ID", None)

    result = run_script("--single-repo", "--analysis-only", env=env)

    assert result.returncode == 1
    assert "PIPELINE_RUN_ID must be set" in result.stderr
    assert not capture.exists()
