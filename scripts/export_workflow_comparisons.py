"""Deterministic representative selection after complete transfer; all directions retained."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forkmem.replay import replay_case
from forkmem.workflows.evaluation import load_transfer


def export(run: Path, destination: Path, replay_root: Path) -> None:
    _, rows, _ = load_transfer(run)
    lookup = {(r["task_id"], r["seed"], r["action_budget"], r["mode"]): r for r in rows}
    source = [
        r
        for r in rows
        if r["mode"] == "fork_verified" and r["action_budget"] == 8 and r["memory_ids"]
    ]
    source.sort(key=lambda r: (r["task_id"], r["seed"]))
    categories: dict[str, list[dict]] = {
        name: []
        for name in [
            "paired_win",
            "paired_loss",
            "same_outcome_different_repair_cost",
            "guarded_win",
            "guarded_loss",
        ]
    }
    for row in source:
        flat = lookup[(row["task_id"], row["seed"], 8, "flat_verified")]
        guard = lookup[(row["task_id"], row["seed"], 8, "unguarded_verified")]
        if row["memory_ids"] != flat["memory_ids"]:
            raise ValueError("primary controls have different positive evidence IDs")
        if row["success"] and not flat["success"]:
            categories["paired_win"].append(row)
        if not row["success"] and flat["success"]:
            categories["paired_loss"].append(row)
        if row["success"] == flat["success"] and (
            row["steps"] != flat["steps"]
            or row["first_verifier_success"] != flat["first_verifier_success"]
        ):
            categories["same_outcome_different_repair_cost"].append(row)
        if row["success"] and not guard["success"]:
            categories["guarded_win"].append(row)
        if not row["success"] and guard["success"]:
            categories["guarded_loss"].append(row)
    destination.mkdir(parents=True, exist_ok=True)
    replay_root.mkdir(parents=True, exist_ok=False)
    selection = {}
    for name, candidates in categories.items():
        selection[name] = {
            "eligible_cells": len(candidates),
            "all_eligible_keys": [[r["task_id"], r["seed"], 8] for r in candidates],
            "selection_rule": "first lexicographic task/seed among all eligible eight-action cells; absence remains absence",
        }
        if not candidates:
            continue
        row = candidates[0]
        modes = ["none", "flat_verified", "fork_verified"]
        if name.startswith("guarded_"):
            modes.append("unguarded_verified")
        task = json.loads(Path(row["task_path"]).read_text())
        branches = []
        for mode in modes:
            cell = lookup[(row["task_id"], row["seed"], 8, mode)]
            directory = Path(cell["episode_dir"])
            events = [
                json.loads(x)
                for x in (directory / "trajectory.jsonl").read_text().splitlines()
            ]
            outcome = json.loads((directory / "result.json").read_text())["outcome"]
            accepted = [
                e["action"]
                for e in events
                if not e["feedback"].startswith("Tool rejected action:")
            ]
            branches.append(
                {
                    "kind": mode,
                    "actions": accepted,
                    "original_trajectory": events,
                    "rejected_tools_omitted_from_replay": sum(
                        e["feedback"].startswith("Tool rejected action:")
                        for e in events
                    ),
                    "expected_success": cell["success"],
                    "expected_tree_sha256": outcome["tree_sha256"],
                    "retrieval": json.loads((directory / "retrieval.json").read_text()),
                    "source_episode": cell,
                    "observed_log": Path(outcome["log_path"]).read_text(),
                }
            )
        case = {
            "case_id": f"{row['task_id']}-{row['seed']}-budget8-{name}",
            "case_type": "matched condition comparison, not an additional same-checkpoint DecisionFork",
            "selection": selection[name],
            "interpretation": "Observed matched task/seed outcomes and repair costs. Inspect actions and source evidence before attributing adoption; this case alone is not a causal estimate or a population claim. Replays apply accepted recorded actions; rejected tools remain in the archived trajectory.",
            "files": task["files"],
            "verifier": task["verifier"],
            "features": task["features"],
            "branches": branches,
        }
        path = destination / f"{name}.json"
        path.write_text(json.dumps(case, indent=2) + "\n")
        result = replay_case(path, replay_root / name)
        selection[name].update(
            selected=[row["task_id"], row["seed"], 8],
            case=str(path),
            all_replays_match=result["all_match"],
        )
    (destination / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    print(json.dumps(selection, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/v2/comparisons"))
    parser.add_argument("--replays", type=Path, required=True)
    args = parser.parse_args()
    export(args.runs, args.output, args.replays)
