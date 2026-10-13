import json
from typing import Annotated


class SafeFileManagementToolkit:
    """FileManagementToolkit whose write_file tool coerces non-string text to a JSON string.

    The LLM occasionally passes a dict instead of a string for the ``text`` argument.
    ``_patch_tools`` subclasses the tool's args_schema to add a BeforeValidator
    that normalises the value before Pydantic validates it.
    """

    def __init__(self, **kwargs):
        from langchain_community.agent_toolkits import FileManagementToolkit

        self._toolkit = FileManagementToolkit(**kwargs)

    def _patch_tools(self, tools: list) -> list:
        """Patch the write_file tool to coerce non-string text and support nested directories."""
        from pydantic import BeforeValidator

        for t in tools:
            if t.name == "write_file":

                class _PatchedSchema(t.args_schema):
                    text: Annotated[
                        str,
                        BeforeValidator(
                            lambda v: v if isinstance(v, str) else (json.dumps(v) if v else "")
                        ),
                    ]

                t.args_schema = _PatchedSchema

                import os

                root_dir = getattr(t, "root_dir", None) or ""
                original_run = t._run

                def _run_with_parents(*args, _original=original_run, _root=root_dir, **kwargs):
                    file_path = args[0] if args else kwargs.get("file_path", "")
                    parent = os.path.dirname(os.path.join(_root, file_path))
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    return _original(*args, **kwargs)

                t._run = _run_with_parents

        return tools

    def get_tools(self):
        tools = self._toolkit.get_tools()
        return self._patch_tools(tools)


def get_log_enrichments_tool(repo_dir: str, git_slug: str | None = None):
    """Return a LangChain tool that logs the enrichments directory to the pipeline asset store.

    The returned tool is a no-argument callable suitable for injection into a skill agent or
    direct invocation. It mirrors the log_results call made by load_external_metadata so that
    skill outputs written under .enrichments/ persist across pipeline runs.

    Args:
        repo_dir:  Root of the cloned repository; .enrichments/ is derived from this path.
        git_slug:  Optional repository slug used to namespace the artifact path and tags.
    """
    from langchain_core.tools import tool

    @tool
    def log_enrichments(note: str = "") -> str:
        """Persist the enrichments directory to the pipeline asset store.

        Call this after all output files have been written so they survive across pipeline runs.
        The note parameter is optional and ignored.
        """
        from loaders.default_asset_loader import DefaultAssetLoader

        return DefaultAssetLoader().log_enrichments(repo_dir, git_slug)

    return log_enrichments


def get_read_asset_tool(repo_dir: str | None = None, git_slug: str | None = None):
    """Return a LangChain tool that reads a file from the pipeline's asset directory.

    When repo_dir and/or git_slug are provided, the tool checks the local enrichments
    folder (tier 1) and the MLflow enrichments experiment (tier 2) before falling back
    to the static asset store (tier 3).

    Args:
        repo_dir:  Root of the cloned repository; used to locate .enrichments/.assets/.
        git_slug:  Optional repository slug for MLflow enrichments namespacing.
    """
    from langchain_core.tools import tool

    @tool
    def read_asset(path: str) -> str:
        """Read a file from the pipeline asset directory by its path relative to assets/."""
        from loaders.default_asset_loader import DefaultAssetLoader

        content = DefaultAssetLoader().download(path, download_dir=repo_dir, git_slug=git_slug)
        if content is None:
            raise RuntimeError(f"Required asset not found: {path}")
        if isinstance(content, (dict, list)):
            return json.dumps(content, indent=2)
        return content

    return read_asset
