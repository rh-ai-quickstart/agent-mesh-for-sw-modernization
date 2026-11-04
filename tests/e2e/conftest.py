"""Opt in to deployed E2E tests that launch real pipeline runs."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-pipelines",
        action="store_true",
        default=False,
        help="Run deployed E2E tests that submit pipelines or analysis runs.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-pipelines"):
        return
    skip = pytest.mark.skip(reason="Requires --run-pipelines (make test-e2e RUN_PIPELINES=true).")
    for item in items:
        if item.get_closest_marker("pipeline"):
            item.add_marker(skip)
