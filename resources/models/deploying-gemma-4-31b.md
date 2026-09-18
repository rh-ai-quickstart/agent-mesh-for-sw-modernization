#################################
# HuggingFace: `https://huggingface.co/RedHatAI/gemma-4-31B-it-NVFP4`
# Sample vLLM Deployment on H200:
#################################
```
pip install vllm==0.19.0 tqdm==4.67.3 jupyter==1.1.1 hf_transfer==0.1.9
pip install huggingface-hub==1.14.0 transformers==5.8.0
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