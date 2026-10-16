"""Exercise the release workflow CLI against isolated Makefiles."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / ".github" / "scripts" / "image_version.py"
MAKEFILE = "# image defaults\nBASE_VERSION    ?= v0.1.6\nIMAGE_TAG ?= $(BASE_VERSION)\n"


def run_version(tmp_path, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "BASE_VERSION": "v9.9.9", "VERSION": "dev"},
    )


def test_read_uses_committed_default_without_loading_env(tmp_path):
    makefile = tmp_path / "Makefile"
    makefile.write_text(MAKEFILE)
    (tmp_path / ".env").write_text("BASE_VERSION=v8.8.8\n")
    result = run_version(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v0.1.6"
    assert makefile.read_text() == MAKEFILE


def test_reads_previous_makefile_without_changing_current_default(tmp_path):
    (tmp_path / "Makefile").write_text(MAKEFILE)
    previous = tmp_path / "Makefile.before"
    previous.write_text(MAKEFILE.replace("v0.1.6", "v0.1.5"))
    result = run_version(tmp_path, "--makefile", str(previous))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v0.1.5"
    assert (tmp_path / "Makefile").read_text() == MAKEFILE


@pytest.mark.parametrize("args", [("--bump",), ("--bump", ""), ("--bump", "v0.1.7")])
def test_patch_bump_changes_only_base_version(tmp_path, args):
    makefile = tmp_path / "Makefile"
    makefile.write_text(MAKEFILE)
    result = run_version(tmp_path, *args)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v0.1.7"
    assert makefile.read_text() == MAKEFILE.replace("v0.1.6", "v0.1.7")


@pytest.mark.parametrize("version", ["v0.2.0", "v1.0.0", "v0.1.10"])
def test_accepts_greater_versions_numerically(tmp_path, version):
    makefile = tmp_path / "Makefile"
    makefile.write_text(MAKEFILE)
    result = run_version(tmp_path, "--bump", version)
    assert result.returncode == 0, result.stderr
    assert makefile.read_text() == MAKEFILE.replace("v0.1.6", version)


@pytest.mark.parametrize(
    "version",
    [
        "v0.1.6",
        "v0.1.5",
        "v0.0.99",
        "0.1.7",
        "v0.01.7",
        "v0.1.7-rc.1",
        "latest",
        "$(touch injected)",
        "v0.1.7\nOTHER=value",
    ],
)
def test_rejects_invalid_or_non_increasing_versions_without_changes(tmp_path, version):
    makefile = tmp_path / "Makefile"
    makefile.write_text(MAKEFILE)
    result = run_version(tmp_path, "--bump", version)
    assert result.returncode != 0
    assert result.stderr
    assert result.stdout == ""
    assert makefile.read_text() == MAKEFILE
    assert not (tmp_path / "injected").exists()


def test_patch_bump_preserves_comments_and_handles_multiple_digits(tmp_path):
    makefile = tmp_path / "Makefile"
    original = MAKEFILE.replace("v0.1.6", "v0.1.9  # published images")
    makefile.write_text(original)
    result = run_version(tmp_path, "--bump")
    assert result.returncode == 0, result.stderr
    assert makefile.read_text() == original.replace("v0.1.9", "v0.1.10")


@pytest.mark.parametrize(
    "content",
    ["IMAGE_TAG ?= latest\n", MAKEFILE + "BASE_VERSION ?= v0.1.7\n", "BASE_VERSION ?= latest\n"],
)
def test_rejects_missing_duplicate_or_invalid_defaults(tmp_path, content):
    makefile = tmp_path / "Makefile"
    makefile.write_text(content)
    result = run_version(tmp_path, "--bump")
    assert result.returncode != 0
    assert makefile.read_text() == content
