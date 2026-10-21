"""Report downloads must skip ad hoc query artifacts."""

from types import SimpleNamespace

from services import fetch_reports as reports


def _run(run_id: str, kfp_run_id: str, adhoc_query: bool = False):
    tags = {"kfp_run_id": kfp_run_id}
    if adhoc_query:
        tags["adhoc_query"] = "true"
    return SimpleNamespace(info=SimpleNamespace(run_id=run_id), data=SimpleNamespace(tags=tags))


def test_fetch_reports_skips_query_run_and_downloads_report_file(monkeypatch, tmp_path):
    report = tmp_path / "migration_report_repo-main.md"
    report.write_text("# Current analysis", encoding="utf-8")
    selected = []

    class Client:
        def get_experiment_by_name(self, name):
            return SimpleNamespace(experiment_id="51")

        def search_runs(self, **kwargs):
            assert "tags.\"kfp_run_id\" = 'selected-kfp'" in kwargs["filter_string"]
            if "evaluation" in kwargs["filter_string"]:
                return []
            return [
                _run("query", "selected-kfp", adhoc_query=True),
                _run("report", "selected-kfp"),
            ]

        def list_artifacts(self, run_id, path):
            selected.append(run_id)
            assert run_id == "report"
            if path.startswith("results/pipelines/"):
                return [SimpleNamespace(path=f"{path}/{report.name}", is_dir=False)]
            return []

    def download_artifacts(**kwargs):
        selected.append(kwargs["run_id"])
        assert kwargs["artifact_path"].endswith(report.name)
        return str(report)

    monkeypatch.setattr(reports, "MlflowClient", Client)
    monkeypatch.setattr(reports.mlflow.artifacts, "download_artifacts", download_artifacts)

    evaluation, analysis = reports.fetch_reports("repo-main", False, "selected-kfp")

    assert evaluation is None
    assert analysis == "# Current analysis"
    assert selected == ["report", "report"]


def test_fetch_reports_does_not_fall_back_to_another_kfp_run(monkeypatch):
    class Client:
        def get_experiment_by_name(self, name):
            return SimpleNamespace(experiment_id="51")

        def search_runs(self, **kwargs):
            assert "tags.\"kfp_run_id\" = 'selected-kfp'" in kwargs["filter_string"]
            return []

        def list_artifacts(self, run_id, path):
            raise AssertionError("Another run's artifacts must not be read")

    monkeypatch.setattr(reports, "MlflowClient", Client)
    assert reports.fetch_reports("repo-main", False, "selected-kfp") == (None, None)


def test_fetch_reports_returns_no_reports_when_mlflow_is_unavailable(monkeypatch):
    class Client:
        def get_experiment_by_name(self, name):
            raise ConnectionError("MLflow is unavailable")

    monkeypatch.setattr(reports, "MlflowClient", Client)
    assert reports.fetch_reports("repo-main", False, "selected-kfp") == (None, None)
