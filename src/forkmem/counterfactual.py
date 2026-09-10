"""Failure-to-fork pipeline with reproducible factual comparison."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from forkmem.agent import AgentRunner
from forkmem.environment import RepoEnvironment, git, git_blob
from forkmem.llm import LLMClient
from forkmem.memory import SQLiteForkStore, update_evidence
from forkmem.models import (
    Action,
    Applicability,
    Branch,
    DecisionFork,
    EvidenceStatus,
    Proposals,
    StateFingerprint,
)


def locate_pivots(events: list[dict[str, Any]], limit: int = 3) -> list[int]:
    """Recent state-changing actions; reads and test commands cannot be pivots."""
    return [
        i
        for i in range(len(events) - 1, -1, -1)
        if isinstance(events[i].get("action"), dict)
        and events[i]["action"].get("tool") == "write"
    ][:limit]


async def fork_episode(
    episode: Path,
    output: Path,
    client: LLMClient,
    *,
    branches: int = 3,
    cached_proposals: Proposals | None = None,
) -> Path:
    if not 2 <= branches <= 8:
        raise ValueError("execute between 2 and 8 branches")
    episode = episode.resolve()
    metadata = json.loads((episode / "episode.json").read_text())
    if metadata["success"]:
        raise ValueError("fork pipeline requires an observed failed episode")
    task = json.loads(Path(metadata["task_path"]).read_text())
    events = [
        json.loads(line)
        for line in (episode / "trajectory.jsonl").read_text().splitlines()
    ]
    pivots = locate_pivots(events)
    if not pivots:
        raise ValueError(
            "no state-changing pivot; retain failure without positive memory"
        )
    pivot_index = pivots[0]
    pivot = events[pivot_index]
    checkpoint = pivot["checkpoint"]
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = RepoEnvironment(
        Path(metadata["repo"]), Path(metadata["verifier"]), output / "base_logs"
    )
    actual = base.fork(checkpoint, output / "factual", output / "factual_logs")
    for event in events[pivot_index:]:
        action = Action.model_validate(event["action"])
        if action.tool not in {"test", "finish"}:
            try:
                actual.execute(action)
            except (ValueError, FileNotFoundError, IsADirectoryError):
                pass  # Replay rejected actions without introducing a different edit.
    actual_outcome = await asyncio.to_thread(
        actual.verify, checkpoint, metadata["seed"]
    )
    if actual_outcome.success:
        raise RuntimeError(
            "factual failure did not reproduce; do not create comparative memory"
        )
    factual_trace = output / "factual.jsonl"
    factual_trace.write_text(
        json.dumps(
            {
                "source_events": events[pivot_index:],
                "outcome": actual_outcome.model_dump(),
            }
        )
        + "\n"
    )
    factual = Branch(
        kind="factual",
        first_action=Action.model_validate(pivot["action"]),
        trajectory_ref=str(factual_trace),
        evidence_status=EvidenceStatus.OBSERVED,
        outcomes=[actual_outcome],
        confidence=1,
    )
    pre_files = {
        name: git_blob(base.root, checkpoint, name)
        for name in git(actual.root, "ls-files").splitlines()
    }
    prompt = f"Task: {task['description']}\nSame checkpoint files: {json.dumps(pre_files)}\nRecent candidate pivot indices: {pivots}; selected most recent source edit {pivot_index}.\nFactual action: {json.dumps(pivot['action'])}\nSubsequent observed failure: {Path(actual_outcome.log_path).read_text()[:12000]}\nGenerate {branches} distinct alternative complete writes to solution.py, each with a suspected failure mechanism, prediction, minimal intervention, prerequisites and risk. Features: {json.dumps(task['features'])}. Do not claim predictions are verified."
    proposals = cached_proposals or await client.generate(
        prompt,
        Proposals,
        temperature=0.8,
        max_tokens=6000,
        seed=metadata["seed"],
        episode_id=episode.name,
        branch_id="proposal",
    )
    (output / "proposals.json").write_text(proposals.model_dump_json(indent=2))
    alternatives: list[Branch] = []
    seen = {factual.first_action.content}
    for index, proposal in enumerate(proposals.proposals):
        if len(alternatives) >= branches:
            break
        if proposal.action.tool != "write" or proposal.action.content in seen:
            continue
        seen.add(proposal.action.content)
        env = base.fork(
            checkpoint,
            output / f"alternative_{index}",
            output / f"alternative_{index}_logs",
        )
        env.execute(proposal.action)
        runner = AgentRunner(
            client,
            env,
            output / f"rollout_{index}",
            max_steps=metadata["max_steps"],
            seed=metadata["seed"],
            episode_id=episode.name + f"-branch-{index}",
        )
        alternative_event = {
            "step": pivot_index,
            "checkpoint": checkpoint,
            "action": proposal.action.model_dump(),
            "feedback": "source updated",
            "outcome": None,
            "tree_sha256": env.tree_hash(),
        }
        await runner.run(
            task["description"],
            prefix=[*events[:pivot_index], alternative_event],
            start_step=pivot_index + 1,
        )
        # The final oracle is associated with the original common intervention state.
        outcome = await asyncio.to_thread(env.verify, checkpoint, metadata["seed"])
        trace = output / f"branch_{index}.jsonl"
        trace.write_text(
            json.dumps(
                {
                    "checkpoint": checkpoint,
                    "first_action": proposal.action.model_dump(),
                    "continuation": str(runner.output / "trajectory.jsonl"),
                    "outcome": outcome.model_dump(),
                }
            )
            + "\n"
        )
        branch = Branch(
            kind="counterfactual",
            first_action=proposal.action,
            trajectory_ref=str(trace),
            predicted_outcome=proposal.predicted_outcome,
            continuation_actions=[
                Action.model_validate(event["action"])
                for event in json.loads((runner.output / "result.json").read_text())[
                    "messages"
                ]
                if event["step"] > pivot_index
            ],
            evidence_status=EvidenceStatus.IMAGINED,
        )
        alternatives.append(update_evidence(branch, outcome, actual_outcome.reward))
    if not alternatives:
        raise RuntimeError("no distinct valid candidate; no memory written")
    fork = DecisionFork(
        source_episode_id=episode.name,
        pivot_step=pivot_index,
        state=StateFingerprint(
            task_family=task["family"],
            features=task["features"],
            summary=task["description"],
            checkpoint=checkpoint,
        ),
        factual=factual,
        alternatives=alternatives,
        applicability=Applicability(requires=task["features"]),
        lesson="Apply the alternative only under the recorded matching contract; the evidence covers the full continuation, not just the first edit.",
        provenance={
            "code_commit": git(Path.cwd(), "rev-parse", "HEAD"),
            "task_path": metadata["task_path"],
            "model": client.model,
            "pivot_candidates": pivots,
            "pivot_selection": "most recent modifying action",
            "episode": str(episode),
            "seed": metadata["seed"],
            "origin": "model_episode",
            "proposal_origin": "recovered_model_response"
            if cached_proposals
            else "live_model_response",
        },
    )
    destination = output / "fork.json"
    destination.write_text(fork.model_dump_json(indent=2))
    store = SQLiteForkStore(output / "memory.sqlite")
    store.put(fork)
    store.close()
    return destination
