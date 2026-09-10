"""Audit source candidate accounting and decision-level verification yield."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from forkmem.evaluation import clustered_interval, load_complete
from forkmem.models import DecisionFork
from forkmem.workflows.analysis import aligned_contrasts, read_workflow_cases

parser = argparse.ArgumentParser()
parser.add_argument("--runs", type=Path, required=True)
parser.add_argument(
    "--output", type=Path, default=Path("artifacts/v2/source_summary.json")
)
args = parser.parse_args()
source = args.runs
manifest, episodes = load_complete(source)
corpus = json.loads((source / "corpus.json").read_text())
rows = []
rejected = Counter()
returned = 0
for value in corpus["forks"]:
    fork = DecisionFork.model_validate(value)
    paths = [
        p
        for p in (source / "forks").glob("*/fork.json")
        if json.loads(p.read_text())["fork_id"] == fork.fork_id
    ]
    assert len(paths) == 1
    proposals = json.loads((paths[0].parent / "proposals.json").read_text())[
        "proposals"
    ]
    returned += len(proposals)
    seen = {fork.factual.first_action.content}
    accepted = 0
    for proposal in proposals:
        action = proposal["action"]
        if action["tool"] != "write":
            rejected["non_write"] += 1
            continue
        if action["content"] in seen:
            rejected["duplicate_code"] += 1
            continue
        if accepted >= manifest["config"]["branches"]:
            rejected["over_requested_limit"] += 1
            continue
        seen.add(action["content"])
        accepted += 1
    assert accepted == len(fork.alternatives)
    for branch in fork.alternatives:
        try:
            cases = read_workflow_cases(branch.outcomes[-1])
            contrasts = aligned_contrasts(
                fork.factual.outcomes[-1], branch.outcomes[-1]
            )
            observation = {
                "structured": True,
                "clean_path_success": cases[0]["success"],
                "case_successes": sum(c["success"] for c in cases.values()),
                "case_total": len(cases),
                "locally_repaired_but_not_globally_valid": any(
                    c["repaired_obligations"] for c in contrasts
                )
                and not branch.outcomes[-1].success,
                "aligned_contrasts": contrasts,
            }
        except ValueError as exc:
            if str(exc) != "expected exactly one workflow observation record":
                raise
            observation = {"structured": False, "reason": str(exc)}
        rows.append(
            {
                "task_id": fork.fork_id,
                "source_episode": fork.provenance["episode"],
                "family": fork.state.task_family,
                "branch_id": branch.branch_id,
                "success": branch.outcomes[-1].success,
                "evidence": branch.evidence_status.value,
                **observation,
            }
        )
calls = [json.loads(x) for x in (source / "llm.jsonl").read_text().splitlines()]
root_ids = {r["episode_id"] for r in episodes}
branch_calls = [c for c in calls if c["episode_id"] not in root_ids]
execution_costs = []
for path in source.rglob("*.json"):
    if path.parent.name.endswith("logs"):
        value = json.loads(path.read_text())
        if "execution_id" in value and "wall_seconds" in value:
            execution_costs.append(value)
proposal_calls = [c for c in branch_calls if c.get("schema") == "Proposals"]
continuation_calls = [c for c in branch_calls if c.get("schema") != "Proposals"]
summary = {
    "source_revision": manifest["revision"],
    "training_episodes": len(episodes),
    "training_successes": sum(r["success"] for r in episodes),
    "failure_families": dict(
        Counter(r["family"] for r in episodes if not r["success"])
    ),
    "forks": len(corpus["forks"]),
    "requested_proposals": len(corpus["forks"]) * manifest["config"]["branches"],
    "returned_proposals": returned,
    "excluded_before_execution": dict(rejected),
    "executed_alternatives": len(rows),
    "successful_alternatives": sum(r["success"] for r in rows),
    "precision_source_fork_cluster_interval": clustered_interval(rows, "success"),
    "partial_repairs_not_globally_valid": sum(
        r.get("locally_repaired_but_not_globally_valid", False) for r in rows
    ),
    "total_model_tokens": sum(c.get("usage", {}).get("total_tokens", 0) for c in calls),
    "branch_discovery_tokens": sum(
        c.get("usage", {}).get("total_tokens", 0) for c in branch_calls
    ),
    "proposal_generation_tokens": sum(
        c.get("usage", {}).get("total_tokens", 0) for c in proposal_calls
    ),
    "alternative_continuation_tokens": sum(
        c.get("usage", {}).get("total_tokens", 0) for c in continuation_calls
    ),
    "source_training_tokens": sum(
        c.get("usage", {}).get("total_tokens", 0)
        for c in calls
        if c["episode_id"] in root_ids
    ),
    "verifier_executions": len(execution_costs),
    "verifier_wall_seconds_sum": sum(c["wall_seconds"] for c in execution_costs),
    "elapsed_wall_seconds": json.loads((source / "status.json").read_text())[
        "wall_seconds"
    ],
    "rows": rows,
}
output = args.output
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(summary, indent=2) + "\n")
print({k: v for k, v in summary.items() if k != "rows"})
