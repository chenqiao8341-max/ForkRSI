"""Independent deterministic replay audit; never mutates the benchmark corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forkmem.environment import RepoEnvironment
from forkmem.lifecycle import add_execution
from forkmem.memory import SQLiteForkStore
from forkmem.models import DecisionFork, EvidenceStatus


def replay_corpus(run_dir: Path, output: Path, repeats: int = 2) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    corpus_path = run_dir / "corpus.json"
    if not corpus_path.exists():
        raise ValueError("wait for frozen corpus before replay auditing")
    forks = [
        DecisionFork.model_validate(f)
        for f in json.loads(corpus_path.read_text())["forks"]
    ]
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    store = SQLiteForkStore(output / "replay_memory.sqlite")
    records = []
    try:
        for index, fork in enumerate(forks):
            store.put(fork)
            source = Path(fork.provenance["episode"])
            metadata = json.loads((source / "episode.json").read_text())
            base = RepoEnvironment(
                Path(metadata["repo"]),
                Path(metadata["verifier"]),
                output / f"base_{index}_logs",
            )
            for branch_index, branch in enumerate(fork.alternatives):
                for repeat in range(repeats):
                    name = f"fork_{index}_branch_{branch_index}_repeat_{repeat}"
                    env = base.fork(
                        fork.state.checkpoint, output / name, output / (name + "_logs")
                    )
                    for action in [branch.first_action, *branch.continuation_actions]:
                        if action.tool not in {"test", "finish"}:
                            env.execute(action)
                    outcome = env.verify(fork.state.checkpoint, seed=repeat + 1)
                    matches = (
                        outcome.success == branch.outcomes[-1].success
                        and outcome.tree_sha256 == branch.outcomes[-1].tree_sha256
                    )
                    records.append(
                        {
                            "fork_id": fork.fork_id,
                            "branch_id": branch.branch_id,
                            "repeat": repeat,
                            "matches": matches,
                            "outcome": outcome.model_dump(),
                        }
                    )
                    with (output / "executions.jsonl").open("a") as handle:
                        handle.write(json.dumps(records[-1]) + "\n")
                    if not matches:
                        raise RuntimeError(
                            "replay diverged from original execution; no stability claim permitted"
                        )
                    add_execution(store, fork.fork_id, branch.branch_id, outcome)
        final = store.all()
        summary = {
            "source_run": str(run_dir.resolve()),
            "forks": len(forks),
            "unique_alternative_branches": sum(len(f.alternatives) for f in forks),
            "additional_replay_executions": len(records),
            "all_replays_match": all(row["matches"] for row in records),
            "repeatedly_verified_branches": sum(
                b.evidence_status == EvidenceStatus.REPEATEDLY_VERIFIED
                for f in final
                for b in f.alternatives
            ),
            "stable_forks_with_positive_alternative": sum(
                any(
                    b.evidence_status == EvidenceStatus.REPEATEDLY_VERIFIED
                    for b in f.alternatives
                )
                for f in final
            ),
            "scope": "repeatability at the original checkpoint, not cross-instance generalization",
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2))
        (output / "corpus.json").write_text(
            json.dumps({"forks": [f.model_dump(mode="json") for f in final]}, indent=2)
        )
        return summary
    finally:
        store.close()
