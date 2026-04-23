#!/usr/bin/env python3
"""
VRAM Calculator for Hugging Face LLM models.

Usage:
    python vram_calculator.py Qwen/Qwen3-30B
    python vram_calculator.py Qwen/Qwen3-30B --precision int4 --seq-len 8192
    python vram_calculator.py meta-llama/Llama-3.1-70B --batch-size 4
"""
import argparse
import math
import sys
from typing import Optional

import requests

PRECISION_BYTES: dict[str, float] = {
    "fp32": 4.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "int8": 1.0,
    "int4": 0.5,
    "nf4":  0.5,
}

GPUS = [
    ("RTX 3080",        10),
    ("RTX 3090 / 4090", 24),
    ("L40S",            48),
    ("A100 40GB",       40),
    ("A100 80GB",       80),
    ("H100 80GB",       80),
    ("H200 141GB",     141),
]


def fetch_hf_config(model_id: str, hf_token: Optional[str] = None) -> dict:
    url = f"https://huggingface.co/{model_id}/raw/main/config.json"
    print(url)
    headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"[error] Could not fetch config.json for '{model_id}' (HTTP {r.status_code})")
    return r.json()


def fetch_hf_num_params(model_id: str, hf_token: Optional[str] = None) -> Optional[int]:
    url = f"https://huggingface.co/api/models/{model_id}"
    headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    # safetensors metadata carries the total parameter count
    total = data.get("safetensors", {}).get("total")
    if total:
        return int(total)
    return None


def estimate_params_from_config(cfg: dict) -> int:
    """Rough estimate when the API doesn't expose a parameter count."""
    h = cfg.get("hidden_size", 0)
    layers = cfg.get("num_hidden_layers", 0)
    vocab = cfg.get("vocab_size", 0)
    intermediate = cfg.get("intermediate_size", h * 4)
    # embedding + attention + FFN per layer (simplified)
    per_layer = 4 * h * h + 2 * h * intermediate
    return vocab * h + layers * per_layer


def model_vram_gb(num_params: int, precision: str) -> float:
    return (num_params * PRECISION_BYTES[precision]) / (1024 ** 3)


def kv_cache_vram_gb(cfg: dict, seq_len: int, batch_size: int, precision: str) -> float:
    # KV cache is stored in fp16/bf16 regardless of weight precision
    kv_bytes = max(PRECISION_BYTES.get(precision, 2.0), 2.0)
    if precision in ("int4", "nf4", "int8"):
        kv_bytes = 2.0

    num_layers = cfg.get("num_hidden_layers", 0)
    num_kv_heads = cfg.get("num_key_value_heads") or cfg.get("num_attention_heads", 0)
    hidden_size = cfg.get("hidden_size", 0)
    num_attn_heads = cfg.get("num_attention_heads", 1)
    head_dim = cfg.get("head_dim") or (hidden_size // num_attn_heads if num_attn_heads else 0)

    # 2 tensors (K + V) × layers × kv_heads × head_dim × seq_len × batch
    total_bytes = 2 * num_layers * num_kv_heads * head_dim * seq_len * batch_size * kv_bytes
    return total_bytes / (1024 ** 3)


def is_moe(cfg: dict) -> bool:
    return "num_experts" in cfg or "num_local_experts" in cfg or cfg.get("model_type", "") in ("mixtral", "qwen_moe")


def active_params_fraction(cfg: dict) -> float:
    """For MoE: fraction of experts active per token."""
    total = cfg.get("num_experts") or cfg.get("num_local_experts")
    active = cfg.get("num_experts_per_tok") or cfg.get("num_selected_experts")
    if total and active:
        return active / total
    return 1.0


def gpu_suggestions(total_gb: float) -> list[tuple[str, int, int]]:
    results = []
    for name, vram in GPUS:
        if total_gb <= vram:
            results.append((name, vram, 1))
        else:
            count = math.ceil(total_gb / vram)
            results.append((name, vram, count))
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Estimate VRAM requirements for a Hugging Face LLM model."
    )
    parser.add_argument("model_id", help="HuggingFace model ID, e.g. Qwen/Qwen3-30B")
    parser.add_argument(
        "--precision",
        choices=list(PRECISION_BYTES),
        default="bf16",
        help="Weight precision (default: bf16)",
    )
    parser.add_argument("--seq-len",   type=int, default=4096, help="Context length (default: 4096)")
    parser.add_argument("--batch-size", type=int, default=1,   help="Inference batch size (default: 1)")
    parser.add_argument("--overhead",  type=float, default=0.1, help="Extra overhead fraction (default: 0.10 = 10%%)")
    parser.add_argument("--token",     default=None, help="Hugging Face API token (for gated models)")
    args = parser.parse_args()

    print(f"Fetching model info: {args.model_id} …")
    cfg = fetch_hf_config(args.model_id, args.token)
    num_params = fetch_hf_num_params(args.model_id, args.token)

    param_source = "HF API"
    if num_params is None:
        num_params = estimate_params_from_config(cfg)
        param_source = "estimated from config"

    moe = is_moe(cfg)
    active_frac = active_params_fraction(cfg) if moe else 1.0

    w_gb   = model_vram_gb(num_params, args.precision)
    kv_gb  = kv_cache_vram_gb(cfg, args.seq_len, args.batch_size, args.precision)
    ovh_gb = (w_gb + kv_gb) * args.overhead
    total  = w_gb + kv_gb + ovh_gb

    SEP = "─" * 54
    print(f"\n{SEP}")
    print(f"  Model      : {args.model_id}")
    print(f"  Parameters : {num_params:,}  ({param_source})")
    if moe:
        print(f"  MoE model  : {active_frac:.0%} experts active per token")
        print(f"               all params must reside in VRAM → full weight size applies")
    print(f"  Precision  : {args.precision}")
    print(f"  Seq length : {args.seq_len:,}  |  batch size: {args.batch_size}")
    print(SEP)
    print(f"  Weights          : {w_gb:>7.2f} GB")
    print(f"  KV cache         : {kv_gb:>7.2f} GB")
    print(f"  Overhead ({args.overhead:.0%})    : {ovh_gb:>7.2f} GB")
    print(SEP)
    print(f"  TOTAL VRAM       : {total:>7.2f} GB")
    print(SEP)

    print("\nGPU fit:")
    for name, vram, count in gpu_suggestions(total):
        if count == 1:
            print(f"  ✓  {name:<22} {vram:>4} GB  — fits")
        else:
            print(f"  ✗  {name:<22} {vram:>4} GB  — need {count}× GPUs")
    print()


if __name__ == "__main__":
    main()
