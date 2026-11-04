#!/usr/bin/env python3
"""Rename and soft-delete quickstart MLflow experiments so reinstalls start fresh."""

import argparse
import os
import re
import sys
from urllib.parse import urlparse

EXPERIMENT_SUFFIXES = (
    "assets/static",
    "assets/result-directories",
    "assets/results",
    "evaluations",
)


def experiment_names(namespace: str, telemetry_experiment: str = "AIP-default") -> list[str]:
    """Use exact names so unrelated experiments in the workspace are preserved."""
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", namespace):
        raise ValueError("KFP_NAMESPACE must be a valid Kubernetes namespace")
    names = [f"{namespace}/code-refactoring/{suffix}" for suffix in EXPERIMENT_SUFFIXES]
    if not telemetry_experiment.strip():
        raise ValueError("MLFLOW_EXPERIMENT_NAME must not be empty")
    if telemetry_experiment not in names:
        names.append(telemetry_experiment)
    return names


def cleanup(client, names: list[str], dry_run: bool = False) -> list[str]:
    """Resolve the complete plan before mutation and preserve names for fresh installs."""
    experiments = [client.get_experiment_by_name(name) for name in names]
    for name, experiment in zip(names, experiments):
        if experiment is not None and experiment.lifecycle_stage == "deleted":
            raise ValueError(
                f"Experiment {name} ({experiment.experiment_id}) was already deleted without "
                "renaming. Server-side garbage collection is required to free its name."
            )
    deleted_ids = []
    for name, experiment in zip(names, experiments):
        if experiment is None:
            print(f"Skip (absent): {name}")
            continue
        retired_name = f"{name}-deleted-{experiment.experiment_id}"
        print(
            f"{'Would rename and delete' if dry_run else 'Renaming and deleting'}: "
            f"{name} -> {retired_name} ({experiment.experiment_id})"
        )
        print(f"  Artifact location: {experiment.artifact_location}")
        if not dry_run:
            client.rename_experiment(experiment.experiment_id, retired_name)
            try:
                client.delete_experiment(experiment.experiment_id)
            except Exception:
                # Leave the original name discoverable so cleanup can be retried.
                try:
                    client.rename_experiment(experiment.experiment_id, name)
                except Exception as rollback_error:
                    print(
                        f"Could not restore the name of experiment {experiment.experiment_id}: "
                        f"{rollback_error}. It may remain active as {retired_name}.",
                        file=sys.stderr,
                    )
                raise
        deleted_ids.append(experiment.experiment_id)
    return deleted_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Show the plan without deleting data"
    )
    args = parser.parse_args(argv)
    try:
        namespace = os.getenv("KFP_NAMESPACE", "")
        names = experiment_names(
            namespace,
            os.getenv("MLFLOW_EXPERIMENT_NAME", "AIP-default"),
        )
        uri = os.getenv("LOCAL_MLFLOW_TRACKING_URI") or os.getenv("MLFLOW_TRACKING_URI", "")
        parsed = urlparse(uri)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MLFLOW_TRACKING_URI must be an HTTP(S) endpoint")
        # Match local index transfer: use the user's kubeconfig and selected workspace.
        os.environ["MLFLOW_WORKSPACE"] = namespace
        os.environ["MLFLOW_NAMESPACE"] = namespace
        os.environ["MLFLOW_TRACKING_URI"] = uri
        os.environ.setdefault("MLFLOW_TRACKING_AUTH", "kubernetes-namespaced")
        from mlflow.tracking import MlflowClient

        print(f"MLflow workspace: {namespace}; tracking URI: {uri}")
        ids = cleanup(MlflowClient(tracking_uri=uri), names, args.dry_run)
        if not args.dry_run and ids:
            print(f"Marked experiments for deletion: {','.join(ids)}")
            print(
                "Stored artifact files remain until an MLflow administrator runs server-side GC."
            )
        return 0
    except Exception as exc:
        print(f"MLflow cleanup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
