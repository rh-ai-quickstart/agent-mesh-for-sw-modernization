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
