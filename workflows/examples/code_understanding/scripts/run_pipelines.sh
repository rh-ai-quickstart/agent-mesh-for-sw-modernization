#!/usr/bin/env bash
# Triggers existing KFP pipeline runs by name.
# Pipelines must be uploaded first via: make upload-pipelines
#
# Usage:
#   ./run_pipelines.sh --single-repo              # trigger single-repo pipeline run
#   ./run_pipelines.sh                            # trigger multi-repo pipeline run (default)
#   ./run_pipelines.sh --multi-repo               # trigger multi-repo pipeline run
#   ./run_pipelines.sh --single-repo --analysis-only  # re-run analysis only (skips data-gen/indexing)
#   ./run_pipelines.sh --multi-repo  --analysis-only  # re-run analysis only (multi-repo)
#
# For multi-repo, inject the repo list via the code-understanding-env secret
# (GIT_REPO_LIST_CONTENTS) using: make run-pipelines PIPELINE_GIT_REPO_LIST=<file>
#
# Environment variables:
#   KFP_NAMESPACE         Kubernetes namespace (KFP_HOST is derived from this)
#   GIT_REPO              Git repository URL to analyse (required for --single-repo)
#   GIT_BRANCH            Git branch to clone (default: main)
#   PIPELINE_RUN_ID       KFP run ID of a previous full pipeline run (required for --analysis-only)
#   PARENT_SOURCE_PATH                 Parent source path (default: source)
#   PARENT_TARGET_PATH                 Parent target path (default: target)
#   KFP_DATA_INDEXING_OUTPUT_PATH      GraphRAG base path (default: graph_rag_app/source)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_UNDERSTANDING_DIR="$(dirname "$SCRIPT_DIR")"

usage() {
    cat >&2 <<EOF
Usage: $(basename "$0") [OPTION]...

Options:
  --single-repo        Trigger single-repo pipeline run (GIT_REPO required)
  --multi-repo         Trigger multi-repo pipeline run (default)
  --analysis-only      Re-run analysis stage only; skips data-gen and indexing
                       (PIPELINE_RUN_ID required)
  -h, --help           Show this help message

Environment variables:
  KFP_NAMESPACE       Kubernetes namespace, used to derive KFP_HOST (required)
  GIT_REPO            Git repository URL to analyse (required for --single-repo)
  GIT_BRANCH          Git branch to clone (default: main)
  PIPELINE_RUN_ID     KFP run ID of a previous full pipeline run (required for --analysis-only)
  PARENT_SOURCE_PATH                Parent source path (default: source)
  PARENT_TARGET_PATH                Parent target path (default: target)
  KFP_DATA_INDEXING_OUTPUT_PATH     GraphRAG base path (default: graph_rag_app/source)
  GIT_REPO_LIST_CONTENTS            JSON repo list (injected via code-understanding-env secret)
EOF
}

if [[ -z "${KFP_NAMESPACE:-}" ]]; then
    echo "Error: KFP_NAMESPACE must be set and non-empty." >&2
    exit 1
fi

KFP_HOST="${KFP_HOST:-https://ds-pipeline-dspa.${KFP_NAMESPACE}.svc.cluster.local:8443}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
GIT_REPO="${GIT_REPO:-}"
GIT_BRANCH="${GIT_BRANCH:-main}"
PIPELINE_RUN_ID="${PIPELINE_RUN_ID:-}"
ANALYSIS_ONLY="false"
SOURCE_PATH="${PARENT_SOURCE_PATH:-source}"
TARGET_PATH="${PARENT_TARGET_PATH:-target}"
GRAPHRAG_SOURCE_PATH="${KFP_DATA_INDEXING_OUTPUT_PATH:-graph_rag_app/source}"

# ---------------------------------------------------------------------------
# trigger_pipeline
#   Looks up an existing pipeline by name in KFP and creates a new run.
#   Errors clearly if the pipeline has not been uploaded yet.
#
#   $1  pipeline_name   name of the registered pipeline in KFP
#   $2  run_name        name for the new run
#   $3  params          optional JSON string of run parameters (default: {})
#   $4  repos_json      optional JSON array string of repo dicts (multi-repo only)
#   $5  enable_caching  optional "true"/"false" (default: false)
# ---------------------------------------------------------------------------
trigger_pipeline() {
    local pipeline_name="$1"
    local run_name="$2"
    local params="$3"
    local repos_json="${4:-}"
    local enable_caching="${5:-false}"
    [ -z "$params" ] && params='{}'
    echo "Triggering $pipeline_name as $run_name on $KFP_HOST..."
    # Pass pipeline_name, run_name, params, and optional repos_json via env vars
    # to avoid shell quoting issues with JSON strings as CLI arguments.
    KFP_TRIGGER_PIPELINE="$pipeline_name" \
    KFP_TRIGGER_RUN="$run_name" \
    KFP_TRIGGER_PARAMS="$params" \
    KFP_TRIGGER_REPOS_JSON="$repos_json" \
    KFP_TRIGGER_ENABLE_CACHING="$enable_caching" \
    PYTHONPATH="$CODE_UNDERSTANDING_DIR:${PYTHONPATH:-}" \
    python3 - <<'PYEOF'
import os, json, logging
from services.trigger_run import trigger_run
from services.update_repos import log_repos
params = json.loads(os.environ["KFP_TRIGGER_PARAMS"])
repos_json = os.environ.get("KFP_TRIGGER_REPOS_JSON", "")
if repos_json:
    try:
        log_repos(json.loads(repos_json))
    except Exception:
        logging.warning("log_repos failed; continuing with pipeline submission.", exc_info=True)
    params["runnable_repos"] = repos_json
enable_caching = os.environ.get("KFP_TRIGGER_ENABLE_CACHING", "false").lower() == "true"
run = trigger_run(os.environ["KFP_TRIGGER_PIPELINE"], os.environ["KFP_TRIGGER_RUN"], params,
                  enable_caching=enable_caching)
print(f"  Submitted run id: {run.run_id}")
print(f"==> Pipeline run ID: {run.run_id}")
PYEOF
    echo "  OK: $run_name submitted."
}

MODE="multi"

for arg in "$@"; do
    case "$arg" in
        --single-repo)   MODE="single" ;;
        --multi-repo)    MODE="multi" ;;
        --analysis-only) ANALYSIS_ONLY="true" ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "Error: Unknown argument: $arg" >&2; usage; exit 1 ;;
    esac
done

if [[ "$ANALYSIS_ONLY" == "true" && -z "$PIPELINE_RUN_ID" ]]; then
    echo "Error: PIPELINE_RUN_ID must be set and non-empty for --analysis-only." >&2
    exit 1
fi

# Only forward pipeline_run_id for analysis-only runs.  Passing a non-empty
# value on a full run causes data-gen and indexing components to return early
# and silently skip their work (they guard on `if pipeline_run_id: return`).
if [[ "$ANALYSIS_ONLY" != "true" ]]; then
    PIPELINE_RUN_ID=""
fi

if [[ "$MODE" == "single" ]]; then
    if [[ -z "$GIT_REPO" ]]; then
        echo "Error: GIT_REPO must be set and non-empty for --single-repo." >&2
        exit 1
    fi
    trigger_pipeline "single_repo" "single_repo_${TIMESTAMP}" \
        "{\"git_repo\": \"$GIT_REPO\", \"git_branch\": \"$GIT_BRANCH\", \"parent_source_path\": \"$SOURCE_PATH\", \"parent_target_path\": \"$TARGET_PATH\", \"pipeline_run_id\": \"$PIPELINE_RUN_ID\"}" \
        "[{\"git_repo\": \"$GIT_REPO\", \"git_branch\": \"$GIT_BRANCH\"}]" \
        "$ANALYSIS_ONLY"
else
    trigger_pipeline "multi_repo" "multi_repo_${TIMESTAMP}" \
        "{\"parent_source_path\": \"$SOURCE_PATH\", \"parent_target_path\": \"$TARGET_PATH\", \"pipeline_run_id\": \"$PIPELINE_RUN_ID\"}" \
        "${GIT_REPO_LIST_CONTENTS:-}" \
        "$ANALYSIS_ONLY"
fi

echo "All done."
