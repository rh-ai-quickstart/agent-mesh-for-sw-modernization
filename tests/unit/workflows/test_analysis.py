import sys
from types import ModuleType

from pipelines.base import analysis, data_generation


def install_analysis_stubs(monkeypatch, *, missing_index=False):
    logged_results = []
    analyzer_instances = []

    loader_module = ModuleType("loaders.default_asset_loader")

    class FakeLoader:
        RESULTS_PATH_PREFIX_PIPELINES = "results/pipelines"

        @staticmethod
        def get_log_results_artifact_path(prefix, git_slug=None, multi_repo=False):
            suffix = "multi-repo" if multi_repo else git_slug
            return f"{prefix}/{suffix}"

        def log_results(self, *args, **kwargs):
            logged_results.append((args, kwargs))

    loader_module.DefaultAssetLoader = FakeLoader
    monkeypatch.setitem(sys.modules, "loaders.default_asset_loader", loader_module)

    graphrag_module = ModuleType("utils.graphrag_utils")

    class FakeAnalyzer:
        def __init__(self, source_path, git_slug="", multi_repo=False):
            analyzer_instances.append((source_path, git_slug, multi_repo))

        @staticmethod
        def download_graphrag_directory(**kwargs):
            if missing_index:
                raise FileNotFoundError("index not found")

        async def generate_migration_report(self):
            return "migration report"

    graphrag_module.DependencyAnalyzer = FakeAnalyzer
    monkeypatch.setitem(sys.modules, "utils.graphrag_utils", graphrag_module)
    return logged_results, analyzer_instances


def test_analysis_generates_and_logs_report(monkeypatch):
    logged_results, analyzer_instances = install_analysis_stubs(monkeypatch)
    monkeypatch.setattr(
        data_generation,
        "generate_git_slug",
        lambda repo, branch: "example-repo-main",
    )

    report = analysis.AnalysisPipeline().run(
        graphrag_source_path="graph/source",
        git_repo="https://github.com/example/repo",
        git_branch="main",
    )

    assert report == "migration report"
    assert analyzer_instances == [("graph/source", "example-repo-main", False)]
    assert logged_results[0][0] == ("migration_report_example-repo-main.md",)
    assert logged_results[0][1]["content"] == "migration report"
    assert logged_results[0][1]["tags"] == {
        "git_slug": "example-repo-main",
        "multi_repo": False,
        "category": "analysis",
    }


def test_adhoc_query_reports_missing_multi_repo_index(monkeypatch):
    logged_results, analyzer_instances = install_analysis_stubs(
        monkeypatch,
        missing_index=True,
    )

    result = analysis.AnalysisPipeline().run_adhoc_query(question="What changed?")

    assert "no multi-repository index was found" in result
    assert analyzer_instances == []
    assert logged_results == []
