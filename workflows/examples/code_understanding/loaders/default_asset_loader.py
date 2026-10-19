import os

from .asset_loader import AssetLoader
from .local_asset_loader import LocalAssetLoader


class DefaultAssetLoader(AssetLoader):
    """Delegates to LocalAssetLoader or MlFlowAssetLoader based on the ASSET_LOADER env var.

    Enrichments-aware callers pass git_slug alongside download_dir (which must be the
    repository root) to activate three-tier resolution:
      1. Local <download_dir>/.enrichments/.assets/ — checked here before delegating.
      2. MLflow enrichments experiment, keyed by git_slug — MlFlowAssetLoader only.
      3. Default static-asset store — fallback for both loaders.
    """

    def __init__(self, namespace: str = None):
        if os.getenv("ASSET_LOADER") == "mlflow":
            # Deferred import: mlflow has a circular-import bug in some versions that
            # triggers when it is imported at module level.  Importing here ensures mlflow
            # is only loaded when it is actually needed.
            from .mlflow_asset_loader import MlFlowAssetLoader

            self._loader = MlFlowAssetLoader(namespace=namespace)

        else:

            self._loader = LocalAssetLoader()

    def download(
        self,
        asset_file_path: str,
        download_dir: str = None,
        experiment_name=None,
        asset_tags=None,
        git_slug: str | None = None,
    ):
        from utils.loader_utils import load_local_enrichments, normalize_asset_path

        asset_file_path = normalize_asset_path(asset_file_path)

        return load_local_enrichments(download_dir, asset_file_path) or self._loader.download(
            asset_file_path,
            download_dir,
            experiment_name=experiment_name,
            asset_tags=asset_tags,
            git_slug=git_slug,
        )

    def download_dir(
        self,
        asset_dir_path: str,
        download_dir: str,
        experiment_name=None,
        asset_tags=None,
        git_slug: str | None = None,
    ):
        from utils.loader_utils import load_local_enrichments, normalize_asset_path

        asset_dir_path = normalize_asset_path(asset_dir_path)

        return load_local_enrichments(
            download_dir, asset_dir_path, is_dir=True
        ) or self._loader.download_dir(
            asset_dir_path,
            download_dir,
            experiment_name=experiment_name,
            asset_tags=asset_tags,
            git_slug=git_slug,
        )

    def load_results(
        self,
        download_dir: str,
        artifact_path: str = None,
        tags: dict = None,
        git_slug: str | None = None,
    ):
        if download_dir and os.path.isdir(download_dir) and os.listdir(download_dir):
            return True

        return self._loader.load_results(download_dir, artifact_path, tags, git_slug)

    def log_results(
        self,
        results_path: str,
        artifact_path: str = None,
        tags: dict = None,
        content: str = None,
    ):

        return self._loader.log_results(results_path, artifact_path, tags, content)

    def log_static_asset(
        self, results_path: str, artifact_path: str = None, tags: dict = None, content: str = None
    ):

        return self._loader.log_static_asset(results_path, artifact_path, tags, content)

    def upload_all_assets(self, assets_dir: str):

        return self._loader.upload_all_assets(assets_dir)

    def upload_prompt(self, prompt_path: str):

        return self._loader.upload_prompt(prompt_path)

    def load_skill(self, name: str) -> tuple[str, dict]:

        return self._loader.load_skill(name)

    def download_prompt(self, prompt_path: str, **kwargs) -> tuple[str, dict]:

        return self._loader.download_prompt(prompt_path, **kwargs)

    def log_enrichments(self, repo_dir: str, git_slug: str | None = None) -> str:
        from utils.loader_utils import process_enrichments

        process_enrichments(self, os.path.join(repo_dir, ".enrichments", ".assets"))

        return self._loader.log_enrichments(repo_dir, git_slug)

    def log_repos(self, git_repos: list) -> None:

        return self._loader.log_repos(git_repos)

    def load_run_repos(self, run_id: str | None = None) -> list:

        return self._loader.load_run_repos(run_id=run_id)

    def load_catalog_repos(self) -> list:

        return self._loader.load_catalog_repos()

    def num_prompts(self, prompt_prefix: str) -> int:

        return self._loader.num_prompts(prompt_prefix)
