#!/usr/bin/env python3
"""Upload a committed GraphRAG index bundle to MLflow when it is not present."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import posixpath
import re
import tarfile
import tempfile
from typing import Any

from mlflow.tracking import MlflowClient

from code_understanding.loaders.mlflow_asset_loader import MlFlowAssetLoader


LOG = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a prebuilt GraphRAG index bundle to MLflow."
    )
    parser.add_argument(
        "--bundle",
        required=True,
        type=Path,
        help="Path to a gzip-compressed tar archive containing manifest.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Upload even when an identical bundle was already installed.",
    )
    return parser.parse_args()


def bundle_sha256(bundle_path: Path) -> str:
    """Return the SHA-256 of the archive as it is stored in source control."""
    digest = hashlib.sha256()
    with bundle_path.open("rb") as bundle:
        for chunk in iter(lambda: bundle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _member_path(member_name: str) -> str:
    """Normalize an archive member path, rejecting unsafe extraction targets."""
    if (
        not member_name
        or "\\" in member_name
        or member_name.startswith("/")
        or re.match(r"^[A-Za-z]:", member_name)
    ):
        raise ValueError("Bundle contains an unsafe member path")

    normalized = posixpath.normpath(member_name).removesuffix("/")
    parts = normalized.split("/")
    if normalized in {"", ".", ".."} or normalized.startswith("../") or any(
        part in {"", ".", ".."} for part in parts
    ):
        raise ValueError("Bundle contains an unsafe member path")
    return normalized


def _validated_members(archive: tarfile.TarFile) -> list[tuple[str, tarfile.TarInfo]]:
    """Return safe regular-file and directory members with unique paths."""
    members = []
    seen = set()
    for member in archive.getmembers():
        path = _member_path(member.name)
        if path in seen:
            raise ValueError("Bundle contains duplicate member paths")
        if not (member.isfile() or member.isdir()):
            raise ValueError("Bundle may contain only regular files and directories")
        seen.add(path)
        members.append((path, member))
    return members


def read_manifest(bundle_path: Path) -> dict[str, Any]:
    """Read the metadata that determines where the index is stored in MLflow."""
    try:
        with tarfile.open(bundle_path, mode="r:gz") as archive:
            members = dict(_validated_members(archive))
            manifest_member = members.get("manifest.json")
            if manifest_member is None or not manifest_member.isfile():
                raise ValueError("Bundle is missing manifest.json")
            manifest_file = archive.extractfile(manifest_member)
            if manifest_file is None:
                raise ValueError("Bundle manifest cannot be read")
            with manifest_file:
                manifest = json.load(manifest_file)
    except (OSError, tarfile.TarError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read index bundle manifest: {exc}") from exc

    git_slug = manifest.get("git_slug")
    multi_repo = manifest.get("multi_repo")
    if not isinstance(git_slug, str) or not git_slug.strip():
        raise ValueError("Bundle manifest git_slug must be a non-empty string")
    if not isinstance(multi_repo, bool):
        raise ValueError("Bundle manifest multi_repo must be a boolean")
    return {"git_slug": git_slug, "multi_repo": multi_repo}


def is_bundle_installed(
    client: Any, experiment_id: str, digest: str, git_slug: str, multi_repo: bool
) -> bool:
    """Return whether a completed indexing run already has this bundle hash."""
    runs = client.search_runs(
        experiment_ids=[experiment_id],
        filter_string=(
            f'tags."bundle_sha256" = \'{digest}\' AND '
            'tags."category" = \'indexing\''
        ),
        order_by=["attributes.start_time DESC"],
        max_results=100,
    )
    return any(
        run.info.status == "FINISHED"
        and run.data.tags.get("git_slug") == git_slug
        and str(run.data.tags.get("multi_repo")).lower() == str(multi_repo).lower()
        and str(run.data.tags.get("uploaded")).lower() == "true"
        for run in runs
    )


def extract_bundle(bundle_path: Path, destination: Path) -> None:
    """Safely extract bundle contents, excluding the upload manifest."""
    with tarfile.open(bundle_path, mode="r:gz") as archive:
        members = [
            member for path, member in _validated_members(archive) if path != "manifest.json"
        ]
        archive.extractall(destination, members=members)


def upload_bundle(bundle_path: Path, force: bool = False) -> bool:
    """Upload one bundle, returning True when a new MLflow run was created."""
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Prebuilt index bundle not found: {bundle_path}")

    manifest = read_manifest(bundle_path)
    digest = bundle_sha256(bundle_path)
    loader = MlFlowAssetLoader()
    client = MlflowClient()
    experiment = loader.get_or_create_experiment_by_name(
        client, loader.RESULT_DIRECTORY_ASSET_EXPERIMENT
    )

    if not force and is_bundle_installed(
        client,
        experiment.experiment_id,
        digest,
        manifest["git_slug"],
        manifest["multi_repo"],
    ):
        LOG.info("Prebuilt index bundle is already installed (sha256=%s); skipping.", digest)
        return False

    with tempfile.TemporaryDirectory(prefix="code-understanding-prebuilt-index-") as temp_dir:
        extracted_index_dir = Path(temp_dir) / "index"
        extracted_index_dir.mkdir()
        extract_bundle(bundle_path, extracted_index_dir)

        artifact_path = loader.get_log_results_artifact_path(
            loader.RESULTS_PATH_PREFIX_REPO_DATASETS,
            git_slug=manifest["git_slug"],
            multi_repo=manifest["multi_repo"],
        )
        loader.log_results(
            str(extracted_index_dir),
            artifact_path=artifact_path,
            tags={
                "category": "indexing",
                "git_slug": manifest["git_slug"],
                "multi_repo": manifest["multi_repo"],
                "uploaded": True,
                "bundle_sha256": digest,
            },
        )

    LOG.info("Uploaded prebuilt index bundle (sha256=%s).", digest)
    return True


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s: %(message)s")
    args = parse_args()
    upload_bundle(args.bundle, force=args.force)


if __name__ == "__main__":
    main()
