import json
import logging
import os
import traceback

import mlflow  # noqa: F401 - module-level import intentional to prevent
               # circular-import

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())

from .asset_loader import AssetLoader  # noqa: E402


class MlFlowAssetLoader(AssetLoader):
    """Loads an asset from the MLflow artifacts registry."""

    _RUN_NAME = "code-understanding"

    def __init__(self, namespace: str = None):

        ns = namespace or os.environ.get(
            "MLFLOW_NAMESPACE", os.environ.get("KFP_NAMESPACE", "demo")
        )
        self.STATIC_ASSET_EXPERIMENT = f"{ns}/code-refactoring/assets/static"
        self.RESULT_DIRECTORY_ASSET_EXPERIMENT = f"{ns}/code-refactoring/assets/result-directories"
        self.RESULT_ASSET_EXPERIMENT = f"{ns}/code-refactoring/assets/results"

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")

        if tracking_uri:
            import mlflow

            mlflow.set_tracking_uri(tracking_uri)

    def _get_absolute_artifact_uri(
        self, asset_file_path: str, experiment_name: str, tags: dict = None
    ):
        import mlflow

        client = mlflow.tracking.MlflowClient()

        experiment = self.get_or_create_experiment_by_name(client, experiment_name)

        if experiment_name == self.STATIC_ASSET_EXPERIMENT and not tags:

            filter_string = "tags.latest = 'true'"

        else:

            filter_parts = []
            for k, v in (tags or {}).items():
                if v is None:
                    filter_parts.append(f'tags."{k}" IS NULL')
                elif v != "":
                    filter_parts.append(f"tags.\"{k}\" = '{str(v)}'")
            filter_string = " AND ".join(filter_parts)

        logging.debug(f"Filter string: {filter_string}")

        latest_runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=filter_string,
            order_by=["attributes.start_time DESC"],
            max_results=1,
        )

        asset_base_uri = (
            latest_runs[0].info.artifact_uri if latest_runs else experiment.artifact_location
        )

        logging.info(f"Base absolute storage URI: {asset_base_uri}")

        return os.path.join(asset_base_uri, asset_file_path)

    def _mark_as_latest(self, client, experiment_id, new_run_id, tags: dict = None):

        filter_parts = ["tags.latest = 'true'"]
        if tags:
            for k, v in tags.items():
                if v is None:
                    filter_parts.append(f'tags."{k}" IS NULL')
                elif v != "":
                    filter_parts.append(f"tags.\"{k}\" = '{str(v)}'")

        existing = client.search_runs(
            experiment_ids=[experiment_id],
            filter_string=" AND ".join(filter_parts),
        )

        for run in existing:

            client.set_tag(run.info.run_id, "latest", "false")

        client.set_tag(new_run_id, "latest", "true")

    def get_or_create_experiment_by_name(self, client, experiment_name):
        """Gets or creates an MLflow experiment by name, handling deleted and non-active states."""

        experiment = client.get_experiment_by_name(experiment_name)

        if experiment:

            if experiment.lifecycle_stage == "deleted":

                logging.info(f"Experiment '{experiment_name}' is deleted. Restoring.")

                client.restore_experiment(experiment.experiment_id)

                experiment = client.get_experiment(experiment.experiment_id)

            elif experiment.lifecycle_stage != "active":

                logging.info(
                    f"Experiment '{experiment_name}' is not active. Deleting and recreating."
                )

                client.delete_experiment(experiment.experiment_id)

                experiment = client.get_experiment(client.create_experiment(name=experiment_name))

            return experiment

        return client.get_experiment(client.create_experiment(name=experiment_name))

    def _get_download_candidate_metadata(
        self,
        asset_path: str,
        git_slug: str | None,
        experiment_name: str | None,
        asset_tags: dict | None,
    ) -> list:
        """Returns the ordered list of (path, experiment_name, tags) candidates to try."""
        from utils.loader_utils import is_global_scoped_enrichment

        enrichment_path = asset_path
        if not enrichment_path.startswith(AssetLoader.RESULTS_PATH_PREFIX_ENRICHMENTS):
            prefix = f"{AssetLoader.RESULTS_PATH_PREFIX_ENRICHMENTS}/.assets"
            enrichment_path = f"{prefix}/{enrichment_path}"
        enrichment_tags = {"category": "enrichments"}
        if is_global_scoped_enrichment(enrichment_path):
            enrichment_tags["git_slug"] = None
        else:
            enrichment_tags["git_slug"] = git_slug
        return [
            (enrichment_path, self.RESULT_DIRECTORY_ASSET_EXPERIMENT, enrichment_tags),
            (asset_path, experiment_name or self.STATIC_ASSET_EXPERIMENT, asset_tags),
        ]

    def download(
        self,
        asset_file_path: str,
        download_dir: str = None,
        experiment_name=None,
        asset_tags: dict = None,
        git_slug: str = None,
    ):
        """Downloads and returns the asset from the MLflow artifacts registry.

        Args:
            asset_file_path: Path to the asset file relative to its artifact backend location
                in MLflow.
            download_dir: Optional directory path to download the artifact to.
            experiment_name: The name of the MLflow experiment to search for the asset.
            asset_tags: Optional tags to filter the asset by.
            git_slug: Optional repository slug for enrichments-aware resolution.

        Returns:
            The asset content (parsed dict for .json files, str otherwise), or None if not found.
        """
        import mlflow

        candidates = self._get_download_candidate_metadata(
            asset_file_path, git_slug, experiment_name, asset_tags
        )

        for path, exp_name, tags in candidates:

            try:

                asset_uri = self._get_absolute_artifact_uri(
                    path, experiment_name=exp_name, tags=tags
                )

                local_path = mlflow.artifacts.download_artifacts(
                    artifact_uri=asset_uri,
                    dst_path=download_dir,
                )

                with open(local_path, "r") as f:

                    return json.load(f) if asset_uri.endswith(".json") else f.read()

            except Exception:

                logging.info(
                    "Asset %s not found, trying next candidate: %s",
                    path,
                    traceback.format_exc(),
                )

        return None

    def download_dir(
        self,
        asset_dir_path: str,
        download_dir: str,
        experiment_name=None,
        asset_tags: dict = None,
        git_slug: str = None,
    ):
        """Downloads a directory from the MLflow artifacts registry to a local directory."""
        import mlflow

        candidates = self._get_download_candidate_metadata(
            asset_dir_path, git_slug, experiment_name, asset_tags
        )

        parent_dir = os.path.dirname(os.path.abspath(download_dir))

        for path, exp_name, tags in candidates:
            try:

                asset_uri = self._get_absolute_artifact_uri(
                    path, experiment_name=exp_name, tags=tags
                )

                os.makedirs(parent_dir, exist_ok=True)

                mlflow.artifacts.download_artifacts(artifact_uri=asset_uri, dst_path=parent_dir)

                return True

            except Exception:

                logging.info(
                    "Asset %s not found, trying next candidate: %s",
                    path,
                    traceback.format_exc(),
                )

        raise Exception(f"Asset {asset_dir_path} not found.")

    def load_results(
        self,
        download_dir: str,
        artifact_path: str = None,
        tags: dict = None,
        git_slug: str | None = None,
    ):
        """Downloads a previously logged result directory from MLflow to download_dir.

        Silently skips if no prior results exist (e.g. on first run).
        """
        try:
            result = self.download_dir(
                artifact_path,
                download_dir,
                experiment_name=self.RESULT_DIRECTORY_ASSET_EXPERIMENT,
                asset_tags=tags,
                git_slug=git_slug,
            )
            logging.info("Loaded prior results from %s to %s", artifact_path, download_dir)
            return result
        except Exception as e:
            logging.info("No prior results to load from %s: %s", artifact_path, e)

    def log_results(
        self,
        results_path: str,
        artifact_path: str = None,
        tags: dict = None,
        content: str = None,
    ):
        """Logs pipeline output artifacts to a new MLflow run."""
        import mlflow

        try:
            is_dir = os.path.isdir(results_path)

            from utils.pipeline_utils import get_pipeline_run_id

            pipeline_run_id = get_pipeline_run_id()
            if pipeline_run_id:
                tags = {**(tags or {}), "pipeline_run_id": pipeline_run_id}

            if os.path.dirname(results_path):

                os.makedirs(os.path.dirname(results_path), exist_ok=True)

            if content is not None and not is_dir:

                with open(results_path, "w") as f:

                    f.write(content)

            client = mlflow.tracking.MlflowClient()

            experiment_name = (
                self.RESULT_DIRECTORY_ASSET_EXPERIMENT if is_dir else self.RESULT_ASSET_EXPERIMENT
            )

            experiment = self.get_or_create_experiment_by_name(client, experiment_name)

            with mlflow.start_run(experiment_id=experiment.experiment_id) as run:

                if tags:

                    mlflow.set_tags(tags)

                if is_dir:

                    mlflow.log_artifacts(results_path, artifact_path=artifact_path)

                else:

                    mlflow.log_artifact(results_path, artifact_path=artifact_path)

                logging.info(f"Logged results to run {run.info.run_id}")

                return run.info.run_id

        except Exception as e:

            logging.error(f"Error logging results {results_path}: {e}")

            raise e

    def log_static_asset(
        self, results_path: str, artifact_path: str = None, tags: dict = None, content: str = None
    ):
        """Logs an artifact to STATIC_ASSET_EXPERIMENT so ``download`` can retrieve it."""
        import mlflow
        import tempfile

        try:
            is_dir = os.path.isdir(results_path)

            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
                # When content is provided, write to a temp directory so we are not
                # dependent on the current working directory being writable.
                if content is not None and not is_dir:
                    log_path = os.path.join(tmp_dir, os.path.basename(results_path))
                    with open(log_path, "w") as f:
                        f.write(content)
                else:
                    log_path = results_path
                    if os.path.dirname(results_path):
                        os.makedirs(os.path.dirname(results_path), exist_ok=True)

                client = mlflow.tracking.MlflowClient()

                experiment = self.get_or_create_experiment_by_name(
                    client, self.STATIC_ASSET_EXPERIMENT
                )

                with mlflow.start_run(experiment_id=experiment.experiment_id) as run:

                    if tags:

                        mlflow.set_tags(tags)

                    if is_dir:

                        mlflow.log_artifacts(log_path, artifact_path=artifact_path)

                    else:

                        mlflow.log_artifact(log_path, artifact_path=artifact_path)

                    logging.info(f"Logged asset to run {run.info.run_id}")

        except Exception as e:

            logging.error(f"Error logging asset {results_path}: {e}")

            raise e

    def get_prompt_name(self, prompt_path: str) -> str:
        """Derives the MLflow prompt registry name by replacing path separators with dashes
        and using a double-dash to delimit the directory from the filename."""
        prompt_name = "--".join(prompt_path.rsplit("/", 1))

        prompt_name = prompt_name.replace("/", "-")

        return prompt_name

    def upload_prompt(self, prompt_path: str):
        """Registers a prompt template from the local assets directory to the MLflow prompt
        registry."""
        import mlflow

        try:

            asset_uri = os.path.join(self._PROMPTS_DIR, prompt_path + ".txt")

            with open(asset_uri, "r") as f:
                content = f.read()

            name = self.get_prompt_name(prompt_path)

            mlflow.genai.register_prompt(name=name, template=content)

            logging.info(f"Registered prompt '{name}'")

        except Exception as e:

            logging.error(f"Error registering prompt {prompt_path}: {e}")

            raise e

    def load_skill(self, name: str) -> tuple[str, dict]:
        """Loads a skill from the MLflow prompt registry.

        The skill must have been uploaded first via ``upload_all_assets``.

        Args:
            name: Skill name (must match the file stem under assets/prompts/skills/).

        Returns:
            Tuple of (body string, frontmatter metadata dict).
        """
        import mlflow

        try:

            prompt_name = self.get_prompt_name(f"skills/{name}")

            prompt = mlflow.genai.load_prompt(prompt_name)

            body, meta = self._get_prompt_body_and_metadata(prompt.template)

            return body, meta

        except Exception as e:

            logging.error(f"Error loading skill {name}: {e}")

            raise e

    def download_prompt(self, prompt_path: str, **kwargs) -> tuple[str, dict]:
        """Loads a prompt from the MLflow prompt registry and renders it with the provided
        variables."""
        import mlflow

        try:

            from jinja2 import Template

            name = self.get_prompt_name(prompt_path)

            prompt = mlflow.genai.load_prompt(name)

            body, meta = self._get_prompt_body_and_metadata(prompt.template)

            return Template(body).render(**kwargs), meta

        except Exception as e:

            logging.error(f"Error loading prompt {prompt_path}: {e}")

            raise e

    def log_enrichments(self, repo_dir: str, git_slug: str | None = None) -> str:
        """Persists the enrichments directory to the MLflow pipeline asset store."""
        enrichments_dir = os.path.join(repo_dir, ".enrichments")
        assets_dir = os.path.join(enrichments_dir, ".assets")
        os.makedirs(enrichments_dir, exist_ok=True)

        tags = {"category": "enrichments"}
        if git_slug:
            tags["git_slug"] = git_slug
        self.log_results(
            enrichments_dir, artifact_path=self.RESULTS_PATH_PREFIX_ENRICHMENTS, tags=tags
        )

        if os.path.exists(assets_dir):
            assets_artifact_path = f"{self.RESULTS_PATH_PREFIX_ENRICHMENTS}/.assets"
            self.log_results(
                assets_dir,
                artifact_path=assets_artifact_path,
                tags={"category": "enrichments"},
            )

        return f"Logged enrichments from {enrichments_dir}"

    def log_repos(self, run_repos: list) -> None:
        """Logs the repo list to the MLflow asset store: first as an enrichment under
        repos/repo_list.json, then under category: repositories.

        ``run_repos`` contains the repositories associated with the current pipeline run.
        The existing ``repos/repo_list.json`` static asset (the full catalog of all known
        repos) is used as the base and merged with ``run_repos`` via
        ``merge_json_enrichment``, producing ``catalog_repos`` — the updated union of all
        repos across the catalog. The enrichment is written with ``catalog_repos`` while
        the asset store entry is written with the unmodified ``run_repos``.
        """
        import json
        import tempfile

        from utils.loader_utils import merge_json_enrichment

        try:
            base = self.download("repos/repo_list.json") or []
            catalog_repos = merge_json_enrichment(base, run_repos)

            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
                assets_dir = os.path.join(tmp_dir, ".enrichments", ".assets", "repos")
                os.makedirs(assets_dir)
                with open(os.path.join(assets_dir, "repo_list.json"), "w") as f:
                    json.dump(catalog_repos, f)
                self.log_enrichments(tmp_dir)
        except Exception:
            logging.warning("Failed to log repo list as enrichment", exc_info=True)

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
                tmp_path = os.path.join(tmp_dir, "repo_list.json")
                self.log_results(
                    tmp_path,
                    artifact_path="repos",
                    tags={"category": "repositories"},
                    content=json.dumps(run_repos),
                )
        except Exception:
            logging.warning("Failed to log repo list to asset store", exc_info=True)

    def load_run_repos(self, run_id: str | None = None) -> list:
        """Loads the repo list from MLflow, scoped by run_id (or get_pipeline_run_id()) if set,
        falling back to GIT_REPO_LIST_CONTENTS."""
        import json

        from utils.pipeline_utils import get_pipeline_run_id

        asset_tags: dict = {"category": "repositories"}
        pipeline_run_id = run_id or get_pipeline_run_id()
        if pipeline_run_id:
            asset_tags["pipeline_run_id"] = pipeline_run_id

        return self.download(
            "repos/repo_list.json",
            experiment_name=self.RESULT_ASSET_EXPERIMENT,
            asset_tags=asset_tags,
        ) or json.loads(os.getenv("GIT_REPO_LIST_CONTENTS", "[]") or "[]")

    def load_catalog_repos(self) -> list:
        """Downloads the full repo catalog from MLflow, trying enrichments first and falling
        back to static assets.

        Delegates to ``download`` which resolves candidates via
        ``_get_download_candidate_metadata``: enrichments in
        ``RESULT_DIRECTORY_ASSET_EXPERIMENT`` are tried first, then
        ``repos/repo_list.json`` in ``STATIC_ASSET_EXPERIMENT``.
        """
        return self.download("repos/repo_list.json") or []

    def num_prompts(self, prompt_prefix: str) -> int:
        """Returns the number of prompts in the MLflow registry matching the given prefix."""
        import mlflow

        try:

            prefix = prompt_prefix.replace("/", "-")

            prompts = mlflow.genai.search_prompts(filter_string=f"name LIKE '{prefix}--%'")

            return len(prompts)

        except Exception as e:

            logging.error(f"Error counting prompts with prefix {prompt_prefix}: {e}")

            return 0

    def upload_all_assets(self, assets_dir: str):
        """Uploads all assets from a directory to the static MLflow experiment in a single run.

        Args:
            assets_dir: Local path to the directory containing assets to upload.
        """
        import mlflow

        try:

            client = mlflow.tracking.MlflowClient()

            experiment = self.get_or_create_experiment_by_name(
                client, self.STATIC_ASSET_EXPERIMENT
            )

            run = client.create_run(experiment.experiment_id, run_name=self._RUN_NAME)

            run_id = run.info.run_id

            logging.info(f"Created run: {run_id}")

            try:

                for entry in sorted(os.scandir(assets_dir), key=lambda e: e.name):

                    if entry.is_dir():

                        logging.info(f"Uploading {entry.name}/")

                        client.log_artifacts(run_id, entry.path, artifact_path=entry.name)

                    elif entry.is_file():

                        logging.info(f"Uploading {entry.name}")

                        client.log_artifact(run_id, entry.path, artifact_path="")

                for root, _, files in os.walk(self._PROMPTS_DIR):

                    for file in sorted(files):

                        abs_path = os.path.join(root, file)
                        rel_path = os.path.relpath(abs_path, self._PROMPTS_DIR)
                        prompt_path = os.path.splitext(rel_path)[0]

                        logging.info(f"Registering prompt '{prompt_path}'")

                        self.upload_prompt(prompt_path)

                client.set_terminated(run_id, status="FINISHED")

                logging.info(f"Upload complete. Run id: {run_id}")

                self._mark_as_latest(client, experiment.experiment_id, run_id)

            except Exception:

                client.set_terminated(run_id, status="FAILED")

                raise

        except Exception as e:

            logging.error(f"Error uploading assets from {assets_dir}: {e}")

            raise e
