"""Generate real forks from already completed source episodes under repaired JSON.

No training episode is rerun. Referenced parent episodes are audit inputs, not
new executions. Every new alternative still uses the same checkpoint and action
budget, and only completed authenticated forks are placed in the source store.
"""

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
from forkmem.llm import PROMPT_VERSION, LLMClient, ModelResponseError
from forkmem.memory import SQLiteForkStore
from forkmem.models import (
    Action,
    DecisionFork,
    NegativeLesson,
    Outcome,
    StateFingerprint,
)


async def run(plan_path: Path, output: Path) -> None:
    plan = json.loads(plan_path.read_text())
    parent = Path(plan["parent"])
    parent_status = json.loads((parent / "status.json").read_text())
    worker = json.loads((parent / "worker.json").read_text())
    proc = Path(f"/proc/{worker['pid']}/cmdline")
    if parent_status["state"] not in {"complete", "interrupted_or_failed"} or (
        proc.exists() and b"run_forkrsi_source.py" in proc.read_bytes()
    ):
        raise ValueError("parent source batch must be confirmed terminal")
    if PROMPT_VERSION != plan["json_protocol"]:
        raise ValueError("source repair protocol differs from the committed plan")
    if git(Path.cwd(), "status", "--porcelain"):
        raise RuntimeError("source fork collection requires a clean committed checkout")
    await asyncio.to_thread(
        subprocess.run,
        ["python", "scripts/check_forkrsi_budget.py", "--reserve-hours", "2"],
        check=True,
    )
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with (output / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        revision = git(Path.cwd(), "rev-parse", "HEAD")
        (output / "manifest.json").write_text(
            json.dumps(
                {
                    "plan": plan,
                    "plan_sha256": digest(plan_path.read_bytes()),
                    "loaded_worker_revision": revision,
                    "design": "new proposal batch on unchanged completed source checkpoints; no new training execution",
                },
                indent=2,
            )
            + "\n"
        )
        (output / "worker.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "revision": revision,
                    "json_protocol": PROMPT_VERSION,
                }
            )
        )
        (output / "results.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        **e["row"],
                        "record_scope": "reference to original source episode; not new execution",
                    }
                )
                + "\n"
                for e in plan["episodes"]
            )
        )
        client = LLMClient(
            output / "llm.jsonl",
            concurrency=1,
            request_budget=plan["request_budget"],
        )
        store = SQLiteForkStore(output / "memory.sqlite")
        records = []
        status_path = output / "status.json"

        def status(state: str, **extra: object) -> None:
            status_path.write_text(
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
            for entry in plan["episodes"]:
                episode = Path(entry["row"]["episode_dir"])
                for name, expected in entry["hashes"].items():
                    if digest((episode / name).read_bytes()) != expected:
                        raise ValueError("immutable source episode changed")
                row = json.loads((episode / "episode.json").read_text())
                if row["success"]:
                    raise ValueError("source fork parent must be a failed episode")
                if (
                    digest(Path(row["task_path"]).read_bytes()) != entry["task_sha256"]
                    or digest(Path(row["verifier"]).read_bytes())
                    != entry["verifier_sha256"]
                ):
                    raise ValueError("source task or verifier changed")
                task = json.loads(Path(row["task_path"]).read_text())
                events = [
                    json.loads(s)
                    for s in (episode / "trajectory.jsonl").read_text().splitlines()
                ]
                pivots = locate_pivots(events)
                if (pivots[0] if pivots else None) != entry["pivot_index"]:
                    raise ValueError("source pivot differs from the committed plan")
                outcome = Outcome.model_validate(
                    json.loads((episode / "result.json").read_text())["outcome"]
                )
                if digest(Path(outcome.log_path).read_bytes()) != outcome.output_sha256:
                    raise ValueError("source outcome digest mismatch")
                state = StateFingerprint(
                    task_family=task["family"],
                    features=task["features"],
                    summary=task["description"],
                    checkpoint=outcome.checkpoint,
                )
                store.put_negative(
                    NegativeLesson(
                        lesson_id=f"parent-source-v2::{row['seed']}::{row['task_id']}",
                        source_episode_id=str(episode),
                        state=state,
                        action=Action.model_validate(
                            events[pivots[0] if pivots else -1]["action"]
                        ),
                        outcome=outcome,
                        summary=Path(outcome.log_path).read_text()[:3000],
                    )
                )
                record = {"episode": str(episode), "pivot_index": entry["pivot_index"]}
                if not pivots:
                    record["status"] = "no_modifying_pivot"
                else:
                    folder = output / "forks" / f"seed_{row['seed']}_{row['task_id']}"
                    try:
                        path = await fork_episode(
                            episode,
                            folder,
                            client,
                            branches=plan["branches"],
                        )
                        fork = DecisionFork.model_validate_json(path.read_text())
                        store.put(fork)
                        record.update(
                            status="complete",
                            fork_id=fork.fork_id,
                            branches=[
                                b.evidence_status.value for b in fork.alternatives
                            ],
                        )
                    except ModelResponseError as exc:
                        record.update(
                            status="response_repair_exhausted",
                            request_id=exc.request_id,
                            error_type=type(exc).__name__,
                        )
                    except RuntimeError as exc:
                        if str(exc) not in {
                            "no distinct valid candidate; no memory written",
                            "factual failure did not reproduce; do not create comparative memory",
                        }:
                            raise
                        record.update(status="no_comparative_memory", error=str(exc))
                records.append(record)
                (output / "source-cells.json").write_text(
                    json.dumps(records, indent=2) + "\n"
                )
                status("running", last=record)
                print(json.dumps(record), flush=True)
            (output / "corpus.json").write_text(
                json.dumps(
                    {
                        "forks": [f.model_dump(mode="json") for f in store.all()],
                        "negative_lessons": [
                            n.model_dump(mode="json") for n in store.negatives()
                        ],
                    },
                    indent=2,
                )
                + "\n"
            )
            status("complete", requested_source_cells=len(plan["episodes"]))
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
        "--plan", type=Path, default=Path("configs/forkrsi/repaired-source-plan.json")
    )
    parser.add_argument("--output", type=Path, default=Path("runs/forkrsi/source-v3"))
    args = parser.parse_args()
    asyncio.run(run(args.plan, args.output))


if __name__ == "__main__":
    main()
