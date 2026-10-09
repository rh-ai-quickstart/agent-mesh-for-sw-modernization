import logging
import os

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())


def get_run_skill_tool(repo_dir: str, use_rhoai_mcp: bool = False):
    """Return a LangChain tool that runs a single skill against the repository.

    Args:
        repo_dir:       Absolute path to the cloned repository.
        use_rhoai_mcp:  Whether to include rhoai-mcp tools in the skill agent.

    Returns:
        A LangChain tool named ``run_skill``.
    """
    from langchain_core.tools import tool

    @tool
    def run_skill(skill_name: str, repo: str, target_dir: str | None = None) -> str:
        """Fetch a skill by name from a remote skills repository URL and run it.

        Args:
            skill_name: Name of the skill to run.
            repo:       URL of the remote Git repository that hosts the skill (e.g.
                        https://github.com/org/skills-repo). Must be a remote URL, not a
                        local path.
            target_dir: Optional subdirectory within the repository to write the report to.
        Skips execution if a report already exists in target_dir.
        """
        from tools.skill.skill_util import SkillConfig
        from tools.skill.skill_util import run_skill as _run_skill

        dest = os.path.join(repo_dir, target_dir) if target_dir else repo_dir
        os.makedirs(dest, exist_ok=True)

        existing = next(
            (
                os.path.join(dest, f"{skill_name}-report.{ext}")
                for ext in ("json", "txt", "md")
                if os.path.exists(os.path.join(dest, f"{skill_name}-report.{ext}"))
            ),
            None,
        )
        if existing:
            msg = f"[{skill_name}] skipped - report already exists at {existing}"
            logging.info(msg)
            return msg

        try:
            skill = SkillConfig(name=skill_name, repo=repo, target_dir=target_dir)
            skill_output_path = _run_skill(skill, repo_dir, use_rhoai_mcp=use_rhoai_mcp)
            msg = f"[{skill_name}] completed. report={skill_output_path or '(none)'}"
            logging.info(msg)
            return msg
        except Exception as exc:
            raise RuntimeError(f"Skill '{skill_name}' failed: {exc}") from exc

    return run_skill
