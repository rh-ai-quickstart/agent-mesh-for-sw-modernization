#!/bin/sh

set -eu

ENV_FILE=${1:-./.env}
MAIN_RELEASE=agent-mesh-for-sw
EMBEDDING_RELEASE=e5-mistral

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: environment file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
. "$ENV_FILE"
set +a

: "${KFP_NAMESPACE:?KFP_NAMESPACE must be set in $ENV_FILE}"
: "${OTEL_NAMESPACE:?OTEL_NAMESPACE must be set in $ENV_FILE}"
: "${OTEL_SERVICE_NAME:?OTEL_SERVICE_NAME must be set in $ENV_FILE}"

case "$KFP_NAMESPACE" in
  default|kube-*|openshift-*|redhat-ods-applications)
    echo "Error: refusing to uninstall from protected namespace: $KFP_NAMESPACE" >&2
    exit 1
    ;;
esac

delete_prefixed() {
  resource_type=$1
  namespace=$2
  shift 2

  resources=$(oc get "$resource_type" -n "$namespace" -o name 2>/dev/null || true)
  for resource in $resources; do
    resource_name=${resource#*/}
    for prefix in "$@"; do
      case "$resource_name" in
        "$prefix"*)
          oc delete "$resource" -n "$namespace" --ignore-not-found
          break
          ;;
      esac
    done
  done
}

namespace_exists() {
  oc get namespace "$1" >/dev/null 2>&1
}

echo "==> Uninstalling Agent Mesh from $KFP_NAMESPACE"
echo "    This removes application resources and PVC-backed data."

if namespace_exists "$KFP_NAMESPACE"; then
  echo "==> Stopping upload, pipeline, and ad-hoc Jobs..."
  oc delete job \
    upload-kubeflow-pipelines upload-assets upload-prebuilt-index run-pipelines \
    -n "$KFP_NAMESPACE" --ignore-not-found
  delete_prefixed job "$KFP_NAMESPACE" run-adhoc-query- cu-pipeline- cu-query-
  delete_prefixed configmap "$KFP_NAMESPACE" adhoc-query- cu-repos-

  echo "==> Removing Notebook and pipeline operator parents..."
  if oc get notebook -n "$KFP_NAMESPACE" -o name >/dev/null 2>&1; then
    oc delete notebook data-generation graphrag-indexing \
      -n "$KFP_NAMESPACE" --ignore-not-found --wait=true --timeout=300s
  fi
  if oc get datasciencepipelinesapplication -n "$KFP_NAMESPACE" -o name >/dev/null 2>&1; then
    oc delete datasciencepipelinesapplication dspa \
      -n "$KFP_NAMESPACE" --ignore-not-found --wait=true --timeout=300s
  fi
fi

echo "==> Removing Agent Mesh telemetry..."
OTEL_OWNED=false
if oc get tempostack "$OTEL_SERVICE_NAME" -n "$OTEL_NAMESPACE" >/dev/null 2>&1 || \
   oc get opentelemetrycollector "$OTEL_SERVICE_NAME" -n "$OTEL_NAMESPACE" >/dev/null 2>&1 || \
   oc get secret tempo-s3-secret -n "$OTEL_NAMESPACE" >/dev/null 2>&1; then
  RELEASE_NAMESPACE=$(oc get tempostack "$OTEL_SERVICE_NAME" -n "$OTEL_NAMESPACE" \
    -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-namespace}' 2>/dev/null || true)
  TEMPO_ENDPOINT=$(oc get secret tempo-s3-secret -n "$OTEL_NAMESPACE" \
    -o go-template='{{index .data "endpoint" | base64decode}}' 2>/dev/null || true)
  EXPECTED_ENDPOINT="http://minio-service.$KFP_NAMESPACE.svc.cluster.local:9000"

  if [ "$RELEASE_NAMESPACE" = "$KFP_NAMESPACE" ] || [ "$TEMPO_ENDPOINT" = "$EXPECTED_ENDPOINT" ]; then
    OTEL_OWNED=true
  else
    echo "Error: telemetry named $OTEL_SERVICE_NAME is not owned by $KFP_NAMESPACE; refusing to delete it." >&2
    exit 1
  fi
fi

if [ "$OTEL_OWNED" = true ]; then
  if oc get opentelemetrycollector -n "$OTEL_NAMESPACE" -o name >/dev/null 2>&1; then
    oc delete opentelemetrycollector "$OTEL_SERVICE_NAME" \
      -n "$OTEL_NAMESPACE" --ignore-not-found --wait=true --timeout=300s
  fi
  if oc get tempostack -n "$OTEL_NAMESPACE" -o name >/dev/null 2>&1; then
    oc delete tempostack "$OTEL_SERVICE_NAME" \
      -n "$OTEL_NAMESPACE" --ignore-not-found --wait=true --timeout=300s
  fi
  oc delete secret tempo-s3-secret -n "$OTEL_NAMESPACE" --ignore-not-found
  delete_prefixed pvc "$OTEL_NAMESPACE" "data-tempo-$OTEL_SERVICE_NAME-ingester-"
fi
oc delete job create-tempo-bucket -n "$OTEL_NAMESPACE" --ignore-not-found

echo "==> Removing Helm releases..."
helm uninstall "$EMBEDDING_RELEASE" -n "$KFP_NAMESPACE" \
  --ignore-not-found --cascade foreground --wait --timeout 10m
helm uninstall "$MAIN_RELEASE" -n "$KFP_NAMESPACE" \
  --ignore-not-found --cascade foreground --wait --timeout 10m

if namespace_exists "$KFP_NAMESPACE"; then
  echo "==> Removing legacy resources and retained storage..."
  oc delete \
    deployment/code-understanding-console \
    service/code-understanding-console \
    route/code-understanding-console \
    buildconfig/code-understanding-console \
    imagestream/code-understanding-console \
    configmap/code-understanding-job-scripts \
    secret/git-credentials \
    secret/code-understanding-env \
    -n "$KFP_NAMESPACE" --ignore-not-found

  oc delete pvc \
    minio-pvc datagen-storage graphrag-storage e5-mistral-cache mariadb-dspa \
    -n "$KFP_NAMESPACE" --ignore-not-found --wait=true --timeout=300s
fi

echo "==> Removing any orphaned release-owned notebook ImageStreams..."
for image_stream in custom-data-generation custom-graphrag custom-analysis; do
  RELEASE_NAMESPACE=$(oc get imagestream "$image_stream" -n redhat-ods-applications \
    -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-namespace}' 2>/dev/null || true)
  if [ "$RELEASE_NAMESPACE" = "$KFP_NAMESPACE" ]; then
    oc delete imagestream "$image_stream" -n redhat-ods-applications --ignore-not-found
  fi
done

echo "==> Verifying uninstall..."
if helm status "$MAIN_RELEASE" -n "$KFP_NAMESPACE" >/dev/null 2>&1 || \
   helm status "$EMBEDDING_RELEASE" -n "$KFP_NAMESPACE" >/dev/null 2>&1; then
  echo "Error: an Agent Mesh Helm release still exists." >&2
  exit 1
fi

if namespace_exists "$KFP_NAMESPACE"; then
  LEFTOVERS=$(oc get \
    deployment,statefulset,job,pod,pvc,service,route,buildconfig,imagestream,notebook,datasciencepipelinesapplication \
    -n "$KFP_NAMESPACE" -o name 2>/dev/null | \
    awk -F/ '$2 ~ /^(code-understanding|data-generation|graphrag-indexing|ds-pipeline|mariadb-dspa|minio|e5-mistral|run-pipelines|run-adhoc-query|upload-|cu-|datagen-storage|graphrag-storage)/ { print }' || true)
  if [ -n "$LEFTOVERS" ]; then
    echo "Error: Agent Mesh resources remain in $KFP_NAMESPACE:" >&2
    echo "$LEFTOVERS" >&2
    exit 1
  fi
fi

echo "==> Agent Mesh uninstall complete. Namespace $KFP_NAMESPACE was preserved."
