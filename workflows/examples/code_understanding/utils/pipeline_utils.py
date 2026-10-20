def uses_jupyter_runtime():
    """Returns True if the current process is running inside a Jupyter notebook."""
    try:
        from IPython import get_ipython

        return get_ipython() is not None
    except ImportError:
        return False


def uses_kfp():
    """Returns True if KFP is installed and the process is not running in a Jupyter notebook."""
    try:
        if uses_jupyter_runtime():
            return False
        import kfp  # noqa: F401

        return True
    except ImportError:
        return False


def get_pipeline_run_id() -> str:
    """Returns a stable identifier for the current pipeline run.

    - KFP (Argo): ``ARGO_WORKFLOW_UID``, auto-injected by Argo into every component pod.
    - Local/non-KFP: a UUID generated once per process and cached in the environment.
    """
    import os

    argo_uid = os.environ.get("ARGO_WORKFLOW_UID", "").strip()
    if argo_uid:
        return argo_uid

    import uuid

    if "_AGENTMESH_PIPELINE_RUN_ID" not in os.environ:
        os.environ["_AGENTMESH_PIPELINE_RUN_ID"] = str(uuid.uuid4())
    return os.environ["_AGENTMESH_PIPELINE_RUN_ID"]
