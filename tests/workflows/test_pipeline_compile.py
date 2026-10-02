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

    for path in tmp_path.glob("*.yaml"):
        document = yaml.safe_load(path.read_text())
        assert document["pipelineInfo"]["name"]
        assert document["root"]["dag"]["tasks"]

        images = {
            executor["container"]["image"]
            for executor in document["deploymentSpec"]["executors"].values()
        }
        assert all("None" not in image for image in images)
        assert all(not image.endswith(":latest") for image in images)

    single_repo = yaml.safe_load((tmp_path / "single_repo.yaml").read_text())
    single_tasks = single_repo["root"]["dag"]["tasks"]
    assert single_tasks["graphrag-indexing-pipeline"]["dependentTasks"] == [
        "data-generation-pipeline"
    ]
    assert single_tasks["graphrag-analysis-pipeline"]["dependentTasks"] == [
        "graphrag-indexing-pipeline"
    ]

    multi_repo = yaml.safe_load((tmp_path / "multi_repo.yaml").read_text())
    multi_tasks = multi_repo["root"]["dag"]["tasks"]
    assert "get-repo-list-op" in collect_task_names(multi_repo)
    assert multi_tasks["graphrag-indexing-multi-repo-pipeline"]["dependentTasks"] == [
        "data-generation-multi-repo-pipeline"
    ]
    assert multi_tasks["graphrag-analysis-multi-repo-pipeline"]["dependentTasks"] == [
        "graphrag-indexing-multi-repo-pipeline"
    ]
