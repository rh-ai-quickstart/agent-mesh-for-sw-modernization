#################################
# HuggingFace: `https://huggingface.co/RedHatAI/Muse-Glimmer-30B-FP8-block`
# vLLM version: `v0.31.0`
# Sample RHOAI Deployment on L40S:
#################################
```
---
apiVersion: serving.kserve.io/v1alpha1
kind: ServingRuntime
metadata:
  annotations:
    opendatahub.io/recommended-accelerators: '["nvidia.com/gpu"]'
    openshift.io/display-name: vLLM ServingRuntime for Muse-Glimmer
  labels:
    opendatahub.io/dashboard: "true"
  name: vllm-cuda-runtime-muse-glimmer
  namespace: test
spec:
  annotations:
    opendatahub.io/kserve-runtime: vllm
    prometheus.io/path: /metrics
    prometheus.io/port: "8080"
  containers:
  - args:
    - --port=8080
    - --model=/mnt/models
    - --served-model-name={{.Name}}
    command:
    - python3
    - -m
    - vllm.entrypoints.openai.api_server
    env:
    - name: HF_HOME
      value: /tmp/hf_home
    - name: TRITON_CACHE_DIR
      value: /tmp/triton_cache
    - name: HOME
      value: /tmp
    - name: FLASHINFER_WORKSPACE_DIR
      value: /tmp/flashinfer
    - name: XDG_CACHE_HOME
      value: /tmp/.cache
    - name: XDG_CONFIG_HOME
      value: /tmp/.config
    image: <path to vllm-openai-muse-glimmer image>
    name: kserve-container
    ports:
    - containerPort: 8080
      protocol: TCP
    securityContext:
      runAsNonRoot: true
  multiModel: false
  supportedModelFormats:
  - autoSelect: true
    name: vLLM
---
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  annotations:
    modelFormat: vLLM
    opendatahub.io/hardware-profile-name: gpu-profile
    opendatahub.io/hardware-profile-namespace: redhat-ods-applications
    opendatahub.io/model-type: generative
    openshift.io/display-name: muse-glimmer-30b
    security.opendatahub.io/enable-auth: "true"
    serving.kserve.io/deploymentMode: Standard
  labels:
    networking.kserve.io/visibility: exposed
    opendatahub.io/dashboard: "true"
  name: muse-glimmer-30b
  namespace: test
spec:
  predictor:
    automountServiceAccountToken: false
    deploymentStrategy:
      type: RollingUpdate
    imagePullSecrets:
    - name: muse-glimmer-30b
    maxReplicas: 1
    minReplicas: 1
    model:
      args:
      - --enable-auto-tool-choice
      - --tool-call-parser=muse_glimmer
      - --reasoning-parser=muse_glimmer
      - --generation-config=auto
      - --max-model-len=131072
      env:
      - name: VLLM_ALLOW_LONG_MAX_MODEL_LEN
        value: "1"
      modelFormat:
        name: vLLM
      name: ""
      protocolVersion: v2
      resources:
        limits:
          cpu: "2"
          memory: 8Gi
          nvidia.com/gpu: "1"
        requests:
          cpu: "1"
          memory: 4Gi
          nvidia.com/gpu: "1"
      runtime: vllm-cuda-runtime-muse-glimmer
      storageUri: oci://<path-to-modelcar-redhatai-muse-glimmer-30b-fp8-block:3.0-1791282062>
    timeout: 600
---
apiVersion: v1
data:
  .dockerconfigjson: <'{}' (base64 encoded)>
  ACCESS_TYPE: <'Pull' (base64 encoded)>
  OCI_HOST: <The Container Registry (base64 encoded)>
kind: Secret
metadata:
  annotations:
    opendatahub.io/connection-type-protocol: oci
    opendatahub.io/connection-type-ref: oci-v1
    openshift.io/display-name: muse-glimmer-30b
  labels:
    opendatahub.io/dashboard: "true"
  name: muse-glimmer-30b
  namespace: test
type: kubernetes.io/dockerconfigjson
```