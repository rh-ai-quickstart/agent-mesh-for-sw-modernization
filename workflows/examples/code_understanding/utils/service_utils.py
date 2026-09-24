"""Shared KFP client utilities used by services and the v2 API."""

from __future__ import annotations

import json
import os
import subprocess
import urllib3
from pathlib import Path
from typing import Any

_SA_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"


def get_namespace() -> str:
    """Return the current Kubernetes namespace."""
    ns = os.getenv("KFP_NAMESPACE", "").strip()
    if ns:
        return ns
    sa_ns = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    if sa_ns.is_file():
        return sa_ns.read_text(encoding="utf-8").strip()
    raise RuntimeError("KFP_NAMESPACE is not set and no in-cluster namespace was found.")


def get_token() -> str:
    """Return a bearer token for KFP authentication."""
    if os.path.isfile(_SA_TOKEN):
        return Path(_SA_TOKEN).read_text(encoding="utf-8").strip()
    return subprocess.check_output(["oc", "whoami", "--show-token"], text=True).strip()


def create_client(host: str | None = None, namespace: str | None = None) -> Any:
    """Create an authenticated KFP client with SSL verification disabled."""
    import kfp
    import kfp_server_api.configuration as _kfp_conf

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    _kfp_conf.Configuration.verify_ssl = property(lambda self: False, lambda self, v: None)

    ns = namespace or get_namespace()
    h = host or os.getenv("KFP_HOST", f"https://ds-pipeline-dspa.{ns}.svc.cluster.local:8443")
    return kfp.Client(host=h, namespace=ns, existing_token=get_token())


def find_pipeline_id(client: Any, pipeline_name: str) -> str:
    """Return the pipeline_id for a registered pipeline, or raise ValueError."""
    result = client.list_pipelines(filter=json.dumps({
        "predicates": [
            {"key": "display_name", "operation": "EQUALS", "stringValue": pipeline_name}
        ]
    }))
    if not result.pipelines:
        raise ValueError(f"Pipeline '{pipeline_name}' not found in KFP.")
    return result.pipelines[0].pipeline_id


def latest_version_id(client: Any, pipeline_id: str) -> str:
    """Return the pipeline_version_id of the most recently created version."""
    total = client.list_pipeline_versions(pipeline_id=pipeline_id, page_size=1).total_size or 1
    versions = client.list_pipeline_versions(pipeline_id=pipeline_id, page_size=int(total))
    if not versions.pipeline_versions:
        raise ValueError("Pipeline has no versions in KFP.")
    return sorted(
        versions.pipeline_versions, key=lambda v: v.created_at, reverse=True
    )[0].pipeline_version_id
