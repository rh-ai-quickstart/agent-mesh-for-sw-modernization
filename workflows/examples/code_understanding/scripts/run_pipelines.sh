#!/usr/bin/env bash
# Triggers existing KFP pipeline runs by name.
# Pipelines must be uploaded first via: make upload-pipelines
#
# Usage:
#   ./run_pipelines.sh --single-repo   # trigger single-repo pipeline run
#   ./run_pipelines.sh                 # trigger multi-repo pipeline run (default)
#   ./run_pipelines.sh --multi-repo    # trigger multi-repo pipeline run
#
# Environment variables:
#   KFP_NAMESPACE         Kubernetes namespace (KFP_HOST is derived from this)
#   GIT_REPO              Git repository URL to analyse (required for --single-repo)
#   GIT_BRANCH            Git branch to clone (default: main)
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
  --single-repo   Trigger single-repo pipeline run (GIT_REPO required)
  --multi-repo    Trigger multi-repo pipeline run (default)
  -h, --help      Show this help message

Environment variables:
  KFP_NAMESPACE  Kubernetes namespace, used to derive KFP_HOST (required)
  GIT_REPO       Git repository URL to analyse (required for --single-repo)
  GIT_BRANCH     Git branch to clone (default: main)
  PARENT_SOURCE_PATH                Parent source path (default: source)
  PARENT_TARGET_PATH                Parent target path (default: target)
  KFP_DATA_INDEXING_OUTPUT_PATH     GraphRAG base path (default: graph_rag_app/source)
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
SOURCE_PATH="${PARENT_SOURCE_PATH:-source}"
TARGET_PATH="${PARENT_TARGET_PATH:-target}"
GRAPHRAG_SOURCE_PATH="${KFP_DATA_INDEXING_OUTPUT_PATH:-graph_rag_app/source}"

# ---------------------------------------------------------------------------
# trigger_pipeline
#   Looks up an existing pipeline by name in KFP and creates a new run.
#   Errors clearly if the pipeline has not been uploaded yet.
#
#   $1  pipeline_name  name of the registered pipeline in KFP
#   $2  run_name       name for the new run
#   $3  params         optional JSON string of run parameters (default: {})
# ---------------------------------------------------------------------------
trigger_pipeline() {
    local pipeline_name="$1"
    local run_name="$2"
    local params="$3"
    [ -z "$params" ] && params='{}'
    echo "Triggering $pipeline_name as $run_name on $KFP_HOST..."
    # Pass pipeline_name, run_name, and params via env vars to avoid shell
    # quoting issues when the JSON params string is passed as a CLI argument.
    KFP_TRIGGER_PIPELINE="$pipeline_name" \
    KFP_TRIGGER_RUN="$run_name" \
    KFP_TRIGGER_PARAMS="$params" \
    PYTHONPATH="$CODE_UNDERSTANDING_DIR:${PYTHONPATH:-}" \
    python3 - <<'PYEOF'
import os, json
from services.trigger_run import trigger_run
run = trigger_run(os.environ["KFP_TRIGGER_PIPELINE"], os.environ["KFP_TRIGGER_RUN"], json.loads(os.environ["KFP_TRIGGER_PARAMS"]))
print(f"  Submitted run id: {run.run_id}")
PYEOF
    echo "  OK: $run_name submitted."
}

MODE="multi"

for arg in "$@"; do
    case "$arg" in
        --single-repo) MODE="single" ;;
        --multi-repo)  MODE="multi" ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "Error: Unknown argument: $arg" >&2; usage; exit 1 ;;
    esac
done

if [[ "$MODE" == "single" ]]; then
    if [[ -z "$GIT_REPO" ]]; then
        echo "Error: GIT_REPO must be set and non-empty for --single-repo." >&2
        exit 1
    fi
    trigger_pipeline "single_repo" "single_repo_${TIMESTAMP}" \
        "{\"git_repo\": \"$GIT_REPO\", \"git_branch\": \"$GIT_BRANCH\", \"parent_source_path\": \"$SOURCE_PATH\", \"parent_target_path\": \"$TARGET_PATH\"}"
else
    trigger_pipeline "multi_repo" "multi_repo_${TIMESTAMP}" \
        "{\"parent_source_path\": \"$SOURCE_PATH\", \"parent_target_path\": \"$TARGET_PATH\"}"
fi

echo "All done."
