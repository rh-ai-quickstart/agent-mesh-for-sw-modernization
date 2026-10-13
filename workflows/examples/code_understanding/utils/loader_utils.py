import json
import logging
import os

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())


def is_global_scoped_enrichment(path: str) -> bool:
    """Returns True if the enrichment path is global-scoped (under .assets), False if repo-scoped."""
    return ".assets" in path


def normalize_asset_path(asset_path: str) -> str:
    """Strip a leading /assets/ prefix from asset_path if present."""

    _, sep, remainder = ("/" + asset_path).partition("/assets/")

    return remainder if sep else asset_path


def load_local_enrichments(download_dir: str, asset_path: str, *, is_dir: bool = False):
    """Tier 1: check <download_dir>/.enrichments/.assets/ on the local filesystem.

    Returns resolved content (file) or True (directory) on hit, None on miss.
    """
    if not download_dir:
        return None

    local_path = os.path.join(download_dir, ".enrichments", ".assets", asset_path)

    if is_dir and os.path.isdir(local_path):
        logging.debug("Resolved asset dir from local enrichments: %s", local_path)
        return True

    if not is_dir and os.path.isfile(local_path):
        logging.debug("Resolved asset from local enrichments: %s", local_path)
        with open(local_path, "r") as f:
            content = json.load(f) if local_path.endswith(".json") else f.read()
        return content

    return None


def download_result_directory(
    git_slug: str,
    download_dir: str,
    results_prefix: str,
    multi_repo: bool,
    asset_tags: dict,
    namespace: str | None = None,
):
    """Downloads a single repo's assets from the backing store to download_dir."""

    from loaders.default_asset_loader import DefaultAssetLoader
    from loaders.mlflow_asset_loader import MlFlowAssetLoader

    DefaultAssetLoader(namespace=namespace).download_dir(
        asset_dir_path=DefaultAssetLoader.get_log_results_artifact_path(
            results_prefix,
            git_slug=git_slug,
            multi_repo=multi_repo,
        ),
        download_dir=download_dir,
        experiment_name=MlFlowAssetLoader.RESULT_DIRECTORY_ASSET_EXPERIMENT,
        asset_tags=asset_tags,
    )


def download_code_metadata_directories(git_repos: list, parent_target_path: str):
    """Downloads generated code metadata for each repo in git_repos to
    parent_target_path/<slug>."""

    from loaders.default_asset_loader import DefaultAssetLoader
    from utils.code_utils import generate_slug_from_repo

    for git_data in git_repos:

        git_repo = git_data["git_repo"]

        git_branch = git_data["git_branch"]

        repo_slug = generate_slug_from_repo(git_repo, git_branch)

        repo_target_path = os.path.join(parent_target_path, repo_slug)

        try:

            logging.info(f"Downloading generated data for {git_repo} ({repo_slug})...")

            download_result_directory(
                git_slug=repo_slug,
                download_dir=repo_target_path,
                results_prefix=DefaultAssetLoader.RESULTS_PATH_PREFIX_METADATA,
                multi_repo=True,
                asset_tags={
                    "git_slug": repo_slug,
                    "category": "data-generation",
                    "code-metadata": True,
                    "multi_repo": True,
                },
            )
        except Exception:

            logging.error(
                f"Could not find generated data for {git_repo} ({repo_slug}); skipping..."
            )
