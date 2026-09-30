"""Finalize a recorded exhausted Action response without generating or editing code.

This recovery is limited to four logged schema failures in a terminal source run.
The original graph database is backed up and the same terminal verification rule
used in future episodes consumes the next action. No source result is fabricated.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from forkmem.agent import AgentRunner
from forkmem.environment import RepoEnvironment, digest, git
from forkmem.llm import LLMClient, ModelResponseError


async def finalize(run: Path) -> None:
    run = run.resolve()
    status = json.loads((run / "status.json").read_text())
    if status["state"] != "interrupted_or_failed":
        raise ValueError("only a confirmed terminal failed batch may be recovered")
    worker = json.loads((run / "worker.json").read_text())
    process = await asyncio.to_thread(
        subprocess.run,
        ["ps", "-p", str(worker["pid"]), "-o", "args="],
        capture_output=True,
        text=True,
        check=False,
    )
    live = process.stdout
    if "run_forkrsi_source" in live:
        raise ValueError("source worker is still alive")
    calls = [json.loads(s) for s in (run / "llm.jsonl").read_text().splitlines()]
    last = calls[-4:]
    if (
        len(last) != 4
        or {c["request_id"] for c in last} != {last[-1]["request_id"]}
        or [c["attempt"] for c in last] != list(range(4))
        or any(c["schema"] != "Action" or c["status"] != "parse_error" for c in last)
    ):
        raise ValueError("last request is not a recorded exhausted Action response")
    candidates = [
        p.parent
        for p in (run / "training").rglob("runner.json")
        if json.loads(p.read_text())["episode_id"] == last[-1]["episode_id"]
    ]
    if len(candidates) != 1:
        raise ValueError("cannot identify exactly one interrupted episode")
    episode = candidates[0]
    if (episode / "result.json").exists() or (episode / "episode.json").exists():
        raise ValueError("episode already terminal")
    settings = json.loads((episode / "runner.json").read_text())
    rows = [json.loads(s) for s in (run / "results.jsonl").read_text().splitlines()]
    if any(r["episode_id"] == settings["episode_id"] for r in rows):
        raise ValueError("episode already recorded")
    manifest = json.loads((run / "manifest.json").read_text())
    entries = [e for e in manifest["dataset"]["tasks"] if e["task_id"] == episode.name]
    if len(entries) != 1:
        raise ValueError("interrupted task is not in source plan")
    task_path = Path(entries[0]["path"])
    if digest(task_path.read_bytes()) != entries[0]["sha256"]:
        raise ValueError("source task changed")
    task = json.loads(task_path.read_text())
    if Path(settings["verifier"]).read_text() != task["verifier"]:
        raise ValueError("episode verifier changed")
    database = episode / "checkpoints.sqlite"
    backup = episode / "checkpoints-before-response-finalization.sqlite"
    if backup.exists():
        raise ValueError("recovery was already attempted; inspect its artifacts")
    with (
        closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as src,
        closing(sqlite3.connect(backup)) as dest,
    ):
        src.backup(dest)
    client = LLMClient(run / "llm.jsonl", request_budget=0, concurrency=1)
    env = RepoEnvironment(
        Path(settings["repo"]),
        Path(settings["verifier"]),
        episode / "logs",
        tuple(settings["editable"]),
    )
    runner = AgentRunner(
        client,
        env,
        episode,
        max_steps=settings["max_steps"],
        wall_seconds=settings["wall_seconds"],
        seed=settings["seed"],
        run_id=settings["run_id"],
        episode_id=settings["episode_id"],
        memory_prompt=settings["memory_prompt"],
    )
    try:
        async with AsyncSqliteSaver.from_conn_string(str(database)) as saver:
            runner.graph = runner.builder.compile(checkpointer=saver)
            snap = await runner.graph.aget_state(runner.config)
            if snap.next != ("decide",) or not snap.values:
                raise ValueError("checkpoint is not awaiting the failed decision")
            if (
                env.tree_hash() != snap.values["environment_tree_hash"]
                or git(env.root, "rev-parse", "HEAD")
                != snap.values["environment_checkpoint"]
                or snap.values["step"] >= settings["max_steps"]
            ):
                raise ValueError("repository or action budget differs from checkpoint")
            state = {
                **snap.values,
                **runner.response_failure(ModelResponseError(last[-1]["request_id"])),
            }
            result = {**state, **await runner.execute(state)}
            await runner.graph.aupdate_state(snap.config, result, as_node="execute")
            await runner.export_history()
        (episode / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    finally:
        await client.close()
    revision = git(Path.cwd(), "rev-parse", "HEAD")
    row = {
        "episode_id": settings["episode_id"],
        "task_id": task["task_id"],
        "task_path": str(task_path.resolve()),
        "split": task["split"],
        "family": task["family"],
        "mode": "none",
        "seed": settings["seed"],
        "model": last[-1]["model"],
        "max_steps": settings["max_steps"],
        "verifier": settings["verifier"],
        "repo": settings["repo"],
        "success": result["outcome"]["success"],
        "steps": result["step"],
        "code_commit": revision,
        "decision_failure": result["decision_failure"],
        "initial_policy_revision": manifest["revision"],
    }
    (episode / "episode.json").write_text(json.dumps(row, indent=2) + "\n")
    row.update(phase="training", episode_dir=str(episode), experiment_revision=revision)
    (episode / "response-finalization.json").write_text(
        json.dumps(
            {
                "original_batch_status": status,
                "source_checkpoint": snap.config,
                "backup_sha256": digest(backup.read_bytes()),
                "request_id": last[-1]["request_id"],
                "logged_attempts": [
                    {k: c[k] for k in ("attempt", "status", "schema", "usage")}
                    for c in last
                ],
                "finalization_revision": revision,
                "policy": "same current code, native graph checkpoint and remaining action budget; no model request or edit",
                "result": row,
            },
            indent=2,
        )
        + "\n"
    )
    with (run / "results.jsonl").open("a") as handle:
        handle.write(json.dumps(row) + "\n")
    (run / "status-before-response-finalization.json").write_text(
        json.dumps(status, indent=2) + "\n"
    )
    (run / "status.json").write_text(
        json.dumps(
            {
                **status,
                "completed_episodes": len(rows) + 1,
                "response_finalization": str(episode / "response-finalization.json"),
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(row, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("runs/forkrsi/source-v2"))
    args = parser.parse_args()
    asyncio.run(finalize(args.source))


if __name__ == "__main__":
    main()
