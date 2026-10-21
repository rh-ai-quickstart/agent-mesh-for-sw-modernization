"""MLflow result artifacts retain their originating pipeline run."""

from types import SimpleNamespace


def test_log_results_tags_kfp_run(monkeypatch, tmp_path):
    from contextlib import nullcontext

    from loaders import mlflow_asset_loader

    result_file = tmp_path / "report.md"
    result_file.write_text("report", encoding="utf-8")
    observed = {}

    monkeypatch.setenv("KFP_RUN_ID", "selected-kfp")
    monkeypatch.setattr(mlflow_asset_loader, "MlflowClient", lambda: object())
    monkeypatch.setattr(
        mlflow_asset_loader.MlFlowAssetLoader,
        "get_or_create_experiment_by_name",
        lambda self, client, name: SimpleNamespace(experiment_id="51"),
    )
    monkeypatch.setattr(
        mlflow_asset_loader.mlflow,
        "start_run",
        lambda **kwargs: nullcontext(SimpleNamespace(info=SimpleNamespace(run_id="mlflow-run"))),
    )
    monkeypatch.setattr(mlflow_asset_loader.mlflow, "set_tags", lambda tags: observed.update(tags))
    monkeypatch.setattr(mlflow_asset_loader.mlflow, "log_artifact", lambda *args, **kwargs: None)

    mlflow_asset_loader.MlFlowAssetLoader().log_results(
        str(result_file), tags={"category": "analysis"}
    )

    assert observed == {"category": "analysis", "kfp_run_id": "selected-kfp"}
