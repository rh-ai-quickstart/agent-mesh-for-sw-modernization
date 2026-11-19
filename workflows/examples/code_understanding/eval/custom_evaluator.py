import functools
import logging
import os
import pathlib
from abc import ABC, abstractmethod

from utils.eval_utils import (
    get_exclude_patterns,
    load_graphrag_eval_config,
    read_selected_files,
    select_relevant_files_from_tree,
)

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())

_DEFAULT_EVAL_DATASET = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "assets",
        "datasets",
        "eval",
        "code_understanding.csv",
    )
)


@functools.lru_cache(maxsize=None)
def _ingest_codebase(graphrag_source_dir: str, max_file_size: int = 50000) -> tuple[str, str]:
    """Ingest the codebase once and cache the result.

    Returns:
        (tree, content) where tree is the directory structure and content is all
        file contents concatenated.  Returns ("", "") on failure.
    """
    codebase_dir = pathlib.Path(graphrag_source_dir) / "input"

    if not codebase_dir.is_dir():
        logging.warning(
            "Codebase directory %s not found; ground truth LLM will have no source context.",
            codebase_dir,
        )
        return ("", "")

    try:
        from gitingest import ingest

        _, tree, content = ingest(
            str(codebase_dir),
            max_file_size=max_file_size,
            exclude_patterns=get_exclude_patterns(),
        )
        return (tree or "", content or "")
    except Exception as e:
        logging.warning("Failed to ingest codebase from %s: %s", codebase_dir, e)
        return ("", "")


def build_repo_context(graphrag_source_dir: str = "", question: str = "") -> str:
    """Returns codebase source as LLM-ready context.

    Context limits are derived from the GraphRAG ``settings.yaml`` in
    *graphrag_source_dir* so that the ground-truth LLM receives a comparable
    retrieval budget to the GraphRAG candidate.  When *question* is provided
    and the codebase exceeds the derived ``max_context_chars``, a cheap LLM
    call selects the most relevant files.

    Result of the underlying gitingest call is cached so repeated calls for
    the same directory do not re-ingest.
    """
    if not graphrag_source_dir:
        logging.warning(
            "No graphrag_source_dir provided; ground truth LLM will have no source context."
        )
        return ""

    cfg = load_graphrag_eval_config(graphrag_source_dir)
    max_file_size = cfg["max_file_size"]
    max_context_chars = cfg["max_context_chars"]
    max_selected_files = cfg["max_selected_files"]

    tree, content = _ingest_codebase(graphrag_source_dir, max_file_size)
    if not content:
        return ""

    # Small codebase — return everything
    if len(content) <= max_context_chars:
        return f"Source code of the codebase being analyzed:\n\n{content}"

    # Large codebase without a question — truncate (backwards-compatible)
    if not question:
        logging.warning(
            "Codebase context truncated from %d to %d chars.",
            len(content),
            max_context_chars,
        )
        return f"Source code of the codebase being analyzed:\n\n{content[:max_context_chars]}"

    # Large codebase with a question — select relevant files
    if not tree:
        logging.warning("No directory tree available; falling back to truncation.")
        return f"Source code of the codebase being analyzed:\n\n{content[:max_context_chars]}"

    try:
        paths = select_relevant_files_from_tree(tree, question, max_selected_files)
        focused = read_selected_files(graphrag_source_dir, paths, max_context_chars)
        if focused:
            return f"Source code of the codebase being analyzed:\n\n{focused}"
        logging.warning("File selection returned no readable files; falling back to truncation.")
    except Exception as e:
        logging.warning("File selection failed (%s); falling back to truncation.", e)

    return f"Source code of the codebase being analyzed:\n\n{content[:max_context_chars]}"


class CustomEvaluator(ABC):

    @abstractmethod
    def evaluate(
        self,
        input: str,
        graphrag_source_dir: str,
        git_repo: str,
        git_branch: str,
        git_slug: str = None,
        multi_repo: bool = False,
    ):
        """Evaluates a single input against a GraphRAG index using LLM-as-judge.

        Args:
            input: The question or prompt to evaluate.
            graphrag_source_dir: Root directory of the GraphRAG index.
            git_repo: Repository URL used as context for the ground truth LLM.
            git_branch: Branch name used as context for the ground truth LLM.
            git_slug: Optional repository slug used to scope results.
            multi_repo: Whether the index spans multiple repositories.

        Returns:
            dict of metric scores and metadata for the evaluated input.
        """

    @abstractmethod
    def evaluate_with_dataset(
        self,
        graphrag_source_dir: str,
        git_repo: str,
        git_branch: str,
        eval_dataset_file: str = _DEFAULT_EVAL_DATASET,
        git_slug: str = None,
        multi_repo: bool = False,
    ):
        """Runs evaluate() for every row in a CSV dataset and uploads the results.

        Args:
            graphrag_source_dir: Root directory of the GraphRAG index
                (must contain output/*.parquet files).
            git_repo: Repository URL used as context for the ground truth LLM.
            git_branch: Branch name used as context for the ground truth LLM.
            eval_dataset_file: Path to the evaluation CSV. Defaults to
                assets/datasets/eval/code_understanding.csv.
            git_slug: Optional repository slug used to scope results and artifact paths.
            multi_repo: Whether the index spans multiple repositories.

        Returns:
            A dict with keys:
            - "results": the updated pandas DataFrame with "answer" and metric columns populated.
            - "improvement_plan": an LLM-generated markdown string with recommendations.
        """
