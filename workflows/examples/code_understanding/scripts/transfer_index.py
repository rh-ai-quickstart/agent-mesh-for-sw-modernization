#!/usr/bin/env python3
"""Local Make/CLI entry point for index listing, export, and import."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Run directly from a checkout without installing the workflow's dependencies.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code_understanding.utils.index_transfer import (  # noqa: E402
    IndexTransfer,
)


def print_indexes(result: dict) -> None:
    """Display repository identities and complete run IDs for copying."""
    indexes = result["indexes"]
    if not indexes:
        print(f"No completed indexes found in {result['namespace']}.")
        return
    headers = ("Repository / Index", "Type", "Uploaded", "Latest", "Started (UTC)", "Run ID")
    rows = []
    for index in indexes:
        started = index["start_time"]
        rows.append(
            (
                "Combined index" if index["multi_repo"] else index["git_slug"],
                "Combined" if index["multi_repo"] else "Single",
                "yes" if index["uploaded"] else "-",
                "yes" if index["latest"] else "-",
                (
                    datetime.fromtimestamp(started / 1000, timezone.utc).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if started is not None
                    else "-"
                ),
                index["run_id"],
            )
        )
    widths = [max(len(row[column]) for row in (headers, *rows)) for column in range(len(headers))]

    def line(row):
        return "  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip()

    print(f"Indexes in {result['namespace']} ({len(indexes)})\n")
    print(line(headers))
    print(line(tuple("-" * width for width in widths)))
    for row in rows:
        print(line(row))


def print_export(result: dict) -> None:
    print(f"Index:     {'Combined index' if result['multi_repo'] else result['git_slug']}")
    print(f"Type:      {'Combined' if result['multi_repo'] else 'Single repository'}")
    print(f"Run ID:    {result['source_run_id']}")
    print(f"Namespace: {result['namespace']}")
    print(f"\nIndex saved to \"{result['bundle_path']}\"")


@contextmanager
def quiet_export_logs(enabled: bool):
    """Hide routine package logs without affecting progress bars or errors."""
    previous = logging.root.manager.disable
    if enabled:
        logging.disable(max(previous, logging.INFO))
    try:
        yield
    finally:
        if enabled:
            logging.disable(previous)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    for operation in ("list", "export", "import"):
        command = commands.add_parser(operation)
        if operation == "export":
            selectors = command.add_mutually_exclusive_group()
            selectors.add_argument("--git-slug", default=os.getenv("INDEX_GIT_SLUG") or None)
            selectors.add_argument("--run-id", default=os.getenv("INDEX_RUN_ID") or None)
        if operation in {"export", "import"}:
            command.add_argument("--bundle", type=Path, default=os.getenv("INDEX_BUNDLE") or None)
        if operation == "import":
            command.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    args.namespace = os.getenv("KFP_NAMESPACE", "")
    if not args.namespace or not args.namespace.strip():
        parser.error("KFP_NAMESPACE is required")
    if args.operation == "export" and bool(args.git_slug) == bool(args.run_id):
        parser.error("Supply exactly one of INDEX_GIT_SLUG or INDEX_RUN_ID")
    if args.operation == "import":
        if not args.bundle:
            parser.error("INDEX_BUNDLE or --bundle is required for import")
        force = os.getenv("INDEX_FORCE", "false").lower()
        if force not in {"true", "false"}:
            parser.error("INDEX_FORCE must be true or false")
        args.force = args.force or force == "true"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    try:
        # The pinned package installs stdout logging handlers when imported.
        # Redirect during imports and transfer so stdout contains only the result.
        with redirect_stdout(sys.stderr), quiet_export_logs(args.operation == "export"):
            from urllib3.exceptions import InsecureRequestWarning

            warnings.filterwarnings("ignore", category=InsecureRequestWarning)
            uri = os.getenv("LOCAL_MLFLOW_TRACKING_URI") or os.getenv("MLFLOW_TRACKING_URI", "")
            parsed = urlparse(uri)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("MLFLOW_TRACKING_URI must be a self-hosted HTTP(S) endpoint")
            os.environ["MLFLOW_WORKSPACE"] = args.namespace
            os.environ["MLFLOW_NAMESPACE"] = args.namespace
            os.environ["MLFLOW_TRACKING_URI"] = uri
            os.environ.setdefault("MLFLOW_TRACKING_AUTH", "kubernetes-namespaced")
            import mlflow
            from mlflow.tracking import MlflowClient

            mlflow.set_tracking_uri(uri)
            transfer = IndexTransfer(MlflowClient(tracking_uri=uri), args.namespace)
            if args.operation == "list":
                result = transfer.list_indexes()
            elif args.operation == "export":
                result = transfer.export_index(args.git_slug, args.run_id, args.bundle)
            else:
                result = transfer.import_index(args.bundle, args.force)
    except Exception as exc:
        logging.error("Index %s failed: %s", args.operation, exc)
        if args.operation == "import":
            print(json.dumps({"operation": args.operation, "outcome": "error", "error": str(exc)}))
        return 1
    if args.operation == "list":
        print_indexes(result)
    elif args.operation == "export":
        print_export(result)
    else:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
