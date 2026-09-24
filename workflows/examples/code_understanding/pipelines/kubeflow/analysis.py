import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))

from kfp import dsl  # noqa: E402
from kfp.dsl import Dataset, Input, Markdown, Output  # noqa: E402
from utils.kubeflow_utils import (  # noqa: E402
    ANALYSIS_BASE_IMAGE,
    get_pip_installable_git_url,
    inject_secret_as_env,
)

_AGENTMESH_INSTALLABLE_URL = get_pip_installable_git_url(
    git_username=os.getenv("GIT_USERNAME"),
    git_token=os.getenv("GIT_TOKEN"),
    repo_url=os.getenv("AGENTMESH_REPO_URL", ""),
    repo_ref=os.getenv("AGENTMESH_REPO_REF", "main"),
    subdirectory="workflows/examples/code_understanding",
)


##############################################################################
# Components
##############################################################################


@inject_secret_as_env(secret_name="code-understanding-env")
@inject_secret_as_env(secret_name="git-credentials")
@dsl.component(base_image=ANALYSIS_BASE_IMAGE, packages_to_install=[_AGENTMESH_INSTALLABLE_URL])
def generate_migration_report_op(
    graphrag_dir: Input[Dataset],
    report: Output[Markdown],
    git_repo: str = "",
    git_branch: str = "",
    multi_repo: bool = False,
):

    from pipelines.base.analysis import write_migration_report
    from utils.kubeflow_utils import read_from_input_artifact, setup_logging

    setup_logging()

    with read_from_input_artifact(graphrag_dir) as tmp_graphrag:
        write_migration_report(
            tmp_graphrag,
            report.path,
            git_repo=git_repo,
            git_branch=git_branch,
            multi_repo=multi_repo,
        )


@inject_secret_as_env(secret_name="code-understanding-env")
@dsl.component(base_image=ANALYSIS_BASE_IMAGE, packages_to_install=[_AGENTMESH_INSTALLABLE_URL])
def run_analysis_multi_repo_op(graphrag_dir: Input[Dataset], report: Output[Markdown]):
    """Runs migration report generation across the combined multi-repo GraphRAG index."""

    from pipelines.base.analysis import write_migration_report
    from utils.kubeflow_utils import read_from_input_artifact, setup_logging

    setup_logging()

    with read_from_input_artifact(graphrag_dir) as tmp_graphrag:
        write_migration_report(tmp_graphrag, report.path, multi_repo=True)


##############################################################################
# Pipeline
##############################################################################


@dsl.pipeline(name="graphrag-analysis-pipeline")
def _run_pipeline(
    graphrag_dir: Input[Dataset],
    git_repo: str = "",
    git_branch: str = "",
    multi_repo: bool = False,
):

    task = generate_migration_report_op(
        graphrag_dir=graphrag_dir, git_repo=git_repo, git_branch=git_branch, multi_repo=multi_repo
    )
    task.set_env_variable("KFP_RUN_ID", dsl.PIPELINE_JOB_ID_PLACEHOLDER)


@dsl.pipeline(name="graphrag-analysis-multi-repo-pipeline")
def _run_multi_repo_pipeline(graphrag_dir: Input[Dataset]):

    task = run_analysis_multi_repo_op(graphrag_dir=graphrag_dir)
    task.set_env_variable("KFP_RUN_ID", dsl.PIPELINE_JOB_ID_PLACEHOLDER)


##############################################################################
# Pipeline stage
##############################################################################


class AnalysisPipeline:
    run = staticmethod(_run_pipeline)
    run_multi_repo = staticmethod(_run_multi_repo_pipeline)
