"""Submit Code Understanding pipeline and adhoc-query Jobs on OpenShift."""

from __future__ import annotations

import logging
import os
import subprocess

# from collections.abc import Iterator  # only used by wait_for_job (commented out)
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
import traceback  # noqa: E402

from kubernetes import client, config  # noqa: E402

ADHOC_MARKER = "ADHOC RESULTS"


def available_namespaces() -> list[str]:
    """Return namespaces the current identity has access to.

    Tries the OpenShift Projects API first — it returns only the projects the
    caller can access without requiring any elevated permissions. Falls back to
    a standard Kubernetes namespace listing (requires cluster-wide list
    permission), then to the current namespace only.
    """
    try:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        # OpenShift: returns only projects the caller has access to
        try:
            result = client.CustomObjectsApi().list_cluster_custom_object(
                group="project.openshift.io",
                version="v1",
                plural="projects",
            )
            names = sorted(
                item["metadata"]["name"]
                for item in result.get("items", [])
                if item.get("metadata", {}).get("name")
            )
            if names:
                logging.info(
                    f"Available namespaces from OpenShift Projects " f"API: {', '.join(names)}"
                )
                return names
        except Exception as e:
            logging.debug(traceback.format_exc(), exc_info=e)
            pass

        # Vanilla Kubernetes fallback (requires cluster-wide list permission)
        items = client.CoreV1Api().list_namespace().items
        names = sorted(ns.metadata.name for ns in items if ns.metadata.name)
        logging.info(f"Available namespaces from Kubernetes API: {names}")
        return names

    except Exception as e:
        logging.debug(traceback.format_exc(), exc_info=e)
        ns = current_namespace()
        logging.info(f"Available namespaces: Fallback to current namespace:" f" {ns}")
        return [ns] if ns else []


def current_namespace(ns: str | None = None) -> str:
    if ns:
        return ns.strip()
    env_ns = os.getenv("KFP_NAMESPACE", "").strip()
    if env_ns:
        return env_ns
    sa_ns = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    if sa_ns.is_file():
        return sa_ns.read_text(encoding="utf-8").strip()
    return ""


def workflow_repo_url() -> str:
    url = os.getenv("AGENTMESH_REPO_URL", "").strip()
    if url:
        return url
    try:
        raw = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if raw.startswith("git@"):
            host, path = raw.split(":", 1)
            return f"https://{host[4:]}/{path}"
        return raw
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def workflow_repo_ref() -> str:
    job_ref = os.getenv("AGENTMESH_JOB_REPO_REF", "").strip()
    if job_ref:
        return job_ref
    ref = os.getenv("AGENTMESH_REPO_REF", "").strip()
    if ref:
        return ref
    try:
        return (
            subprocess.check_output(
                ["git", "branch", "--show-current"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            or "main"
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "main"


def analysis_image() -> str:
    registry = os.getenv("KFP_IMAGE_REGISTRY", "quay.io/ai-shadowman").strip()
    name = os.getenv("KFP_ANALYSIS_BASE_IMAGE_NAME", "data-indexing").strip()
    tag = os.getenv("KFP_ANALYSIS_BASE_IMAGE_TAG", "latest").strip()
    return f"{registry}/{name}:{tag}"


def k8s_clients(
    ns: str | None = None,
) -> tuple[client.BatchV1Api, client.CoreV1Api, str]:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    resolved = current_namespace(ns)
    if not resolved:
        raise RuntimeError("KFP_NAMESPACE is not set and no in-cluster namespace was found.")
    return client.BatchV1Api(), client.CoreV1Api(), resolved


def cluster_status(ns: str | None = None) -> dict[str, Any]:
    try:
        _, core, resolved = k8s_clients(ns)
        core.read_namespace(resolved)
        return {
            "ok": True,
            "namespace": resolved,
            "repo_url": workflow_repo_url(),
            "repo_ref": workflow_repo_ref(),
            "message": f"Connected to namespace {resolved}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "namespace": current_namespace(ns),
            "repo_url": workflow_repo_url(),
            "repo_ref": workflow_repo_ref(),
            "message": str(exc),
        }


def _as_text(logs: str | bytes | None) -> str:
    if logs is None:
        return ""
    if isinstance(logs, bytes):
        return logs.decode("utf-8", errors="replace")
    return str(logs)


def _decode_hex_escapes_as_utf8(text: str) -> str:
    """Decode literal \\xNN sequences (Python log repr) as UTF-8, not as code points."""
    import re

    pattern = re.compile(r"(?:\\x[0-9a-fA-F]{2})+")

    def repl(match: re.Match[str]) -> str:
        try:
            raw = bytes(
                int(byte_hex, 16) for byte_hex in re.findall(r"[0-9a-fA-F]{2}", match.group(0))
            )
            return raw.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return match.group(0)

    return pattern.sub(repl, text)


def _fix_residual_mojibake_artifacts(text: str) -> str:
    import re

    text = re.sub(r"\u00e2\s*\u0304", " ", text)
    text = re.sub(r"\u00e2(?=s\b)", "'", text)
    text = re.sub(r"\u00e2(?=\d)", "'", text)
    text = re.sub(r"\u00e2(?=[A-Za-z])", "-", text)
    return text.replace("\u00e2", "")


def fix_mojibake(text: str) -> str:
    """Repair UTF-8 text that was mis-decoded as Latin-1 or Windows-1252."""
    if any(0x80 <= ord(ch) <= 0xFF for ch in text) or "\u00e2" in text or "â" in text:
        for encoding in ("latin-1", "cp1252"):
            try:
                candidate = text.encode(encoding).decode("utf-8")
                if candidate != text:
                    text = candidate
                    break
            except (UnicodeDecodeError, UnicodeEncodeError):
                continue

    for _ in range(2):
        if not any(marker in text for marker in ("â€", "Ã", "Â", "â€™", "â€œ", "ï»")):
            break
        try:
            text = text.encode("cp1252").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            break

    replacements = {
        "â€¯": " ",
        "â€'": "-",
        "â€\u201c": "-",
        "â€\u201d": "-",
        "â€™": "'",
        "â€œ": '"',
        "â€\x9d": '"',
        "â€˜": "'",
        "Ã©": "e",
        "Ã§": "c",
        "Ã¨": "e",
        "Ã¢": "a",
        "Ã´": "o",
        "Ã¼": "u",
        "Â ": " ",
        "Â": "",
        "ï»¿": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return _fix_residual_mojibake_artifacts(text)


def _sanitize_unicode(text: str) -> str:
    import re
    import unicodedata

    text = fix_mojibake(text)
    text = unicodedata.normalize("NFKC", text)
    cleaned: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Mn":
            continue
        if cat.startswith("Z"):
            cleaned.append(" ")
        elif cat == "Cf" or (cat == "Cc" and ch not in "\n\t"):
            continue
        elif ord(ch) > 0xFFFF:
            continue
        else:
            cleaned.append(ch)
    text = "".join(cleaned)
    text = _normalize_unicode_punctuation(text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text


def _normalize_unicode_punctuation(text: str) -> str:
    for ch in ("\u202f", "\u00a0", "\u2009", "\u200a"):
        text = text.replace(ch, " ")
    for ch in ("\u2011", "\u2010", "\u2013", "\u2014"):
        text = text.replace(ch, "-")
    for ch in ("\u2018", "\u2019"):
        text = text.replace(ch, "'")
    for ch in ("\u201c", "\u201d"):
        text = text.replace(ch, '"')
    return text


def _improve_markdown(text: str) -> str:
    import re

    # Remove invisible chars that break **bold** parsing.
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    text = re.sub(r"\*\*([^*\n]+?)\*\*", lambda m: f"**{m.group(1).strip()}**", text)
    text = re.sub(r"(?<!\n)(\*\*\d+\.)", r"\n\n\1", text)
    text = re.sub(r"  \n", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def format_chat_answer(text: str) -> str:
    """Normalize adhoc query text for readable markdown in the console."""
    import ast
    import re

    text = (text or "").strip()
    if not text:
        return text

    if len(text) > 2 and text[0] == text[-1] and text[0] in "\"'":
        try:
            text = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            pass

    if "\\x" in text:
        text = _decode_hex_escapes_as_utf8(text)
    if "\\n" in text:
        text = text.replace("\\n", "\n").replace("\\t", "\t")

    text = _sanitize_unicode(text)

    text = re.sub(r"#+\s*ADHOC RESULTS\s*#+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^#+\s*$", "", text, flags=re.MULTILINE)

    text = _improve_markdown(text)
    text = _fence_tree_blocks(text)
    return text.strip()


def _fence_tree_blocks(text: str) -> str:
    """Wrap ASCII directory trees in fenced code blocks for markdown rendering."""
    import re

    lines = text.splitlines()
    out: list[str] = []
    block: list[str] = []

    def flush() -> None:
        nonlocal block
        if not block:
            return
        out.append("```text")
        out.extend(block)
        out.append("```")
        block = []

    tree_line = re.compile(r"[│├└─]")
    for line in lines:
        if tree_line.search(line):
            block.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def format_job_logs(logs: str | bytes | None) -> str:
    """Clean Kubernetes job logs for display in the console."""
    import re

    text = _as_text(logs).strip()
    if not text:
        return ""

    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"\r[^\n]*", "", text)
    if "\\n" in text and text.count("\n") < text.count("\\n"):
        text = text.replace("\\n", "\n").replace("\\t", "\t")
    if "\\x" in text:
        text = _decode_hex_escapes_as_utf8(text)

    skip_markers = (
        "[notice]",
        "FutureWarning:",
        "warnings.warn(",
        "site-packages/kfp",
        "site-packages/urllib3",
        "InsecureRequestWarning",
    )
    cleaned: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in skip_markers):
            continue
        cleaned.append(line.rstrip())

    return "\n".join(cleaned[-120:])


def extract_pipeline_summary(logs: str | bytes | None) -> dict[str, Any]:
    """Pull human-readable highlights from a pipeline submit job."""
    summary: dict[str, Any] = {"submitted": [], "run_url": "", "experiment_url": ""}
    for line in format_job_logs(logs).splitlines():
        if "OK:" in line and "submitted" in line:
            summary["submitted"].append(line.strip().removeprefix("OK:").strip())
        elif line.startswith("Triggering "):
            summary["submitted"].append(line.strip())
        elif "Run details:" in line:
            summary["run_url"] = line.split("Run details:", 1)[-1].strip()
        elif "Experiment details:" in line:
            summary["experiment_url"] = line.split("Experiment details:", 1)[-1].strip()
        elif line.strip() == "All done.":
            summary["done"] = True
    return summary


def extract_adhoc_answer(logs: str | bytes | None) -> str:
    logs = _as_text(logs)
    import re

    logs = re.sub(r"\x1b\[[0-9;]*m", "", logs)
    logs = re.sub(r"\r[^\n]*", "", logs)

    idx = logs.find(ADHOC_MARKER)
    if idx != -1:
        body = logs[idx + len(ADHOC_MARKER) :]
        lines = [
            line
            for line in body.splitlines()
            if ADHOC_MARKER not in line and set(line.strip()) not in ({"#"}, {"-"})
        ]
        answer = "\n".join(lines).strip()
        if answer:
            return format_chat_answer(answer)

    for line in reversed(logs.splitlines()):
        stripped = line.strip()
        if stripped.startswith("Could not perform query:"):
            return stripped
        if stripped.startswith("TypeError:") or stripped.startswith("ValueError:"):
            return f"Query failed: {stripped}"
        if stripped.startswith("Error:") and "notice" not in stripped.lower():
            return stripped

    return (
        "The query job finished but no answer was found in the logs. "
        "Try again in a moment, or check the job logs in the sidebar."
    )
