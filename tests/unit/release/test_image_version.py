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


def test_patch_bump_changes_only_base_version(tmp_path):
    makefile = tmp_path / "Makefile"
    original = MAKEFILE.replace("v0.1.6", "v0.1.9  # published images")
    makefile.write_text(original)
    result = run_version(tmp_path, "--bump", "")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v0.1.10"
    assert makefile.read_text() == original.replace("v0.1.9", "v0.1.10")


def test_accepts_explicit_version_numerically(tmp_path):
    makefile = tmp_path / "Makefile"
    makefile.write_text(MAKEFILE)
    result = run_version(tmp_path, "--bump", "v0.1.10")
    assert result.returncode == 0, result.stderr
    assert makefile.read_text() == MAKEFILE.replace("v0.1.6", "v0.1.10")


@pytest.mark.parametrize("version", ["v0.1.6", "v0.1.5", "latest"])
def test_rejects_invalid_or_non_increasing_versions_without_changes(tmp_path, version):
    makefile = tmp_path / "Makefile"
    makefile.write_text(MAKEFILE)
    result = run_version(tmp_path, "--bump", version)
    assert result.returncode != 0
    assert result.stderr
    assert result.stdout == ""
    assert makefile.read_text() == MAKEFILE


@pytest.mark.parametrize(
    "content",
    ["IMAGE_TAG ?= latest\n", MAKEFILE + "BASE_VERSION ?= v0.1.7\n"],
)
def test_rejects_missing_or_duplicate_defaults(tmp_path, content):
    makefile = tmp_path / "Makefile"
    makefile.write_text(content)
    result = run_version(tmp_path, "--bump")
    assert result.returncode != 0
    assert makefile.read_text() == content
