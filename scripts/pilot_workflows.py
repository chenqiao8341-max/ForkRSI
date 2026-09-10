"""Development-only workflow difficulty pilot; never selects held-out outcomes."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from forkmem.agent import run_task
from forkmem.environment import digest, git
from forkmem.llm import LLMClient


async def main(output: Path, source: Path) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(source.read_text())
    entries = [t for t in manifest["tasks"] if t["split"] == "development"]
    settings = {
        "source_manifest_sha256": digest(source.read_bytes()),
        "revision": git(Path.cwd(), "rev-parse", "HEAD"),
        "split": "development only",
        "seed": 17,
        "max_steps": 8,
        "episode_concurrency": 4,
        "request_budget": 160,
    }
    (output / "manifest.json").write_text(json.dumps(settings, indent=2))
    client = LLMClient(output / "llm.jsonl", concurrency=4, request_budget=160)
    sem = asyncio.Semaphore(4)
    rows = []

    async def one(entry):
        async with sem:
            assert digest(Path(entry["path"]).read_bytes()) == entry["sha256"]
            row = await run_task(
                Path(entry["path"]),
                output / entry["task_id"],
                client,
                seed=17,
                max_steps=8,
            )
            row["phase"] = "development"
            rows.append(row)
            with (output / "results.jsonl").open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(
                json.dumps(
                    {
                        "task": row["task_id"],
                        "success": row["success"],
                        "steps": row["steps"],
                    }
                ),
                flush=True,
            )

    try:
        await asyncio.gather(*(one(e) for e in entries))
        summary = {
            "state": "complete",
            "episodes": len(rows),
            "successes": sum(r["success"] for r in rows),
            "transfer_evaluations": 0,
        }
        (output / "status.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary), flush=True)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/v2/workflow_dev0/manifest.json")
    )
    args = parser.parse_args()
    asyncio.run(main(args.output, args.manifest))
