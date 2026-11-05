"""Discover accessible namespaces and report console cluster connectivity."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
import traceback  # noqa: E402

from kubernetes import client, config  # noqa: E402


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


def k8s_clients(ns: str | None = None) -> tuple[client.BatchV1Api, client.CoreV1Api, str]:
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
