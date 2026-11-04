"""CLI E2E fixtures for an existing deployment; run with make test-cli-e2e."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from workflows.examples.code_understanding.utils.service_utils import get_token

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def deployed_namespace():
    namespace = os.environ.get("KFP_NAMESPACE", "").strip()
    if not namespace:
        pytest.fail(
            "KFP_NAMESPACE is not set; run with make test-cli-e2e KFP_NAMESPACE=<project>."
        )
    for command in ("make", "oc", "helm", "bash"):
        if not shutil.which(command):
            pytest.fail(f"CLI E2E tests require {command} on PATH.")
    return namespace


@pytest.fixture
def run_cli(deployed_namespace, tmp_path):
    """Keep complete command output for diagnostics, including failed commands."""
    env = {**os.environ, "KFP_NAMESPACE": deployed_namespace}
    # Nested make commands must use the same deployment configuration, without
    # inheriting command-line overrides from the outer make invocation.
    for key in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES"):
        env.pop(key, None)
    env["MAKEFLAGS"] = f"-- KFP_NAMESPACE={deployed_namespace}"

    def run(args, *, name, timeout):
        output_file = tmp_path / f"{name}.log"
        with output_file.open("w", encoding="utf-8") as output:
            try:
                result = subprocess.run(
                    args,
                    cwd=PROJECT_ROOT,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                pytest.fail(
                    f"{name} timed out after {timeout}s. Output: {output_file}\n"
                    f"{output_file.read_text(encoding='utf-8')}"
                )
        text = output_file.read_text(encoding="utf-8")
        assert (
            result.returncode == 0
        ), f"{name} exited with {result.returncode}. Output: {output_file}\n{text}"
        return text

    return run


@pytest.fixture
def deployed_mlflow_client(deployed_namespace, run_cli, monkeypatch):
    """Use the external MLflow gateway and the selected deployment's workspace."""
    from mlflow.tracking import MlflowClient

    uri = os.environ.get("MLFLOW_GATEWAY_URL", "").strip() or os.environ.get(
        "LOCAL_MLFLOW_TRACKING_URI", ""
    )
    if not uri:
        host = run_cli(
            [
                "oc",
                "get",
                "route",
                "data-science-gateway",
                "--namespace",
                "openshift-ingress",
                "-o",
                "jsonpath={.spec.host}",
            ],
            name="mlflow-gateway",
            timeout=60,
        ).strip()
        assert host, "The data-science-gateway Route has no host."
        uri = f"https://{host}/mlflow"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("MLFLOW_WORKSPACE", deployed_namespace)
    monkeypatch.setenv("MLFLOW_NAMESPACE", deployed_namespace)
    monkeypatch.setenv("MLFLOW_TRACKING_AUTH", "kubernetes-namespaced")
    monkeypatch.setenv("MLFLOW_TRACKING_INSECURE_TLS", "true")
    return MlflowClient(tracking_uri=uri)


@pytest.fixture
def deployed_kfp_client(deployed_namespace, run_cli):
    """Reach KFP through its authenticated external route, without a port-forward."""
    import kfp_server_api

    host = os.environ.get("CLI_E2E_KFP_HOST", "").strip()
    if not host:
        route_host = run_cli(
            [
                "oc",
                "get",
                "route",
                "ds-pipeline-dspa",
                "--namespace",
                deployed_namespace,
                "-o",
                "jsonpath={.spec.host}",
            ],
            name="kfp-route",
            timeout=60,
        ).strip()
        assert route_host, "The ds-pipeline-dspa Route has no host."
        host = f"https://{route_host}"
    assert host.startswith("https://"), "CLI_E2E_KFP_HOST must be an HTTPS URL."

    configuration = kfp_server_api.Configuration(host=host.rstrip("/"))
    # Match the project's existing KFP client TLS setting.
    configuration.verify_ssl = False
    configuration.retries = 0  # The polling loop owns the retry budget.
    with kfp_server_api.ApiClient(
        configuration=configuration,
        header_name="Authorization",
        header_value=f"Bearer {get_token()}",
    ) as api_client:
        yield kfp_server_api.RunServiceApi(api_client)
