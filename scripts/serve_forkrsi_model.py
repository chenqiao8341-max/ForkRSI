"""Frozen local Qwen3.5-4B text API; serialized sampling and exact usage accounting."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI, HTTPException
from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration

MODEL_DIR = Path(os.getenv("FORKRSI_MODEL_DIR", "/root/autodl-tmp/models/Qwen3.5-4B"))
LOG_DIR = Path(
    os.getenv(
        "FORKRSI_SERVICE_LOG_DIR", "/root/autodl-tmp/ForkRSI/runs/forkrsi/model-service"
    )
)
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOCK = threading.Lock()
app = FastAPI()
torch.set_num_threads(4)
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
model = Qwen3_5ForConditionalGeneration.from_pretrained(
    MODEL_DIR,
    local_files_only=True,
    dtype=torch.bfloat16,
    device_map="cuda",
    attn_implementation="sdpa",
)
model.eval()
model.requires_grad_(False)
startup = {
    "model": "Qwen3.5-4B",
    "model_dir": str(MODEL_DIR),
    "torch": torch.__version__,
    "dtype": str(next(model.parameters()).dtype),
    "gpu": torch.cuda.get_device_name(),
    "weights_frozen": all(not p.requires_grad for p in model.parameters()),
    "config_sha256": hashlib.sha256(
        (MODEL_DIR / "config.json").read_bytes()
    ).hexdigest(),
    "started_unix": time.time(),
    "sampling": "serialized; seed is not a proof of determinism",
    "structured_output": "prompted JSON only; client validates and logs repair attempts",
}
(LOG_DIR / "startup.json").write_text(json.dumps(startup, indent=2))


@app.get("/health")
def health() -> dict[str, Any]:
    return {**startup, "ready": True}


@app.post("/tokenize")
def tokenize(body: dict[str, Any]) -> dict[str, Any]:
    ids = tokenizer.encode(
        body.get("prompt", ""),
        add_special_tokens=bool(body.get("add_special_tokens", False)),
    )
    return {"count": len(ids), "tokens": ids}


@app.post("/v1/chat/completions")
def completion(body: dict[str, Any]) -> dict[str, Any]:
    messages = body.get("messages")
    if not isinstance(messages, list):
        raise HTTPException(400, "messages must be a list")
    if any(not isinstance(m.get("content", ""), str) for m in messages):
        raise HTTPException(400, "this experiment service accepts text only")
    max_tokens = int(body.get("max_tokens", 3000))
    if not 1 <= max_tokens <= 8192:
        raise HTTPException(400, "max_tokens must be 1..8192")
    if body.get("chat_template_kwargs", {}).get("enable_thinking", False):
        raise HTTPException(400, "thinking mode is fixed off for these experiments")
    seed = int(body.get("seed", 0))
    temperature = float(body.get("temperature", 0.3))
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    prompt_tokens = inputs.input_ids.shape[1]
    if prompt_tokens > 24000:
        raise HTTPException(400, "experimental context ceiling is 24000 tokens")
    kwargs = {"max_new_tokens": max_tokens, "do_sample": temperature > 0}
    if temperature > 0:
        kwargs.update(
            temperature=temperature, top_p=float(body.get("top_p", 1)), top_k=0
        )
    started = time.monotonic()
    with LOCK, torch.inference_mode():
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        output = model.generate(**inputs, **kwargs)
    new_ids = output[0, prompt_tokens:]
    content = tokenizer.decode(new_ids, skip_special_tokens=True)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": len(new_ids),
        "total_tokens": prompt_tokens + len(new_ids),
    }
    finish_reason = "length" if len(new_ids) == max_tokens else "stop"
    event = {
        "seed": seed,
        "usage": usage,
        "latency_seconds": time.monotonic() - started,
        "finish_reason": finish_reason,
    }
    with LOCK, (LOG_DIR / "requests.jsonl").open("a") as handle:
        handle.write(json.dumps(event) + "\n")
    return {
        "id": "forkrsi-" + str(time.time_ns()),
        "object": "chat.completion",
        "model": "Qwen3.5-4B",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
