"""Execute recorded subscription hypotheses at original failed checkpoints."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import subprocess
import traceback
from pathlib import Path

from forkmem.counterfactual import fork_episode, locate_pivots
from forkmem.environment import digest, git
from forkmem.llm import LLMClient
from forkmem.memory import SQLiteForkStore
from forkmem.models import DecisionFork, Proposals


async def run(manifest_path: Path, output: Path) -> None:
    if git(Path.cwd(), "status", "--porcelain"):
        raise RuntimeError(
            "subscription source execution requires clean committed code"
        )
    manifest = json.loads(manifest_path.read_text())
    await asyncio.to_thread(
        subprocess.run,
        ["python", "scripts/check_forkrsi_budget.py", "--reserve-hours", "1"],
        check=True,
    )
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with (output / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        revision = git(Path.cwd(), "rev-parse", "HEAD")
        (output / "worker.json").write_text(
            json.dumps({"pid": os.getpid(), "revision": revision}) + "\n"
        )
        (output / "manifest.json").write_text(
            json.dumps(
                {
                    "design": "executed subscription-assisted source hypotheses; references are not new training samples",
                    "subscription_assistance": manifest,
                    "proposal_manifest_path": str(manifest_path.resolve()),
                    "proposal_manifest_sha256": digest(manifest_path.read_bytes()),
                    "loaded_worker_revision": revision,
                },
                indent=2,
            )
            + "\n"
        )
        (output / "results.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        **entry["parent"]["row"],
                        "record_scope": "reference to original source episode; not new execution",
                    }
                )
                + "\n"
                for entry in manifest["entries"]
            )
        )
        client = LLMClient(output / "llm.jsonl", concurrency=1, request_budget=0)
        store = SQLiteForkStore(output / "memory.sqlite")
        records = []

        def status(state: str, **extra: object) -> None:
            (output / "status.json").write_text(
                json.dumps(
                    {
                        "state": state,
                        "completed_source_cells": len(records),
                        "forks": len(store.all()),
                        "new_training_executions": 0,
                        **extra,
                    },
                    indent=2,
                )
                + "\n"
            )

        status("running")
        try:
            for entry in manifest["entries"]:
                parent = entry["parent"]
                episode = Path(parent["row"]["episode_dir"])
                for name, expected in parent["hashes"].items():
                    if digest((episode / name).read_bytes()) != expected:
                        raise ValueError("immutable parent changed")
                row = json.loads((episode / "episode.json").read_text())
                if row["success"]:
                    raise ValueError("parent must remain failed")
                for key, sha_key in (
                    ("task_path", "task_sha256"),
                    ("verifier", "verifier_sha256"),
                ):
                    if digest(Path(row[key]).read_bytes()) != parent[sha_key]:
                        raise ValueError("task or verifier changed")
                for key in ("input", "output"):
                    if digest(Path(entry[key]).read_bytes()) != entry[key + "_sha256"]:
                        raise ValueError("recorded subscription input/output changed")
                events = [
                    json.loads(x)
                    for x in (episode / "trajectory.jsonl").read_text().splitlines()
                ]
                pivots = locate_pivots(events)
                if not pivots or pivots[0] != parent["pivot_index"]:
                    raise ValueError("recorded checkpoint changed")
                if row["max_steps"] - pivots[0] - 1 != 0:
                    raise ValueError(
                        "this zero-request batch requires no remaining continuation actions"
                    )
                proposals = Proposals.model_validate_json(
                    Path(entry["output"]).read_text()
                )
                path = await fork_episode(
                    episode,
                    output / "forks" / entry["family"],
                    client,
                    branches=2,
                    cached_proposals=proposals,
                    cached_proposal_origin="subscription_assistant",
                    cached_proposal_record={
                        "manifest_sha256": digest(manifest_path.read_bytes()),
                        "input_sha256": entry["input_sha256"],
                        "output_sha256": entry["output_sha256"],
                        "origin": manifest["origin"],
                        "no_qwen_proposal_request": True,
                    },
                )
                fork = DecisionFork.model_validate_json(path.read_text())
                store.put(fork)
                records.append(
                    {
                        "family": entry["family"],
                        "fork_id": fork.fork_id,
                        "proposal_origin": fork.provenance["proposal_origin"],
                        "branches": [
                            b.evidence_status.value for b in fork.alternatives
                        ],
                    }
                )
                (output / "source-cells.json").write_text(
                    json.dumps(records, indent=2) + "\n"
                )
                status("running", last=records[-1])
                print(json.dumps(records[-1]), flush=True)
            (output / "corpus.json").write_text(
                json.dumps(
                    {
                        "forks": [f.model_dump(mode="json") for f in store.all()],
                        "negative_lessons": [],
                    },
                    indent=2,
                )
                + "\n"
            )
            status("complete")
        except BaseException as exc:
            status(
                "interrupted_or_failed",
                error_type=type(exc).__name__,
                traceback=traceback.format_exc(),
            )
            raise
        finally:
            await client.close()
            store.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("configs/forkrsi/subscription-source-v1/manifest.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("runs/forkrsi/source-v4-subscription")
    )
    args = parser.parse_args()
    asyncio.run(run(args.manifest, args.output))


if __name__ == "__main__":
    main()
