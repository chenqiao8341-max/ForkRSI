"""Same synthetic 8 jobs under concurrency 1/4/8; not research outcomes."""

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path("/root/autodl-tmp/ForkRSI/runs/forkrsi/vllm-deployment")
PROMPT = (
    "Synthetic throughput benchmark context. No research task or source evidence.\n"
    * 40
) + ("\nReturn only a JSON array of integers from 1 to 1000, with no explanation.")


async def main():
    async with httpx.AsyncClient(timeout=900, trust_env=False) as client:
        health = (await client.get("http://127.0.0.1:8000/health")).json()
        assert health["ready"] and health["backend"] == "vllm"
        records = []

        async def call(index, condition, maximum=256):
            started = time.monotonic()
            body = {
                "model": "Qwen3.5-4B",
                "messages": [
                    {"role": "system", "content": "Follow the output instruction."},
                    {"role": "user", "content": PROMPT},
                ],
                "temperature": 0,
                "top_p": 1,
                "max_tokens": maximum,
                "seed": 90000 + index,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            response = await client.post(
                "http://127.0.0.1:8000/v1/chat/completions",
                headers={"X-Request-ID": f"benchmark-{condition}-{index}"},
                json=body,
            )
            response.raise_for_status()
            result = response.json()
            return {
                "job": index,
                "condition": condition,
                "request": body,
                "response": result,
                "latency_seconds": time.monotonic() - started,
            }

        records.append(await call(0, "warmup", 64))
        conditions = []
        for n in [1, 4, 8]:
            sem = asyncio.Semaphore(n)

            async def bounded(i, semaphore=sem, condition=n):
                async with semaphore:
                    return await call(i, condition)

            start = time.monotonic()
            rows = await asyncio.gather(*(bounded(i) for i in range(8)))
            elapsed = time.monotonic() - start
            records.extend(rows)
            prompt = sum(r["response"]["usage"]["prompt_tokens"] for r in rows)
            output = sum(r["response"]["usage"]["completion_tokens"] for r in rows)
            result = {
                "concurrency": n,
                "jobs": 8,
                "wall_seconds": elapsed,
                "prompt_tokens": prompt,
                "completion_tokens": output,
                "aggregate_output_tokens_per_second": output / elapsed,
                "mean_request_latency_seconds": sum(r["latency_seconds"] for r in rows)
                / 8,
            }
            conditions.append(result)
            print(json.dumps(result), flush=True)
        after = (await client.get("http://127.0.0.1:8000/health")).json()
        artifact = {
            "checked_utc": datetime.now(UTC).isoformat(),
            "scope": "synthetic identical 8 prompts after warmup; serving throughput only",
            "backend": health,
            "conditions": conditions,
            "peak_active_requests": after["peak_active"],
            "records": records,
            "total_measured_usage": {
                k: sum(r["response"]["usage"][k] for r in records)
                for k in ["prompt_tokens", "completion_tokens", "total_tokens"]
            },
            "limitations": [
                "Not a direct Transformers-vLLM comparison.",
                "No research-task accuracy claim.",
                "Fixed input seeds do not establish deterministic GPU outputs.",
            ],
        }
        (ROOT / "concurrency-benchmark.json").write_text(
            json.dumps(artifact, indent=2) + "\n"
        )
        print(
            json.dumps(
                {
                    "peak_active_requests": after["peak_active"],
                    "result": str(ROOT / "concurrency-benchmark.json"),
                }
            ),
            flush=True,
        )


asyncio.run(main())
