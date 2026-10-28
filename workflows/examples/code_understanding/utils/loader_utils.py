import json
import logging
import os

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())


def merge_json_enrichment(base, override, treat_lists_as_singletons: bool = False):
    """Recursively merges override into base. Delegates to json_utils.merge_json."""
    from utils.json_utils import merge_json

    return merge_json(base, override, treat_lists_as_singletons)


def is_global_scoped_enrichment(path: str) -> bool:
    """Returns True if the path is global-scoped — i.e., at or under .enrichments/.assets."""
    parts = os.path.normpath(path).split(os.sep)
    return any(
        parts[i] == ".enrichments" and parts[i + 1] == ".assets"
        for i in range(len(parts) - 1)
    )


def get_global_scoped_enrichment_dir(base_dir: str | None) -> str | None:
    """Returns the global-scoped enrichments assets directory for base_dir.

    Returns None if base_dir is None.  If base_dir is already the enrichments
    assets directory (.enrichments/.assets), it is returned unchanged.
    Otherwise {base_dir}/.enrichments/.assets is returned.
    """
    if not base_dir:
        return None
    if is_global_scoped_enrichment(base_dir):
        return base_dir
    return os.path.join(base_dir, ".enrichments", ".assets")


def is_global_scoped_enrichment_tagset(tags: dict) -> bool:
    """Returns True if tags represent a global-scoped enrichment run
    (category=enrichments with git_slug explicitly None)."""
    return (
        bool(tags)
        and tags.get("category") == "enrichments"
        and "git_slug" in tags
        and tags["git_slug"] is None
    )


def normalize_asset_path(asset_path: str) -> str:
    """Strip a leading /assets/ prefix from asset_path if present."""

    _, sep, remainder = ("/" + asset_path).partition("/assets/")

    return remainder if sep else asset_path


def load_local_enrichments(download_dir: str, asset_path: str, *, is_dir: bool = False):
    """Tier 1: check the global-scoped enrichments assets directory on the local filesystem.

    ``download_dir`` is passed to ``get_global_scoped_enrichment_dir`` so callers
    may pass either the repository root or the assets directory itself.

    Returns resolved content (file) or True (directory) on hit, None on miss.
    """
    if not download_dir:
        return None

    local_path = os.path.join(get_global_scoped_enrichment_dir(download_dir), asset_path)

    if is_dir and os.path.isdir(local_path):
        logging.debug("Resolved asset dir from local enrichments: %s", local_path)
        return True

    if not is_dir and os.path.isfile(local_path):
        logging.debug("Resolved asset from local enrichments: %s", local_path)
        with open(local_path, "r") as f:
            content = json.load(f) if local_path.endswith(".json") else f.read()
        return content

    return None


def process_enrichments(loader, assets_dir: str) -> None:
    """For each file in assets_dir, merges its JSON content with the static counterpart
    if one exists."""
    import json
    from pathlib import Path

    if not os.path.exists(assets_dir):
        return

    for path in Path(assets_dir).rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(assets_dir)
        try:
            enrichment = json.loads(path.read_text())
            original = loader.download(str(rel_path))
            original = json.loads(original) if isinstance(original, str) else original
            if original:
                path.write_text(json.dumps(merge_json_enrichment(original, enrichment), indent=2))
        except (json.JSONDecodeError, ValueError):
            continue


def download_result_directory(
    git_slug: str,
    download_dir: str,
    results_prefix: str,
    multi_repo: bool,
    asset_tags: dict,
    namespace: str | None = None,
):
    """Downloads a single repo's assets from the backing store to download_dir."""

    from loaders.asset_loader import AssetLoader
    from loaders.default_asset_loader import DefaultAssetLoader

    DefaultAssetLoader(namespace=namespace).download_dir(
        asset_dir_path=DefaultAssetLoader.get_log_results_artifact_path(
            results_prefix,
            git_slug=git_slug,
            multi_repo=multi_repo,
        ),
        download_dir=download_dir,
        experiment_name=AssetLoader.RESULT_DIRECTORY_ASSET_EXPERIMENT,
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
