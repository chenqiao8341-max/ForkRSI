"""Controlled offline memory comparison with a shared training exposure stream."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import yaml

from forkmem.agent import run_task
from forkmem.counterfactual import fork_episode, locate_pivots
from forkmem.environment import digest, git
from forkmem.llm import LLMClient, parse_json
from forkmem.memory import SQLiteForkStore
from forkmem.models import (
    Action,
    DecisionFork,
    NegativeLesson,
    Outcome,
    Proposals,
    StateFingerprint,
)


async def benchmark(config_path: Path, output: Path, *, resume: bool = False) -> Path:
    config = yaml.safe_load(config_path.read_text())
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=resume)
    revision = git(Path.cwd(), "rev-parse", "HEAD")
    if git(Path.cwd(), "status", "--porcelain"):
        raise RuntimeError(
            "benchmark requires clean tracked source and task definitions"
        )
    manifest = json.loads(Path(config["task_manifest"]).read_text())
    entries = manifest["tasks"]
    for entry in entries:
        if digest(Path(entry["path"]).read_bytes()) != entry["sha256"]:
            raise ValueError("task hash mismatch: " + entry["task_id"])
    provenance = {
        "config": config,
        "config_sha256": digest(config_path.read_bytes()),
        "revision": revision,
        "dataset": manifest,
        "started_unix": time.time(),
        "design": "shared no-memory training stream; frozen corpus; independent evaluation episodes; no held-out updates",
    }
    if resume:
        old = json.loads((output / "manifest.json").read_text())
        state = json.loads((output / "status.json").read_text())
        if state["state"] != "interrupted_or_failed":
            raise ValueError("resume requires a confirmed terminal failed run")
        if (
            old["config_sha256"] != provenance["config_sha256"]
            or old["dataset"] != manifest
        ):
            raise ValueError("cannot change config or dataset on resume")
        (output / f"manifest-before-resume-{int(time.time())}.json").write_text(
            json.dumps(old, indent=2)
        )
        provenance.update(
            started_unix=old["started_unix"],
            original_training_revision=old.get(
                "original_training_revision", old["revision"]
            ),
            policy_source_root=str(Path.cwd()),
            resume_history=[
                *old.get("resume_history", []),
                {
                    "revision": revision,
                    "reason": "resume completed episodes; structural proposal JSON compatibility",
                    "previous_state": state,
                },
            ],
        )
    (output / "manifest.json").write_text(json.dumps(provenance, indent=2))
    previous_calls = (
        [json.loads(line) for line in (output / "llm.jsonl").read_text().splitlines()]
        if resume and (output / "llm.jsonl").exists()
        else []
    )
    client = LLMClient(
        output / "llm.jsonl",
        concurrency=config["concurrency"],
        request_budget=config["request_budget"] - len(previous_calls),
    )
    semaphore = asyncio.Semaphore(config["episode_concurrency"])
    store = SQLiteForkStore(output / "memory.sqlite")
    rows: list[dict[str, Any]] = (
        [
            json.loads(line)
            for line in (output / "results.jsonl").read_text().splitlines()
        ]
        if resume
        else []
    )
    completed = {
        (row["phase"], row["task_id"], row["seed"], row["mode"]): row for row in rows
    }
    if len(completed) != len(rows):
        raise ValueError("duplicate persisted episode cells")
    (output / "worker.json").write_text(
        json.dumps({"pid": os.getpid(), "revision": revision})
    )
    (output / "status.json").write_text(
        json.dumps(
            {
                "state": "running",
                "completed_episodes": len(rows),
                "phase": "resume" if resume else "training",
            }
        )
    )

    def record(row: dict[str, Any]) -> None:
        rows.append(row)
        with (output / "results.jsonl").open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        (output / "status.json").write_text(
            json.dumps(
                {"completed_episodes": len(rows), "last": row, "state": "running"},
                indent=2,
            )
        )
        print(
            json.dumps(
                {
                    "phase": row["phase"],
                    "task": row["task_id"],
                    "seed": row["seed"],
                    "mode": row["mode"],
                    "success": row["success"],
                }
            ),
            flush=True,
        )

    async def episode(
        entry: dict[str, Any], seed: int, mode: str, phase: str
    ) -> dict[str, Any]:
        async with semaphore:
            key = (phase, entry["task_id"], seed, mode)
            if key in completed:
                saved = completed[key]
                actual = json.loads(
                    (Path(saved["episode_dir"]) / "episode.json").read_text()
                )
                if actual["success"] != saved["success"]:
                    raise ValueError("persisted episode result mismatch")
                return saved
            target = output / phase / f"seed_{seed}" / mode / entry["task_id"]
            target.parent.mkdir(parents=True, exist_ok=True)
            row = await run_task(
                Path(entry["path"]),
                target,
                client,
                store=store if phase == "evaluation" else None,
                mode=mode,
                seed=seed,
                max_steps=config["max_steps"],
            )
            row.update(
                phase=phase, episode_dir=str(target), experiment_revision=revision
            )
            record(row)
            return row

    try:
        training = [e for e in entries if e["split"] == "train"]

        # Each seed has an identical task order. Parallelism is across independent seeds.
        async def training_stream(seed: int) -> None:
            for entry in training:
                await episode(entry, seed, "none", "training")

        await asyncio.gather(
            *(training_stream(seed) for seed in config["training_seeds"])
        )
        failed = [
            row for row in rows if row["phase"] == "training" and not row["success"]
        ]
        for row in failed:
            episode_dir = Path(row["episode_dir"])
            events = [
                json.loads(line)
                for line in (episode_dir / "trajectory.jsonl").read_text().splitlines()
            ]
            task = json.loads(Path(row["task_path"]).read_text())
            pivots = locate_pivots(events)
            last_action = Action.model_validate(
                events[pivots[0] if pivots else -1]["action"]
            )
            outcome = Outcome.model_validate(
                json.loads((episode_dir / "result.json").read_text())["outcome"]
            )
            state = StateFingerprint(
                task_family=task["family"],
                features=task["features"],
                summary=task["description"],
                checkpoint=outcome.checkpoint,
            )
            if f"{row['seed']}-{row['task_id']}" not in {
                lesson.lesson_id for lesson in store.negatives()
            }:
                store.put_negative(
                    NegativeLesson(
                        lesson_id=f"{row['seed']}-{row['task_id']}",
                        source_episode_id=str(episode_dir),
                        state=state,
                        action=last_action,
                        outcome=outcome,
                        summary=Path(outcome.log_path).read_text()[:3000],
                    )
                )
            if not pivots:
                continue
            fork_dir = output / "forks" / f"seed_{row['seed']}_{row['task_id']}"
            complete_paths = [
                path
                for path in sorted(
                    (output / "forks").glob(
                        f"seed_{row['seed']}_{row['task_id']}*/fork.json"
                    )
                )
                if json.loads(path.read_text())["provenance"]["episode"]
                == str(episode_dir)
            ]
            if complete_paths:
                destination = complete_paths[0]
            else:
                cached = None
                recovery = None
                if resume:
                    for call in previous_calls:
                        if (
                            call.get("episode_id") == episode_dir.name
                            and call.get("seed") == row["seed"]
                            and call.get("schema") == "Proposals"
                        ):
                            try:
                                cached = parse_json(call["response"], Proposals)
                                recovery = {
                                    "request_id": call["request_id"],
                                    "attempt": call["attempt"],
                                    "response_sha256": digest(
                                        call["response"].encode()
                                    ),
                                    "method": "unambiguous wrapper normalization; code unchanged",
                                }
                                break
                            except (ValueError, KeyError):
                                continue
                retry = 0
                original_dir = fork_dir
                while fork_dir.exists():
                    retry += 1
                    fork_dir = original_dir.with_name(
                        original_dir.name + f"_retry_{retry}"
                    )
                destination = await fork_episode(
                    episode_dir,
                    fork_dir,
                    client,
                    branches=config["branches"],
                    cached_proposals=cached,
                )
                if recovery:
                    (fork_dir / "proposal_recovery.json").write_text(
                        json.dumps(recovery, indent=2)
                    )
            fork = DecisionFork.model_validate_json(destination.read_text())
            if fork.fork_id not in {existing.fork_id for existing in store.all()}:
                store.put(fork)
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
        )
        evaluation = [e for e in entries if e["split"] in {"held_out", "near_miss"}]

        # Modes have the same frozen source experience and independent reset repositories.
        async def evaluation_stream(seed: int, mode: str) -> None:
            for entry in evaluation:
                await episode(entry, seed, mode, "evaluation")

        await asyncio.gather(
            *(
                evaluation_stream(seed, mode)
                for seed in config["evaluation_seeds"]
                for mode in config["modes"]
            )
        )
        (output / "status.json").write_text(
            json.dumps(
                {
                    "state": "complete",
                    "episodes": len(rows),
                    "factual_failures": len(failed),
                    "forks": len(store.all()),
                    "wall_seconds": time.time() - provenance["started_unix"],
                },
                indent=2,
            )
        )
    except BaseException as exc:
        (output / "status.json").write_text(
            json.dumps(
                {
                    "state": "interrupted_or_failed",
                    "error_type": type(exc).__name__,
                    "completed_episodes": len(rows),
                },
                indent=2,
            )
        )
        raise
    finally:
        await client.close()
        store.close()
    return output / "results.jsonl"
