import asyncio
import concurrent.futures
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())


@dataclass
class SkillConfig:
    name: str
    repo: str | None = None
    enabled: bool = True
    target_dir: str | None = None
    repo_branch: str | None = None
    skill_params: dict | None = None


async def _run_as_agent(
    repo_dir: str,
    instructions: str,
    use_rhoai_mcp: bool = False,
    extra_tools: list | None = None,
) -> None:
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_litellm import ChatLiteLLM
    from utils.tool_utils import SafeFileManagementToolkit

    llm = ChatLiteLLM(
        model=f"{os.environ['CODE_LLM_PROVIDER']}/{os.environ['CODE_LLM_ID']}",
        api_base=os.environ["CODE_LLM_API_BASE"],
        api_key=os.environ["CODE_LLM_TOKEN"],
    )
    tools = SafeFileManagementToolkit(
        root_dir=repo_dir,
        selected_tools=["read_file", "write_file", "list_directory"],
    ).get_tools()
    if extra_tools:
        tools = tools + extra_tools
    from loaders.default_asset_loader import DefaultAssetLoader

    system_prompt, _ = DefaultAssetLoader().download_prompt("skills/skills-system-prompt")
    if not system_prompt:
        raise RuntimeError(
            "skills-system-prompt could not be loaded; aborting to prevent prompt injection"
        )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )

    if use_rhoai_mcp:
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            async with MultiServerMCPClient(
                {
                    "rhoai-mcp": {
                        "url": os.environ["RHOAI_MCP_BASE_URL"] + "/sse",
                        "transport": "sse",
                    }
                }
            ) as client:
                all_tools = tools + client.get_tools()
                agent = create_tool_calling_agent(llm, all_tools, prompt)
                await AgentExecutor(
                    agent=agent, tools=all_tools, verbose=True, max_iterations=50
                ).ainvoke({"input": instructions})
                return
        except Exception as exc:
            logging.warning(
                "RHOAI MCP requested but unavailable — skill ran WITHOUT MCP tools: %s",
                exc,
            )

    agent = create_tool_calling_agent(llm, tools, prompt)
    await AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=50).ainvoke(
        {"input": instructions}
    )


def fetch_skills(name: str) -> list[SkillConfig]:
    """Load the skills list from a composite skill's frontmatter metadata."""
    from loaders.default_asset_loader import DefaultAssetLoader

    _, frontmatter = DefaultAssetLoader().load_skill(name)
    return [
        SkillConfig(
            name=entry["name"],
            repo=entry.get("repo"),
            enabled=entry.get("enabled", True),
            target_dir=entry.get("target_dir"),
            repo_branch=entry.get("repo_branch"),
        )
        for entry in ((frontmatter.get("metadata") or {}).get("skills") or [])
    ]


def load_external_skill_instructions(name: str, repo: str, repo_branch: str | None = None) -> str:
    """Clone a skills repo and return the SKILL.md body for the named skill."""
    with tempfile.TemporaryDirectory(prefix=f"skill-{name}-") as skills_dir:
        clone_cmd = ["git", "clone", "--depth", "1"]
        if repo_branch:
            clone_cmd += ["--branch", repo_branch]
        clone_cmd += [repo, skills_dir]
        subprocess.run(
            clone_cmd,
            check=True,
            capture_output=True,
        )
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.exists(skill_md):
            raise FileNotFoundError(f"{name}/SKILL.md not found in {repo}")
        with open(skill_md) as f:
            content = f.read()

    match = re.match(r"^---\n.*?\n---\n(.*)", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def load_skill_instructions(
    name: str,
    repo: str | None = None,
    repo_branch: str | None = None,
    **kwargs,
) -> str:
    """Return the body of the named skill.

    When repo is None the skill is loaded from the asset loader.
    When repo is provided the skill repo is cloned and SKILL.md is read.

    Any extra keyword arguments are rendered as Jinja2 template variables
    in the skill body (e.g. ``{{ goal }}``).
    """
    if repo is None:
        from loaders.default_asset_loader import DefaultAssetLoader

        body, _ = DefaultAssetLoader().load_skill(name)
    else:
        body = load_external_skill_instructions(name, repo, repo_branch)

    if kwargs:
        from jinja2 import Template

        body = Template(body).render(**kwargs)

    return body


def run_local_skill(
    skill_name: str,
    repo_dir: str,
    git_slug: str,
    use_rhoai_mcp: bool = False,
    skill_params: dict | None = None,
    enrichment_dest: str | None = None,
    persist_enrichments: bool = False,
) -> str | None:
    """
    Run a local skill by name against repo_dir.

    Constructs a SkillConfig from skill_name (loading instructions from the asset loader)
    and delegates to run_skill.
    Returns the path to the generated report file, or None if no report was written.
    """
    return run_skill(
        SkillConfig(name=skill_name, skill_params=skill_params),
        repo_dir,
        git_slug,
        use_rhoai_mcp,
        enrichment_dest=enrichment_dest,
        persist_enrichments=persist_enrichments,
    )


def run_skill(
    skill: SkillConfig,
    repo_dir: str,
    git_slug: str,
    use_rhoai_mcp: bool = False,
    enrichment_dest: str | None = None,
    persist_enrichments: bool = False,
) -> str | None:
    """Run a single skill against repo_dir.

    Args:
        skill:                Skill configuration.
        repo_dir:             Root of the cloned repository.
        git_slug:             Repository slug for artifact namespacing.
        use_rhoai_mcp:        Whether to use the RHOAI MCP server.
        enrichment_dest:      If set, the report file produced by the skill is
                              moved to this path (parent dirs created automatically).
                              A warning is logged when the skill produces no report
                              or the report is empty.
        persist_enrichments:  If True, ``register_enrichments`` is called after
                              the skill completes (idempotent).

    Returns:
        Path to the report file, or None if no report was produced.
    """
    logging.info("Running skill: %s", skill.name)

    instructions = load_skill_instructions(
        skill.name, skill.repo, skill.repo_branch, **(skill.skill_params or {})
    )
    from utils.tool_utils import (
        get_download_base_prompts_tool,
        get_read_asset_tool,
        get_register_enrichments_tool,
    )

    extra_tools = (
        [
            get_read_asset_tool(repo_dir, git_slug),
            get_register_enrichments_tool(repo_dir, git_slug),
            get_download_base_prompts_tool(repo_dir),
        ]
        if skill.repo is None
        else None
    )
    coro = _run_as_agent(
        repo_dir, instructions, use_rhoai_mcp=use_rhoai_mcp, extra_tools=extra_tools
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, coro).result()
    else:
        asyncio.run(coro)

    report_path = _collect_report(skill, repo_dir, enrichment_dest)

    if persist_enrichments:
        from loaders.default_asset_loader import DefaultAssetLoader

        DefaultAssetLoader().register_enrichments(repo_dir, git_slug)

    return report_path


def _collect_report(skill: SkillConfig, repo_dir: str, enrichment_dest: str | None) -> str | None:
    """Locate the skill's report file, optionally move it, and return its path."""
    for ext in ("json", "txt", "md"):
        candidate = os.path.join(repo_dir, f"{skill.name}-report.{ext}")
        if not os.path.exists(candidate):
            continue

        if enrichment_dest:
            os.makedirs(os.path.dirname(enrichment_dest), exist_ok=True)
            shutil.move(candidate, enrichment_dest)
            report_path = enrichment_dest
        elif skill.target_dir:
            dest_dir = os.path.join(repo_dir, skill.target_dir)
            shutil.move(candidate, dest_dir)
            report_path = os.path.join(dest_dir, os.path.basename(candidate))
        else:
            report_path = candidate

        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            logging.warning("[%s] report file is empty: %s", skill.name, report_path)
        else:
            logging.info("[%s] report content:\n%s", skill.name, content)
        return report_path

    if enrichment_dest:
        logging.warning(
            "[%s] skill did not produce a report file (expected at %s)",
            skill.name,
            enrichment_dest,
        )
    return None


def run_composite_skill(
    repo_dir: str,
    composite_skill: str,
    git_slug: str,
    use_rhoai_mcp: bool = False,
    skill_params: dict | None = None,
    persist_enrichments: bool = False,
) -> None:
    """Run a composite skill against repo_dir using the autonomous agent pattern.

    Loads the composite skill's body as agent instructions, injects the enabled
    skills list, and invokes an agent equipped with the run_skill tool.

    Args:
        persist_enrichments:  If True, ``register_enrichments`` is called after
                              the composite skill completes (idempotent).
    """
    from loaders.default_asset_loader import DefaultAssetLoader
    from tools.skill.skill_tool import get_run_skill_tool
    from utils.tool_utils import get_register_enrichments_tool

    logging.info("Running composite skill: %s", composite_skill)

    body, _ = DefaultAssetLoader().load_skill(composite_skill)
    enabled_skills = [s for s in fetch_skills(composite_skill) if s.enabled]
    skills_desc = "\n".join(
        f"- name={s.name}, repo={s.repo}, repo_branch={s.repo_branch}, target_dir={s.target_dir}"
        for s in enabled_skills
    )
    instructions = f"{body}\n\nEnabled skills:\n{skills_desc or 'None'}"
    logging.info("Composite skill instructions:\n%s", instructions)

    skill_tool = get_run_skill_tool(repo_dir, git_slug, use_rhoai_mcp, skill_params)
    register_enrichments_tool = get_register_enrichments_tool(repo_dir, git_slug)
    coro = _run_as_agent(
        repo_dir,
        instructions,
        use_rhoai_mcp=use_rhoai_mcp,
        extra_tools=[skill_tool, register_enrichments_tool],
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, coro).result()
    else:
        asyncio.run(coro)

    if persist_enrichments:
        DefaultAssetLoader().register_enrichments(repo_dir, git_slug)
