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

    - KFP (RHOAI): reads the ``pipeline/runid`` pod label via the Kubernetes API.
      ``KFP_POD_NAME`` (injected via downward API) identifies the current pod.
      The label value equals the KFP run UUID and is consistent across all pods
      in a run, including all stages and multi-repo sub-pipelines.
    - Local/non-KFP: a UUID generated once per process and cached in the environment.
    """
    import os

    if "_AGENTMESH_PIPELINE_RUN_ID" in os.environ:
        return os.environ["_AGENTMESH_PIPELINE_RUN_ID"]

    try:
        from utils.kubeflow_utils import get_kfp_run_id

        pipeline_run_id = get_kfp_run_id()
        if pipeline_run_id:
            os.environ["_AGENTMESH_PIPELINE_RUN_ID"] = pipeline_run_id
            return pipeline_run_id

    except Exception:
        pass

    import uuid

    os.environ["_AGENTMESH_PIPELINE_RUN_ID"] = str(uuid.uuid4())
    return os.environ["_AGENTMESH_PIPELINE_RUN_ID"]
