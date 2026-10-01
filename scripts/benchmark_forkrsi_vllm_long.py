"""Fixed-length vLLM decode benchmark; synthetic requests, never task policy."""

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from transformers import AutoTokenizer

ROOT = Path("/root/autodl-tmp/ForkRSI/runs/forkrsi/vllm-deployment")
MODEL = "/root/autodl-tmp/models/Qwen3.5-4B"


async def main():
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    messages = [
        {"role": "system", "content": "Write a complete educational Python example."},
        {
            "role": "user",
            "content": "Implement an in-memory priority job scheduler with at least 100 lines of Python. Include queue ordering, insertion, cancellation, execution, error handling, and a demonstration. This is a synthetic inference benchmark, unrelated to research tasks.",
        },
    ]
    rendered = tokenizer.apply_chat_template(
        messages, tokenize=False, enable_thinking=False
    )
    ids = tokenizer.encode(rendered, add_special_tokens=True)
    records = []
    with (ROOT / "concurrency-long-output-requests.jsonl").open("x") as ledger:
        async with httpx.AsyncClient(timeout=900, trust_env=False) as client:
            health = (await client.get("http://127.0.0.1:8000/health")).json()
            assert (
                health["ready"] and health["backend"] == "vllm" and not health["active"]
            )

            async def call(index, condition, length=256):
                body = {
                    "model": "Qwen3.5-4B",
                    "prompt": ids,
                    "temperature": 0,
                    "top_p": 1,
                    "seed": 91000 + index,
                    "max_tokens": length,
                    "min_tokens": length,
                    "ignore_eos": True,
                    "top_k": -1,
                    "repetition_penalty": 1,
                    "presence_penalty": 0,
                    "frequency_penalty": 0,
                }
                began = time.monotonic()
                response = await client.post(
                    "http://127.0.0.1:8002/v1/completions", json=body
                )
                response.raise_for_status()
                result = response.json()
                row = {
                    "job": index,
                    "condition": condition,
                    "request": body,
                    "response": result,
                    "latency_seconds": time.monotonic() - began,
                }
                ledger.write(json.dumps(row) + "\n")
                ledger.flush()
                records.append(row)
                usage = result["usage"]
                assert usage["prompt_tokens"] == len(ids)
                assert usage["completion_tokens"] == length
                assert usage["total_tokens"] == len(ids) + length
                return row

            await call(0, "warmup", 64)
            conditions = []
            for n in [1, 4, 8]:
                sem = asyncio.Semaphore(n)

                async def bounded(i, semaphore=sem, condition=n):
                    async with semaphore:
                        return await call(i, condition)

                began = time.monotonic()
                rows = await asyncio.gather(*(bounded(i) for i in range(8)))
                elapsed = time.monotonic() - began
                output = sum(r["response"]["usage"]["completion_tokens"] for r in rows)
                result = {
                    "concurrency": n,
                    "jobs": 8,
                    "wall_seconds": elapsed,
                    "prompt_tokens": sum(
                        r["response"]["usage"]["prompt_tokens"] for r in rows
                    ),
                    "completion_tokens": output,
                    "aggregate_output_tokens_per_second": output / elapsed,
                    "mean_request_latency_seconds": sum(
                        r["latency_seconds"] for r in rows
                    )
                    / 8,
                }
                conditions.append(result)
                print(json.dumps(result), flush=True)
            for r in conditions:
                r["wall_speedup_vs_concurrency_1"] = (
                    conditions[0]["wall_seconds"] / r["wall_seconds"]
                )
            artifact = {
                "checked_utc": datetime.now(UTC).isoformat(),
                "scope": "same eight synthetic prompts and seeds under 1/4/8 after warmup",
                "policy": "direct internal vLLM completion API; force 256 output tokens for throughput only. This min_tokens/ignore_eos policy is NEVER used for ForkRSI task inference.",
                "backend": health,
                "messages": messages,
                "rendered_prompt": rendered,
                "conditions": conditions,
                "records": records,
                "total_measured_usage": {
                    k: sum(r["response"]["usage"][k] for r in records)
                    for k in ["prompt_tokens", "completion_tokens", "total_tokens"]
                },
                "cost_policy": "direct engine requests bypass adapter ledger; add this raw usage separately, once, to campaign cost accounting",
                "limitations": [
                    "No direct Transformers-vLLM comparison",
                    "No task accuracy claim",
                    "Fixed seeds do not prove bitwise GPU reproducibility",
                ],
            }
            (ROOT / "concurrency-long-output.json").write_text(
                json.dumps(artifact, indent=2) + "\n"
            )
            print(
                json.dumps(
                    {
                        "result": str(ROOT / "concurrency-long-output.json"),
                        "total": artifact["total_measured_usage"],
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    asyncio.run(main())
