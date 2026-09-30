"""Real local model protocol smoke; these toy calls are not research evidence."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from forkmem.llm import LLMClient
from forkmem.models import Action, Proposals


async def main() -> None:
    root = Path("runs/forkrsi/model-smoke")
    root.mkdir(parents=True, exist_ok=False)
    client = LLMClient(root / "llm.jsonl", concurrency=1, request_budget=8)
    try:
        health = (await client.client.get("http://127.0.0.1:8000/health")).json()
        if not health["ready"] or not health["weights_frozen"]:
            raise ValueError("model is not frozen and ready")
        action = await client.generate(
            "Return an Action to read README.md. This is a protocol test only.",
            Action,
            seed=1201,
            max_tokens=300,
            run_id="protocol-smoke",
        )
        proposals = await client.generate(
            "Protocol test only, no execution claim. Propose two distinct complete writes to solution.py: "
            "one assigning value = 2, another assigning value = 3. Return all fields of Proposals, "
            "with a short suspected mechanism, prediction, requires/excludes dictionaries of strings and risk.",
            Proposals,
            seed=1202,
            max_tokens=6000,
            run_id="protocol-smoke",
        )
        if action.tool != "read" or len(proposals.proposals) != 2:
            raise ValueError("toy protocol response did not follow instruction")
        events = [json.loads(line) for line in client.log_path.read_text().splitlines()]
        summary = {
            "purpose": "real protocol smoke only; not source or RSI evidence",
            "health": health,
            "action": action.model_dump(),
            "proposals": proposals.model_dump(),
            "requests": [
                {
                    "schema": e["schema"],
                    "status": e["status"],
                    "usage": e.get("usage"),
                    "latency_seconds": e["latency_seconds"],
                    "completion_tokens_per_second": e.get("usage", {}).get(
                        "completion_tokens", 0
                    )
                    / e["latency_seconds"],
                }
                for e in events
            ],
        }
        (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({k: summary[k] for k in ("purpose", "requests")}))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
