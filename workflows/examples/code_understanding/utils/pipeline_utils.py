def uses_jupyter_runtime():
    """Returns True if the current process is running inside a Jupyter notebook."""
    try:
        from IPython import get_ipython

        return get_ipython() is not None
    except ImportError:
        return False


def _running_in_kubernetes_pod() -> bool:
    """Returns True if the process is running inside a Kubernetes pod."""
    import os

    return os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token")


def uses_kfp():
    """Returns True when KFP pipeline graph construction should be used.
    """
    import os

    try:
        if uses_jupyter_runtime():
            return False
        import kfp  # noqa: F401

        if _running_in_kubernetes_pod() or os.getenv("PIPELINE_COMPILE_ONLY"):
            return True
        return False
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

    # In a KFP run every stage must share the same ID; a random fallback would
    # cause stages to store and look up results under different keys.
    if uses_kfp() and _running_in_kubernetes_pod():
        raise RuntimeError(
            "Running in KFP but could not read the pipeline/runid pod label. "
            "Ensure KFP_POD_NAME and KFP_NAMESPACE are set via the downward API."
        )

    import uuid

    os.environ["_AGENTMESH_PIPELINE_RUN_ID"] = str(uuid.uuid4())
    return os.environ["_AGENTMESH_PIPELINE_RUN_ID"]
