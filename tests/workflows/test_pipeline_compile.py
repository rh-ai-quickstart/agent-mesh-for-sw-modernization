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

    for mode in ("single", "multi"):
        document = yaml.safe_load((tmp_path / f"{mode}_repo.yaml").read_text())
        assert document["root"]["inputDefinitions"]["parameters"]["analysis_only"] == {
            "defaultValue": False,
            "isOptional": True,
            "parameterType": "BOOLEAN",
        }
        root_task = next(iter(document["root"]["dag"]["tasks"].values()))
        branches = document["components"][root_task["componentRef"]["name"]]["dag"]["tasks"]
        condition = "inputs.parameter_values['pipelinechannel--analysis_only'] == true"
        assert {task["triggerPolicy"]["condition"] for task in branches.values()} == {
            condition,
            f"!({condition})",
        }
        for branch in branches.values():
            tasks = document["components"][branch["componentRef"]["name"]]["dag"]["tasks"]
            analysis_tasks = [name for name in tasks if name.startswith("graphrag-analysis")]
            assert len(analysis_tasks) == 1
            report = tasks[analysis_tasks[0]]
            if branch["triggerPolicy"]["condition"] == condition:
                assert set(tasks) == {"load-existing-index-op", analysis_tasks[0]}
                assert report["dependentTasks"] == ["load-existing-index-op"]
                assert report["inputs"]["artifacts"]["graphrag_dir"] == {
                    "taskOutputArtifact": {
                        "outputArtifactKey": "graphrag_dir",
                        "producerTask": "load-existing-index-op",
                    }
                }
                lookup = tasks["load-existing-index-op"]["inputs"]["parameters"]
                if mode == "single":
                    assert lookup == {
                        name: {"componentInputParameter": f"pipelinechannel--{name}"}
                        for name in ("git_repo", "git_branch", "multi_repo")
                    }
                else:
                    assert lookup["multi_repo"] == {"runtimeValue": {"constant": True}}
            else:
                generation = f"data-generation{'-multi-repo' if mode == 'multi' else ''}-pipeline"
                indexing = f"graphrag-indexing{'-multi-repo' if mode == 'multi' else ''}-pipeline"
                assert set(tasks) == {generation, indexing, analysis_tasks[0]}
                assert tasks[indexing]["dependentTasks"] == [generation]
                assert report["dependentTasks"] == [indexing]
        if mode == "multi":
            assert "get-repo-list-op" in collect_task_names(document)
