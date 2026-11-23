import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))

from utils.otel_utils import enable_telemetry  # noqa: E402

##############################################################################
# Enhanced adhoc-query helpers
##############################################################################


def _is_unhelpful_response(text: str) -> bool:
    """Return True if the GraphRAG response indicates it could not answer."""
    if not text or not text.strip():
        return True
    from graphrag.prompts.query.global_search_reduce_system_prompt import (
        NO_DATA_ANSWER,
    )

    return NO_DATA_ANSWER.lower() in text.strip().lower()


def _get_enhanced_prompt(base_prompt: str, context_data) -> str:
    """Build an LLM prompt that includes any GraphRAG context found so far."""
    import os

    from utils.graphrag_utils import DependencyAnalyzer

    context_text = DependencyAnalyzer.extract_context_content(context_data)
    if not context_text:
        return base_prompt
    max_context = int(os.environ.get("ENHANCED_MAX_CONTEXT_CHARS", 80000))
    return (
        "Use the following context where relevant, supplementing"
        " with your own knowledge:\n\n" + context_text[:max_context] + "\n\n" + base_prompt
    )


##############################################################################
# Pipeline stage
##############################################################################


class AnalysisPipeline:

    @enable_telemetry
    def run(
        self,
        graphrag_source_path: str,
        git_repo: str = "",
        git_branch: str = "",
        multi_repo: bool = False,
        pipeline_run_id: str = "",
    ):
        """Generates a migration report from the GraphRAG index and returns the result."""
        import asyncio
        import logging
        import os

        from loaders.default_asset_loader import DefaultAssetLoader
        from pipelines.base.data_generation import generate_git_slug
        from utils.graphrag_utils import DependencyAnalyzer

        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())

        git_slug = generate_git_slug(git_repo, git_branch) if git_repo else None

        analyzer = DependencyAnalyzer(
            graphrag_source_path,
            git_slug=git_slug or "",
            multi_repo=multi_repo,
            pipeline_run_id=pipeline_run_id,
        )

        report = asyncio.run(analyzer.generate_migration_report())

        result_file = f"migration_report_{git_slug}.md" if git_slug else "migration_report.md"

        DefaultAssetLoader().log_results(
            result_file,
            artifact_path=DefaultAssetLoader.get_log_results_artifact_path(
                DefaultAssetLoader.RESULTS_PATH_PREFIX_PIPELINES,
                git_slug=git_slug,
                multi_repo=multi_repo,
            ),
            content=report,
            tags={
                "git_slug": git_slug,
                "multi_repo": multi_repo,
                "category": "analysis",
            },
        )

        return report

    def run_multi_repo(self):
        """Runs migration report generation across the combined multi-repo GraphRAG index."""
        import logging
        import os

        from utils.graphrag_utils import DependencyAnalyzer

        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())

        graphrag_source_path = os.getenv("KFP_DATA_INDEXING_OUTPUT_PATH", "graph_rag_app/source")

        logging.info("Downloading multi-repo GraphRAG index...")
        DependencyAnalyzer.download_graphrag_directory(
            download_dir=graphrag_source_path,
            git_slug="",
            multi_repo=True,
        )

        self.run(graphrag_source_path=graphrag_source_path, multi_repo=True)

    @enable_telemetry
    def run_adhoc_query(
        self,
        question: str,
        retry_count: int = 3,
        use_global: bool = True,
        git_repo: str = "",
        git_branch: str = "main",
        multi_repo: bool = False,
        pipeline_run_id: str = "",
        namespace: str | None = None,
        enhanced: bool = False,
    ):
        """Queries the GraphRAG index with an LLM and returns the result."""
        import asyncio
        import logging
        import os
        from datetime import datetime

        from loaders.default_asset_loader import DefaultAssetLoader
        from pipelines.base.data_generation import generate_git_slug
        from utils.graphrag_utils import DependencyAnalyzer

        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())

        use_multi_repo = multi_repo or not git_repo

        git_slug = generate_git_slug(git_repo, git_branch) if git_repo else ""

        graphrag_source_path = "graph_rag_app/source"

        adhoc_results_header = "\n---\n\n# ##################ADHOC RESULTS##################\n"

        try:
            DependencyAnalyzer.download_graphrag_directory(
                download_dir=graphrag_source_path,
                git_slug=git_slug,
                multi_repo=use_multi_repo,
                git_repo=git_repo,
                namespace=namespace,
                pipeline_run_id=pipeline_run_id,
            )
        except Exception:
            msg = (
                "Could not perform query: "
                + (
                    "no multi-repository index was found"
                    if use_multi_repo
                    else f"no index was found (git_repo='{git_repo}')"
                )
                + ". Maybe you need to generate it first?"
            )
            logging.error(msg)
            print(adhoc_results_header, flush=True)
            return msg

        analyzer = DependencyAnalyzer(
            graphrag_source_path, git_slug=git_slug, multi_repo=use_multi_repo
        )

        postamble = "Provide as much detail as possible. Include the git repo url(s) in the report."  # noqa: E501

        if use_multi_repo:
            postamble += (
                " Include ALL the git repo urls that you can find."
                " Group git repositories by their git repo url."
            )

        full_query = question + postamble
        result, context_data = asyncio.run(
            analyzer.query_with_llm(
                full_query,
                retry_count=retry_count,
                use_global=use_global,
                include_context=True,
                response_type="Multiple Paragraphs, plain text, no markdown formatting",
            )
        )

        if enhanced and _is_unhelpful_response(result):
            logging.info(
                "GraphRAG returned unhelpful response; retrying with LLM knowledge (enhanced mode)"
            )
            result = asyncio.run(
                analyzer.query_with_llm(
                    _get_enhanced_prompt(full_query, context_data),
                    retry_count=retry_count,
                    bypass_index=True,
                    response_type="Multiple Paragraphs, plain text, no markdown formatting",
                )
            )

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        result_file = f"adhoc_query_{timestamp}.txt"

        DefaultAssetLoader(namespace=namespace).log_results(
            result_file,
            artifact_path=(
                DefaultAssetLoader.get_log_results_artifact_path(
                    DefaultAssetLoader.RESULTS_PATH_PREFIX_ADHOC_QUERIES,
                    git_slug=git_slug,
                    multi_repo=use_multi_repo,
                )
            ),
            content=f"Question: {question}\n\nAnswer:\n{result}",
            tags={
                "category": "adhoc-query",
                "git_slug": git_slug,
                "multi_repo": use_multi_repo,
                **({"pipeline_run_id": pipeline_run_id} if pipeline_run_id else {}),
            },
        )

        print(adhoc_results_header, flush=True)
        return f"{result}\n\n"


##############################################################################
# Helpers
##############################################################################


def write_migration_report(
    graphrag_source_path: str,
    report_path: str,
    git_repo: str = "",
    git_branch: str = "",
    multi_repo: bool = False,
    pipeline_run_id: str = "",
):
    """Run the migration report and write the result to report_path."""
    import os

    if pipeline_run_id:
        from utils.loader_utils import download_graphrag_output_directory

        download_graphrag_output_directory(
            graphrag_source_path,
            pipeline_run_id,
            git_repo=git_repo,
            git_branch=git_branch,
            multi_repo=multi_repo,
        )

    migration_report = AnalysisPipeline().run(
        graphrag_source_path,
        git_repo=git_repo,
        git_branch=git_branch,
        multi_repo=multi_repo,
        pipeline_run_id=pipeline_run_id,
    )
    if dirname := os.path.dirname(report_path):
        os.makedirs(dirname, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(migration_report)


##############################################################################
# Module-level aliases for external callers (notebooks, scripts)
##############################################################################


def run_full_pipeline(*args, **kwargs):
    return AnalysisPipeline().run(*args, **kwargs)


def run_full_pipeline_multi_repo(*args, **kwargs):
    return AnalysisPipeline().run_multi_repo(*args, **kwargs)


def run_adhoc_query_pipeline(*args, **kwargs):
    return AnalysisPipeline().run_adhoc_query(*args, **kwargs)
