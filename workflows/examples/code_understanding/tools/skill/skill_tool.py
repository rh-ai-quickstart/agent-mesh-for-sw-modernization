import logging
import os
import shutil

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
        """Run a skill against the repository. Skips if a report already exists in target_dir."""
        from tools.skill.skill_util import SkillConfig
        from tools.skill.skill_util import run_skill as _run_skill

        if target_dir:
            dest = os.path.join(repo_dir, target_dir)
            existing = next(
                (os.path.join(dest, f"{skill_name}-report.{ext}")
                 for ext in ("json", "txt", "md")
                 if os.path.exists(os.path.join(dest, f"{skill_name}-report.{ext}"))),
                None,
            )
            if existing:
                return f"[{skill_name}] skipped - report already exists at {existing}"

        try:
            skill = SkillConfig(name=skill_name, repo=repo, target_dir=target_dir)
            report_path = _run_skill(skill, repo_dir, use_rhoai_mcp=use_rhoai_mcp)
            if report_path and target_dir:
                dest = os.path.join(repo_dir, target_dir)
                os.makedirs(dest, exist_ok=True)
                shutil.copy2(report_path, dest)
            return f"[{skill_name}] completed. report={report_path or '(none)'}"
        except Exception as exc:
            raise RuntimeError(f"Skill '{skill_name}' failed: {exc}") from exc

    return run_skill
