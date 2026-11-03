import logging
import os
import sys
from contextlib import contextmanager

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())

##############################################################################
# Base images
##############################################################################

DATA_GENERATION_BASE_IMAGE = (
    f"{os.getenv('KFP_IMAGE_REGISTRY')}"
    f"/{os.getenv('KFP_DATA_GENERATION_BASE_IMAGE_NAME')}"
    f":{os.getenv('KFP_DATA_GENERATION_BASE_IMAGE_TAG')}"
)

INDEXING_BASE_IMAGE = (
    f"{os.getenv('KFP_IMAGE_REGISTRY')}"
    f"/{os.getenv('KFP_INDEXING_BASE_IMAGE_NAME')}"
    f":{os.getenv('KFP_INDEXING_BASE_IMAGE_TAG')}"
)

ANALYSIS_BASE_IMAGE = (
    f"{os.getenv('KFP_IMAGE_REGISTRY')}"
    f"/{os.getenv('KFP_ANALYSIS_BASE_IMAGE_NAME')}"
    f":{os.getenv('KFP_ANALYSIS_BASE_IMAGE_TAG')}"
)


##############################################################################
# Logging setup
##############################################################################


def setup_logging():
    """Configures logging for KFP component pods.

    ``logging.basicConfig`` is a no-op when handlers are already present
    (KFP executor pre-configures them before the component body runs).
    Calling ``setLevel`` on the root logger overrides the level regardless.
    """
    import logging

    _level = os.environ.get("LOGLEVEL", "INFO").upper()
    logging.basicConfig(level=_level)
    logging.getLogger().setLevel(_level)


##############################################################################
# Git URL helper
##############################################################################


def get_pip_installable_git_url(
    git_username: str,
    git_token: str,
    repo_url: str,
    repo_ref: str,
    subdirectory: str,
) -> str:
    """Returns a pip-installable VCS URL with embedded credentials."""
    return (
        f"git+https://{git_username}:{git_token}"
        f"@{repo_url.removeprefix('https://')}"
        f"@{repo_ref}"
        f"#subdirectory={subdirectory}"
    )


##############################################################################
# Secret-injection decorator
##############################################################################


def inject_secret_as_env(secret_name: str, keys: list[str] | None = None):
    """Decorator factory that injects keys from a K8s secret as env vars.

    Args:
        secret_name: Name of the Kubernetes Secret whose keys should be
                     exposed as environment variables of the same name.
        keys: Explicit list of keys to inject.
        If not present, injects the full secret.
    """
    import functools

    def read_secret_keys() -> list:
        """Returns the data keys of the secret, or [] on any error."""
        try:

            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config

            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

            namespace = os.getenv("KFP_NAMESPACE", "default")

            secret = k8s_client.CoreV1Api().read_namespaced_secret(
                name=secret_name, namespace=namespace
            )

            return list((secret.data or {}).keys())

        except Exception:

            return []

    def decorator(component_fn):

        @functools.wraps(component_fn)
        def wrapper(*args, **kwargs):
            task = component_fn(*args, **kwargs)
            try:
                from kfp import kubernetes

                inject_keys = keys if keys is not None else read_secret_keys()

                if inject_keys:
                    kubernetes.use_secret_as_env(
                        task,
                        secret_name=secret_name,
                        secret_key_to_env={k: k for k in inject_keys},
                    )

            except ImportError:
                pass

            return task

        return wrapper

    return decorator


##############################################################################
# Skill-component hardening
##############################################################################


def sigterm_handler(signum, frame):
    logging.error(
        "SIGTERM received — Kubernetes is terminating this pod "
        "(node eviction, pod preemption, or manual deletion). "
        "Exiting with code 143."
    )
    sys.exit(143)


def harden_skill_component(
    component_fn=None,
    *,
    cpu_limit: str = "2",
    memory_limit: str = "8G",
    timeout_seconds: int | None = None,
):
    """
    Decorator that hardens a KFP component for isolated skill execution.

    Args:
        cpu_limit:       CPU limit for the component pod (default: "2").
        memory_limit:    Memory limit for the component pod (default: "8G").
        timeout_seconds: KFP task timeout in seconds. Pass an integer to enforce a
                         deadline (e.g. 1800 for 30 min). Defaults to None (no timeout).
    """
    import functools

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            task = fn(*args, **kwargs)
            task.set_cpu_limit(cpu_limit).set_memory_limit(memory_limit)
            try:
                from kfp import kubernetes

                kubernetes.add_pod_label(task, "skill-agent", "true")
                if timeout_seconds is not None:
                    kubernetes.set_timeout(task, timeout_seconds)
            except ImportError:
                pass
            return task

        return wrapper

    # Support both @harden_skill_component and @harden_skill_component(...)
    return decorator(component_fn) if component_fn is not None else decorator


##############################################################################
# Pipeline run ID helpers
##############################################################################


def get_kfp_run_id() -> str | None:
    """Return the KFP run ID for the current pod by reading the ``pipeline/runid`` label.

    Uses ``KFP_POD_NAME`` (injected via downward API) to look up the pod via the
    Kubernetes API. Returns ``None`` if the label is absent or the API call fails.
    """
    try:
        from kubernetes import client as k8s_client
        from kubernetes import config as k8s_config

        k8s_config.load_incluster_config()

        pod_name = os.environ.get("KFP_POD_NAME", "").strip()
        ns = (os.environ.get("KFP_NAMESPACE") or os.environ.get("MLFLOW_NAMESPACE", "")).strip()

        if pod_name and ns:
            pod = k8s_client.CoreV1Api().read_namespaced_pod(pod_name, ns)
            kfp_run_id = (pod.metadata.labels or {}).get("pipeline/runid", "").strip()
            return kfp_run_id or None

    except Exception:
        pass

    return None


##############################################################################
# Pipeline compilation helper
##############################################################################


def compile_all_and_exit(pipelines: dict):
    """Compiles all pipeline functions to <KFP_PIPELINE_OUTPUT_DIR>/<name>.yaml and exits."""
    if os.getenv("PIPELINE_COMPILE_ONLY"):

        from kfp import compiler

        output_dir = os.environ.get("KFP_PIPELINE_OUTPUT_DIR", "compiled_pipelines")

        os.makedirs(output_dir, exist_ok=True)

        for name, fn in pipelines.items():

            out = os.path.join(output_dir, f"{name}.yaml")

            compiler.Compiler().compile(fn, out)

            logging.info(f"  Compiled {name} -> {out}")

        raise SystemExit(0)


##############################################################################
# Artifact I/O context managers
##############################################################################


@contextmanager
def read_from_input_artifact(artifact):
    """Extract a KFP Input[Dataset] tar.gz archive to a temp dir."""
    import tarfile
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:

        with tarfile.open(artifact.path, "r:gz") as tar:
            tar.extractall(tmp)

        yield tmp


@contextmanager
def write_to_output_artifact(artifact, compresslevel=1):
    """Yield a fresh temp dir; archive it to a KFP Output[Dataset] on clean exit.

    Args:
        artifact:      KFP Output[Dataset] whose ``.path`` receives the archive.
        compresslevel: gzip compression level (1 = fastest, 9 = smallest).
                       Defaults to 1; switch to 0 / ``"w:"`` mode for binary
                       data (e.g. parquet + embeddings) that compresses poorly.
    """
    import os
    import tarfile
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:

        yield tmp

        os.makedirs(os.path.dirname(artifact.path), exist_ok=True)

        with tarfile.open(artifact.path, "w:gz", compresslevel=compresslevel) as tar:
            tar.add(tmp, arcname=".")


@contextmanager
def use_ephemeral_space():
    """Yield a temporary directory and remove it on exit."""
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:

        yield tmp
