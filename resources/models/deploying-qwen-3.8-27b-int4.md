#################################
# HuggingFace: `https://huggingface.co/RedHatAI/Qwen3.8-27B-INT4`
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
    openshift.io/display-name: vLLM NVIDIA GPU ServingRuntime (Qwen3.5 compatible)
  labels:
    opendatahub.io/dashboard: "true"
  name: vllm-cuda-runtime-qwen3
  namespace: <namespace>
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
    image: <vllm-0.31.0-compatible-cuda-runtime-image>
    securityContext:
      runAsNonRoot: true
    name: kserve-container
    ports:
    - containerPort: 8080
      protocol: TCP
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
    opendatahub.io/connections: qwen38-27b
    opendatahub.io/hardware-profile-name: gpu-profile
    opendatahub.io/hardware-profile-namespace: redhat-ods-applications
    opendatahub.io/model-type: generative
    openshift.io/description: ""
    openshift.io/display-name: qwen38-27b
    security.opendatahub.io/enable-auth: "true"
    serving.kserve.io/deploymentMode: Standard
  labels:
    networking.kserve.io/visibility: exposed
    opendatahub.io/dashboard: "true"
  name: qwen38-27b
  namespace: <namespace>
spec:
  predictor:
    automountServiceAccountToken: false
    deploymentStrategy:
      type: RollingUpdate
    imagePullSecrets:
    - name: qwen38-27b
    maxReplicas: 1
    minReplicas: 1
    model:
      args:
      - --reasoning-parser=qwen3
      - --enable-auto-tool-choice
      - --tool-call-parser=qwen3_xml
      - --speculative-config
      - '{"method":"mtp","num_speculative_tokens":3}'
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
      runtime: vllm-cuda-runtime-qwen3
      storageUri: oci://quay.io/oawofolurh/qwen3.8-27b-int4:v1
    timeout: 30
```