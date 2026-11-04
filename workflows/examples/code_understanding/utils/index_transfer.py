"""Transfer completed index runs using MLflow's native single-run export format.

The caller supplies an MLflow client already configured for the selected workspace.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)
INDEX_ROOT = "results/datasets/repos"
EXPERIMENT_SUFFIX = "/code-refactoring/assets/result-directories"
MAX_BYTES = 5 * 1024**3
MAX_MEMBERS = 100_000
MAX_METADATA_BYTES = 16 * 1024**2


class IndexTransferError(ValueError):
    """The run or bundle cannot be safely transferred."""


def _safe_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:", value)
        or any(ord(char) < 32 for char in value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise IndexTransferError(f"Unsafe path: {value!r}")
    return value


def _index_identity(tags: dict) -> tuple[str, bool, str]:
    if tags.get("category") != "indexing":
        raise IndexTransferError("Run must have category=indexing")
    combined = str(tags.get("multi_repo", "")).lower()
    if combined not in {"true", "false"}:
        raise IndexTransferError("Run must have multi_repo=true or false")
    slug = tags.get("git_slug", "")
    if not isinstance(slug, str):
        raise IndexTransferError("git_slug must be a string")
    if combined == "true":
        return slug, True, f"{INDEX_ROOT}/multi-repo"
    _safe_path(slug)
    if "/" in slug or not slug.strip():
        raise IndexTransferError("git_slug must be a nonempty single path component")
    return slug, False, f"{INDEX_ROOT}/{slug}"


def bundle_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_json_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise IndexTransferError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _read_metadata(directory: Path) -> dict:
    path = directory / "run.json"
    if not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
        raise IndexTransferError("Missing or oversized run.json")
    try:
        data = json.loads(path.read_text(), object_pairs_hook=_unique_json_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IndexTransferError(f"Invalid run.json: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("system"), dict):
        raise IndexTransferError("run.json must contain the native system envelope")
    if data["system"].get("export_file_version") != "2":
        raise IndexTransferError("Only native export_file_version=2 is supported")
    run = data.get("mlflow")
    if not isinstance(run, dict):
        raise IndexTransferError("run.json must contain the native mlflow envelope")
    info = run.get("info")
    if not isinstance(info, dict) or any(
        not isinstance(info.get(key), str) or not info[key]
        for key in ("run_id", "experiment_id", "user_id")
    ):
        raise IndexTransferError("Invalid native run info")
    if info.get("status") != "FINISHED" or info.get("lifecycle_stage") != "active":
        raise IndexTransferError("Source run must be active and FINISHED")
    for name in ("tags", "params"):
        values = run.get(name)
        if not isinstance(values, dict) or any(
            not isinstance(value, str) for value in values.values()
        ):
            raise IndexTransferError(f"Invalid native run {name}")
    _index_identity(run["tags"])
    metrics = run.get("metrics")
    if not isinstance(metrics, dict):
        raise IndexTransferError("Invalid native metric histories")
    for history in metrics.values():
        if not isinstance(history, list) or any(
            not isinstance(point, dict)
            or not isinstance(point.get("value"), (float, int))
            or not isinstance(point.get("timestamp"), int)
            or not isinstance(point.get("step"), int)
            for point in history
        ):
            raise IndexTransferError("Invalid native metric history entry")
    inputs = run.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(inputs.get("dataset_inputs"), list):
        raise IndexTransferError("Invalid native dataset inputs")
    # Validate with the same entity constructors the pinned importer uses,
    # before it can create a run or experiment.
    if inputs["dataset_inputs"]:
        from mlflow.entities import Dataset, InputTag

        try:
            for item in inputs["dataset_inputs"]:
                Dataset.from_dictionary(item["dataset"])
                for tag in item["tags"]:
                    InputTag.from_dictionary(tag)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise IndexTransferError("Invalid native dataset input entry") from exc
    return data


def _local_files(directory: Path, max_bytes: int) -> dict[str, int]:
    files = {}
    total = 0
    count = 0
    for path in directory.rglob("*"):
        count += 1
        if count > MAX_MEMBERS or path.is_symlink():
            raise IndexTransferError("Too many files or a link in the export")
        if path.is_dir():
            continue
        if not path.is_file():
            raise IndexTransferError("Export contains a special file")
        relative = _safe_path(path.relative_to(directory).as_posix())
        size = path.stat().st_size
        total += size
        if total > max_bytes:
            raise IndexTransferError("Export exceeds the 5 GiB transfer limit")
        files[relative] = size
    return files


def _require_index(files: dict[str, int], artifact_path: str) -> None:
    if not any(path.startswith(artifact_path + "/") and size > 0 for path, size in files.items()):
        raise IndexTransferError(f"Missing or empty index directory: {artifact_path}")


def _extract_bundle(bundle: Path, directory: Path, max_bytes: int) -> None:
    if bundle.stat().st_size > max_bytes:
        raise IndexTransferError("Compressed bundle exceeds the 5 GiB transfer limit")
    # Scan the entire member table before writing anything. Never let tarfile
    # interpret links, devices, traversal paths, or duplicate members.
    with tarfile.open(bundle, "r:gz") as archive:
        members = []
        seen = set()
        total = 0
        for member in archive:
            name = _safe_path(member.name.rstrip("/") if member.isdir() else member.name)
            if name in seen or not (member.isfile() or member.isdir()):
                raise IndexTransferError("Duplicate member or unsupported archive entry")
            if name != "run.json" and name != "artifacts" and not name.startswith("artifacts/"):
                raise IndexTransferError("Bundle root must contain only run.json and artifacts/")
            total += member.size
            if member.size < 0 or total > max_bytes or len(members) >= MAX_MEMBERS:
                raise IndexTransferError("Extracted bundle exceeds transfer limits")
            if name == "run.json" and (not member.isfile() or member.size > MAX_METADATA_BYTES):
                raise IndexTransferError("Invalid or oversized run.json")
            seen.add(name)
            members.append((name, member))
        if "run.json" not in seen:
            raise IndexTransferError("Bundle is missing run.json")
        for name, member in members:
            target = directory / name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination)


@contextmanager
def _self_hosted_package():
    """Disable the pinned package's unauthenticated Databricks detection probe.

    Native run transfer uses the configured SDK exclusively with notebooks,
    logged models, and MLmodel rewriting disabled. Its otherwise unused HTTP
    clients must not probe Databricks endpoints on an OpenShift gateway.
    """
    from mlflow_export_import.common import utils
    from mlflow_export_import.run.export_run import export_run
    from mlflow_export_import.run.import_run import import_run

    previous = utils._calling_databricks
    utils._calling_databricks = False
    try:
        yield export_run, import_run
    finally:
        utils._calling_databricks = previous


class IndexTransfer:
    def __init__(self, client: Any, namespace: str):
        if not namespace.strip():
            raise IndexTransferError("Namespace is required")
        self.client = client
        self.namespace = namespace
        self.experiment_name = namespace + EXPERIMENT_SUFFIX
        self.max_bytes = MAX_BYTES

    def _experiment(self):
        experiment = self.client.get_experiment_by_name(self.experiment_name)
        if experiment and experiment.lifecycle_stage != "active":
            raise IndexTransferError("Selected experiment is not active")
        return experiment

    def _describe(self, run: Any, experiment_id: str) -> dict:
        info = run.info
        if (
            info.experiment_id != experiment_id
            or info.status != "FINISHED"
            or info.lifecycle_stage != "active"
        ):
            raise IndexTransferError(
                "Run must be active, FINISHED, and in the selected experiment"
            )
        slug, combined, path = _index_identity(run.data.tags)
        return {
            "git_slug": slug,
            "multi_repo": combined,
            "run_id": info.run_id,
            "experiment_id": info.experiment_id,
            "start_time": info.start_time,
            "end_time": info.end_time,
            "artifact_path": path,
            "uploaded": str(run.data.tags.get("uploaded", "")).lower() == "true",
        }

    def _search(self, experiment_id: str, extra_filter: str = ""):
        token = None
        while True:
            page = self.client.search_runs(
                experiment_ids=[experiment_id],
                filter_string="attributes.status = 'FINISHED' AND tags.category = 'indexing'"
                + extra_filter,
                run_view_type=1,  # MLflow ViewType.ACTIVE_ONLY
                order_by=["attributes.start_time DESC", "attributes.run_id ASC"],
                max_results=1000,
                page_token=token,
            )
            yield from page
            token = getattr(page, "token", None)
            if not token:
                return

    def list_indexes(self) -> dict:
        experiment = self._experiment()
        indexes = []
        if experiment:
            for run in self._search(experiment.experiment_id):
                try:
                    indexes.append(self._describe(run, experiment.experiment_id))
                except IndexTransferError as exc:
                    LOG.warning("Skipping run %s: %s", run.info.run_id, exc)
        indexes.sort(key=lambda index: (-(index["start_time"] or 0), index["run_id"]))
        seen = set()
        for index in indexes:
            key = (index["git_slug"], index["multi_repo"])
            index["latest"] = key not in seen
            seen.add(key)
        return {
            "operation": "list",
            "outcome": "success",
            "namespace": self.namespace,
            "experiment": self.experiment_name,
            "indexes": indexes,
        }

    def _select(self, git_slug: str | None, run_id: str | None) -> dict:
        if bool(git_slug) == bool(run_id):
            raise IndexTransferError("Supply exactly one of INDEX_GIT_SLUG or INDEX_RUN_ID")
        experiment = self._experiment()
        if not experiment:
            raise IndexTransferError(f"Experiment does not exist: {self.experiment_name}")
        if run_id:
            return self._describe(self.client.get_run(run_id), experiment.experiment_id)
        _index_identity({"category": "indexing", "git_slug": git_slug, "multi_repo": "false"})
        for index in self.list_indexes()["indexes"]:
            if index["git_slug"] == git_slug and not index["multi_repo"]:
                return index
        raise IndexTransferError(f"No completed single-repository index for slug {git_slug!r}")

    def _remote_files(self, run_id: str) -> dict[str, int]:
        files = {}
        pending = [""]
        seen = set()
        total = 0
        while pending:
            parent = pending.pop()
            for item in self.client.list_artifacts(run_id, parent):
                path = _safe_path(item.path)
                if path in seen or (parent and not path.startswith(parent + "/")):
                    raise IndexTransferError("Invalid artifact hierarchy")
                seen.add(path)
                if len(seen) > MAX_MEMBERS:
                    raise IndexTransferError("Too many run artifacts")
                if item.is_dir:
                    pending.append(path)
                else:
                    if not isinstance(item.file_size, int) or item.file_size < 0:
                        raise IndexTransferError(
                            "Artifact size unavailable; cannot enforce transfer limit"
                        )
                    total += item.file_size
                    if total > self.max_bytes:
                        raise IndexTransferError("Run artifacts exceed the 5 GiB transfer limit")
                    files[path] = item.file_size
        return files

    def export_index(
        self,
        git_slug: str | None = None,
        run_id: str | None = None,
        bundle: Path | None = None,
    ) -> dict:
        index = self._select(git_slug, run_id)
        source_run_id = index["run_id"]
        files = self._remote_files(source_run_id)
        _require_index(files, index["artifact_path"])
        label = "multi-repo" if index["multi_repo"] else index["git_slug"]
        _safe_path(source_run_id)
        if "/" in source_run_id:
            raise IndexTransferError("Invalid source run ID")
        bundle = Path(bundle or f"artifacts/indexes/{label}-{source_run_id}.tar.gz")
        if bundle.exists():
            raise IndexTransferError(f"Refusing to overwrite {bundle}")
        bundle.parent.mkdir(parents=True, exist_ok=True)
        # Publish on the same filesystem, with an atomic no-overwrite hard link.
        with tempfile.TemporaryDirectory(dir=bundle.parent, prefix=".index-export-") as temporary:
            directory = Path(temporary) / "export"
            with _self_hosted_package() as (export_run, _):
                run = export_run(
                    run_id=source_run_id,
                    output_dir=str(directory),
                    mlflow_client=self.client,
                    raise_exception=True,
                    export_logged_models=False,
                )
            if run is None:
                raise IndexTransferError("MLflow export did not produce a run")
            metadata = _read_metadata(directory)["mlflow"]
            if (
                metadata["info"]["run_id"] != source_run_id
                or metadata["info"]["experiment_id"] != index["experiment_id"]
                or _index_identity(metadata["tags"])
                != (index["git_slug"], index["multi_repo"], index["artifact_path"])
            ):
                raise IndexTransferError("Exported metadata does not match the selected run")
            _local_files(directory, self.max_bytes)
            if _local_files(directory / "artifacts", self.max_bytes) != files:
                raise IndexTransferError(
                    "Exported artifact tree differs from the source inventory"
                )
            archive_path = Path(temporary) / "bundle.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for path in sorted(directory.rglob("*")):
                    archive.add(
                        path, arcname=path.relative_to(directory).as_posix(), recursive=False
                    )
            if archive_path.stat().st_size > self.max_bytes:
                raise IndexTransferError("Compressed bundle exceeds the 5 GiB transfer limit")
            digest = bundle_sha256(archive_path)
            os.link(archive_path, bundle)
        return {
            "operation": "export",
            "outcome": "exported",
            "bundle_path": str(bundle),
            "bundle_sha256": digest,
            "source_run_id": source_run_id,
            "namespace": self.namespace,
            "experiment": self.experiment_name,
            "git_slug": index["git_slug"],
            "multi_repo": index["multi_repo"],
        }

    def import_index(self, bundle: Path, force: bool = False) -> dict:
        bundle = Path(bundle)
        with tempfile.TemporaryDirectory(prefix="index-import-") as temporary:
            directory = Path(temporary)
            _extract_bundle(bundle, directory, self.max_bytes)
            metadata = _read_metadata(directory)
            source = metadata["mlflow"]
            slug, combined, path = _index_identity(source["tags"])
            files = _local_files(directory / "artifacts", self.max_bytes)
            _require_index(files, path)
            digest = bundle_sha256(bundle)
            result = {
                "operation": "import",
                "bundle_path": str(bundle),
                "bundle_sha256": digest,
                "source_run_id": source["info"]["run_id"],
                "destination_namespace": self.namespace,
                "destination_experiment": self.experiment_name,
                "git_slug": slug,
                "multi_repo": combined,
            }
            experiment = self._experiment()
            if experiment and not force:
                for run in self._search(
                    experiment.experiment_id, f" AND tags.bundle_sha256 = '{digest}'"
                ):
                    try:
                        index = self._describe(run, experiment.experiment_id)
                    except IndexTransferError:
                        continue
                    if (
                        index["git_slug"] == slug
                        and index["multi_repo"] == combined
                        and run.data.tags.get("uploaded") == "true"
                        and run.data.tags.get("index_transfer.destination_namespace")
                        == self.namespace
                    ):
                        _require_index(self._remote_files(run.info.run_id), path)
                        return {
                            **result,
                            "outcome": "existing",
                            "destination_run_id": run.info.run_id,
                        }
            original_tags = source["tags"]
            tags = {
                key: value
                for key, value in original_tags.items()
                if not key.startswith("index_transfer.")
                and key not in {"uploaded", "bundle_sha256"}
            }
            parent = tags.pop("mlflow.parentRunId", None)
            provenance = {
                "uploaded": "true",
                "bundle_sha256": digest,
                "index_transfer.source_run_id": source["info"]["run_id"],
                "index_transfer.source_experiment_id": source["info"]["experiment_id"],
                "index_transfer.destination_namespace": self.namespace,
            }
            for key in ("start_time", "end_time"):
                if source["info"].get(key) is not None:
                    provenance[f"index_transfer.source_{key}"] = str(source["info"][key])
            if parent:
                provenance["index_transfer.source_parent_run_id"] = parent
            source["tags"] = {**tags, **provenance}
            (directory / "run.json").write_text(json.dumps(metadata))
            with _self_hosted_package() as (_, import_run):
                destination, _ = import_run(
                    input_dir=str(directory),
                    experiment_name=self.experiment_name,
                    mlflow_client=self.client,
                    import_source_tags=True,
                    mlmodel_fix=False,
                    import_logged_models=False,
                )
            destination_id = destination.info.run_id
            try:
                experiment = self._experiment()
                if not experiment or destination_id == source["info"]["run_id"]:
                    raise IndexTransferError("Import did not produce a new destination run")
                destination = self.client.get_run(destination_id)
                index = self._describe(destination, experiment.experiment_id)
                if (index["git_slug"], index["multi_repo"]) != (slug, combined) or any(
                    destination.data.tags.get(key) != value for key, value in provenance.items()
                ):
                    raise IndexTransferError("Imported tags do not match the bundle")
                if "mlflow.parentRunId" in destination.data.tags:
                    raise IndexTransferError("Imported run retains a source parent reference")
                if self._remote_files(destination_id) != files:
                    raise IndexTransferError("Imported artifact tree differs from the bundle")
            except Exception:
                self.client.set_terminated(destination_id, "FAILED")
                raise
            return {**result, "outcome": "imported", "destination_run_id": destination_id}
