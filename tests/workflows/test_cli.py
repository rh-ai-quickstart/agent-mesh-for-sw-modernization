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
        "def trigger_run(pipeline_name, run_name, params, repos=None):\n"
        "    with open(os.environ['TEST_SUBMISSION'], 'w') as output:\n"
        "        json.dump(dict(pipeline_name=pipeline_name, run_name=run_name, "
        "params=params, repos=repos), output)\n"
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
    repos = [
        {"git_repo": "https://github.com/example/one", "git_branch": "dev"},
        {"git_repo": "https://github.com/example/two"},
    ]
    # Analysis-only must work without a repository list (or an upload).
    env["GIT_REPO_LIST_CONTENTS"] = "" if analysis_only else json.dumps(repos)
    args = [f"--{mode}-repo"]
    if analysis_only:
        args.append("--analysis-only")

    result = run_script(*args, env=env)

    assert result.returncode == 0, result.stderr
    assert "Submitted run id: mock-run-123" in result.stdout
    submission = json.loads(capture.read_text())
    assert submission["pipeline_name"] == f"{mode}_repo"
    prefix = "analysis_" if analysis_only else ""
    assert re.fullmatch(f"{prefix}{mode}_repo_" + r"\d{8}_\d{6}", submission["run_name"])
    expected_params = {
        "parent_source_path": "custom/source",
        "parent_target_path": "custom/target",
    }
    if mode == "single":
        expected_params.update(git_repo=env["GIT_REPO"], git_branch="develop")
    if analysis_only:
        expected_params["analysis_only"] = True
    assert submission["params"] == expected_params
    assert submission["repos"] == (repos if mode == "multi" and not analysis_only else None)


def test_full_multi_repo_requires_repository_list(capture_submission):
    capture, env = capture_submission
    env["GIT_REPO_LIST_CONTENTS"] = "[]"

    result = run_script("--multi-repo", env=env)

    assert result.returncode != 0
    assert "GIT_REPO_LIST_CONTENTS is required" in result.stderr
    assert not capture.exists()
