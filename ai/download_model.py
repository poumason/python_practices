from huggingface_hub import hf_hub_download, snapshot_download

REPO_ID = "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"

# hf_hub_download(repo_id=REPO_ID)

snapshot_download(repo_id=REPO_ID)