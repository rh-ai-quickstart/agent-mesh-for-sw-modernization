from pipelines.base import indexing


def test_indexing_runs_generation_and_evaluation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        indexing,
        "generate_graphrag_index",
        lambda **kwargs: calls.append(("generate", kwargs)),
    )
    monkeypatch.setattr(
        indexing,
        "evaluate_graphrag_index",
        lambda **kwargs: calls.append(("evaluate", kwargs)),
    )

    result = indexing.IndexingPipeline().run(
        codebase_path="target/repo",
        graphrag_source_path="graph/source",
        git_repo="https://github.com/example/repo",
        git_branch="main",
    )

    assert result["status"] == "success"
    assert [name for name, _ in calls] == ["generate", "evaluate"]


def test_indexing_returns_failure_when_generation_fails(monkeypatch):
    evaluated = []

    def fail_generation(**kwargs):
        raise RuntimeError("index failed")

    monkeypatch.setattr(indexing, "generate_graphrag_index", fail_generation)
    monkeypatch.setattr(
        indexing,
        "evaluate_graphrag_index",
        lambda **kwargs: evaluated.append(kwargs),
    )

    result = indexing.IndexingPipeline().run(
        codebase_path="target/repo",
        graphrag_source_path="graph/source",
        git_repo="https://github.com/example/repo",
        git_branch="main",
    )

    assert result["status"] == "fail"
    assert "index failed" in result["fail_message"]
    assert evaluated == []


def test_indexing_evaluation_failure_is_nonfatal(monkeypatch):
    monkeypatch.setattr(indexing, "generate_graphrag_index", lambda **kwargs: None)

    def fail_evaluation(**kwargs):
        raise RuntimeError("evaluation failed")

    monkeypatch.setattr(indexing, "evaluate_graphrag_index", fail_evaluation)

    result = indexing.IndexingPipeline().run(
        codebase_path="target/repo",
        graphrag_source_path="graph/source",
        git_repo="https://github.com/example/repo",
        git_branch="main",
    )

    assert result["status"] == "success"


def test_multi_repo_indexing_skips_evaluation(monkeypatch):
    evaluations = []
    monkeypatch.setattr(indexing, "generate_graphrag_index", lambda **kwargs: None)
    monkeypatch.setattr(
        indexing,
        "evaluate_graphrag_index",
        lambda **kwargs: evaluations.append(kwargs),
    )

    result = indexing.IndexingPipeline().run(
        codebase_path="targets",
        graphrag_source_path="graph/source",
        git_repo="",
        git_branch="",
        multi_repo=True,
    )

    assert result["status"] == "success"
    assert evaluations == []
