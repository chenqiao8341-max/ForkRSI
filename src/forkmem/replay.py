"""Portable executable cases, independent of original temporary worktrees."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forkmem.environment import RepoEnvironment, git, git_blob
from forkmem.models import Action


def replay_case(case_path: Path, output: Path) -> dict[str, Any]:
    case = json.loads(case_path.read_text())
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    verifier = output / "verifier.py"
    verifier.write_text(case["verifier"])
    base = RepoEnvironment.create(
        output / "base", case["files"], verifier, output / "logs"
    )
    checkpoint = git(base.root, "rev-parse", "HEAD")
    results = []
    for index, branch in enumerate(case["branches"]):
        env = base.fork(
            checkpoint, output / f"branch_{index}", output / f"logs_{index}"
        )
        for action in branch["actions"]:
            parsed = Action.model_validate(action)
            if parsed.tool not in {"test", "finish"}:
                env.execute(parsed)
        outcome = env.verify(checkpoint)
        results.append(
            {
                "kind": branch["kind"],
                "expected_success": branch["expected_success"],
                "matches": outcome.success == branch["expected_success"]
                and (
                    "expected_tree_sha256" not in branch
                    or outcome.tree_sha256 == branch["expected_tree_sha256"]
                ),
                "outcome": outcome.model_dump(),
            }
        )
    result = {
        "case": str(case_path),
        "all_match": all(row["matches"] for row in results),
        "branches": results,
    }
    (output / "replay.json").write_text(json.dumps(result, indent=2))
    if not result["all_match"]:
        raise RuntimeError("case failed deterministic replay; inspect replay.json")
    return result


def export_fork_case(fork_path: Path, output: Path) -> Path:
    """Bundle actual source files and complete plans, without depending on old paths."""
    from forkmem.models import DecisionFork

    fork = DecisionFork.model_validate_json(fork_path.read_text())
    episode = Path(fork.provenance["episode"])
    metadata = json.loads((episode / "episode.json").read_text())
    task = json.loads(Path(metadata["task_path"]).read_text())
    files = {
        name: git_blob(Path(metadata["repo"]), fork.state.checkpoint, name)
        for name in task["files"]
    }
    events = [
        json.loads(line)
        for line in (episode / "trajectory.jsonl").read_text().splitlines()
    ]
    branches = [
        {
            "kind": "factual",
            "actions": [event["action"] for event in events[fork.pivot_step :]],
            "expected_success": fork.factual.outcomes[-1].success,
            "expected_tree_sha256": fork.factual.outcomes[-1].tree_sha256,
            "observed_log": Path(fork.factual.outcomes[-1].log_path).read_text(),
        }
    ]
    for branch in fork.alternatives:
        branches.append(
            {
                "kind": "counterfactual",
                "actions": [
                    action.model_dump()
                    for action in [branch.first_action, *branch.continuation_actions]
                ],
                "expected_success": branch.outcomes[-1].success,
                "expected_tree_sha256": branch.outcomes[-1].tree_sha256,
                "evidence_status": branch.evidence_status.value,
                "prediction": branch.predicted_outcome,
                "observed_log": Path(branch.outcomes[-1].log_path).read_text(),
            }
        )
    case = {
        "case_id": fork.fork_id,
        "origin": "real model episode and executed alternatives",
        "files": files,
        "verifier": task["verifier"],
        "fork": fork.model_dump(mode="json"),
        "branches": branches,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(case, indent=2) + "\n")
    return output
