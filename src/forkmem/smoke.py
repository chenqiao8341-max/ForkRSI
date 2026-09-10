"""First auditable fork: a declared seeded failure, real model proposals and tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from forkmem.environment import RepoEnvironment, git
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


async def run_smoke(output: Path, task_path: Path) -> Path:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    task = json.loads(task_path.read_text())
    verifier = output / "verifier.py"
    verifier.write_text(task["verifier"])
    env = RepoEnvironment.create(
        output / "base", task["files"], verifier, output / "logs"
    )
    checkpoint = git(env.root, "rev-parse", "HEAD")
    factual_env = env.fork(checkpoint, output / "factual", output / "factual_logs")
    action = Action.model_validate(task["factual_action"])
    factual_env.execute(action)
    factual_outcome = await asyncio.to_thread(factual_env.verify, checkpoint)
    if factual_outcome.success:
        raise RuntimeError("seeded factual action unexpectedly succeeded")
    trajectory = output / "factual_trajectory.jsonl"
    trajectory.write_text(
        json.dumps(
            {
                "checkpoint": checkpoint,
                "action": action.model_dump(),
                "outcome": factual_outcome.model_dump(),
                "origin": "seeded_smoke_fixture_not_model_policy",
            }
        )
        + "\n"
    )
    factual = Branch(
        kind="factual",
        first_action=action,
        trajectory_ref=str(trajectory),
        evidence_status=EvidenceStatus.OBSERVED,
        outcomes=[factual_outcome],
        confidence=1,
    )
    client = LLMClient(output / "llm.jsonl", request_budget=8)
    prompt = f"Task: {task['description']}\nFiles before failed action: {json.dumps(task['files'])}\nFailed action: {action.model_dump_json()}\nObserved failure: {Path(factual_outcome.log_path).read_text()[:10000]}\nPropose 3 substantively different alternative write actions for solution.py from the SAME pre-action state. Include at least two plausible competing hypotheses about why the code failed. Explain prerequisites and risk. Features available: {json.dumps(task['features'])}. Predictions are hypotheses, not facts."
    try:
        proposals = await client.generate(
            prompt,
            Proposals,
            temperature=0.8,
            max_tokens=4000,
            episode_id="seeded-smoke",
        )
    finally:
        await client.close()
    (output / "proposals.json").write_text(proposals.model_dump_json(indent=2))
    alternatives = []
    seen = {action.content}
    for index, proposal in enumerate(proposals.proposals):
        if proposal.action.tool != "write" or proposal.action.content in seen:
            continue
        seen.add(proposal.action.content)
        branch_env = env.fork(
            checkpoint, output / f"branch_{index}", output / f"branch_{index}_logs"
        )
        branch_env.execute(proposal.action)
        outcome = await asyncio.to_thread(branch_env.verify, checkpoint)
        trace = output / f"branch_{index}.jsonl"
        trace.write_text(
            json.dumps(
                {
                    "checkpoint": checkpoint,
                    "action": proposal.action.model_dump(),
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
            evidence_status=EvidenceStatus.IMAGINED,
        )
        alternatives.append(update_evidence(branch, outcome, factual_outcome.reward))
    if len(alternatives) < 2:
        raise RuntimeError("need at least two distinct executable alternatives")
    fork = DecisionFork(
        source_episode_id="seeded-smoke-" + uuid4().hex,
        pivot_step=0,
        state=StateFingerprint(
            task_family=task["family"],
            features=task["features"],
            summary=task["description"],
            checkpoint=checkpoint,
        ),
        factual=factual,
        alternatives=alternatives,
        applicability=Applicability(requires=task["features"]),
        lesson="Compare explicit presence against truthiness when zero is valid; use only verified alternatives under matching contract.",
        provenance={
            "origin": "seeded smoke failure; model-generated alternatives",
            "code_commit": git(Path.cwd(), "rev-parse", "HEAD"),
            "model": client.model,
            "verifier": factual_outcome.verifier,
            "task_path": str(task_path),
            "checkpoint": checkpoint,
        },
    )
    store = SQLiteForkStore(output / "memory.sqlite")
    store.put(fork)
    store.close()
    destination = output / "fork.json"
    destination.write_text(fork.model_dump_json(indent=2))
    if not any(
        b.evidence_status == EvidenceStatus.REPLAY_VERIFIED for b in alternatives
    ):
        raise RuntimeError("no executed alternative succeeded; inspect fork.json")
    return destination
