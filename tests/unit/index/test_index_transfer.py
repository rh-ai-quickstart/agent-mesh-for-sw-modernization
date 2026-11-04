"""Native transfer validation and real MLflow REST/workspace round trips."""

from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import tarfile
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from code_understanding.scripts import transfer_index as cli
from code_understanding.utils import index_transfer as transfer

REPO_ROOT = Path(__file__).resolve().parents[3]
PREBUILT_BUNDLE = (
    REPO_ROOT
    / "workflows/examples/code_understanding/assets/prebuilt-indexes"
    / "agapebondservant-tic-tac-toe-sample-main-index.tar.gz"
)


def test_prebuilt_bundle_has_portable_metadata_and_anonymous_tar_headers(tmp_path):
    transfer._extract_bundle(PREBUILT_BUNDLE, tmp_path, transfer.MAX_BYTES)
    metadata = transfer._read_metadata(tmp_path)
    assert set(metadata["system"]) == {
        "export_file_version",
        "package_version",
        "mlflow_version",
    }
    info = metadata["mlflow"]["info"]
    assert set(info) == {
        "run_id",
        "experiment_id",
        "user_id",
        "status",
        "lifecycle_stage",
        "run_name",
    }
    assert info["experiment_id"] == "0"
    assert info["user_id"] == "example"
    assert info["run_name"] == "tic-tac-toe-prebuilt-index"
    assert metadata["mlflow"]["tags"] == {
        "category": "indexing",
        "git_slug": "agapebondservant-tic-tac-toe-sample-main",
        "multi_repo": "False",
        "mlflow.runName": "tic-tac-toe-prebuilt-index",
    }
    assert metadata["mlflow"]["params"] == {
        "embedding_model": "intfloat/e5-mistral-7b-instruct",
        "embedding_dimensions": "4096",
    }
    files = transfer._local_files(tmp_path / "artifacts", transfer.MAX_BYTES)
    _, _, index_path = transfer._index_identity(metadata["mlflow"]["tags"])
    transfer._require_index(files, index_path)
    with tarfile.open(PREBUILT_BUNDLE, "r:gz") as archive:
        for member in archive:
            assert (member.uid, member.gid, member.uname, member.gname, member.mtime) == (
                0,
                0,
                "",
                "",
                0,
            )


@pytest.fixture(autouse=True)
def isolated_mlflow_environment(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("MLFLOW_", "LOCAL_MLFLOW_", "INDEX_")) or key == "KFP_NAMESPACE":
            monkeypatch.delenv(key)


def make_run(run_id="source-id", start_time=1, combined=False, **info_overrides):
    info = {
        "run_id": run_id,
        "experiment_id": "source-exp",
        "status": "FINISHED",
        "lifecycle_stage": "active",
        "start_time": start_time,
        "end_time": start_time + 1,
        **info_overrides,
    }
    return SimpleNamespace(
        info=SimpleNamespace(**info),
        data=SimpleNamespace(
            tags={
                "category": "indexing",
                "git_slug": "owner-repo-main",
                "multi_repo": str(combined),
            }
        ),
    )


def fake_client(runs=None):
    client = MagicMock()
    client.get_experiment_by_name.return_value = SimpleNamespace(
        experiment_id="source-exp", lifecycle_stage="active"
    )
    client.search_runs.return_value = runs or []
    client.get_run.return_value = make_run()
    client.list_artifacts.return_value = []
    return client


def native_metadata():
    return {
        "system": {"export_file_version": "2"},
        "mlflow": {
            "info": {
                "run_id": "source-id",
                "experiment_id": "source-exp",
                "user_id": "source-user",
                "status": "FINISHED",
                "lifecycle_stage": "active",
                "start_time": 1,
                "end_time": 2,
            },
            "tags": make_run().data.tags,
            "params": {"embedding_model": "test-model"},
            "metrics": {"count": [{"value": 2.5, "timestamp": 1, "step": 0}]},
            "inputs": {"dataset_inputs": []},
        },
    }


def write_bundle(path, metadata=None, entries=None):
    with tarfile.open(path, "w:gz") as archive:
        content = json.dumps(native_metadata() if metadata is None else metadata).encode()
        member = tarfile.TarInfo("run.json")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
        for name, body, kind in entries or [
            ("artifacts/results/datasets/repos/owner-repo-main/entities.parquet", b"data", None)
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(body)
            if kind:
                member.type = kind
                member.linkname = "../../outside"
            archive.addfile(member, io.BytesIO(body))
    return path


def package_stub(monkeypatch, exporter=None, importer=None):
    @contextmanager
    def functions():
        yield exporter, importer

    monkeypatch.setattr(transfer, "_self_hosted_package", functions)


def test_latest_selection_order_and_combined_run_id():
    runs = [make_run("older", 1), make_run("z-tie", 10), make_run("a-tie", 10)]
    combined = make_run("combined", 20, combined=True)
    client = fake_client([combined, *runs])
    wrapper = transfer.IndexTransfer(client, "source")
    indexes = wrapper.list_indexes()["indexes"]
    assert [item["run_id"] for item in indexes] == ["combined", "a-tie", "z-tie", "older"]
    assert [item["latest"] for item in indexes] == [True, True, False, False]
    assert wrapper._select("owner-repo-main", None)["run_id"] == "a-tie"
    client.get_run.return_value = combined
    assert wrapper._select(None, "combined")["artifact_path"].endswith("/multi-repo")


def test_listing_paginates_and_does_not_create_missing_experiment():
    class Page(list):
        token = None

    first = Page([make_run("older", 1)])
    first.token = "next-page"
    client = fake_client()
    client.search_runs.side_effect = [first, Page([make_run("latest", 10)])]
    wrapper = transfer.IndexTransfer(client, "source")
    assert wrapper.list_indexes()["indexes"][0]["run_id"] == "latest"
    assert client.search_runs.call_args.kwargs["page_token"] == "next-page"
    client.get_experiment_by_name.return_value = None
    assert wrapper.list_indexes()["indexes"] == []
    client.create_experiment.assert_not_called()


@pytest.mark.parametrize("slug,run_id", [(None, None), ("slug", "id")])
def test_invalid_selector_combinations(slug, run_id):
    with pytest.raises(transfer.IndexTransferError, match="exactly one"):
        transfer.IndexTransfer(fake_client(), "source").export_index(slug, run_id)


@pytest.mark.parametrize(
    "change",
    [
        {"status": "RUNNING"},
        {"experiment_id": "wrong-experiment"},
    ],
)
def test_explicit_run_rejects_ineligible_source(change):
    client = fake_client()
    client.get_run.return_value = make_run(**change)
    with pytest.raises(transfer.IndexTransferError):
        transfer.IndexTransfer(client, "source").export_index(run_id="source-id")


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../outside", None),
        ("/absolute", None),
        ("artifacts/link", tarfile.SYMTYPE),
    ],
)
def test_unsafe_archive_rejected_before_destination_calls(tmp_path, name, kind):
    bundle = write_bundle(tmp_path / "bad.tar.gz", entries=[(name, b"x", kind)])
    client = fake_client()
    with pytest.raises((transfer.IndexTransferError, tarfile.TarError)):
        transfer.IndexTransfer(client, "destination").import_index(bundle)
    client.get_experiment_by_name.assert_not_called()
    client.create_run.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", "3"),
        ("status", "RUNNING"),
        ("git_slug", "../unsafe"),
    ],
)
def test_invalid_native_metadata(tmp_path, field, value):
    metadata = native_metadata()
    if field == "version":
        metadata["system"]["export_file_version"] = value
    elif field == "status":
        metadata["mlflow"]["info"][field] = value
    else:
        metadata["mlflow"]["tags"][field] = value
    bundle = write_bundle(tmp_path / "bad.tar.gz", metadata)
    client = fake_client()
    with pytest.raises(transfer.IndexTransferError):
        transfer.IndexTransfer(client, "destination").import_index(bundle)
    client.create_run.assert_not_called()
    client.get_experiment_by_name.assert_not_called()


def test_archive_limits(tmp_path, monkeypatch):
    bundle = write_bundle(
        tmp_path / "large.tar.gz", entries=[("artifacts/large", b"x" * 4096, None)]
    )
    monkeypatch.setattr(transfer, "MAX_BYTES", 10)
    with pytest.raises(transfer.IndexTransferError, match="Compressed"):
        transfer.IndexTransfer(fake_client(), "destination").import_index(bundle)
    monkeypatch.setattr(transfer, "MAX_BYTES", 2048)
    with pytest.raises(transfer.IndexTransferError, match="Extracted"):
        transfer.IndexTransfer(fake_client(), "destination").import_index(bundle)
    monkeypatch.setattr(transfer, "MAX_BYTES", 5 * 1024**3)
    monkeypatch.setattr(transfer, "MAX_MEMBERS", 1)
    with pytest.raises(transfer.IndexTransferError, match="limits"):
        transfer.IndexTransfer(fake_client(), "destination").import_index(bundle)


def test_missing_artifacts_and_source_export_failure(tmp_path, monkeypatch):
    client = fake_client()
    wrapper = transfer.IndexTransfer(client, "source")
    bundle = tmp_path / "output.tar.gz"
    with pytest.raises(transfer.IndexTransferError, match="Missing or empty"):
        wrapper.export_index(run_id="source-id", bundle=bundle)
    monkeypatch.setattr(
        wrapper, "_remote_files", lambda _: {f"{transfer.INDEX_ROOT}/owner-repo-main/file": 4}
    )
    exporter = MagicMock(return_value=None)
    package_stub(monkeypatch, exporter=exporter)
    with pytest.raises(transfer.IndexTransferError, match="did not produce"):
        wrapper.export_index(run_id="source-id", bundle=bundle)
    assert exporter.call_args.kwargs["raise_exception"] is True
    assert not bundle.exists()
    assert not list(tmp_path.glob(".index-export-*"))
    exporter.side_effect = RuntimeError("download failed")
    with pytest.raises(RuntimeError, match="download failed"):
        wrapper.export_index(run_id="source-id", bundle=bundle)
    assert not bundle.exists()


def test_existing_export_is_not_overwritten(tmp_path, monkeypatch):
    wrapper = transfer.IndexTransfer(fake_client(), "source")
    monkeypatch.setattr(
        wrapper, "_remote_files", lambda _: {f"{transfer.INDEX_ROOT}/owner-repo-main/file": 4}
    )
    bundle = tmp_path / "existing.tar.gz"
    bundle.write_bytes(b"original")
    with pytest.raises(transfer.IndexTransferError, match="overwrite"):
        wrapper.export_index(run_id="source-id", bundle=bundle)
    assert bundle.read_bytes() == b"original"


def test_failed_post_import_validation_marks_run_failed(tmp_path, monkeypatch):
    bundle = write_bundle(tmp_path / "valid.tar.gz")
    client = fake_client()
    destination = make_run("new-id")
    client.get_run.return_value = destination
    package_stub(monkeypatch, importer=MagicMock(return_value=(destination, None)))
    with pytest.raises(transfer.IndexTransferError, match="tags"):
        transfer.IndexTransfer(client, "destination").import_index(bundle)
    client.set_terminated.assert_called_once_with("new-id", "FAILED")


def test_cli_requires_kfp_namespace(monkeypatch):
    monkeypatch.setenv("MLFLOW_WORKSPACE", "unrelated-workspace")
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(["list"])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "operation,env",
    [
        ("export", {}),
        ("export", {"INDEX_GIT_SLUG": "slug", "INDEX_RUN_ID": "id"}),
        ("import", {}),
        ("import", {"INDEX_BUNDLE": "file", "INDEX_FORCE": "maybe"}),
    ],
)
def test_cli_invalid_inputs(operation, env, monkeypatch):
    monkeypatch.setenv("KFP_NAMESPACE", "source")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit) as exc:
        cli.parse_args([operation])
    assert exc.value.code == 2


@pytest.fixture(scope="session")
def mlflow_server(tmp_path_factory):
    import requests
    from mlflow.tracking import MlflowClient

    directory = tmp_path_factory.mktemp("mlflow-server")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    uri = f"http://127.0.0.1:{port}"
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("MLFLOW_")
    }
    with (directory / "server.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mlflow",
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--workers",
                "1",
                "--backend-store-uri",
                f"sqlite:///{directory}/tracking.db",
                "--artifacts-destination",
                str(directory / "artifacts"),
                "--enable-workspaces",
            ],
            stdout=log,
            stderr=log,
            cwd=directory,
            env=environment,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail((directory / "server.log").read_text())
                try:
                    if requests.get(uri + "/health", timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail(
                    "MLflow server did not start: " + (directory / "server.log").read_text()
                )
            with pytest.MonkeyPatch.context() as clean:
                for key in list(os.environ):
                    if key.startswith("MLFLOW_"):
                        clean.delenv(key)
                client = MlflowClient(tracking_uri=uri)
                client.create_workspace("source")
                client.create_workspace("destination")
            yield uri
        finally:
            import signal

            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)


@pytest.mark.parametrize("combined", [False, True])
def test_real_workspace_round_trip(mlflow_server, tmp_path, combined):
    import mlflow
    from mlflow.entities import Metric
    from mlflow.tracking import MlflowClient
    from mlflow.utils.workspace_context import WorkspaceContext

    client = MlflowClient(tracking_uri=mlflow_server)
    mlflow.set_tracking_uri(mlflow_server)
    slug = "" if combined else "owner-repo-main"
    source_tree = tmp_path / "source-tree"
    index_path = f"{transfer.INDEX_ROOT}/{'multi-repo' if combined else slug}"
    file_data = {
        f"{index_path}/entities.parquet": b"entities",
        f"{index_path}/lancedb/table/data/0.lance": b"\x00nested-data\xff",
        "other/run-note.txt": b"retain all artifacts",
    }
    for relative, content in file_data.items():
        target = source_tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    with WorkspaceContext("source"):
        experiment_name = "source" + transfer.EXPERIMENT_SUFFIX
        experiment = client.get_experiment_by_name(experiment_name)
        experiment_id = (
            experiment.experiment_id if experiment else client.create_experiment(experiment_name)
        )
        source = client.create_run(
            experiment_id,
            start_time=1000,
            tags={
                "category": "indexing",
                "git_slug": slug,
                "multi_repo": str(combined),
                "mlflow.parentRunId": "source-parent",
                "custom": "preserved",
            },
        )
        source_id = source.info.run_id
        client.log_param(source_id, "embedding_model", "test-model")
        client.log_batch(
            source_id, metrics=[Metric("count", 1.5, 1100, 0), Metric("count", 2.5, 1200, 1)]
        )
        client.log_artifacts(source_id, str(source_tree))
        client.set_terminated(source_id, "FINISHED", end_time=2000)
        wrapper = transfer.IndexTransfer(client, "source")
        bundle = tmp_path / "index.tar.gz"
        exported = wrapper.export_index(
            run_id=source_id if combined else None,
            git_slug=None if combined else slug,
            bundle=bundle,
        )
        assert exported["source_run_id"] == source_id
    with WorkspaceContext("destination"):
        experiment_name = "destination" + transfer.EXPERIMENT_SUFFIX
        importer = transfer.IndexTransfer(client, "destination")
        imported = importer.import_index(bundle)
        new_id = imported["destination_run_id"]
        assert new_id != source_id
        run = client.get_run(new_id)
        assert run.info.status == "FINISHED"
        assert client.get_experiment(run.info.experiment_id).name == experiment_name
        assert run.data.params == {"embedding_model": "test-model"}
        assert run.data.tags["custom"] == "preserved"
        assert run.data.tags["index_transfer.destination_namespace"] == "destination"
        assert run.data.tags["index_transfer.source_parent_run_id"] == "source-parent"
        assert run.data.tags["bundle_sha256"] == exported["bundle_sha256"]
        assert "mlflow.parentRunId" not in run.data.tags
        assert [
            (metric.value, metric.timestamp, metric.step)
            for metric in client.get_metric_history(new_id, "count")
        ] == [(1.5, 1100, 0), (2.5, 1200, 1)]
        for relative, content in file_data.items():
            download = Path(client.download_artifacts(new_id, relative, str(tmp_path)))
            assert download.read_bytes() == content
        assert importer.import_index(bundle)["destination_run_id"] == new_id
        forced = importer.import_index(bundle, force=True)
        assert forced["destination_run_id"] != new_id


def test_prebuilt_bundle_imports_through_job_cli_and_skips_duplicate(mlflow_server, tmp_path):
    import mlflow
    from mlflow.tracking import MlflowClient
    from mlflow.utils.workspace_context import WorkspaceContext

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("MLFLOW_", "LOCAL_MLFLOW_", "INDEX_"))
    } | {
        "KFP_NAMESPACE": "destination",
        "MLFLOW_TRACKING_URI": mlflow_server,
        # The local test server has no Kubernetes authentication gateway.
        "MLFLOW_TRACKING_AUTH": "",
    }

    def run_import():
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "workflows/examples/code_understanding/scripts/transfer_index.py"),
                "import",
                "--bundle",
                str(PREBUILT_BUNDLE),
            ],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout)

    imported = run_import()
    assert imported["outcome"] == "imported"
    mlflow.set_tracking_uri(mlflow_server)
    client = MlflowClient(tracking_uri=mlflow_server)
    with WorkspaceContext("destination"):
        run_id = imported["destination_run_id"]
        run = client.get_run(run_id)
        assert run.info.status == "FINISHED"
        assert client.get_experiment(run.info.experiment_id).name == (
            "destination" + transfer.EXPERIMENT_SUFFIX
        )
        assert run.data.tags["uploaded"] == "true"
        assert run.data.tags["bundle_sha256"] == transfer.bundle_sha256(PREBUILT_BUNDLE)
        assert run.data.params["embedding_model"] == "intfloat/e5-mistral-7b-instruct"
        downloaded = Path(client.download_artifacts(run_id, "", str(tmp_path)))
        with tarfile.open(PREBUILT_BUNDLE, "r:gz") as archive:
            for member in archive:
                if member.isfile() and member.name.startswith("artifacts/"):
                    relative = member.name.removeprefix("artifacts/")
                    assert hashlib.sha256((downloaded / relative).read_bytes()).digest() == (
                        hashlib.sha256(archive.extractfile(member).read()).digest()
                    )
        existing = run_import()
        assert existing["outcome"] == "existing"
        assert existing["destination_run_id"] == run_id
