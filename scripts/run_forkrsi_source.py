"""Start or resume the existing ForkMem real-source collection pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from forkmem.benchmark import benchmark
from forkmem.environment import digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("runs/forkrsi/source-v2"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    subprocess.run(
        ["python", "scripts/check_forkrsi_budget.py", "--reserve-hours", "2"],
        check=True,
    )
    manifest = Path("data/forkrsi/semantic_v1/manifest.json")
    expected = json.loads(manifest.read_text())["source_tasks"]
    source_manifest = Path("configs/forkrsi/source-manifest.json")
    actual = json.loads(source_manifest.read_text())["tasks"]
    if [{k: v for k, v in e.items() if k != "split"} for e in actual] != expected:
        raise ValueError("source manifest must exactly match frozen source plan")
    for e in actual:
        if digest(Path(e["path"]).read_bytes()) != e["sha256"]:
            raise ValueError("source task changed")
    asyncio.run(
        benchmark(Path("configs/forkrsi/source.yaml"), args.output, resume=args.resume)
    )


if __name__ == "__main__":
    main()
