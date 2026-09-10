"""Frozen-corpus workflow transfer with exact-input reuse and explicit budgets."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from forkmem.agent import run_task
from forkmem.environment import digest, git
from forkmem.evaluation import load_complete
from forkmem.llm import LLMClient
from forkmem.memory import SQLiteForkStore
from forkmem.models import DecisionFork, NegativeLesson, StateFingerprint
from forkmem.workflows.memory import views


class MemoryTokenizer:
    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.removesuffix("/v1") + "/tokenize"
        self.model = model
        self.ledger: dict[str, dict[str, Any]] = {}
        self.client = httpx.Client(timeout=30, trust_env=False)

    def count(self, text: str) -> int:
        sha = digest(text.encode())
        if sha not in self.ledger:
            if not text:
                count = 0
            else:
                response = self.client.post(
                    self.endpoint,
                    json={
                        "model": self.model,
                        "prompt": text,
                        "add_special_tokens": False,
                    },
                )
                response.raise_for_status()
                count = int(response.json()["count"])
            self.ledger[sha] = {"tokens": count, "characters": len(text)}
        return int(self.ledger[sha]["tokens"])


def cell_key(task: str, seed: int, budget: int, mode: str) -> tuple[str, int, int, str]:
    return task, seed, budget, mode


async def transfer(
    source: Path, config_path: Path, output: Path, *, resume: bool = False
) -> Path:
    source, output = source.resolve(), output.resolve()
    source_manifest, _ = load_complete(source)
    config = yaml.safe_load(config_path.read_text())
    dataset = json.loads(Path(config["task_manifest"]).read_text())
    if dataset != source_manifest["dataset"]:
        raise ValueError("source and transfer task manifests differ")
    for entry in dataset["tasks"]:
        if digest(Path(entry["path"]).read_bytes()) != entry["sha256"]:
            raise ValueError("task hash mismatch")
    if git(Path.cwd(), "status", "--porcelain"):
        raise ValueError("transfer requires a clean committed checkout")
    revision = git(Path.cwd(), "rev-parse", "HEAD")
    output.mkdir(parents=True, exist_ok=resume)
    corpus_bytes = (source / "corpus.json").read_bytes()
    provenance = {
        "source": str(source),
        "source_revision": source_manifest["revision"],
        "source_corpus_sha256": digest(corpus_bytes),
        "config": config,
        "config_sha256": digest(config_path.read_bytes()),
        "dataset": dataset,
        "revision": revision,
        "started_unix": time.time(),
        "reuse_policy": "Exact memory body, task, seed and action budget share one execution. Aliases are recorded, not counted as independent runs.",
    }
    if resume:
        worker = json.loads((output / "worker.json").read_text())
        process_command = Path(f"/proc/{worker['pid']}/cmdline")
        if (
            process_command.exists()
            and str(output).encode() in process_command.read_bytes()
        ):
            raise ValueError("cannot resume while the original worker is still alive")
        old = json.loads((output / "manifest.json").read_text())
        status = json.loads((output / "status.json").read_text())
        if status["state"] != "interrupted_or_failed":
            raise ValueError("resume requires confirmed terminal failed status")
        if (
            old["source_corpus_sha256"] != provenance["source_corpus_sha256"]
            or old["config_sha256"] != provenance["config_sha256"]
            or old["dataset"] != dataset
        ):
            raise ValueError("source/config/tasks changed on resume")
        (output / f"manifest-before-resume-{int(time.time())}.json").write_text(
            json.dumps(old, indent=2)
        )
        provenance.update(
            started_unix=old["started_unix"],
            resume_history=[
                *old.get("resume_history", []),
                {
                    "previous_revision": old["revision"],
                    "revision": revision,
                    "previous_status": status,
                },
            ],
        )
    (output / "manifest.json").write_text(json.dumps(provenance, indent=2))
    (output / "worker.json").write_text(
        json.dumps({"pid": os.getpid(), "revision": revision})
    )
    calls_path = output / "llm.jsonl"
    previous_calls = (
        len(calls_path.read_text().splitlines()) if calls_path.exists() else 0
    )
    client = LLMClient(
        calls_path,
        concurrency=config["concurrency"],
        request_budget=config["request_budget"] - previous_calls,
    )
    tokenizer = MemoryTokenizer(client.base_url, client.model)
    store = SQLiteForkStore(output / "source_memory.sqlite")
    corpus = json.loads(corpus_bytes)
    known_forks = {f.fork_id for f in store.all()}
    known_negatives = {n.lesson_id for n in store.negatives()}
    for fork in corpus["forks"]:
        if fork["fork_id"] not in known_forks:
            store.put(DecisionFork.model_validate(fork))
    for lesson in corpus["negative_lessons"]:
        if lesson["lesson_id"] not in known_negatives:
            store.put_negative(NegativeLesson.model_validate(lesson))
    rows = (
        [json.loads(x) for x in (output / "results.jsonl").read_text().splitlines()]
        if resume and (output / "results.jsonl").exists()
        else []
    )
    completed = {
        cell_key(r["task_id"], r["seed"], r["action_budget"], r["mode"]): r
        for r in rows
    }
    if len(completed) != len(rows):
        raise ValueError("duplicate saved cells")
    prepared: dict[str, dict[str, tuple[str, list[str]]]] = {}
    entries = [entry for entry in dataset["tasks"] if entry["split"] == "held_out"]

    def record(row: dict[str, Any]) -> None:
        rows.append(row)
        completed[
            cell_key(row["task_id"], row["seed"], row["action_budget"], row["mode"])
        ] = row
        with (output / "results.jsonl").open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        (output / "status.json").write_text(
            json.dumps(
                {
                    "state": "running",
                    "completed_cells": len(rows),
                    "last": row["task_id"],
                    "mode": row["mode"],
                },
                indent=2,
            )
        )
        print(
            json.dumps(
                {
                    "task": row["task_id"],
                    "seed": row["seed"],
                    "budget": row["action_budget"],
                    "mode": row["mode"],
                    "success": row["success"],
                    "reused": bool(row.get("reuse_of")),
                }
            ),
            flush=True,
        )

    semaphore = asyncio.Semaphore(config["episode_concurrency"])
    try:
        (output / "status.json").write_text(
            json.dumps(
                {
                    "state": "running",
                    "phase": "memory_preparation",
                    "completed_cells": len(rows),
                }
            )
        )
        for entry in entries:
            spec = json.loads(Path(entry["path"]).read_text())
            state = StateFingerprint(
                task_family=spec["family"],
                features=spec["features"],
                summary=spec["description"],
                checkpoint="retrieval-only",
            )
            prepared[entry["task_id"]] = views(
                store,
                state,
                tokenizer.count,
                token_cap=config["memory_token_cap"],
                limit=config["memory_records"],
                character_cap=config.get("memory_character_cap", 20000),
            )
        prepared_json = json.dumps(prepared, sort_keys=True)
        prepared_path = output / "prepared_memories.json"
        if (
            resume
            and prepared_path.exists()
            and prepared_path.read_text() != prepared_json
        ):
            raise ValueError("prepared memory changed on resume")
        prepared_path.write_text(prepared_json)
        # Ensure each final body is present in the exact-token ledger.
        for task_views in prepared.values():
            for body, _ in task_views.values():
                tokenizer.count(body)
        (output / "memory_tokens.json").write_text(
            json.dumps(
                {
                    "model": client.model,
                    "add_special_tokens": False,
                    "items": tokenizer.ledger,
                },
                indent=2,
            )
        )

        async def one(
            entry: dict[str, Any], seed: int, budget: int, modes: list[str]
        ) -> None:
            async with semaphore:
                task_id = entry["task_id"]
                canonical = modes[0]
                existing = next(
                    (
                        completed[cell_key(task_id, seed, budget, m)]
                        for m in modes
                        if cell_key(task_id, seed, budget, m) in completed
                    ),
                    None,
                )
                if existing:
                    result = existing
                else:
                    target = (
                        output
                        / f"budget_{budget}"
                        / f"seed_{seed}"
                        / canonical
                        / task_id
                    )
                    original = target
                    retry = 0
                    while target.exists():
                        retry += 1
                        target = original.with_name(original.name + f"_retry_{retry}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    result = await run_task(
                        Path(entry["path"]),
                        target,
                        client,
                        mode=canonical,
                        seed=seed,
                        max_steps=budget,
                        prepared_memory=prepared[task_id][canonical],
                    )
                    result.update(
                        episode_dir=str(target),
                        action_budget=budget,
                        phase="evaluation",
                        semantic_context=entry["semantic_context"],
                        memory_body_sha256=digest(
                            prepared[task_id][canonical][0].encode()
                        ),
                        experiment_revision=revision,
                    )
                for mode in modes:
                    key = cell_key(task_id, seed, budget, mode)
                    if key in completed:
                        continue
                    row = {
                        **result,
                        "mode": mode,
                        "memory_ids": prepared[task_id][mode][1],
                    }
                    if mode != canonical:
                        row["reuse_of"] = {
                            "task_id": task_id,
                            "seed": seed,
                            "action_budget": budget,
                            "mode": canonical,
                            "episode_id": result["episode_id"],
                        }
                    record(row)

        jobs = []
        for budget in config["action_budgets"]:
            for seed in config["evaluation_seeds"]:
                for entry in entries:
                    groups: dict[str, list[str]] = {}
                    for mode in config["modes"]:
                        body = prepared[entry["task_id"]][mode][0]
                        groups.setdefault(body, []).append(mode)
                    for modes in groups.values():
                        jobs.append(one(entry, seed, budget, modes))
        running = [asyncio.create_task(job) for job in jobs]
        try:
            await asyncio.gather(*running)
        except BaseException:
            for job in running:
                job.cancel()
            await asyncio.gather(*running, return_exceptions=True)
            raise
        expected = (
            len(entries)
            * len(config["evaluation_seeds"])
            * len(config["action_budgets"])
            * len(config["modes"])
        )
        if len(rows) != expected:
            raise ValueError("incomplete transfer grid")
        (output / "status.json").write_text(
            json.dumps(
                {
                    "state": "complete",
                    "cells": len(rows),
                    "unique_episodes": len({r["episode_id"] for r in rows}),
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
                    "error": str(exc),
                    "completed_cells": len(rows),
                },
                indent=2,
            )
        )
        raise
    finally:
        tokenizer.client.close()
        store.close()
        await client.close()
    return output / "results.jsonl"
