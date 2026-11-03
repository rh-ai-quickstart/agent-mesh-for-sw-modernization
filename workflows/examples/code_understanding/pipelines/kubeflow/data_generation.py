import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))

from typing import NamedTuple  # noqa: E402

from kfp import dsl  # noqa: E402
from kfp.dsl import Dataset, Input, Output  # noqa: E402
from utils.kubeflow_utils import DATA_GENERATION_BASE_IMAGE  # noqa: E402
from utils.kubeflow_utils import (  # noqa: E402
    get_pip_installable_git_url,
    harden_skill_component,
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
@dsl.component(
    base_image=DATA_GENERATION_BASE_IMAGE, packages_to_install=[_AGENTMESH_INSTALLABLE_URL]
)
def prepare_environment_op(
    git_repo: str, git_branch: str, source_dir: Output[Dataset], pipeline_run_id: str = ""
):
    """Clones the repository and archives it as a gzip tarball."""

    from pipelines.base.data_generation import prepare_environment
    from utils.kubeflow_utils import setup_logging, use_ephemeral_space, write_to_output_artifact

    setup_logging()

    with write_to_output_artifact(source_dir) as tmp_source, use_ephemeral_space() as tmp_target:
        prepare_environment(
            source_path=tmp_source,
            target_path=tmp_target,
            git_repo=git_repo,
            git_branch=git_branch,
            pipeline_run_id=pipeline_run_id,
        )


@inject_secret_as_env(secret_name="code-understanding-env")
@harden_skill_component
@dsl.component(
    base_image=DATA_GENERATION_BASE_IMAGE, packages_to_install=[_AGENTMESH_INSTALLABLE_URL]
)
def preflight_op(
    git_repo: str,
    git_branch: str,
    source_dir: Input[Dataset],
    multi_repo: bool = False,
    pipeline_run_id: str = "",
) -> NamedTuple("Outputs", [("languages", list), ("external_metadata_json", str)]):
    """Runs preflight relevant skills."""
    import json
    import logging
    import signal
    import traceback
    from collections import namedtuple

    from pipelines.base.data_generation import run_preflight
    from utils import code_utils
    from utils.kubeflow_utils import read_from_input_artifact, setup_logging, sigterm_handler

    setup_logging()
    signal.signal(signal.SIGTERM, sigterm_handler)

    Outputs = namedtuple("Outputs", ["languages", "external_metadata_json"])

    with read_from_input_artifact(source_dir) as tmp_source:
        git_slug = code_utils.generate_slug_from_repo(git_repo, git_branch)
        try:
            result = run_preflight(tmp_source, git_slug, pipeline_run_id=pipeline_run_id)
        except Exception:
            logging.error(
                "Preflight failed for repo=%s branch=%s git_slug=%s:\n%s",
                git_repo,
                git_branch,
                git_slug,
                traceback.format_exc(),
            )
            if not multi_repo:
                raise
            return Outputs(languages=[], external_metadata_json=json.dumps([]))

    return Outputs(
        languages=result.languages,
        external_metadata_json=json.dumps(result.external_metadata),
    )


@inject_secret_as_env(secret_name="code-understanding-env")
@inject_secret_as_env(secret_name="git-credentials")
@dsl.component(
    base_image=DATA_GENERATION_BASE_IMAGE, packages_to_install=[_AGENTMESH_INSTALLABLE_URL]
)
def generate_code_and_meta_op(
    git_repo: str,
    git_branch: str,
    source_dir: Input[Dataset],
    target_dir: Output[Dataset],
    languages: list,
    external_metadata_json: str,
    multi_repo: bool = False,
    pipeline_run_id: str = "",
):
    """Generates code metadata for all detected languages."""
    import json
    import logging

    from exceptions import EmptyLanguagesError
    from pipelines.base.data_generation import generate_code_and_meta
    from utils.kubeflow_utils import (
        read_from_input_artifact,
        setup_logging,
        write_to_output_artifact,
    )

    setup_logging()

    with (
        read_from_input_artifact(source_dir) as tmp_source,
        write_to_output_artifact(target_dir) as tmp_target,
    ):
        try:

            external_metadata = json.loads(external_metadata_json)

            generate_code_and_meta(
                git_repo=git_repo,
                git_branch=git_branch,
                languages=languages,
                source_path=tmp_source,
                target_path=tmp_target,
                multi_repo=multi_repo,
                external_metadata=external_metadata,
                pipeline_run_id=pipeline_run_id,
            )

        except Exception as e:

            is_rate_limit = type(e).__name__ == "RateLimitError" or "429" in str(e)
            is_empty_languages = isinstance(e, EmptyLanguagesError)
            hint = " Consider reducing GRAPHRAG_PARALLEL_REPOS." if is_rate_limit else ""

            if is_rate_limit or is_empty_languages:
                logging.error(
                    f"Data generation failed for repo '{git_repo}' (branch='{git_branch}')"
                    f" [{type(e).__name__}]: {e}{hint}"
                )
                raise

            logging.error(
                f"Skipping repo '{git_repo}' (branch='{git_branch}') [{type(e).__name__}]: {e}"
            )


@inject_secret_as_env(secret_name="code-understanding-env")
@dsl.component(
    base_image=DATA_GENERATION_BASE_IMAGE, packages_to_install=[_AGENTMESH_INSTALLABLE_URL]
)
def get_repo_list_op(repos: str = "[]") -> list:
    """Returns the repo list for this pipeline run and logs it to the asset store."""
    import json

    from loaders.default_asset_loader import DefaultAssetLoader
    from services.get_run_repos import get_run_repos
    from utils.kubeflow_utils import setup_logging

    setup_logging()

    repo_list = get_run_repos(json.loads(repos))
    DefaultAssetLoader().log_repos(repo_list)
    return repo_list


##############################################################################
# Pipelines
##############################################################################


@dsl.pipeline(name="data-generation-pipeline")
def _run_pipeline(
    git_repo: str = os.getenv("GIT_REPO", ""),
    git_branch: str = os.getenv("GIT_BRANCH", "main"),
    multi_repo: bool = False,
    pipeline_run_id: str = "",
) -> Dataset:

    prep = prepare_environment_op(
        git_repo=git_repo,
        git_branch=git_branch,
        pipeline_run_id=pipeline_run_id,
    )

    pre = preflight_op(
        git_repo=git_repo,
        git_branch=git_branch,
        source_dir=prep.outputs["source_dir"],
        multi_repo=multi_repo,
        pipeline_run_id=pipeline_run_id,
    )

    gen = generate_code_and_meta_op(
        git_repo=git_repo,
        git_branch=git_branch,
        source_dir=prep.outputs["source_dir"],
        languages=pre.outputs["languages"],
        external_metadata_json=pre.outputs["external_metadata_json"],
        multi_repo=multi_repo,
        pipeline_run_id=pipeline_run_id,
    )

    return gen.outputs["target_dir"]


@dsl.pipeline(name="data-generation-multi-repo-pipeline")
def _run_pipeline_multi_repo(  # noqa: B006 — mutable default is safe here: KFP
    repos: list = [], pipeline_run_id: str = ""
):
    """Generates code metadata for all repositories in the repo list."""

    with dsl.ParallelFor(
        items=repos, parallelism=int(os.getenv("GRAPHRAG_PARALLEL_REPOS", "2"))
    ) as repo:

        _run_pipeline(
            git_repo=repo.git_repo,
            git_branch=repo.git_branch,
            multi_repo=True,
            pipeline_run_id=pipeline_run_id,
        )


##############################################################################
# Pipeline stage
##############################################################################


def _get_repo_list(repos):
    # Resolve the repo list at the top-level pipeline so the list param is passed
    # directly to a component (not through an intermediate sub-pipeline - recommended
    # for KFP v2).
    task = get_repo_list_op(repos=repos)
    return task


class DataGenerationPipeline:
    run = staticmethod(_run_pipeline)
    run_multi_repo = staticmethod(_run_pipeline_multi_repo)
    get_repo_list = staticmethod(_get_repo_list)
