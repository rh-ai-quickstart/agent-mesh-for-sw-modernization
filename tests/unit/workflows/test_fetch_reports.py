"""Report download contracts for HEAD's MlFlowAssetLoader-based fetch_reports."""

import os
import sys
from pathlib import Path
from types import ModuleType

from services import fetch_reports as reports


def _inject_fake_loader(
    monkeypatch,
    *,
    eval_files=None,
    analysis_files=None,
    improvement_files=None,
    raise_on=(),
    fail_init=False,
):
    """Inject fake loaders into sys.modules to intercept fetch_reports' internal imports."""
    raise_on = set(raise_on)

    class FakeAssetLoader:
        RESULTS_PATH_PREFIX_EVAL = "results/eval"
        RESULTS_PATH_PREFIX_PIPELINES = "results/pipelines"
        RESULT_ASSET_EXPERIMENT = "result-assets"

        @staticmethod
        def get_log_results_artifact_path(prefix, git_slug=None, multi_repo=False):
            suffix = "multi_repo" if multi_repo else (git_slug or "unknown")
            return f"{prefix}/{suffix}"

    class FakeLoader(FakeAssetLoader):
        def __init__(self):
            if fail_init:
                raise ConnectionError("MLflow is unavailable")

        def download_dir(self, artifact_path, download_dir, experiment_name, asset_tags):
            category = asset_tags.get("category", "")
            if category in raise_on:
                raise Exception(f"not found: {category}")
            os.makedirs(download_dir, exist_ok=True)
            files_map = {
                "evaluation": eval_files,
                "analysis": analysis_files,
                "improvement": improvement_files,
            }
            files = files_map.get(category)
            for name, content in (files or {}).items():
                (Path(download_dir) / name).write_text(content, encoding="utf-8")

    loader_mod = ModuleType("loaders.mlflow_asset_loader")
    loader_mod.MlFlowAssetLoader = FakeLoader
    monkeypatch.setitem(sys.modules, "loaders.mlflow_asset_loader", loader_mod)

    asset_mod = ModuleType("loaders.asset_loader")
    asset_mod.AssetLoader = FakeAssetLoader
    monkeypatch.setitem(sys.modules, "loaders.asset_loader", asset_mod)


def test_fetch_reports_downloads_analysis_report(monkeypatch):
    _inject_fake_loader(
        monkeypatch,
        analysis_files={"migration_report_repo-main.md": "# Current analysis"},
    )

    evaluation, analysis, improvement = reports.fetch_reports("selected-kfp", "repo-main", False)

    assert evaluation is None
    assert analysis == "# Current analysis"
    assert improvement is None


def test_fetch_reports_returns_none_when_download_fails(monkeypatch):
    _inject_fake_loader(monkeypatch, raise_on=("evaluation", "analysis", "improvement"))

    assert reports.fetch_reports("selected-kfp", "repo-main", False) == (None, None, None)


def test_fetch_reports_returns_no_reports_when_loader_unavailable(monkeypatch):
    _inject_fake_loader(monkeypatch, fail_init=True)

    assert reports.fetch_reports("selected-kfp", "repo-main", False) == (None, None, None)


def test_fetch_reports_downloads_improvement_plan(monkeypatch):
    _inject_fake_loader(
        monkeypatch,
        improvement_files={"improvement_plan_repo-main.md": "# Plan\n\nImprove X."},
    )

    evaluation, analysis, improvement = reports.fetch_reports("kfp-1", "repo-main", False)

    assert evaluation is None
    assert analysis is None
    assert improvement == "# Plan\n\nImprove X."
