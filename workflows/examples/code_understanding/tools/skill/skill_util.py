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
    repo: str
    enabled: bool = True
    target_dir: str | None = None


def fetch_skills(name: str) -> list[SkillConfig]:
    """Load the skills list from a composite skill's frontmatter metadata."""
    from loaders.default_asset_loader import DefaultAssetLoader

    _, frontmatter = DefaultAssetLoader().load_skill(name)
    return [
        SkillConfig(
            name=entry["name"],
            repo=entry["repo"],
            enabled=entry.get("enabled", True),
            target_dir=entry.get("target_dir"),
        )
        for entry in ((frontmatter.get("metadata") or {}).get("skills") or [])
    ]


def load_skill_instructions(name: str, repo: str) -> str:
    """Clone a skills repo and return the SKILL.md body for the named skill."""
    with tempfile.TemporaryDirectory(prefix=f"skill-{name}-") as skills_dir:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo, skills_dir],
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


async def _run_as_agent(
    repo_dir: str,
    instructions: str,
    use_rhoai_mcp: bool = False,
    extra_tools: list | None = None,
) -> None:
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_community.agent_toolkits import FileManagementToolkit
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=os.environ["CODE_LLM_ID"],
        base_url=os.environ["CODE_LLM_API_BASE"],
        api_key=os.environ["CODE_LLM_TOKEN"],
    )
    tools = FileManagementToolkit(
        root_dir=repo_dir,
        selected_tools=["read_file", "write_file", "list_directory"],
    ).get_tools()
    if extra_tools:
        tools = tools + extra_tools
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant."),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    if use_rhoai_mcp:
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            async with MultiServerMCPClient(
                {"rhoai-mcp": {"url": os.environ["RHOAI_MCP_BASE_URL"] + "/sse", "transport": "sse"}}
            ) as client:
                all_tools = tools + client.get_tools()
                agent = create_tool_calling_agent(llm, all_tools, prompt)
                await AgentExecutor(agent=agent, tools=all_tools).ainvoke({"input": instructions})
                return
        except Exception as exc:
            logging.warning("Could not load rhoai-mcp tools: %s", exc)

    agent = create_tool_calling_agent(llm, tools, prompt)
    await AgentExecutor(agent=agent, tools=tools).ainvoke({"input": instructions})


def run_skill(
    skill: SkillConfig,
    repo_dir: str,
    use_rhoai_mcp: bool = False,
) -> str | None:
    """
    Run a single skill against repo_dir.

    Returns the path to the generated report file, or None if no report was written.
    """
    output_filename = f"{skill.name}-report.json"
    instructions = (
        f"{load_skill_instructions(skill.name, skill.repo)}"
        f"\n\nWrite your output report to: {output_filename} at the root of the repository."
    )
    coro = _run_as_agent(repo_dir, instructions, use_rhoai_mcp=use_rhoai_mcp)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, coro).result()
    else:
        asyncio.run(coro)

    for ext in ("json", "txt", "md"):
        candidate = os.path.join(repo_dir, f"{skill.name}-report.{ext}")
        if os.path.exists(candidate):
            dest = os.path.join(repo_dir, skill.target_dir) if skill.target_dir else repo_dir
            shutil.move(candidate, dest)
            candidate = os.path.join(dest, os.path.basename(candidate))
            with open(candidate, "r", encoding="utf-8") as f:
                logging.info(f"[{skill.name}] report content:\n{f.read()}")
            return candidate
    return None


def run_composite_skill(
    repo_dir: str,
    composite_skill: str,
    use_rhoai_mcp: bool = False,
) -> None:
    """
    Run a composite skill against repo_dir using the autonomous agent pattern.

    Loads the composite skill's body as agent instructions, injects the enabled
    skills list, and invokes an agent equipped with the run_skill tool.
    """
    from loaders.default_asset_loader import DefaultAssetLoader
    from tools.skill.skill_tool import get_run_skill_tool

    logging.info("Running composite skill: %s", composite_skill)

    body, _ = DefaultAssetLoader().load_skill(composite_skill)
    enabled_skills = [s for s in fetch_skills(composite_skill) if s.enabled]
    skills_desc = "\n".join(
        f"- name={s.name}, repo={s.repo}, target_dir={s.target_dir}"
        for s in enabled_skills
    )
    instructions = f"{body}\n\nEnabled skills:\n{skills_desc or 'None'}"
    logging.info("Composite skill instructions:\n%s", instructions)

    skill_tool = get_run_skill_tool(repo_dir, use_rhoai_mcp)
    coro = _run_as_agent(
        repo_dir,
        instructions,
        use_rhoai_mcp=use_rhoai_mcp,
        extra_tools=[skill_tool],
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
