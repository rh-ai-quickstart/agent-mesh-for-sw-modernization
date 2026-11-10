import os
import subprocess
import sys

import yaml
from conftest import REPO_ROOT, WORKFLOW_ROOT

EXPECTED_PIPELINES = {
    "analysis.yaml",
    "data_generation.yaml",
    "indexing.yaml",
    "multi_repo.yaml",
    "single_repo.yaml",
}


def collect_task_names(value):
    task_names = set()
    if isinstance(value, dict):
        tasks = value.get("tasks")
        if isinstance(tasks, dict):
            task_names.update(tasks)
        for child in value.values():
            task_names.update(collect_task_names(child))
    elif isinstance(value, list):
        for child in value:
            task_names.update(collect_task_names(child))
    return task_names


def test_all_pipelines_compile(tmp_path):
    env = os.environ | {
        "PYTHONPATH": str(WORKFLOW_ROOT),
        "KUBECONFIG": os.devnull,
        "PIPELINE_COMPILE_ONLY": "1",
        "KFP_PIPELINE_OUTPUT_DIR": str(tmp_path),
        "KFP_IMAGE_REGISTRY": "quay.io/test",
        "KFP_DATA_GENERATION_BASE_IMAGE_NAME": "data-generation",
        "KFP_DATA_GENERATION_BASE_IMAGE_TAG": "test",
        "KFP_INDEXING_BASE_IMAGE_NAME": "data-indexing",
        "KFP_INDEXING_BASE_IMAGE_TAG": "test",
        "KFP_ANALYSIS_BASE_IMAGE_NAME": "data-analysis",
        "KFP_ANALYSIS_BASE_IMAGE_TAG": "test",
        "AGENTMESH_REPO_URL": (
            "https://github.com/rh-ai-quickstart/" "agent-mesh-for-sw-modernization.git"
        ),
        "AGENTMESH_REPO_REF": "main",
        "GIT_USERNAME": "ci",
        "GIT_TOKEN": "unused",
    }

    subprocess.run(
        [sys.executable, str(WORKFLOW_ROOT / "pipelines" / "orchestrator.py")],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )

    generated = {path.name for path in tmp_path.glob("*.yaml")}
    assert generated == EXPECTED_PIPELINES

    def _load_pipeline(path):
        """Return first non-None document from a potentially multi-document YAML file."""
        return next(
            (d for d in yaml.safe_load_all(path.read_text()) if d is not None),
            None,
        )

    for path in tmp_path.glob("*.yaml"):
        document = _load_pipeline(path)
        assert document["pipelineInfo"]["name"]
        assert document["root"]["dag"]["tasks"]

        images = {
            executor["container"]["image"]
            for executor in document["deploymentSpec"]["executors"].values()
        }
        assert all("None" not in image for image in images)
        assert all(not image.endswith(":latest") for image in images)

        preflight = document["deploymentSpec"]["executors"].get("exec-preflight-op")
        if preflight is not None:
            resources = preflight["container"]["resources"]
            # A CPU limit without a request becomes a full reservation in Kubernetes.
            assert resources["resourceCpuRequest"] == "100m"
            assert resources["resourceCpuLimit"] == "2"

    for mode in ("single", "multi"):
        document = _load_pipeline(tmp_path / f"{mode}_repo.yaml")
        # pipeline_run_id (string) replaces analysis_only (bool) from ext-tools
        params = document["root"]["inputDefinitions"]["parameters"]
        assert "analysis_only" not in params
        assert "pipeline_run_id" in params
        assert params["pipeline_run_id"]["parameterType"] == "STRING"
        # No ext-tools branching components
        task_names = collect_task_names(document)
        assert "load-existing-index-op" not in task_names
        # multi-repo uses get-repo-list-op; single-repo does not
        if mode == "multi":
            assert "get-repo-list-op" in task_names
        else:
            assert "get-repo-list-op" not in task_names
        # Indexing component receives pipeline_run_id (not kfp_run_id in HEAD)
        component_name = (
            "run-indexing-multi-repo-op" if mode == "multi" else "graphrag-indexing-op"
        )
        indexing_component = document["components"][f"comp-{component_name}"]
        indexing_params = indexing_component["inputDefinitions"]["parameters"]
        assert "pipeline_run_id" in indexing_params
        assert indexing_params["pipeline_run_id"]["parameterType"] == "STRING"
