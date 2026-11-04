"""Ensure cleanup stays within its requested experiment scope."""

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from workflows.examples.code_understanding.scripts.cleanup_mlflow import (
    cleanup,
    experiment_names,
    main,
)


def test_exact_names_include_default_telemetry_and_exclude_other_namespaces():
    assert experiment_names("demo") == [
        "demo/code-refactoring/assets/static",
        "demo/code-refactoring/assets/result-directories",
        "demo/code-refactoring/assets/results",
        "demo/code-refactoring/evaluations",
        "AIP-default",
    ]
    assert experiment_names("demo", "custom-telemetry")[-1] == "custom-telemetry"


@pytest.mark.parametrize("namespace", ["", " ", "demo/other", "UPPER", "-demo", "x" * 64])
def test_invalid_namespace_rejected(namespace):
    with pytest.raises(ValueError, match="KFP_NAMESPACE"):
        experiment_names(namespace)


def test_cleanup_skips_missing_and_renames_before_deleting():
    client = Mock()
    client.get_experiment_by_name.side_effect = [
        None,
        SimpleNamespace(
            lifecycle_stage="active", experiment_id="12", artifact_location="s3://a/b"
        ),
    ]
    assert cleanup(client, ["missing", "active"]) == ["12"]
    assert client.method_calls == [
        call.get_experiment_by_name("missing"),
        call.get_experiment_by_name("active"),
        call.rename_experiment("12", "active-deleted-12"),
        call.delete_experiment("12"),
    ]


def test_preview_does_not_mutate():
    client = Mock()
    client.get_experiment_by_name.return_value = SimpleNamespace(
        lifecycle_stage="active", experiment_id="12", artifact_location="s3://a/b"
    )
    assert cleanup(client, experiment_names("demo"), dry_run=True) == ["12"] * 5
    client.delete_experiment.assert_not_called()
    client.rename_experiment.assert_not_called()


def test_failed_plan_does_not_start_deleting():
    client = Mock()
    client.get_experiment_by_name.side_effect = [
        SimpleNamespace(
            lifecycle_stage="active", experiment_id="12", artifact_location="s3://a/b"
        ),
        RuntimeError("permission denied"),
    ]
    with pytest.raises(RuntimeError, match="permission denied"):
        cleanup(client, experiment_names("demo"))
    client.delete_experiment.assert_not_called()


def test_delete_failure_is_reported():
    client = Mock()
    client.get_experiment_by_name.return_value = SimpleNamespace(
        lifecycle_stage="active", experiment_id="12", artifact_location="s3://a/b"
    )
    client.delete_experiment.side_effect = RuntimeError("permission denied")
    with pytest.raises(RuntimeError, match="permission denied"):
        cleanup(client, ["active"])
    assert client.rename_experiment.call_args_list == [
        call("12", "active-deleted-12"),
        call("12", "active"),
    ]


def test_rename_failure_does_not_delete():
    client = Mock()
    client.get_experiment_by_name.return_value = SimpleNamespace(
        lifecycle_stage="active", experiment_id="12", artifact_location="s3://a/b"
    )
    client.rename_experiment.side_effect = RuntimeError("rename denied")
    with pytest.raises(RuntimeError, match="rename denied"):
        cleanup(client, ["active"])
    client.delete_experiment.assert_not_called()


def test_old_deleted_name_blocks_plan_before_any_mutation():
    client = Mock()
    client.get_experiment_by_name.side_effect = [
        SimpleNamespace(lifecycle_stage="active", experiment_id="12"),
        SimpleNamespace(lifecycle_stage="deleted", experiment_id="13"),
    ]
    with pytest.raises(ValueError, match="garbage collection"):
        cleanup(client, ["active", "old-deleted"])
    client.rename_experiment.assert_not_called()
    client.delete_experiment.assert_not_called()


def test_main_refuses_missing_namespace_before_connecting(monkeypatch, capsys):
    monkeypatch.delenv("KFP_NAMESPACE", raising=False)
    assert main([]) == 1
    assert "KFP_NAMESPACE" in capsys.readouterr().err
