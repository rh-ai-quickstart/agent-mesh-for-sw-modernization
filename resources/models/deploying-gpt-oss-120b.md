#################################
# HuggingFace: `https://huggingface.co/RedHatAI/gpt-oss-120b`
# Sample vLLM Deployment on H100:
#################################
```
export HF_TOKEN=<your-huggingface-token>
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
nohup python3 -m vllm.entrypoints.openai.api_server \
    --model RedHatAI/gpt-oss-120b \
    --enable-auto-tool-choice \
    --tool-call-parser openai \
    --max-model-len 128000 \
    > vllm.log 2>&1 &
```
