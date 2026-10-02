# ============================================================================
# Configuration
# ============================================================================

.DEFAULT_GOAL := install

ENV_FILE            	?= ./.env

ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
endif

# Export included configuration and the defaults below to every recipe.
export

RELEASE               ?= agent-mesh-for-sw
CHART_DIR             ?= resources/helm
NAMESPACE             ?=
WAIT_TIMEOUT          ?= 5m
ADHOC_TIMEOUT         ?= 20m
WORKBENCH_IMAGESTREAM_NAMESPACE ?= redhat-ods-applications
# Fall back to origin and the local branch when no upstream is configured.
GIT_LOCAL_BRANCH    	?= $(shell git branch --show-current 2>/dev/null)
GIT_REPO_REMOTE     	?= $(or $(shell git config --get "branch.$(GIT_LOCAL_BRANCH).remote" 2>/dev/null),origin)
GIT_REPO_URL        	?= $(shell git remote get-url "$(GIT_REPO_REMOTE)" 2>/dev/null | sed 's|^git@\([^:]*\):\(.*\)$$|https://\1/\2|')
GIT_REPO_BRANCH     	?= $(or $(shell git config --get "branch.$(GIT_LOCAL_BRANCH).merge" 2>/dev/null | sed 's|^refs/heads/||'),$(GIT_LOCAL_BRANCH))
CLUSTER_DOMAIN      	?= $(shell oc get ingress.config cluster --request-timeout=10s -o jsonpath='{.spec.domain}' 2>/dev/null)
GATEWAY_HOST        	?= $(shell oc get gateway data-science-gateway -n openshift-ingress --request-timeout=10s -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)
# Keep these lazy cluster lookups out of every recipe's exported environment,
# so install can run its preflight before the lookups are expanded.
unexport CLUSTER_DOMAIN GATEWAY_HOST
PIPELINE_GIT_REPO   	?=
PIPELINE_GIT_BRANCH 	?=
PIPELINE_GIT_REPO_LIST	?=
DEPLOY_EMBEDDING_MODEL ?= false
DEPLOY_OTEL            ?= false

# Image build/push settings. CI sets REGISTRY and VERSION for its build; when
# unset, recipes use KFP_IMAGE_REGISTRY and the per-image tags below.
# Local development uses Podman by default. GitHub Actions sets CI=true and
# provides Docker Buildx; callers can override this with CONTAINER_ENGINE.
CONTAINER_ENGINE      ?= $(if $(CI),docker,podman)
REGISTRY              ?=
VERSION               ?=

# Defaults for values omitted from .env and the calling environment.
AWS_S3_BUCKET                      ?= data
GIT_REPO                           ?= https://github.com/agapebondservant/tic-tac-toe-sample
GIT_BRANCH                         ?= main
GIT_REPO_LIST                      ?= workflows/examples/code_understanding/assets/repos/repo_list.json
KFP_DATA_GENERATION_OUTPUT_PATH    ?= target
KFP_DATA_INDEXING_OUTPUT_PATH      ?= graphrag-source
KFP_IMAGE_REGISTRY                 ?= quay.io/rh-ai-quickstart
KFP_DATA_GENERATION_BASE_IMAGE_NAME ?= agent-mesh-for-sw-modernization-data-generation
KFP_INDEXING_BASE_IMAGE_NAME         ?= agent-mesh-for-sw-modernization-data-indexing
KFP_ANALYSIS_BASE_IMAGE_NAME         ?= agent-mesh-for-sw-modernization-data-indexing
KFP_PIPELINE_TOOLS_IMAGE_NAME        ?= agent-mesh-for-sw-modernization-pipeline-tools
CONSOLE_APP_IMAGE_NAME               ?= agent-mesh-for-sw-modernization-console-app
CONSOLE_PLUGIN_IMAGE_NAME            ?= agent-mesh-for-sw-modernization-console-plugin
# Shared fallback for image tags omitted from .env. VERSION overrides these
# tags for build/push only.
BASE_VERSION                         ?= v0.1.2
KFP_DATA_GENERATION_BASE_IMAGE_TAG   ?= $(BASE_VERSION)
KFP_INDEXING_BASE_IMAGE_TAG          ?= $(BASE_VERSION)
KFP_ANALYSIS_BASE_IMAGE_TAG          ?= $(BASE_VERSION)
KFP_PIPELINE_TOOLS_IMAGE_TAG         ?= $(BASE_VERSION)
CONSOLE_IMAGE_TAG                    ?= $(BASE_VERSION)
ASSET_LOADER                        ?= mlflow
INSTALL_PREBUILT_INDEX              ?= true
CUSTOM_EVALUATOR                    ?= mlflow
OTEL_SERVICE_NAME                   ?= code-understanding
OTEL_NAMESPACE                      ?= $(KFP_NAMESPACE)
OTEL_EXPORTER_OTLP_ENDPOINT         ?= http://$(OTEL_SERVICE_NAME)-collector.$(OTEL_NAMESPACE).svc.cluster.local:4318
OTEL_EXPORTER                       ?= otlp_http
MLFLOW_TRACKING_INSECURE_TLS        ?= true
MLFLOW_TRACKING_AUTH                ?= kubernetes-namespaced
MLFLOW_TRACE_ENABLE_OTLP_DUAL_EXPORT ?= true
OTEL_SEMCONV_STABILITY_OPT_IN       ?= genai

SECRET_ENV_VARS := \
	AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_S3_BUCKET \
	GIT_USERNAME GIT_TOKEN GIT_REPO GIT_BRANCH GIT_REPO_LIST \
	GRAPHRAG_LLM_TOKEN GRAPHRAG_LLM_ID GRAPHRAG_LLM_API_BASE \
	GRAPHRAG_LLM_PROVIDER GRAPHRAG_LLM_PROVIDER_SETTINGS_XML \
	EMBED_LLM_TOKEN EMBED_LLM_API_BASE EMBED_LLM_ID \
	EMBED_LLM_PROVIDER EMBED_LLM_PROVIDER_SETTINGS_XML \
	GROUND_TRUTH_LLM_TOKEN GROUND_TRUTH_LLM_ID GROUND_TRUTH_LLM_API_BASE \
	GROUND_TRUTH_LLM_PROVIDER GROUND_TRUTH_LLM_THINKING \
	JUDGE_LLM_TOKEN JUDGE_LLM_ID JUDGE_LLM_API_BASE \
	JUDGE_LLM_PROVIDER JUDGE_LLM_THINKING \
	CODE_LLM_TOKEN CODE_LLM_API_BASE CODE_LLM_ID CODE_LLM_PROVIDER \
	KFP_NAMESPACE KFP_DATA_GENERATION_OUTPUT_PATH KFP_DATA_INDEXING_OUTPUT_PATH \
	KFP_IMAGE_REGISTRY \
	KFP_DATA_GENERATION_BASE_IMAGE_NAME KFP_INDEXING_BASE_IMAGE_NAME \
	KFP_ANALYSIS_BASE_IMAGE_NAME KFP_PIPELINE_TOOLS_IMAGE_NAME \
	CONSOLE_APP_IMAGE_NAME CONSOLE_PLUGIN_IMAGE_NAME \
	KFP_DATA_GENERATION_BASE_IMAGE_TAG KFP_INDEXING_BASE_IMAGE_TAG \
	KFP_ANALYSIS_BASE_IMAGE_TAG KFP_PIPELINE_TOOLS_IMAGE_TAG CONSOLE_IMAGE_TAG \
	MLFLOW_TRACKING_URI MLFLOW_TRACKING_INSECURE_TLS MLFLOW_TRACKING_AUTH \
	ASSET_LOADER INSTALL_PREBUILT_INDEX CUSTOM_EVALUATOR LOGLEVEL \
	OTEL_SERVICE_NAME OTEL_NAMESPACE OTEL_EXPORTER_OTLP_ENDPOINT OTEL_EXPORTER \
	MLFLOW_TRACE_ENABLE_OTLP_DUAL_EXPORT OTEL_SEMCONV_STABILITY_OPT_IN

export UI_URL

E2E_UI_PYTHON ?= 3.12
E2E_UI_REQUIREMENTS ?= ui/tests_e2e_ui/requirements.txt

E2E_UI_INSTALL_CMD := uv python install $(E2E_UI_PYTHON) && uv run --no-project --python $(E2E_UI_PYTHON) --with-requirements $(E2E_UI_REQUIREMENTS) -- playwright install chromium
E2E_UI_TEST_CMD    := uv run --no-project --python $(E2E_UI_PYTHON) --with-requirements $(E2E_UI_REQUIREMENTS) -- python -m pytest ui/tests_e2e_ui/ -v --tb=short --browser chromium --output=ui/tests_e2e_ui/test-results --screenshot=on --tracing=retain-on-failure

# ============================================================================
# Container engine
# ============================================================================

ifeq ($(CONTAINER_ENGINE),docker)
IMAGE_BUILD := docker buildx build --load
IMAGE_PUSH  := docker push
else ifeq ($(CONTAINER_ENGINE),podman)
IMAGE_BUILD := podman build
IMAGE_PUSH  := podman push
else
$(error Unsupported CONTAINER_ENGINE '$(CONTAINER_ENGINE)'; use docker or podman)
endif

BUILD_REGISTRY       = $(or $(REGISTRY),$(KFP_IMAGE_REGISTRY))
DATAGEN_IMAGE        = $(BUILD_REGISTRY)/$(KFP_DATA_GENERATION_BASE_IMAGE_NAME):$(or $(VERSION),$(KFP_DATA_GENERATION_BASE_IMAGE_TAG))
INDEX_IMAGE          = $(BUILD_REGISTRY)/$(KFP_INDEXING_BASE_IMAGE_NAME):$(or $(VERSION),$(KFP_INDEXING_BASE_IMAGE_TAG))
ANALYSIS_IMAGE       = $(BUILD_REGISTRY)/$(KFP_ANALYSIS_BASE_IMAGE_NAME):$(or $(VERSION),$(KFP_ANALYSIS_BASE_IMAGE_TAG))
PIPELINE_TOOLS_IMAGE = $(BUILD_REGISTRY)/$(KFP_PIPELINE_TOOLS_IMAGE_NAME):$(or $(VERSION),$(KFP_PIPELINE_TOOLS_IMAGE_TAG))
CONSOLE_APP_IMAGE    = $(BUILD_REGISTRY)/$(CONSOLE_APP_IMAGE_NAME):$(or $(VERSION),$(CONSOLE_IMAGE_TAG))
CONSOLE_PLUGIN_IMAGE = $(BUILD_REGISTRY)/$(CONSOLE_PLUGIN_IMAGE_NAME):$(or $(VERSION),$(CONSOLE_IMAGE_TAG))

HELM_REPO_ARGS = \
	--set "repoUrl=$(GIT_REPO_URL)" \
	--set "repoRef=$(GIT_REPO_BRANCH)"
HELM_WORKFLOW_IMAGE_ARGS = \
	--set "dataGeneration.image.registry=$(KFP_IMAGE_REGISTRY)" \
	--set "dataGeneration.image.name=$(KFP_DATA_GENERATION_BASE_IMAGE_NAME)" \
	--set "dataGeneration.image.tag=$(KFP_DATA_GENERATION_BASE_IMAGE_TAG)" \
	--set "graphrag.image.registry=$(KFP_IMAGE_REGISTRY)" \
	--set "graphrag.image.name=$(KFP_INDEXING_BASE_IMAGE_NAME)" \
	--set "graphrag.image.tag=$(KFP_INDEXING_BASE_IMAGE_TAG)" \
	--set "analysis.image.registry=$(KFP_IMAGE_REGISTRY)" \
	--set "analysis.image.name=$(KFP_ANALYSIS_BASE_IMAGE_NAME)" \
	--set "analysis.image.tag=$(KFP_ANALYSIS_BASE_IMAGE_TAG)"
HELM_PIPELINE_TOOLS_ARGS = \
	--set "pipelineTools.image.registry=$(KFP_IMAGE_REGISTRY)" \
	--set "pipelineTools.image.name=$(KFP_PIPELINE_TOOLS_IMAGE_NAME)" \
	--set "pipelineTools.image.tag=$(KFP_PIPELINE_TOOLS_IMAGE_TAG)"
HELM_UPGRADE_ARGS = agent-mesh-for-sw resources/helm \
	--namespace "$(KFP_NAMESPACE)" \
	--reset-then-reuse-values \
	--no-hooks \
	--wait \
	--wait-for-jobs \
	--timeout "$(WAIT_TIMEOUT)" \
	--set "namespace=$(KFP_NAMESPACE)"

# ============================================================================
# Help
# ============================================================================

.PHONY: \
	help \
	help-all \
	helm-dependencies \
	helm-lint \
	helm-template \
	verify-secrets \
	verify-deploy \
	test-ui \
	test-workflows \
	test-all \
	format \
	lint \
	install \
	_install-preflight \
	uninstall \
	deploy-embedding-model \
	prepare-workbench-images \
	deploy-notebooks \
	apply-secrets \
	build-images \
	build-all-images \
	push-all-images \
	build-data-generation-image \
	push-data-generation-image \
	build-data-indexing-image \
	push-data-indexing-image \
	build-data-analysis-image \
	push-data-analysis-image \
	build-pipeline-tools-image \
	push-pipeline-tools-image \
	build-console-app-image \
	push-console-app-image \
	build-console-plugin-image \
	push-console-plugin-image \
	_build-one-image \
	_push-one-image \
	upload-pipelines \
	upload-mlflow-assets \
	upload-prebuilt-index \
	run-adhoc-query \
	run-pipelines \
	deploy-otel \
	apply-console-src \
	run-console-app \
	deploy-console-app \
	port-forward-console-app \
	apply-plugin-src \
	deploy-console-plugin \
	enable-console-plugin \
	test-ui-install \
	test-ui

help:
	@echo "Agent Mesh for Software Modernization"
	@echo ""
	@echo "Usage:"
	@echo "  make <target> [VARIABLE=value ...]"
	@echo ""
	@echo "User tasks:"
	@echo "  run-pipelines               Submit the configured pipeline run"
	@echo "  run-adhoc-query             Run an ad hoc code-understanding query"
	@echo ""
	@echo "Administrator tasks:"
	@echo "  install                     Install the complete application stack"
	@echo "  uninstall                   Remove the application stack and PVC-backed data"
	@echo "  deploy-otel                 Deploy OpenTelemetry and Tempo resources when available"
	@echo ""
	@echo "Run 'make help-all' to list all administrative and development tasks."

help-all:
	@echo "Agent Mesh for Software Modernization"
	@echo ""
	@echo "Usage:"
	@echo "  make <target> [VARIABLE=value ...]"
	@echo ""
	@echo "Help:"
	@echo "  help                        Show user and administrator tasks"
	@echo "  help-all                    Show all tasks and common overrides"
	@echo ""
	@echo "Deployment:"
	@echo "  install                     Install the complete application stack"
	@echo "  uninstall                   Remove the application stack and PVC-backed data"
	@echo "  deploy-embedding-model      Deploy the e5-mistral embedding model"
	@echo "  prepare-workbench-images    Register project workbench images with OpenShift AI"
	@echo "  deploy-notebooks            Deploy the data generation and indexing notebooks"
	@echo "  apply-secrets               Create or update application secrets"
	@echo "  deploy-otel                 Deploy OpenTelemetry and Tempo resources when enabled"
	@echo ""
	@echo "Testing:"
	@echo "  test-all                    Run all test suites"
	@echo "  helm-dependencies           Download Helm chart dependencies"
	@echo "  helm-lint                   Lint the deployment chart"
	@echo "  helm-template               Render the deployment chart"
	@echo "  verify-secrets              Check tracked files for committed secrets"
	@echo "  verify-deploy               Verify the installed release and health endpoints"
	@echo ""
	@echo "Utility commands:"
	@echo "  format                      Format Python code with isort and Black"
	@echo "  lint                        Check Python code with Flake8, Black, and isort"
	@echo ""
	@echo "Container images:"
	@echo "  build-images                Build and push all application images"
	@echo "  build-all-images            Build all application images"
	@echo "  push-all-images             Push all application images"
	@echo "  build-data-generation-image Build the data generation image"
	@echo "  push-data-generation-image  Push the data generation image"
	@echo "  build-data-indexing-image  Build the data indexing image"
	@echo "  push-data-indexing-image   Push the data indexing image"
	@echo "  build-data-analysis-image  Build the data analysis image"
	@echo "  push-data-analysis-image   Push the data analysis image"
	@echo "  build-pipeline-tools-image Build the pipeline tools image"
	@echo "  push-pipeline-tools-image  Push the pipeline tools image"
	@echo "  build-console-app-image    Build the console app image"
	@echo "  push-console-app-image     Push the console app image"
	@echo "  build-console-plugin-image Build the console plugin image"
	@echo "  push-console-plugin-image  Push the console plugin image"
	@echo ""
	@echo "Pipelines and assets:"
	@echo "  upload-pipelines            Upload the Kubeflow pipelines"
	@echo "  upload-mlflow-assets        Upload MLflow-hosted application assets"
	@echo "  upload-prebuilt-index       Upload the prebuilt code index"
	@echo "  run-adhoc-query             Run an ad hoc code-understanding query"
	@echo "  run-pipelines               Submit the configured pipeline run"
	@echo ""
	@echo "Console application:"
	@echo "  apply-console-src           Publish console job scripts"
	@echo "  run-console-app             Run the console application locally"
	@echo "  deploy-console-app          Deploy the console application"
	@echo "  port-forward-console-app    Forward the deployed console to localhost:8080"
	@echo "  test-ui-install             Install Playwright and Chromium for UI smoke tests"
	@echo "  test-ui                     Check the deployed console UI with Playwright"
	@echo ""
	@echo "OpenShift console plugin:"
	@echo "  apply-plugin-src            Publish console-plugin job scripts"
	@echo "  deploy-console-plugin       Deploy the plugin and API"
	@echo "  enable-console-plugin       Enable the plugin in the OpenShift console"
	@echo ""
	@echo "Container image build overrides (used by CI):"
	@echo "  CONTAINER_ENGINE            Image tool: podman locally, docker in CI"
	@echo "  REGISTRY                    Build/push registry (default: KFP_IMAGE_REGISTRY)"
	@echo "  VERSION                     Tag for all images in this build/push run"
	@echo ""
	@echo "Common runtime overrides (not exhaustive):"
	@echo "  ENV_FILE                    Environment file to load (default: ./.env)"
	@echo "  BASE_VERSION                Fallback for omitted image tags (default: $(BASE_VERSION))"
	@echo "  UI_URL                      Override the console URL for test-ui (for example http://localhost:8080)"
	@echo "  E2E_UI_PYTHON               Python version for Playwright tests (default: 3.12)"
	@echo "  DEPLOY_EMBEDDING_MODEL      Deploy e5-mistral during install (default: false)"
	@echo "  DEPLOY_OTEL                 Deploy OpenTelemetry and Tempo during install (default: false)"
	@echo "  PIPELINE_GIT_REPO           Override the repository used by run-pipelines"
	@echo "  PIPELINE_GIT_BRANCH         Override the branch used by run-pipelines"
	@echo "  PIPELINE_GIT_REPO_LIST      Override the repository-list file"
	@echo "  ARGS                        Arguments passed to run-pipelines"
	@echo "  QUESTION_FILE               Required input file for run-adhoc-query"
	@echo "  WAIT_TIMEOUT                Resource readiness timeout (default: $(WAIT_TIMEOUT))"
	@echo "  ADHOC_TIMEOUT               Ad-hoc query timeout (default: $(ADHOC_TIMEOUT))"
	@echo ""
	@echo "See .env.template for additional deployment, pipeline, and image configuration."

# ============================================================================
# Installation and deployment
# ============================================================================

_install-preflight:
	@set -e; \
	[ -n "$(AWS_ACCESS_KEY_ID)" ] || { echo "AWS_ACCESS_KEY_ID must be set" >&2; exit 1; }; \
	[ -n "$(AWS_SECRET_ACCESS_KEY)" ] || { echo "AWS_SECRET_ACCESS_KEY must be set" >&2; exit 1; }; \
	[ -n "$(AWS_S3_BUCKET)" ] || { echo "AWS_S3_BUCKET must be set" >&2; exit 1; }; \
	echo "==> Checking OpenShift login (10-second limit)..."; \
	if ! oc whoami --request-timeout=10s >/dev/null 2>&1; then \
		echo "Error: Could not verify OpenShift login. Run 'oc login' and check cluster connectivity, then retry." >&2; \
		exit 1; \
	fi
	@echo "==> OpenShift login verified."

# Make expands recipe variables after prerequisites finish. This keeps the
# cluster lookups in CLUSTER_DOMAIN and GATEWAY_HOST behind the login check.
install: _install-preflight
	$(MAKE) helm-dependencies
	@set -e; \
	\
	echo "==> Creating namespaces..." && \
	set -- agent-mesh-for-sw resources/helm \
		--set "namespace=$(KFP_NAMESPACE)" \
		--set "requester=$$(oc whoami)"; \
	if [ "$(DEPLOY_OTEL)" = "true" ] && [ "$(OTEL_NAMESPACE)" != "$(KFP_NAMESPACE)" ]; then \
		set -- "$$@" --set "otel.namespace=$(OTEL_NAMESPACE)"; \
	fi; \
	helm template "$$@" -s templates/namespace.yaml | oc apply -f - && \
	\
	echo "==> Waiting for OpenShift to inject service CA into odh-trusted-ca-bundle..." && \
	oc wait configmap/odh-trusted-ca-bundle -n "$(KFP_NAMESPACE)" \
		--for=create --timeout="$(WAIT_TIMEOUT)" && \
	oc wait configmap/odh-trusted-ca-bundle -n "$(KFP_NAMESPACE)" \
		--for=jsonpath='{.data.ca-bundle\.crt}' --timeout="$(WAIT_TIMEOUT)"
	$(MAKE) prepare-workbench-images
	@if [ "$(DEPLOY_EMBEDDING_MODEL)" = "true" ]; then \
		$(MAKE) deploy-embedding-model; \
	fi
	$(MAKE) apply-secrets
	@set -e; \
	[ -n "$(KFP_IMAGE_REGISTRY)" ] || { echo "KFP_IMAGE_REGISTRY must be set" >&2; exit 1; }; \
	OTEL_ENABLED=false; \
	set -- $(HELM_UPGRADE_ARGS) \
		--create-namespace \
		--set "requester=$$(oc whoami)" \
		$(HELM_REPO_ARGS) \
		--set-string "aws-compatible-storage.s3.accessKeyId=$(AWS_ACCESS_KEY_ID)" \
		--set-string "aws-compatible-storage.s3.secretAccessKey=$(AWS_SECRET_ACCESS_KEY)" \
		--set-string "applicationStorage.bucket=$(AWS_S3_BUCKET)" \
		$(HELM_WORKFLOW_IMAGE_ARGS) \
		$(HELM_PIPELINE_TOOLS_ARGS) \
		--set "clusterDomain=$(CLUSTER_DOMAIN)" \
		--set "mlflowGatewayHost=$(GATEWAY_HOST)" \
		--set imageStreams.enabled=false \
		--set deployNotebooks=true \
		--set otel.enabled=false; \
	if [ "$(DEPLOY_OTEL)" = "true" ] && \
	   [ -n "$(OTEL_NAMESPACE)" ] && [ -n "$(OTEL_SERVICE_NAME)" ] && \
	   oc get crd opentelemetrycollectors.opentelemetry.io >/dev/null 2>&1 && \
	   oc get crd tempostacks.tempo.grafana.com >/dev/null 2>&1; then \
		set -- "$$@" \
			--set otel.enabled=true \
			--set "otel.namespace=$(OTEL_NAMESPACE)" \
			--set "otel.name=$(OTEL_SERVICE_NAME)"; \
	fi; \
	echo "==> Installing Agent Mesh Helm release..."; \
	helm upgrade --install "$$@"; \
	echo "==> Waiting for pipeline server..."; \
	oc wait deployment/ds-pipeline-dspa -n "$(KFP_NAMESPACE)" \
		--for=create --timeout="$(WAIT_TIMEOUT)"; \
	oc wait deployment/ds-pipeline-dspa -n "$(KFP_NAMESPACE)" \
		--for=condition=Available --timeout="$(WAIT_TIMEOUT)"
	@if [ "$(ASSET_LOADER)" = "mlflow" ]; then \
		echo "==> Preloading MLflow assets..." && \
		$(MAKE) upload-mlflow-assets; \
	fi
	@if [ "$(ASSET_LOADER)" = "mlflow" ] && [ "$(INSTALL_PREBUILT_INDEX)" = "true" ]; then \
		echo "==> Uploading prebuilt index..." && \
		$(MAKE) upload-prebuilt-index; \
	fi
	$(MAKE) upload-pipelines

uninstall:
	@set -eu; \
	[ -n "$(KFP_NAMESPACE)" ] || { echo "KFP_NAMESPACE must be set" >&2; exit 1; }; \
	case "$(KFP_NAMESPACE)" in default|kube-*|openshift-*|redhat-ods-applications) \
		echo "Error: refusing to uninstall from protected namespace: $(KFP_NAMESPACE)" >&2; exit 1;; \
	esac; \
	echo "==> Uninstalling Agent Mesh from $(KFP_NAMESPACE)"; \
	echo "==> Stopping upload, pipeline, and ad-hoc Jobs..."; \
	for resource in $$(oc get job,configmap -n "$(KFP_NAMESPACE)" -o name 2>/dev/null || true); do \
		case "$$resource" in \
			job.batch/upload-*|job.batch/run-pipelines|job.batch/run-adhoc-query-*|job.batch/cu-pipeline-*|job.batch/cu-query-*|configmap/adhoc-query-*|configmap/cu-repos-*) \
				oc delete "$$resource" -n "$(KFP_NAMESPACE)" --ignore-not-found \
					--wait=true --timeout="$(WAIT_TIMEOUT)";; \
		esac; \
	done; \
	echo "==> Removing Agent Mesh Kubeflow pipeline runs..."; \
	for workflow in $$(oc get workflows.argoproj.io -n "$(KFP_NAMESPACE)" -o name 2>/dev/null || true); do \
		case "$${workflow#*/}" in \
			single-repo-pipeline-*|multi-repo-pipeline-*) \
				oc delete "$$workflow" -n "$(KFP_NAMESPACE)" \
					--cascade=foreground --wait=true --timeout="$(WAIT_TIMEOUT)";; \
		esac; \
	done; \
	echo "==> Removing Helm releases..."; \
	helm uninstall e5-mistral -n "$(KFP_NAMESPACE)" \
		--ignore-not-found --cascade foreground --wait --timeout "$(WAIT_TIMEOUT)"; \
	helm uninstall agent-mesh-for-sw -n "$(KFP_NAMESPACE)" \
		--ignore-not-found --cascade foreground --wait --timeout "$(WAIT_TIMEOUT)"; \
	echo "==> Removing non-Helm resources..."; \
	oc delete \
		deployment/code-understanding-console-plugin \
		deployment/code-understanding-plugin-api \
		service/code-understanding-console-plugin \
		service/code-understanding-plugin-api \
		route.route.openshift.io/code-understanding-plugin-api \
		configmap/code-understanding-console-plugin-config \
		configmap/code-understanding-job-scripts \
		-n "$(KFP_NAMESPACE)" --ignore-not-found \
		--wait=true --timeout="$(WAIT_TIMEOUT)"; \
	oc delete imagestream -n "$(KFP_NAMESPACE)" \
		-l "app.kubernetes.io/part-of=agent-mesh-for-sw,agent-mesh.redhat.com/owner-namespace=$(KFP_NAMESPACE)" \
		--ignore-not-found --wait=true --timeout="$(WAIT_TIMEOUT)"; \
	oc delete secret git-credentials code-understanding-env \
		-n "$(KFP_NAMESPACE)" --ignore-not-found \
		--wait=true --timeout="$(WAIT_TIMEOUT)"; \
	oc delete pvc mariadb-dspa -n "$(KFP_NAMESPACE)" \
		--ignore-not-found --wait=true --timeout="$(WAIT_TIMEOUT)"; \
	if [ -n "$(OTEL_NAMESPACE)" ]; then \
		oc delete job -n "$(OTEL_NAMESPACE)" \
			-l "app.kubernetes.io/part-of=agent-mesh-for-sw,agent-mesh.redhat.com/owner-namespace=$(KFP_NAMESPACE)" \
			--ignore-not-found --wait=true --timeout="$(WAIT_TIMEOUT)"; \
		if [ -n "$(OTEL_SERVICE_NAME)" ]; then \
			for pvc in $$(oc get pvc -n "$(OTEL_NAMESPACE)" -o name 2>/dev/null || true); do \
				case "$${pvc#*/}" in data-tempo-"$(OTEL_SERVICE_NAME)"-ingester-*) \
					oc delete "$$pvc" -n "$(OTEL_NAMESPACE)" --ignore-not-found \
						--wait=true --timeout="$(WAIT_TIMEOUT)";; \
				esac; \
			done; \
		fi; \
	fi; \
	echo "==> Agent Mesh uninstall complete. Namespace $(KFP_NAMESPACE) was preserved."

deploy-embedding-model:
	@echo "==> Deploying e5-mistral embedding model..." && \
		helm upgrade --install e5-mistral resources/helm/e5-mistral \
			--namespace "$(KFP_NAMESPACE)" \
			--create-namespace && \
		echo "==> Waiting for e5-mistral deployment..." && \
		oc rollout status deployment/e5-mistral -n "$(KFP_NAMESPACE)" \
			--timeout="$(WAIT_TIMEOUT)"

prepare-workbench-images:
	@set -e; \
		echo "==> Registering project workbench images with OpenShift AI..."; \
		IMAGESTREAMS="$$(helm template agent-mesh-for-sw resources/helm \
			--namespace "$(KFP_NAMESPACE)" \
			--set "namespace=$(KFP_NAMESPACE)" \
			--set imageStreams.enabled=true \
			--set "imageStreams.namespace=$(KFP_NAMESPACE)" \
			$(HELM_WORKFLOW_IMAGE_ARGS) \
			-s templates/workbench-imagestreams.yaml | \
			oc apply -f - -o name)"; \
		echo "==> Waiting for project workbench images to import..."; \
		oc wait -n "$$KFP_NAMESPACE" \
			--for=jsonpath='{.status.tags[0].items[0].image}' \
			--timeout="$(WAIT_TIMEOUT)" $$IMAGESTREAMS

deploy-notebooks: prepare-workbench-images
	@set -e; \
		echo "==> Waiting for DSPA to be fully reconciled..." && \
		oc wait datasciencepipelinesapplication/dspa -n "$(KFP_NAMESPACE)" \
			--for=create --timeout="$(WAIT_TIMEOUT)" && \
		oc wait datasciencepipelinesapplication/dspa -n "$(KFP_NAMESPACE)" \
			--for=condition=Ready --timeout="$(WAIT_TIMEOUT)" && \
		\
		echo "==> Deploying notebooks..." && \
		helm upgrade $(HELM_UPGRADE_ARGS) \
			--set requester="$$(oc whoami)" \
			$(HELM_REPO_ARGS) \
			$(HELM_WORKFLOW_IMAGE_ARGS) \
			--set imageStreams.namespace="$(KFP_NAMESPACE)" \
			--set deployNotebooks=true

apply-secrets:
	@[ -n "$(AWS_ACCESS_KEY_ID)" ] || { echo "AWS_ACCESS_KEY_ID must be set" >&2; exit 1; }; \
	[ -n "$(AWS_SECRET_ACCESS_KEY)" ] || { echo "AWS_SECRET_ACCESS_KEY must be set" >&2; exit 1; }; \
	[ -n "$(AWS_S3_BUCKET)" ] || { echo "AWS_S3_BUCKET must be set" >&2; exit 1; }; \
	if [ "$(DEPLOY_EMBEDDING_MODEL)" = "true" ]; then \
		: "$${EMBED_LLM_TOKEN:=dummy}"; \
		: "$${EMBED_LLM_API_BASE:=http://e5-mistral:8000/v1}"; \
		: "$${EMBED_LLM_ID:=intfloat/e5-mistral-7b-instruct}"; \
		: "$${EMBED_LLM_PROVIDER:=openai}"; \
		: "$${EMBED_LLM_PROVIDER_SETTINGS_XML:=openai}"; \
		export EMBED_LLM_TOKEN EMBED_LLM_API_BASE EMBED_LLM_ID EMBED_LLM_PROVIDER EMBED_LLM_PROVIDER_SETTINGS_XML; \
	fi && \
	\
	echo "==> Applying git-credentials secret..." && \
	oc create secret generic git-credentials \
		--from-literal=GIT_USERNAME="$(GIT_USERNAME)" \
		--from-literal=GIT_TOKEN="$(GIT_TOKEN)" \
		-n $(KFP_NAMESPACE) --dry-run=client -o yaml | oc apply -f - && \
	\
	echo "==> Recreating secret code-understanding-env..." && \
	SECRET_ENV_FILE=$$(mktemp) && \
	trap 'rm -f "$$SECRET_ENV_FILE"' 0 && \
	for key in $(SECRET_ENV_VARS); do \
		if printenv "$$key" >/dev/null 2>&1; then \
			printf '%s=' "$$key" >> "$$SECRET_ENV_FILE"; \
			printenv "$$key" >> "$$SECRET_ENV_FILE"; \
		fi; \
	done && \
	oc delete secret code-understanding-env -n $(KFP_NAMESPACE) --ignore-not-found=true \
		--wait=true --timeout="$(WAIT_TIMEOUT)" && \
	oc create secret generic code-understanding-env --from-env-file "$$SECRET_ENV_FILE" -n $(KFP_NAMESPACE) && \
	\
	REPO_LIST="$(GIT_REPO_LIST)" && \
	if [ -n "$(PIPELINE_GIT_REPO_LIST)" ] && [ -f "$(PIPELINE_GIT_REPO_LIST)" ]; then \
		echo "==> PIPELINE_GIT_REPO_LIST is set, using instead of GIT_REPO_LIST"; \
		REPO_LIST="$(PIPELINE_GIT_REPO_LIST)"; \
	fi && \
	if [ -n "$$REPO_LIST" ] && [ -f "$$REPO_LIST" ]; then \
		oc set data secret/code-understanding-env -n $(KFP_NAMESPACE) \
			--from-file=GIT_REPO_LIST_CONTENTS="$$REPO_LIST"; \
	fi && \
	oc patch secret code-understanding-env -n $(KFP_NAMESPACE) \
		--type=merge \
		-p '{"stringData":{"MLFLOW_NAMESPACE":"$(KFP_NAMESPACE)"}}' && \
	if [ -n "$(GATEWAY_HOST)" ]; then \
		echo "==> Patching MLFLOW_TRACKING_URI with external gateway URL..." && \
		oc patch secret code-understanding-env -n $(KFP_NAMESPACE) \
			--type=merge \
			-p "{\"stringData\":{\"MLFLOW_TRACKING_URI\":\"https://$(GATEWAY_HOST)/mlflow\"}}"; \
	fi

# ============================================================================
# Testing
# ============================================================================

helm-dependencies:
	helm dependency update $(CHART_DIR)

helm-lint: helm-dependencies
	helm lint $(CHART_DIR)

helm-template: helm-dependencies
	@VERIFY_NAMESPACE="$(or $(NAMESPACE),$(KFP_NAMESPACE),demo)"; \
	helm template $(RELEASE) $(CHART_DIR) \
		--namespace "$$VERIFY_NAMESPACE" \
		--set-string "namespace=$$VERIFY_NAMESPACE"

verify-secrets:
	@if git grep -nE '(AWS_SECRET_ACCESS_KEY|GIT_TOKEN|[A-Z0-9_]+_(API_KEY|TOKEN))=[^<[:space:]"$$]' \
		-- ':!.env.template'; then \
		echo "Error: possible plaintext secret found in a tracked file." >&2; \
		exit 1; \
	fi
	@echo "Tracked-file secret scan passed."

verify-deploy: verify-secrets
	@set -eu; \
	VERIFY_NAMESPACE="$(or $(NAMESPACE),$(KFP_NAMESPACE))"; \
	: "$${VERIFY_NAMESPACE:?Set NAMESPACE or KFP_NAMESPACE}"; \
	echo "==> Verifying Helm release $(RELEASE) in $$VERIFY_NAMESPACE..."; \
	helm status $(RELEASE) -n "$$VERIFY_NAMESPACE" >/dev/null; \
	STORAGE_VALUES=$$(helm get values $(RELEASE) -n "$$VERIFY_NAMESPACE" --all -o json); \
	STORAGE_NAME=$$(printf '%s' "$$STORAGE_VALUES" | jq -er '."aws-compatible-storage".fullnameOverride | select(type == "string" and length > 0)'); \
	STORAGE_SECRET=$$(printf '%s' "$$STORAGE_VALUES" | jq -r '."aws-compatible-storage".s3.existingSecret // empty'); \
	STORAGE_SECRET=$${STORAGE_SECRET:-$$STORAGE_NAME-credentials}; \
	STORAGE_HEALTH_PORT=$$(printf '%s' "$$STORAGE_VALUES" | jq -er '."aws-compatible-storage".service.port // 5000'); \
	echo "==> Waiting for aws-compatible-storage ($$STORAGE_NAME)..."; \
	oc rollout status "deployment/$$STORAGE_NAME" -n "$$VERIFY_NAMESPACE" --timeout="$(WAIT_TIMEOUT)"; \
	STORAGE_SECRET_STATE=$$(oc get secret "$$STORAGE_SECRET" -n "$$VERIFY_NAMESPACE" \
		-o go-template='{{if and .data.AWS_ACCESS_KEY_ID .data.AWS_SECRET_ACCESS_KEY}}configured{{else}}missing{{end}}'); \
	[ "$$STORAGE_SECRET_STATE" = configured ] || { echo "Error: storage credentials are missing." >&2; exit 1; }; \
	VERIFY_POD="storage-health-$$(date +%s)"; \
	oc run "$$VERIFY_POD" -n "$$VERIFY_NAMESPACE" --rm --attach=true --restart=Never \
		--pod-running-timeout="$(WAIT_TIMEOUT)" \
		--image=image-registry.openshift-image-registry.svc:5000/openshift/cli:latest \
		--command -- curl -fsS --connect-timeout 10 --max-time 60 "http://$$STORAGE_NAME:$$STORAGE_HEALTH_PORT/api" >/dev/null; \
	echo "==> Waiting for the OpenShift AI pipeline server..."; \
	oc wait datasciencepipelinesapplication/dspa -n "$$VERIFY_NAMESPACE" \
		--for=condition=Ready --timeout="$(WAIT_TIMEOUT)"; \
	oc rollout status deployment/ds-pipeline-dspa -n "$$VERIFY_NAMESPACE" \
		--timeout="$(WAIT_TIMEOUT)"; \
	if [ "$(DEPLOY_EMBEDDING_MODEL)" = true ]; then \
		echo "==> Verifying embedding-model release..."; \
		helm status e5-mistral -n "$$VERIFY_NAMESPACE" >/dev/null; \
	fi; \
	if [ "$(DEPLOY_OTEL)" = true ]; then \
		[ -n "$(OTEL_NAMESPACE)" ] || { echo "OTEL_NAMESPACE must be set" >&2; exit 1; }; \
		[ -n "$(OTEL_SERVICE_NAME)" ] || { echo "OTEL_SERVICE_NAME must be set" >&2; exit 1; }; \
		echo "==> Verifying OpenTelemetry and Tempo resources..."; \
		oc get opentelemetrycollector "$(OTEL_SERVICE_NAME)" -n "$(OTEL_NAMESPACE)" >/dev/null; \
		oc get tempostack "$(OTEL_SERVICE_NAME)" -n "$(OTEL_NAMESPACE)" >/dev/null; \
	fi; \
	echo "verify-deploy: PASS namespace=$$VERIFY_NAMESPACE release=$(RELEASE)"

test-ui:
	@echo "==> Running UI tests..."
	uv run --project ui --frozen pytest ui/tests

test-workflows:
	@echo "==> Running workflow pipeline tests..."
	uv run --project workflows/examples/code_understanding --group test --frozen \
		pytest tests/workflows

test-all: test-ui test-workflows

# ============================================================================
# Utility commands
# ============================================================================

format:
	@echo "==> Sorting Python imports with isort..."
	uv run --project ui --frozen isort --settings-path ui/pyproject.toml --skip-glob '*/.venv/*' .
	@echo "==> Formatting Python code with Black..."
	uv run --project ui --frozen black --config ui/pyproject.toml --extend-exclude '/\.venv/' .
	@echo "==> Formatting completed successfully."

lint:
	@echo "==> Running Flake8..."
	uv run --project ui --frozen flake8 --extend-exclude=.venv --max-line-length=99 --extend-ignore=E203,W503 .
	@echo "==> Checking Python formatting with Black..."
	uv run --project ui --frozen black --config ui/pyproject.toml --extend-exclude '/\.venv/' --check --diff .
	@echo "==> Checking Python import sorting with isort..."
	uv run --project ui --frozen isort --settings-path ui/pyproject.toml --skip-glob '*/.venv/*' --check-only --diff .
	@echo "==> Lint checks completed successfully."

# ============================================================================
# Container images
# ============================================================================

# Build or push one image by selecting its variable names and build context.
_build-one-image:
	@if [ -f "$(ENV_FILE)" ]; then set -a && . "$(ENV_FILE)" && set +a; fi && \
	REGISTRY="$(REGISTRY)" && \
	VERSION="$(VERSION)" && \
	: "$${REGISTRY:=$$KFP_IMAGE_REGISTRY}" && \
	: "$${REGISTRY:?Set REGISTRY or KFP_IMAGE_REGISTRY}" && \
	IMAGE_NAME="$$(printenv "$(IMAGE_NAME_VAR)")" && \
	IMAGE_TAG="$${VERSION:-$$(printenv "$(IMAGE_TAG_VAR)")}" && \
	: "$${IMAGE_NAME:?Set $(IMAGE_NAME_VAR) in $(ENV_FILE)}" && \
	: "$${IMAGE_TAG:?Set VERSION or $(IMAGE_TAG_VAR) in $(ENV_FILE)}" && \
	IMAGE="$$REGISTRY/$$IMAGE_NAME:$$IMAGE_TAG" && \
	if [ -n "$(SKIP_IF_NAME_VAR)" ]; then \
		OTHER_NAME="$$(printenv "$(SKIP_IF_NAME_VAR)")" && \
		OTHER_TAG="$${VERSION:-$$(printenv "$(SKIP_IF_TAG_VAR)")}" && \
		if [ "$$IMAGE" = "$$REGISTRY/$$OTHER_NAME:$$OTHER_TAG" ]; then \
			echo "==> Skipping duplicate image build: $$IMAGE"; exit 0; \
		fi; \
	fi && \
	echo "==> Building image: $$IMAGE" && \
	$(IMAGE_BUILD) -t "$$IMAGE" -f "$(IMAGE_FILE)" "$(IMAGE_CONTEXT)"

_push-one-image:
	@if [ -f "$(ENV_FILE)" ]; then set -a && . "$(ENV_FILE)" && set +a; fi && \
	REGISTRY="$(REGISTRY)" && \
	VERSION="$(VERSION)" && \
	: "$${REGISTRY:=$$KFP_IMAGE_REGISTRY}" && \
	: "$${REGISTRY:?Set REGISTRY or KFP_IMAGE_REGISTRY}" && \
	IMAGE_NAME="$$(printenv "$(IMAGE_NAME_VAR)")" && \
	IMAGE_TAG="$${VERSION:-$$(printenv "$(IMAGE_TAG_VAR)")}" && \
	: "$${IMAGE_NAME:?Set $(IMAGE_NAME_VAR) in $(ENV_FILE)}" && \
	: "$${IMAGE_TAG:?Set VERSION or $(IMAGE_TAG_VAR) in $(ENV_FILE)}" && \
	IMAGE="$$REGISTRY/$$IMAGE_NAME:$$IMAGE_TAG" && \
	if [ -n "$(SKIP_IF_NAME_VAR)" ]; then \
		OTHER_NAME="$$(printenv "$(SKIP_IF_NAME_VAR)")" && \
		OTHER_TAG="$${VERSION:-$$(printenv "$(SKIP_IF_TAG_VAR)")}" && \
		if [ "$$IMAGE" = "$$REGISTRY/$$OTHER_NAME:$$OTHER_TAG" ]; then \
			echo "==> Skipping duplicate image push: $$IMAGE"; exit 0; \
		fi; \
	fi && \
	echo "==> Pushing image: $$IMAGE" && \
	$(IMAGE_PUSH) "$$IMAGE"

build-data-generation-image:
	@$(MAKE) --no-print-directory _build-one-image \
		IMAGE_NAME_VAR=KFP_DATA_GENERATION_BASE_IMAGE_NAME \
		IMAGE_TAG_VAR=KFP_DATA_GENERATION_BASE_IMAGE_TAG \
		IMAGE_FILE=resources/images/data-generation/Containerfile \
		IMAGE_CONTEXT=resources/images/data-generation

push-data-generation-image:
	@$(MAKE) --no-print-directory _push-one-image \
		IMAGE_NAME_VAR=KFP_DATA_GENERATION_BASE_IMAGE_NAME \
		IMAGE_TAG_VAR=KFP_DATA_GENERATION_BASE_IMAGE_TAG

build-data-indexing-image:
	@$(MAKE) --no-print-directory _build-one-image \
		IMAGE_NAME_VAR=KFP_INDEXING_BASE_IMAGE_NAME \
		IMAGE_TAG_VAR=KFP_INDEXING_BASE_IMAGE_TAG \
		IMAGE_FILE=resources/images/data-indexing/Containerfile \
		IMAGE_CONTEXT=resources/images/data-indexing

push-data-indexing-image:
	@$(MAKE) --no-print-directory _push-one-image \
		IMAGE_NAME_VAR=KFP_INDEXING_BASE_IMAGE_NAME \
		IMAGE_TAG_VAR=KFP_INDEXING_BASE_IMAGE_TAG

build-data-analysis-image:
	@$(MAKE) --no-print-directory _build-one-image \
		IMAGE_NAME_VAR=KFP_ANALYSIS_BASE_IMAGE_NAME \
		IMAGE_TAG_VAR=KFP_ANALYSIS_BASE_IMAGE_TAG \
		SKIP_IF_NAME_VAR=KFP_INDEXING_BASE_IMAGE_NAME \
		SKIP_IF_TAG_VAR=KFP_INDEXING_BASE_IMAGE_TAG \
		IMAGE_FILE=resources/images/data-indexing/Containerfile \
		IMAGE_CONTEXT=resources/images/data-indexing

push-data-analysis-image:
	@$(MAKE) --no-print-directory _push-one-image \
		IMAGE_NAME_VAR=KFP_ANALYSIS_BASE_IMAGE_NAME \
		IMAGE_TAG_VAR=KFP_ANALYSIS_BASE_IMAGE_TAG \
		SKIP_IF_NAME_VAR=KFP_INDEXING_BASE_IMAGE_NAME \
		SKIP_IF_TAG_VAR=KFP_INDEXING_BASE_IMAGE_TAG

build-pipeline-tools-image:
	@$(MAKE) --no-print-directory _build-one-image \
		IMAGE_NAME_VAR=KFP_PIPELINE_TOOLS_IMAGE_NAME \
		IMAGE_TAG_VAR=KFP_PIPELINE_TOOLS_IMAGE_TAG \
		IMAGE_FILE=resources/images/pipeline-tools/Containerfile \
		IMAGE_CONTEXT=resources/images/pipeline-tools

push-pipeline-tools-image:
	@$(MAKE) --no-print-directory _push-one-image \
		IMAGE_NAME_VAR=KFP_PIPELINE_TOOLS_IMAGE_NAME \
		IMAGE_TAG_VAR=KFP_PIPELINE_TOOLS_IMAGE_TAG

build-console-app-image:
	@$(MAKE) --no-print-directory _build-one-image \
		IMAGE_NAME_VAR=CONSOLE_APP_IMAGE_NAME \
		IMAGE_TAG_VAR=CONSOLE_IMAGE_TAG \
		IMAGE_FILE=ui/Dockerfile \
		IMAGE_CONTEXT=.

push-console-app-image:
	@$(MAKE) --no-print-directory _push-one-image \
		IMAGE_NAME_VAR=CONSOLE_APP_IMAGE_NAME \
		IMAGE_TAG_VAR=CONSOLE_IMAGE_TAG

build-console-plugin-image:
	@$(MAKE) --no-print-directory _build-one-image \
		IMAGE_NAME_VAR=CONSOLE_PLUGIN_IMAGE_NAME \
		IMAGE_TAG_VAR=CONSOLE_IMAGE_TAG \
		IMAGE_FILE=console-plugin/Dockerfile \
		IMAGE_CONTEXT=console-plugin

push-console-plugin-image:
	@$(MAKE) --no-print-directory _push-one-image \
		IMAGE_NAME_VAR=CONSOLE_PLUGIN_IMAGE_NAME \
		IMAGE_TAG_VAR=CONSOLE_IMAGE_TAG

build-images: build-all-images push-all-images

build-all-images:
	@[ -n "$(or $(VERSION),$(CONSOLE_IMAGE_TAG))" ] || { echo "Set VERSION or CONSOLE_IMAGE_TAG to build console images" >&2; exit 1; }
	@echo "==> Building data generation image: $(DATAGEN_IMAGE)" && \
	$(IMAGE_BUILD) -t "$(DATAGEN_IMAGE)" -f resources/images/data-generation/Containerfile resources/images/data-generation && \
	echo "==> Building indexing image: $(INDEX_IMAGE)" && \
	$(IMAGE_BUILD) -t "$(INDEX_IMAGE)" -f resources/images/data-indexing/Containerfile resources/images/data-indexing && \
	if [ "$(ANALYSIS_IMAGE)" = "$(INDEX_IMAGE)" ]; then \
		echo "==> Skipping analysis image build; it uses the indexing image."; \
	else \
		echo "==> Building analysis image: $(ANALYSIS_IMAGE)" && \
		$(IMAGE_BUILD) -t "$(ANALYSIS_IMAGE)" -f resources/images/data-indexing/Containerfile resources/images/data-indexing; \
	fi && \
	echo "==> Building pipeline-tools image: $(PIPELINE_TOOLS_IMAGE)" && \
	$(IMAGE_BUILD) -t "$(PIPELINE_TOOLS_IMAGE)" -f resources/images/pipeline-tools/Containerfile resources/images/pipeline-tools && \
	echo "==> Building console application image: $(CONSOLE_APP_IMAGE)" && \
	$(IMAGE_BUILD) -t "$(CONSOLE_APP_IMAGE)" -f ui/Dockerfile . && \
	echo "==> Building console plugin image: $(CONSOLE_PLUGIN_IMAGE)" && \
	$(IMAGE_BUILD) -t "$(CONSOLE_PLUGIN_IMAGE)" -f console-plugin/Dockerfile console-plugin

push-all-images:
	@[ -n "$(or $(VERSION),$(CONSOLE_IMAGE_TAG))" ] || { echo "Set VERSION or CONSOLE_IMAGE_TAG to push console images" >&2; exit 1; }
	@echo "==> Pushing data generation image: $(DATAGEN_IMAGE)" && \
	$(IMAGE_PUSH) "$(DATAGEN_IMAGE)" && \
	echo "==> Pushing indexing image: $(INDEX_IMAGE)" && \
	$(IMAGE_PUSH) "$(INDEX_IMAGE)" && \
	if [ "$(ANALYSIS_IMAGE)" = "$(INDEX_IMAGE)" ]; then \
		echo "==> Skipping analysis image push; it uses the indexing image."; \
	else \
		echo "==> Pushing analysis image: $(ANALYSIS_IMAGE)" && \
		$(IMAGE_PUSH) "$(ANALYSIS_IMAGE)"; \
	fi && \
	echo "==> Pushing pipeline-tools image: $(PIPELINE_TOOLS_IMAGE)" && \
	$(IMAGE_PUSH) "$(PIPELINE_TOOLS_IMAGE)" && \
	echo "==> Pushing console application image: $(CONSOLE_APP_IMAGE)" && \
	$(IMAGE_PUSH) "$(CONSOLE_APP_IMAGE)" && \
	echo "==> Pushing console plugin image: $(CONSOLE_PLUGIN_IMAGE)" && \
	$(IMAGE_PUSH) "$(CONSOLE_PLUGIN_IMAGE)"

# ============================================================================
# Pipelines and assets
# ============================================================================

upload-pipelines:
	@set -e; \
	echo "==> Waiting for pipeline server to be ready..."; \
	oc wait deployment/ds-pipeline-dspa -n "$(KFP_NAMESPACE)" \
		--for=create --timeout="$(WAIT_TIMEOUT)"; \
	oc wait deployment/ds-pipeline-dspa -n "$(KFP_NAMESPACE)" \
		--for=condition=Available --timeout="$(WAIT_TIMEOUT)"; \
	\
	echo "==> Uploading Kubeflow pipelines..."; \
	oc delete job upload-kubeflow-pipelines -n "$(KFP_NAMESPACE)" --ignore-not-found=true \
		--wait=true --timeout="$(WAIT_TIMEOUT)"; \
	helm template agent-mesh-for-sw resources/helm \
		--set namespace="$(KFP_NAMESPACE)" \
		$(HELM_REPO_ARGS) \
		--set requester="$$(oc whoami)" \
		$(HELM_PIPELINE_TOOLS_ARGS) \
		-s templates/upload-pipelines-job.yaml | oc apply -n "$(KFP_NAMESPACE)" -f -; \
	echo "==> Waiting for pipeline upload to complete..."; \
	JOB_EXIT=0; \
	oc wait job/upload-kubeflow-pipelines -n "$(KFP_NAMESPACE)" \
		--for=condition=complete --timeout="$(WAIT_TIMEOUT)" || JOB_EXIT=$$?; \
	[ "$$JOB_EXIT" -eq 0 ] || { echo "Error: pipeline upload failed or timed out." >&2; exit "$$JOB_EXIT"; }

upload-mlflow-assets:
	@set -e; \
	echo "==> Deleting existing upload-assets job..."; \
	oc delete job upload-assets -n "$(KFP_NAMESPACE)" --ignore-not-found=true \
		--wait=true --timeout="$(WAIT_TIMEOUT)"; \
	\
	echo "==> Submitting upload-assets job..."; \
	helm template agent-mesh-for-sw resources/helm \
		--set namespace="$(KFP_NAMESPACE)" \
		$(HELM_REPO_ARGS) \
		--set requester="$$(oc whoami)" \
		$(HELM_PIPELINE_TOOLS_ARGS) \
		--set mlflowGatewayHost="$(GATEWAY_HOST)" \
		-s templates/upload-assets-job.yaml | oc apply -n "$(KFP_NAMESPACE)" -f -; \
	echo "==> Waiting for MLflow asset upload to complete..."; \
	JOB_EXIT=0; \
	oc wait job/upload-assets -n "$(KFP_NAMESPACE)" \
		--for=condition=complete --timeout="$(WAIT_TIMEOUT)" || JOB_EXIT=$$?; \
	[ "$$JOB_EXIT" -eq 0 ] || { echo "Error: MLflow asset upload failed or timed out." >&2; exit "$$JOB_EXIT"; }

upload-prebuilt-index:
	@set -e; \
	echo "==> Deleting existing prebuilt-index upload job..."; \
	oc delete job upload-prebuilt-index -n "$(KFP_NAMESPACE)" --ignore-not-found=true \
		--wait=true --timeout="$(WAIT_TIMEOUT)"; \
	\
	echo "==> Submitting prebuilt-index upload job..."; \
	helm template agent-mesh-for-sw resources/helm \
		--set namespace="$(KFP_NAMESPACE)" \
		$(HELM_REPO_ARGS) \
		--set requester="$$(oc whoami)" \
		$(HELM_PIPELINE_TOOLS_ARGS) \
		--set mlflowGatewayHost="$(GATEWAY_HOST)" \
		--set prebuiltIndex.enabled=true \
		-s templates/upload-prebuilt-index-job.yaml | oc apply -n "$(KFP_NAMESPACE)" -f -; \
	echo "==> Waiting for prebuilt-index upload to complete..."; \
	JOB_EXIT=0; \
	oc wait job/upload-prebuilt-index -n "$(KFP_NAMESPACE)" \
		--for=condition=complete --timeout="$(WAIT_TIMEOUT)" || JOB_EXIT=$$?; \
	[ "$$JOB_EXIT" -eq 0 ] || { echo "Error: prebuilt-index upload failed or timed out." >&2; exit "$$JOB_EXIT"; }

run-adhoc-query:
	@[ -z "$(QUESTION_FILE)" ] && { echo "Error: QUESTION_FILE is required: generate it via wrappers/adhoc.sh." >&2; exit 1; } || true
	@set -e; \
	JOB_ID="$$(date +%Y%m%d%H%M%S)$$(printf '%04x' $$((RANDOM)))"; \
	USE_GLOBAL=1 && \
	if [ -n "$(GIT_REPO)" ]; then USE_GLOBAL=0; fi && \
	\
	echo "==> Storing query parameters (job: $$JOB_ID)..." && \
	oc create configmap adhoc-query-$$JOB_ID \
		--from-file=question=$(QUESTION_FILE) \
		-n $(KFP_NAMESPACE) && \
	\
	echo "==> Submitting adhoc query job..." && \
	helm template agent-mesh-for-sw resources/helm \
		--set namespace="$(KFP_NAMESPACE)" \
		$(HELM_REPO_ARGS) \
		--set adhocQuery.run=true \
		--set-string adhocQuery.jobId="$$JOB_ID" \
		--set-string adhocQuery.useGlobal="$$USE_GLOBAL" \
		--set-string adhocQuery.gitRepo="$(GIT_REPO)" \
		--set-string adhocQuery.gitBranch="$(GIT_BRANCH)" \
		--set-string adhocQuery.retryCount="$${RETRY_COUNT:-3}" \
		--set analysis.image.registry="$(KFP_IMAGE_REGISTRY)" \
		--set analysis.image.name="$(KFP_ANALYSIS_BASE_IMAGE_NAME)" \
		--set analysis.image.tag="$(KFP_ANALYSIS_BASE_IMAGE_TAG)" \
		-s templates/run-adhoc-query-job.yaml | oc apply -n $(KFP_NAMESPACE) -f - && \
	\
	JOB_EXIT=0; \
	echo "==> Waiting for query to complete..."; \
	oc wait "job/run-adhoc-query-$$JOB_ID" -n "$(KFP_NAMESPACE)" \
		--for=condition=complete --timeout="$(ADHOC_TIMEOUT)" || JOB_EXIT=$$?; \
	oc delete configmap "adhoc-query-$$JOB_ID" -n "$(KFP_NAMESPACE)" --ignore-not-found=true \
		--wait=true --timeout="$(WAIT_TIMEOUT)" || [ "$$JOB_EXIT" -ne 0 ]; \
	[ "$$JOB_EXIT" -eq 0 ] || echo "Error: ad-hoc query failed or timed out." >&2; \
	exit "$$JOB_EXIT"

run-pipelines:
	@set -e; \
	if [ -n "$(PIPELINE_GIT_REPO)" ]; then \
		oc patch secret code-understanding-env -n $(KFP_NAMESPACE) \
			--type=merge -p '{"stringData":{"GIT_REPO":"$(PIPELINE_GIT_REPO)"}}'; \
	fi; \
	if [ -n "$(PIPELINE_GIT_BRANCH)" ]; then \
		oc patch secret code-understanding-env -n $(KFP_NAMESPACE) \
			--type=merge -p '{"stringData":{"GIT_BRANCH":"$(PIPELINE_GIT_BRANCH)"}}'; \
	fi; \
	echo "==> Submitting run-pipelines job..."; \
	oc delete job run-pipelines -n $(KFP_NAMESPACE) --ignore-not-found=true \
		--wait=true --timeout="$(WAIT_TIMEOUT)"; \
	helm template agent-mesh-for-sw resources/helm \
		--set namespace="$(KFP_NAMESPACE)" \
		$(HELM_REPO_ARGS) \
		--set runPipelines.run=true \
		--set-string runPipelines.args="$${ARGS:---single-repo}" \
		--set-string runPipelines.targetPath="$(KFP_DATA_GENERATION_OUTPUT_PATH)" \
		--set-string runPipelines.graphragSourcePath="$(KFP_DATA_INDEXING_OUTPUT_PATH)" \
		$(HELM_PIPELINE_TOOLS_ARGS) \
		-s templates/run-pipelines-job.yaml | oc apply -n $(KFP_NAMESPACE) -f -; \
	echo "==> Waiting for pipeline submission to complete..."; \
	JOB_EXIT=0; \
	oc wait job/run-pipelines -n "$(KFP_NAMESPACE)" \
		--for=condition=complete --timeout="$(WAIT_TIMEOUT)" || JOB_EXIT=$$?; \
	[ "$$JOB_EXIT" -eq 0 ] || { echo "Error: pipeline submission failed or timed out." >&2; exit "$$JOB_EXIT"; }

# ============================================================================
# Observability
# ============================================================================

deploy-otel:
	@if [ "$(DEPLOY_OTEL)" != "true" ]; then \
		echo "Skipping deploy-otel: set DEPLOY_OTEL=true to enable it."; \
		exit 0; \
	fi; \
	[ -n "$(OTEL_SERVICE_NAME)" ] || { echo "Error: OTEL_SERVICE_NAME is not set."; exit 1; }; \
	[ -n "$(OTEL_NAMESPACE)" ] || { echo "Error: OTEL_NAMESPACE or KFP_NAMESPACE is not set."; exit 1; }; \
	\
	echo "==> Checking for OpenTelemetry and Tempo CRDs..." && \
	if ! oc get crd opentelemetrycollectors.opentelemetry.io >/dev/null 2>&1 || \
	   ! oc get crd tempostacks.tempo.grafana.com >/dev/null 2>&1; then \
		echo "Skipping deploy-otel: OpenTelemetry and/or Tempo operators are not installed."; \
		exit 0; \
	fi && \
	\
	if [ "$(OTEL_NAMESPACE)" != "$(KFP_NAMESPACE)" ]; then \
		echo "==> Creating OTel namespace $(OTEL_NAMESPACE)..."; \
		oc create namespace $(OTEL_NAMESPACE) --dry-run=client -o yaml | oc apply -f -; \
	fi && \
	\
	echo "==> Deploying TempoStack and OpenTelemetry Collector..." && \
	helm upgrade $(HELM_UPGRADE_ARGS) \
		--set otel.namespace=$(OTEL_NAMESPACE) \
		--set otel.enabled=true \
		--set otel.name=$(OTEL_SERVICE_NAME) && \
	echo "==> Waiting for TempoStack and OpenTelemetry Collector..." && \
	oc wait tempostack/$(OTEL_SERVICE_NAME) -n "$(OTEL_NAMESPACE)" \
		--for=condition=Ready --timeout="$(WAIT_TIMEOUT)" && \
	oc wait deployment/$(OTEL_SERVICE_NAME)-collector -n "$(OTEL_NAMESPACE)" \
		--for=create --timeout="$(WAIT_TIMEOUT)" && \
	oc rollout status deployment/$(OTEL_SERVICE_NAME)-collector -n "$(OTEL_NAMESPACE)" \
		--timeout="$(WAIT_TIMEOUT)"

# ============================================================================
# Console application
# ============================================================================

apply-console-src:
	@echo "==> Publishing job scripts ConfigMap..." && \
	helm upgrade $(HELM_UPGRADE_ARGS) \
		--set console.jobScripts.enabled=true \
		--set-file console.jobScripts.runPipelines=workflows/examples/code_understanding/scripts/run_pipelines.sh \
		--set-file console.jobScripts.mlflowAssetLoader=workflows/examples/code_understanding/loaders/mlflow_asset_loader.py \
		--set-file console.jobScripts.defaultAssetLoader=workflows/examples/code_understanding/loaders/default_asset_loader.py

run-console-app:
	@AGENTMESH_REPO_URL="$(GIT_REPO_URL)" AGENTMESH_REPO_REF="$(GIT_REPO_BRANCH)" \
	KFP_NAMESPACE="$(KFP_NAMESPACE)" \
	uv run --project ui --frozen uvicorn --app-dir ui main:app --host 127.0.0.1 --port 8080

deploy-console-app:
	@[ -n "$(KFP_IMAGE_REGISTRY)" ] || { echo "KFP_IMAGE_REGISTRY must be set" >&2; exit 1; }; \
	[ -n "$(CONSOLE_IMAGE_TAG)" ] || { echo "CONSOLE_IMAGE_TAG must be set" >&2; exit 1; }; \
	echo "==> Deploying Code Understanding console..." && \
	helm upgrade $(HELM_UPGRADE_ARGS) \
		--set requester="$$(oc whoami)" \
		$(HELM_REPO_ARGS) \
		--set console.enabled=true \
		--set-string console.image="$(KFP_IMAGE_REGISTRY)/$(CONSOLE_APP_IMAGE_NAME):$(CONSOLE_IMAGE_TAG)" \
		--set console.jobScripts.enabled=true \
		--set-file console.jobScripts.runPipelines=workflows/examples/code_understanding/scripts/run_pipelines.sh \
		--set-file console.jobScripts.mlflowAssetLoader=workflows/examples/code_understanding/loaders/mlflow_asset_loader.py \
		--set-file console.jobScripts.defaultAssetLoader=workflows/examples/code_understanding/loaders/default_asset_loader.py && \
	oc rollout status deployment/code-understanding-console -n $(KFP_NAMESPACE) --timeout="$(WAIT_TIMEOUT)" && \
	ROUTE_HOST="$$(oc get route code-understanding-console -n $(KFP_NAMESPACE) -o jsonpath='{.spec.host}')" && \
	echo "" && \
	echo "==> Open the console in your browser:" && \
	echo "    https://$$ROUTE_HOST" && \
	echo "" && \
	echo "    Namespace access is enough; this is a Kubernetes Deployment, not an OpenShift console plugin." && \
	echo "    Or run: make port-forward-console-app  then open http://localhost:8080" && \
	echo ""

port-forward-console-app:
	@echo "==> Forwarding http://localhost:8080 -> code-understanding-console:8080" && \
	oc port-forward svc/code-understanding-console 8080:8080 -n $(KFP_NAMESPACE)

test-ui-install:
	@echo "==> Installing Playwright and Chromium for UI smoke tests..."
	$(E2E_UI_INSTALL_CMD)

test-ui:
	@set -eu; \
	KFP_NAMESPACE="$(KFP_NAMESPACE)"; export KFP_NAMESPACE; \
	: "$${KFP_NAMESPACE:?ERROR: set KFP_NAMESPACE in the environment or pass KFP_NAMESPACE=<namespace> to make}"; \
	echo "==> Checking deployed Code Understanding console in namespace $$KFP_NAMESPACE..."; \
	oc get deployment code-understanding-console -n "$$KFP_NAMESPACE" >/dev/null; \
	oc rollout status deployment/code-understanding-console -n "$$KFP_NAMESPACE" --timeout=300s; \
	ROUTE_HOST="$$(oc get route code-understanding-console -n "$$KFP_NAMESPACE" -o jsonpath='{.spec.host}')"; \
	if [ -z "$$ROUTE_HOST" ]; then echo "ERROR: Route code-understanding-console has no host in namespace $$KFP_NAMESPACE." >&2; exit 1; fi; \
	if [ -z "$$UI_URL" ]; then export UI_URL="https://$$ROUTE_HOST"; fi; \
	export KFP_NAMESPACE; \
	echo "==> Testing console UI at $$UI_URL"; \
	$(MAKE) test-ui-install; \
	$(E2E_UI_TEST_CMD)

# ============================================================================
# OpenShift console plugin
# ============================================================================

apply-plugin-src:
	@echo "==> Publishing plugin job scripts ConfigMap..." && \
	oc create configmap code-understanding-job-scripts \
		--from-file=run_pipelines.sh=workflows/examples/code_understanding/scripts/run_pipelines.sh \
		--from-file=mlflow_asset_loader.py=workflows/examples/code_understanding/loaders/mlflow_asset_loader.py \
		--from-file=default_asset_loader.py=workflows/examples/code_understanding/loaders/default_asset_loader.py \
		-n $(KFP_NAMESPACE) --dry-run=client -o yaml | oc apply -f -

deploy-console-plugin: apply-plugin-src
	@[ -n "$(KFP_IMAGE_REGISTRY)" ] || { echo "KFP_IMAGE_REGISTRY must be set" >&2; exit 1; }; \
	[ -n "$(CONSOLE_IMAGE_TAG)" ] || { echo "CONSOLE_IMAGE_TAG must be set" >&2; exit 1; }; \
	CONSOLE_HOST="$$(oc get route console -n openshift-console -o jsonpath='{.spec.host}')" && \
	CLUSTER_DOMAIN="$$(oc get ingress.config cluster -o jsonpath='{.spec.domain}')" && \
	echo "==> Deploying OpenShift console plugin and FastAPI backend..." && \
	helm template agent-mesh-for-sw resources/helm \
		--set namespace="$(KFP_NAMESPACE)" \
		$(HELM_REPO_ARGS) \
		--set clusterDomain="$$CLUSTER_DOMAIN" \
		--set consolePlugin.enabled=true \
		--set-string consolePlugin.image="$(KFP_IMAGE_REGISTRY)/$(CONSOLE_PLUGIN_IMAGE_NAME):$(CONSOLE_IMAGE_TAG)" \
		--set-string consolePlugin.apiImage="$(KFP_IMAGE_REGISTRY)/$(CONSOLE_APP_IMAGE_NAME):$(CONSOLE_IMAGE_TAG)" \
		--set consolePlugin.consoleBaseUrl="https://$$CONSOLE_HOST" \
		-s templates/console-plugin.yaml | oc apply -f - && \
	echo "==> Waiting for plugin-api Route hostname to be assigned..." && \
	oc wait route/code-understanding-plugin-api -n "$(KFP_NAMESPACE)" \
		--for=jsonpath='{.spec.host}' --timeout="$(WAIT_TIMEOUT)" && \
	API_HOST="$$(oc get route code-understanding-plugin-api -n $(KFP_NAMESPACE) -o jsonpath='{.spec.host}')" && \
	helm template agent-mesh-for-sw resources/helm \
		--set namespace="$(KFP_NAMESPACE)" \
		$(HELM_REPO_ARGS) \
		--set clusterDomain="$$CLUSTER_DOMAIN" \
		--set consolePlugin.enabled=true \
		--set-string consolePlugin.image="$(KFP_IMAGE_REGISTRY)/$(CONSOLE_PLUGIN_IMAGE_NAME):$(CONSOLE_IMAGE_TAG)" \
		--set-string consolePlugin.apiImage="$(KFP_IMAGE_REGISTRY)/$(CONSOLE_APP_IMAGE_NAME):$(CONSOLE_IMAGE_TAG)" \
		--set consolePlugin.consoleBaseUrl="https://$$CONSOLE_HOST" \
		--set consolePlugin.apiRouteHost="$$API_HOST" \
		-s templates/console-plugin.yaml | oc apply -f - && \
	oc rollout restart deployment/code-understanding-console-plugin -n $(KFP_NAMESPACE) && \
	oc rollout restart deployment/code-understanding-plugin-api -n $(KFP_NAMESPACE) && \
	oc rollout status deployment/code-understanding-console-plugin -n $(KFP_NAMESPACE) --timeout="$(WAIT_TIMEOUT)" && \
	oc rollout status deployment/code-understanding-plugin-api -n $(KFP_NAMESPACE) --timeout="$(WAIT_TIMEOUT)" && \
	$(MAKE) enable-console-plugin

enable-console-plugin:
	@echo "==> Enabling code-understanding-console in OpenShift console..." && \
	EXISTING="$$(oc get consoles.operator.openshift.io cluster -o jsonpath='{.spec.plugins}' 2>/dev/null)" && \
	if echo "$$EXISTING" | grep -q 'code-understanding-console'; then \
	  echo "Plugin already enabled."; \
	else \
	  CONSOLE_GENERATION="$$(oc patch consoles.operator.openshift.io cluster --type=json \
	    -p='[{"op":"add","path":"/spec/plugins/-","value":"code-understanding-console"}]' \
	    -o jsonpath='{.metadata.generation}')" && \
	  echo "==> Waiting for the OpenShift console to load the plugin..." && \
	  oc wait consoles.operator.openshift.io/cluster \
	    --for=jsonpath='{.status.observedGeneration}'="$$CONSOLE_GENERATION" \
	    --timeout="$(WAIT_TIMEOUT)"; \
	fi && \
	oc rollout status deployment/console -n openshift-console --timeout="$(WAIT_TIMEOUT)" && \
	CONSOLE_HOST="$$(oc get route console -n openshift-console -o jsonpath='{.spec.host}')" && \
	echo "" && \
	echo "==> Open in OpenShift console:" && \
	echo "    https://$$CONSOLE_HOST/code-understanding" && \
	echo "    Application launcher: Code Understanding" && \
	echo ""
