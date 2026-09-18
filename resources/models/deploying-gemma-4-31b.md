#################################
# HuggingFace: `https://huggingface.co/RedHatAI/gemma-4-31B-it-NVFP4`
# Sample vLLM Deployment on H200:
#################################
```
wget -O chat_template.jinja https://huggingface.co/RedHatAI/gemma-4-31B-it-NVFP4/resolve/main/chat_template.jinja
nohup python3 -m vllm.entrypoints.openai.api_server \
     --model RedHatAI/gemma-4-31B-it-NVFP4 \
     --quantization fp8 \
     --kv-cache-dtype fp8 \
     --enable-auto-tool-choice \
     --reasoning-parser gemma4 \
     --tool-call-parser gemma4 \
     --chat-template chat_template.jinja \
     --gpu-memory-utilization 0.90 \
     --max-model-len 262144 \
      > vllm.log 2>&1 &
```