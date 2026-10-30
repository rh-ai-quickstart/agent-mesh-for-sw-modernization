# Agent model

Deploy Qwen3.5 9B FP8 Dynamic (default) or Muse Glimmer 30B FP8 with one chart.
The chart creates a KServe `ServingRuntime`, `InferenceService`, ServiceAccount,
and persistent model cache. KServe manages the Deployment and Services.

Requires OpenShift AI/KServe model serving, the NVIDIA device plugin, and a
compatible GPU node. Qwen requires a CUDA-compatible R580+ driver.


| Setting                        | `qwen` (default)                  | `muse-glimmer`                        |
| ------------------------------ | --------------------------------- | ------------------------------------- |
| Hugging Face model             | `RedHatAI/Qwen3.5-9B-FP8-dynamic` | `RedHatAI/Muse-Glimmer-30B-FP8-block` |
| GPU                            | One NVIDIA A10G                   | One NVIDIA L40S                       |
| vLLM image tag                 | `v0.27.1`                         | `muse-glimmer`                        |
| Context limit (input + output) | 16,384 tokens                     | 16,384 tokens                         |
| Host memory request / limit    | 20 GiB / 26 GiB                   | 32 GiB / 48 GiB                       |
| CPU request / limit            | 4 / 8                             | 4 / 8                                 |
| Node toleration                | `g5-gpu=true:NoSchedule`          | `g6e-gpu=true:NoSchedule`             |
| Shared memory                  | 2 GiB                             | 8 GiB                                 |
| Tool / reasoning parser        | `qwen3_coder` / `qwen3`           | `muse_glimmer` / `muse_glimmer`       |


Both profiles use one GPU, tensor parallel size 1, and a 50 GiB ReadWriteOnce
cache using the cluster's default storage class. See [values.yaml](values.yaml)
for shared and profile defaults.
Qwen is text only, with eager execution, one concurrent sequence, and 1,024
batched tokens. Its image and model revision are pinned. On A10G, vLLM uses
weight-only FP8 with BF16 computation through Marlin. 

Run from the repository root. To install Qwen:

```sh
export NAMESPACE=your-model-project
helm upgrade --install agent-model resources/helm/agent-model \
  --namespace "$NAMESPACE" --create-namespace
```

To install Muse Glimmer instead:

```sh
helm upgrade --install agent-model resources/helm/agent-model \
  --namespace "$NAMESPACE" --create-namespace \
  --set modelVariant=muse-glimmer
```

`--set modelVariant=qwen` explicitly selects Qwen. Resource names use the Helm  
release name (`agent-model` above), so separate releases can deploy both models  
in one namespace.

Override profile settings through top-level values, for example
`--set model.maxModelLen=8192` or `--set resources.limits.memory=28Gi`.
Override `tolerations`, `nodeSelector`, and `cache.storageClassName` for your
cluster using `--set` or a values file. Top-level values take precedence over the
selected profile. The public models require no Hugging Face token; leave
`huggingFace.existingSecret` empty, or set it to a Secret containing `HF_TOKEN`.

The default deployment mode is `RawDeployment`. For KServe versions that use
`Standard`, add `--set serving.deploymentMode=Standard`.

The first startup downloads the weights; later starts reuse the cache. One
replica stays running. Recreate updates interrupt serving while the replacement
loads. Changing `modelVariant` on the same release updates the existing endpoint
and reuses its cache PVC. When switching profiles, use `--reset-values` and
reapply any desired overrides to avoid carrying previous overrides forward.

These resources use release-based names, unlike the previous standalone charts.
Existing installations of those charts are separate releases; this chart does
not automatically adopt their resources or cache PVCs.

Uninstall with `helm uninstall agent-model -n "$NAMESPACE"`; this deletes the
cache PVC.

Wait for readiness and get the endpoint:

```sh
oc wait --for=condition=Ready inferenceservice/agent-model \
  -n "$NAMESPACE" --timeout=60m
oc get inferenceservice agent-model -n "$NAMESPACE" \
  -o jsonpath='{.status.url}{"\n"}'
```

Append `/v1` for OpenAI clients and use the selected Hugging Face model ID from
the table above. Reachability depends on cluster routing. The vLLM container
has no API-key authentication by default.

For local access:

```sh
oc port-forward -n "$NAMESPACE" deployment/agent-model-predictor 8000:8000
```

Then, in another terminal, query the default Qwen model:

```sh
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"RedHatAI/Qwen3.5-9B-FP8-dynamic","messages":[{"role":"user","content":"Hello!"}],"max_tokens":512,"chat_template_kwargs":{"enable_thinking":false}}'
```

For Muse Glimmer, use `RedHatAI/Muse-Glimmer-30B-FP8-block` as the model ID
and omit `chat_template_kwargs`. Reasoning tokens count toward the output budget;
if `finish_reason` is `length` and `content` is empty, increase `max_tokens` or
(for Qwen) disable thinking as in the example above.