"""Checkpointed coding agent with explicit budgets and immutable verifier."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from forkmem.environment import RepoEnvironment, digest, git
from forkmem.llm import LLMClient, ModelResponseError
from forkmem.memory import ForkStore, negative_context, render_memory, retrieve
from forkmem.models import Action, Outcome, StateFingerprint


class AgentState(TypedDict):
    task: str
    messages: list[dict[str, Any]]
    action: dict[str, Any]
    step: int
    done: bool
    checkpoint: str
    outcome: dict[str, Any]
    environment_checkpoint: str
    environment_tree_hash: str
    decision_failure: NotRequired[dict[str, str]]


class AgentRunner:
    def __init__(
        self,
        client: LLMClient,
        env: RepoEnvironment,
        output: Path,
        *,
        max_steps: int = 8,
        wall_seconds: float = 240,
        seed: int = 0,
        run_id: str = "agent",
        episode_id: str | None = None,
        memory_prompt: str = "",
    ):
        self.client = client
        self.env = env
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.max_steps = max_steps
        self.wall_seconds = wall_seconds
        self.seed = seed
        self.run_id = run_id
        self.episode_id = episode_id or uuid4().hex
        self.memory_prompt = memory_prompt
        self.started = time.monotonic()
        graph = StateGraph(AgentState)
        graph.add_node("decide", self.decide)
        graph.add_node("execute", self.execute)
        graph.add_edge(START, "decide")
        graph.add_edge("decide", "execute")
        graph.add_conditional_edges(
            "execute", lambda state: END if state["done"] else "decide"
        )
        self.builder = graph
        self.graph = graph.compile(checkpointer=InMemorySaver())
        self.config: Any = {
            "configurable": {"thread_id": self.episode_id},
            "recursion_limit": max_steps * 2 + 4,
        }

    async def decide(self, state: AgentState) -> dict[str, Any]:
        observations = [
            {
                "step": event["step"],
                "action": event["action"],
                "feedback": event["feedback"],
                "test_success": event["outcome"]["success"]
                if event.get("outcome")
                else None,
            }
            for event in state["messages"]
        ]
        prompt = f"You are a coding agent. Solve the task in this isolated Python repository.\nTask: {state['task']}\nAvailable files: {git(self.env.root, 'ls-files')}\nTools: read(path), search(content), write(path,content), test(), finish(). Only {self.env.editable} may be changed. write replaces the complete file. Test is a deterministic external verifier; never try to bypass it. Read the source and contract before editing. You have {self.max_steps - state['step']} actions left.\nPrior-task memory (may be inapplicable; check the current contract):\n{self.memory_prompt}\nCurrent trajectory:\n{json.dumps(observations, ensure_ascii=False)[-40000:]}"
        public_files = git(self.env.root, "ls-files").splitlines()
        read_paths = {
            e["action"]["path"]
            for e in state["messages"]
            if e["action"]["tool"] == "read"
        }
        missing = [
            name
            for name in ("README.md", "deployment.json", "solution.py")
            if name in public_files and name not in read_paths
        ]
        prompt += (
            "\nThe trajectory lists actions ALREADY executed, not actions to repeat. "
            "Choose exactly one NEXT action that advances the task. "
            "Do not reread an unchanged file whose contents are already in the trajectory. "
            f"Files already read: {sorted(read_paths)}. Still unread public task files: {missing}. "
            "Read missing contract/deployment/source context first. Once available, write the "
            "complete repaired solution.py, then test it. If a test failed, use that failure "
            "to produce a changed complete write and test again within the remaining budget. "
            "Never submit unchanged incomplete source or repeat reads until the budget expires."
        )
        try:
            action = await self.client.generate(
                prompt,
                Action,
                seed=self.seed + state["step"],
                episode_id=self.episode_id,
                run_id=self.run_id,
            )
        except ModelResponseError as exc:
            return self.response_failure(exc)
        return {"action": action.model_dump()}

    @staticmethod
    def response_failure(exc: ModelResponseError) -> dict[str, Any]:
        # No fabricated edit and no extra model request. Apply the existing final
        # verification to the current repository, consuming one terminal action.
        return {
            "action": Action(
                tool="finish",
                thought_summary="Model schema repair exhausted; verify existing code.",
            ).model_dump(),
            "decision_failure": {
                "error_type": type(exc).__name__,
                "request_id": exc.request_id,
                "policy": "verify_current_code_without_extra_model_request",
            },
        }

    async def execute(self, state: AgentState) -> dict[str, Any]:
        action = Action.model_validate(state["action"])
        checkpoint = self.env.checkpoint()
        outcome: Outcome | None = None
        try:
            if action.tool in {"test", "finish"}:
                outcome = await asyncio.to_thread(
                    self.env.verify, checkpoint, self.seed
                )
                feedback = Path(outcome.log_path).read_text()[:16000]
            else:
                feedback = self.env.execute(action)
        except (ValueError, FileNotFoundError, IsADirectoryError) as exc:
            feedback = f"Tool rejected action: {type(exc).__name__}: {exc}"
        step = state["step"] + 1
        done = (
            action.tool == "finish"
            or bool(outcome and outcome.success)
            or step >= self.max_steps
            or time.monotonic() - self.started >= self.wall_seconds
        )
        if done and outcome is None:
            outcome = await asyncio.to_thread(self.env.verify, checkpoint, self.seed)
        event = {
            "step": state["step"],
            "checkpoint": checkpoint,
            "action": action.model_dump(),
            "action_origin": "protocol_failure_finalization"
            if state.get("decision_failure")
            else "model_response",
            "decision_failure": state.get("decision_failure"),
            "feedback": feedback,
            "outcome": outcome.model_dump() if outcome else None,
            "tree_sha256": self.env.tree_hash(),
        }
        with (self.output / "trajectory.jsonl").open("a") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return {
            "messages": [*state["messages"], event],
            "step": step,
            "done": done,
            "checkpoint": checkpoint,
            "environment_checkpoint": self.env.checkpoint(),
            "environment_tree_hash": self.env.tree_hash(),
            "outcome": outcome.model_dump() if outcome else state["outcome"],
        }

    async def run(
        self,
        task: str,
        *,
        prefix: list[dict[str, Any]] | None = None,
        start_step: int = 0,
    ) -> dict[str, Any]:
        self.started = time.monotonic()
        initial: AgentState = {
            "task": task,
            "messages": prefix or [],
            "action": {},
            "step": start_step,
            "done": False,
            "checkpoint": git(self.env.root, "rev-parse", "HEAD"),
            "outcome": {},
            "environment_checkpoint": git(self.env.root, "rev-parse", "HEAD"),
            "environment_tree_hash": self.env.tree_hash(),
        }
        (self.output / "runner.json").write_text(
            json.dumps(
                {
                    "task": task,
                    "agent_prompt_version": "forkrsi-next-action-v1",
                    "response_failure_policy": "verify-current-code-v1",
                    "repo": str(self.env.root),
                    "verifier": str(self.env.verifier),
                    "editable": self.env.editable,
                    "max_steps": self.max_steps,
                    "wall_seconds": self.wall_seconds,
                    "seed": self.seed,
                    "run_id": self.run_id,
                    "episode_id": self.episode_id,
                    "memory_prompt": self.memory_prompt,
                },
                indent=2,
            )
        )
        if start_step >= self.max_steps:
            outcome = await asyncio.to_thread(
                self.env.verify, initial["checkpoint"], self.seed
            )
            result: dict[str, Any] = {
                **initial,
                "done": True,
                "outcome": outcome.model_dump(),
            }
        else:
            async with AsyncSqliteSaver.from_conn_string(
                str(self.output / "checkpoints.sqlite")
            ) as saver:
                self.graph = self.builder.compile(checkpointer=saver)
                result = dict(await self.graph.ainvoke(initial, self.config))
                await self.export_history()
        (self.output / "result.json").write_text(json.dumps(result, indent=2))
        return result

    async def export_history(self) -> None:
        history = []
        async for snapshot in self.graph.aget_state_history(self.config):
            history.append(
                {
                    "config": snapshot.config,
                    "parent_config": snapshot.parent_config,
                    "next": snapshot.next,
                    "values": snapshot.values,
                }
            )
        (self.output / "graph_checkpoints.json").write_text(
            json.dumps(history, indent=2)
        )


async def resume_episode(
    episode: Path, output: Path, client: LLMClient, checkpoint_id: str | None = None
) -> dict[str, Any]:
    """Fork a persisted graph checkpoint and its matching filesystem into a fresh run."""
    episode = episode.resolve()
    settings = json.loads((episode / "runner.json").read_text())
    database = episode / "checkpoints.sqlite"
    if not database.is_file():
        raise ValueError("episode has no persistent native checkpoint database")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # SQLite backup includes committed WAL pages and does not mutate the source run.
    with (
        closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(output / "checkpoints.sqlite")) as destination,
    ):
        source.backup(destination)
    base = RepoEnvironment(
        Path(settings["repo"]),
        Path(settings["verifier"]),
        output / "logs",
        tuple(settings["editable"]),
    )
    runner = AgentRunner(
        client,
        base,
        output,
        max_steps=settings["max_steps"],
        wall_seconds=settings["wall_seconds"],
        seed=settings["seed"],
        run_id="resume-" + output.name,
        episode_id=settings["episode_id"],
        memory_prompt=settings["memory_prompt"],
    )
    if checkpoint_id:
        runner.config["configurable"]["checkpoint_id"] = checkpoint_id
    async with AsyncSqliteSaver.from_conn_string(
        str(output / "checkpoints.sqlite")
    ) as saver:
        runner.graph = runner.builder.compile(checkpointer=saver)
        snapshot = await runner.graph.aget_state(runner.config)
        empty_initial = not snapshot.values
        if empty_initial:
            trajectory = episode / "trajectory.jsonl"
            if (
                trajectory.exists()
                and trajectory.read_text().strip()
                or git(base.root, "status", "--porcelain")
            ):
                raise ValueError(
                    "missing graph checkpoint after existing edits/actions"
                )
            # A sibling can be cancelled after runner/DB creation but before START
            # is persisted. No action has executed; preserve the untouched initial
            # repository and use the original full remaining action budget.
            checkpoint = git(base.root, "rev-parse", "HEAD")
            runner.env = base.fork(checkpoint, output / "repo", output / "logs")
            initial: AgentState = {
                "task": settings["task"],
                "messages": [],
                "action": {},
                "step": 0,
                "done": False,
                "checkpoint": checkpoint,
                "outcome": {},
                "environment_checkpoint": checkpoint,
                "environment_tree_hash": runner.env.tree_hash(),
            }
        else:
            if not snapshot.next:
                raise ValueError("choose a nonterminal checkpoint to resume")
            runner.env = base.fork(
                snapshot.values["environment_checkpoint"],
                output / "repo",
                output / "logs",
            )
            if runner.env.tree_hash() != snapshot.values["environment_tree_hash"]:
                raise ValueError("filesystem does not match persisted graph checkpoint")
        (output / "resume.json").write_text(
            json.dumps(
                {
                    "source_episode": str(episode),
                    "source_config": snapshot.config,
                    "empty_initial_checkpoint": empty_initial,
                    "policy": "same remaining action budget; fresh per-invocation wall timeout",
                },
                indent=2,
            )
        )
        (output / "runner.json").write_text(
            json.dumps({**settings, "repo": str(runner.env.root)}, indent=2)
        )
        result = dict(
            await runner.graph.ainvoke(
                initial if empty_initial else None,
                runner.config if empty_initial else snapshot.config,
            )
        )
        await runner.export_history()
    (output / "result.json").write_text(json.dumps(result, indent=2))
    return result


async def run_task(
    task_path: Path,
    output: Path,
    client: LLMClient,
    *,
    store: ForkStore | None = None,
    mode: str = "none",
    seed: int = 0,
    max_steps: int = 8,
    prepared_memory: tuple[str, list[str]] | None = None,
) -> dict[str, Any]:
    task = json.loads(task_path.read_text())
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    verifier = output / "verifier.py"
    verifier.write_text(task["verifier"])
    env = RepoEnvironment.create(
        output / "repo", task["files"], verifier, output / "logs"
    )
    state = StateFingerprint(
        task_family=task["family"],
        features=task["features"],
        summary=task["description"],
        checkpoint=git(env.root, "rev-parse", "HEAD"),
    )
    items = retrieve(store, state, mode) if store else []
    memory_prompt = render_memory(items, mode)
    memory_ids = [f.fork_id for f, _, _ in items]
    if store and mode == "negative":
        memory_prompt, memory_ids = negative_context(store, state)
    if prepared_memory is not None:
        memory_prompt, memory_ids = prepared_memory
    (output / "retrieval.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "fork_ids": memory_ids,
                "prompt": memory_prompt,
            },
            indent=2,
        )
    )
    runner = AgentRunner(
        client,
        env,
        output,
        seed=seed,
        max_steps=max_steps,
        episode_id=output.name + "-" + digest(str(output).encode())[:12],
        memory_prompt=memory_prompt,
    )
    result = await runner.run(task["description"])
    metadata = {
        "episode_id": runner.episode_id,
        "task_id": task["task_id"],
        "task_path": str(task_path.resolve()),
        "split": task["split"],
        "family": task["family"],
        "mode": mode,
        "seed": seed,
        "model": client.model,
        "max_steps": max_steps,
        "verifier": str(verifier),
        "repo": str(env.root),
        "success": result["outcome"]["success"],
        "steps": result["step"],
        "code_commit": git(Path.cwd(), "rev-parse", "HEAD"),
        "decision_failure": result.get("decision_failure"),
    }
    (output / "episode.json").write_text(json.dumps(metadata, indent=2))
    return metadata
