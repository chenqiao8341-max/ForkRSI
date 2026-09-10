from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import httpx
import typer

from forkmem.agent import resume_episode
from forkmem.agent import run_task as execute_task
from forkmem.benchmark import benchmark
from forkmem.counterfactual import fork_episode
from forkmem.llm import LLMClient
from forkmem.memory import SQLiteForkStore
from forkmem.replay import export_fork_case, replay_case
from forkmem.reporting import build_report
from forkmem.smoke import run_smoke
from forkmem.stability import replay_corpus

app = typer.Typer(no_args_is_help=True)


@app.command()
def inspect_vllm() -> None:
    """Read live model metadata without changing the service."""

    async def inspect() -> None:
        client = LLMClient(Path("runs/inspect.jsonl"))
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=15) as http:
                response = await http.get(client.base_url + "/models")
                response.raise_for_status()
                typer.echo(json.dumps(response.json(), indent=2))
        finally:
            await client.close()

    asyncio.run(inspect())


@app.command()
def smoke(
    output: Path | None = None, task: Path = Path("data/task_specs/config_smoke.json")
) -> None:
    """Execute a seeded failure and >=2 real-model counterfactual branches."""
    target = output or Path("runs") / ("smoke-" + uuid4().hex[:8])
    result = asyncio.run(run_smoke(target, task))
    typer.echo(str(result))


@app.command("run-task")
def run_task_command(
    task: Annotated[Path, typer.Option()],
    output: Path | None = None,
    memory_mode: str = "none",
    memory_db: Path | None = None,
    seed: int = 0,
    max_steps: int = 8,
) -> None:
    """Run the real-model checkpointed coding agent on one MicroRepo."""
    target = output or Path("runs") / ("episode-" + uuid4().hex[:8])

    async def execute() -> None:
        client = LLMClient(Path("runs/llm.jsonl"))
        store = SQLiteForkStore(memory_db) if memory_db else None
        try:
            result = await execute_task(
                task,
                target,
                client,
                store=store,
                mode=memory_mode,
                seed=seed,
                max_steps=max_steps,
            )
            typer.echo(json.dumps(result, indent=2))
        finally:
            await client.close()
            if store:
                store.close()

    asyncio.run(execute())


@app.command("fork")
def fork_command(
    episode: Annotated[Path, typer.Option()],
    branches: int = 3,
    output: Path | None = None,
) -> None:
    """Generate and execute alternatives from a recorded failed episode."""
    target = output or Path("runs") / ("fork-" + uuid4().hex[:8])

    async def execute() -> None:
        client = LLMClient(Path("runs/fork_llm.jsonl"))
        try:
            typer.echo(
                str(
                    await fork_episode(
                        episode.parent if episode.is_file() else episode,
                        target,
                        client,
                        branches=branches,
                    )
                )
            )
        finally:
            await client.close()

    asyncio.run(execute())


@app.command("replay")
def replay_command(
    case: Annotated[Path, typer.Option()], output: Path | None = None
) -> None:
    """Re-execute a portable case without any model requests."""
    target = output or Path("runs") / ("replay-" + uuid4().hex[:8])
    typer.echo(json.dumps(replay_case(case, target), indent=2))


@app.command("benchmark")
def benchmark_command(
    config: Annotated[Path, typer.Option()],
    output: Path | None = None,
    resume: bool = False,
) -> None:
    """Build memory on training tasks and compare frozen-memory conditions."""
    target = output or Path("runs") / ("benchmark-" + uuid4().hex[:8])
    typer.echo(str(asyncio.run(benchmark(config, target, resume=resume))))


@app.command("report")
def report_command(
    runs: Annotated[Path, typer.Option()], output: Path = Path("docs/final_report.md")
) -> None:
    """Validate a complete experiment and generate tables, figures and report."""
    typer.echo(str(build_report(runs, output)))


@app.command("resume")
def resume_command(
    episode: Annotated[Path, typer.Option()],
    checkpoint_id: str | None = None,
    output: Path | None = None,
) -> None:
    """Resume a native graph checkpoint in an isolated matching worktree."""
    target = output or Path("runs") / ("resume-" + uuid4().hex[:8])

    async def execute() -> None:
        client = LLMClient(Path("runs/resume_llm.jsonl"))
        try:
            result = await resume_episode(episode, target, client, checkpoint_id)
            typer.echo(
                json.dumps(
                    {
                        "output": str(target),
                        "success": result["outcome"]["success"],
                        "steps": result["step"],
                    }
                )
            )
        finally:
            await client.close()

    asyncio.run(execute())


@app.command("audit-replays")
def audit_replays_command(
    runs: Annotated[Path, typer.Option()], output: Path | None = None, repeats: int = 2
) -> None:
    """Independently repeat a frozen corpus without modifying experiment memory."""
    target = output or Path("runs") / ("stability-" + uuid4().hex[:8])
    typer.echo(json.dumps(replay_corpus(runs, target, repeats), indent=2))


@app.command("export-case")
def export_case_command(
    fork: Annotated[Path, typer.Option()], output: Annotated[Path, typer.Option()]
) -> None:
    """Bundle an executed DecisionFork into a portable deterministic case."""
    typer.echo(str(export_fork_case(fork, output)))


if __name__ == "__main__":
    app()
