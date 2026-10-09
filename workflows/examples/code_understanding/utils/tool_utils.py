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
        """Patch the write_file tool in tools to coerce non-string text to a JSON string."""
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
        return tools

    def get_tools(self):
        tools = self._toolkit.get_tools()
        return self._patch_tools(tools)


def get_log_enrichments_tool(enrichments_dir: str, git_slug: str | None = None):
    """Return a LangChain tool that logs the enrichments directory to the pipeline asset store.

    The returned tool is a no-argument callable suitable for injection into a skill agent or
    direct invocation. It mirrors the log_results call made by load_external_metadata so that
    skill outputs written under .enrichments/ persist across pipeline runs.

    Args:
        enrichments_dir: Absolute path to the .enrichments directory to log.
        git_slug:        Optional repository slug used to namespace the artifact path and tags.
    """
    from langchain_core.tools import tool

    @tool
    def log_enrichments(note: str = "") -> str:
        """Persist the enrichments directory to the pipeline asset store.

        Call this after all output files have been written so they survive across pipeline runs.
        The note parameter is optional and ignored.
        """
        import os

        from loaders.default_asset_loader import DefaultAssetLoader

        os.makedirs(enrichments_dir, exist_ok=True)

        kwargs = {}
        if git_slug:
            kwargs["artifact_path"] = DefaultAssetLoader.get_log_results_artifact_path(
                DefaultAssetLoader.RESULTS_PATH_PREFIX_ENRICHMENTS,
                git_slug=git_slug,
            )
            kwargs["tags"] = {"git_slug": git_slug, "category": "data-generation"}
        DefaultAssetLoader().log_results(enrichments_dir, **kwargs)
        return f"Logged enrichments from {enrichments_dir}"

    return log_enrichments


def get_read_asset_tool():
    """Return a LangChain tool that reads a file from the pipeline's asset directory."""
    from langchain_core.tools import tool

    @tool
    def read_asset(path: str) -> str:
        """Read a file from the pipeline asset directory by its path relative to assets/."""
        from loaders.default_asset_loader import DefaultAssetLoader

        content = DefaultAssetLoader().download(path)
        if content is None:
            raise RuntimeError(f"Required asset not found: {path}")
        if isinstance(content, (dict, list)):
            return json.dumps(content, indent=2)
        return content

    return read_asset
