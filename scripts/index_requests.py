"""Recover unique episode/branch provenance for the earlier frozen run log format."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def index(run: Path, output: Path) -> dict[str, int]:
    rows = [
        json.loads(line) for line in (run / "results.jsonl").read_text().splitlines()
    ]
    roots = {row["episode_id"]: row for row in rows}
    forks = json.loads((run / "corpus.json").read_text())["forks"]
    calls = [json.loads(line) for line in (run / "llm.jsonl").read_text().splitlines()]
    records = []
    for line_number, call in enumerate(calls, 1):
        candidates = []
        if call["episode_id"] in roots:
            row = roots[call["episode_id"]]
            candidates.append((row["episode_id"], "root", row["phase"]))
        for fork in forks:
            seed = fork["provenance"]["seed"]
            source = next(
                row
                for row in rows
                if row["phase"] == "training"
                and row["task_id"] == fork["source_episode_id"]
                and row["seed"] == seed
            )
            if (
                call["schema"] == "Proposals"
                and call["episode_id"] == fork["source_episode_id"]
                and call["seed"] == seed
            ):
                candidates.append(
                    (source["episode_id"], "proposal", "counterfactual_proposal")
                )
            for branch in fork["alternatives"]:
                match = re.search(r"branch_(\d+)\.jsonl$", branch["trajectory_ref"])
                if (
                    match
                    and call["episode_id"]
                    == fork["source_episode_id"] + "-branch-" + match[1]
                    and seed + fork["pivot_step"] + 1
                    <= call["seed"]
                    < seed + source["max_steps"]
                ):
                    candidates.append(
                        (
                            source["episode_id"],
                            branch["branch_id"],
                            "counterfactual_rollout",
                        )
                    )
        candidates = list(set(candidates))
        if len(candidates) != 1:
            raise ValueError(
                f"ambiguous/unmapped provenance at raw line {line_number}: {candidates}"
            )
        episode_id, branch_id, phase = candidates[0]
        records.append(
            {
                "run_id": run.name,
                "episode_id": episode_id,
                "branch_id": branch_id,
                "phase": phase,
                "request_id": call["request_id"],
                "attempt": call["attempt"],
                "raw_log": str((run / "llm.jsonl").resolve()),
                "raw_line": line_number,
                "derived_fields": True,
                "model": call["model"],
                "usage": call.get("usage", {}),
                "latency_seconds": call["latency_seconds"],
                "status": call["status"],
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row) + "\n" for row in records))
    return {"indexed_calls": len(records), "ambiguous_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(index(args.runs, args.output))
