"""Run the publication gate against actual Git histories and push boundaries."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/build-and-push.yaml").read_text())
GATE = next(
    step["run"] for step in WORKFLOW["jobs"]["version"]["steps"] if step.get("id") == "version"
)


def git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def commit(repo, version, message):
    (repo / "Makefile").write_text(f"BASE_VERSION ?= {version}\n# {message}\n")
    git(repo, "add", "Makefile")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init")
    git(tmp_path, "config", "user.name", "Workflow Test")
    git(tmp_path, "config", "user.email", "workflow-test@example.com")
    scripts = tmp_path / ".github/scripts"
    scripts.mkdir(parents=True)
    (scripts / "image_version.py").write_bytes(
        (ROOT / ".github/scripts/image_version.py").read_bytes()
    )
    return tmp_path


def run_gate(repo, before):
    result = subprocess.run(
        ["bash", "-e", "-c", GATE],
        cwd=repo,
        env={
            **os.environ,
            "BEFORE_SHA": before,
            "RUNNER_TEMP": str(repo),
            "GITHUB_OUTPUT": str(repo / "output"),
            "GITHUB_STEP_SUMMARY": str(repo / "summary"),
        },
        capture_output=True,
        text=True,
    )
    outputs = dict(line.split("=", 1) for line in (repo / "output").read_text().splitlines())
    return result, outputs


@pytest.mark.parametrize(
    ("versions", "changed"),
    [
        (["v0.1.6"], "false"),
        (["v0.1.7"], "true"),
        (["v0.1.7", "v0.1.7"], "true"),
        (["v0.1.7", "v0.1.6"], "false"),
    ],
)
def test_compares_version_across_entire_push(repo, versions, changed):
    before = commit(repo, "v0.1.6", "before push")
    for index, version in enumerate(versions):
        commit(repo, version, f"push commit {index}")
    result, outputs = run_gate(repo, before)
    assert result.returncode == 0, result.stderr
    assert outputs == {"version": versions[-1], "changed": changed}


def test_skips_new_branch_without_previous_commit(repo):
    commit(repo, "v0.1.6", "initial commit")
    result, outputs = run_gate(repo, "0" * 40)
    assert result.returncode == 0, result.stderr
    assert outputs["changed"] == "false"


def test_does_not_publish_when_previous_commit_cannot_be_read(repo):
    commit(repo, "v0.1.7", "current commit")
    result, outputs = run_gate(repo, "f" * 40)
    assert result.returncode != 0
    assert outputs.get("changed") != "true"
