import os
import subprocess

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
