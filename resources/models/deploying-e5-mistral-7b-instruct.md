#################################
# HuggingFace: `https://huggingface.co/intfloat/e5-mistral-7b-instruct`
# Sample vLLM Deployment on L40S:
#################################
```
export HF_TOKEN=<your-huggingface-token>
nohup python -m vllm.entrypoints.openai.api_server \
    --model=intfloat/e5-mistral-7b-instruct \
    --runner pooling \
    --dtype float16 \
    > vllm.log 2>&1 &
```


#################################
# Other
#################################
To deploy the embedding model as a standalone job, run `make deploy-embedding-model`.
