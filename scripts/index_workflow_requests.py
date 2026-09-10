"""Index actual transfer requests and their canonical/aliased condition cells."""

import argparse
import json
from pathlib import Path

from forkmem.workflows.evaluation import load_transfer

parser = argparse.ArgumentParser()
parser.add_argument("--runs", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
manifest, rows, calls = load_transfer(args.runs)
identities = {}
for row in rows:
    info = identities.setdefault(
        row["episode_id"],
        {
            "episode_dir": row["episode_dir"],
            "task_id": row["task_id"],
            "seed": row["seed"],
            "action_budget": row["action_budget"],
            "modes": [],
        },
    )
    info["modes"].append(row["mode"])
    if not row.get("reuse_of"):
        info["canonical_mode"] = row["mode"]
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open("w") as handle:
    for line, call in enumerate(calls, 1):
        identity = identities.get(call["episode_id"])
        entry = {
            "raw_log": str((args.runs / "llm.jsonl").resolve()),
            "raw_line": line,
            "request_id": call["request_id"],
            "episode_id": call["episode_id"],
            "attempt": call["attempt"],
            "model": call["model"],
            "status": call["status"],
            "usage": call.get("usage", {}),
            "latency_seconds": call["latency_seconds"],
            "executed_cell": identity,
            "unassigned_interrupted_attempt": identity is None,
            "source_revision": manifest["source_revision"],
            "transfer_revision": manifest["revision"],
        }
        handle.write(json.dumps(entry) + "\n")
print(
    {
        "indexed_calls": len(calls),
        "canonical_episodes": len(identities),
        "unassigned_calls": sum(c["episode_id"] not in identities for c in calls),
    }
)
