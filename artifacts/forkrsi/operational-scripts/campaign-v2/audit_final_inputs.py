"""Audit completed final inputs and case coverage without model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    campaign = Path(__file__).resolve().parent
    root = campaign.parents[2]
    seal = load(campaign / "final-freeze.json")["value"]
    protocol = seal["protocol"]
    manifest = load(root / protocol["manifest"])
    tasks = {row["task_id"]: row for row in manifest["tasks"] if row["split"] == "final"}
    pools = load(campaign / "pools.json")["pools"]
    checks = []
    cells = set()
    for metrics in sorted((campaign / "evaluations/final").rglob("metrics.json")):
        row = load(metrics)
        evidence_mode = row["mode"]
        if evidence_mode in {"success_only", "paired"}:
            selected = seal["selections"][evidence_mode]["C"]
            assert selected != seal["C0"], "This physical-grid audit is for the recorded campaign with distinct selected C."
            if row["compiler_id"] == seal["C0"]:
                logical_mode = evidence_mode + "_initial"
            elif row["compiler_id"] == selected:
                logical_mode = evidence_mode + "_evolved"
            else:
                raise AssertionError("unexpected compiler in final cells")
        else:
            logical_mode = evidence_mode
            assert row["compiler_id"] == seal["C0"]
        assert logical_mode in protocol["final_modes"]
        episode = metrics.parent
        entry = tasks[row["task_id"]]
        task_bytes = (root / entry["path"]).read_bytes()
        assert digest(task_bytes) == entry["sha256"], "task definition changed"
        task = json.loads(task_bytes)
        verifier = (episode / "verifier.py").read_bytes()
        assert verifier == task["verifier"].encode(), "actual verifier mismatch"
        metadata = load(episode / "episode.json")
        runner = load(episode / "runner.json")
        memory = load(episode / "compiler-memory.json")
        assert metadata["code_commit"] == seal["inputs"]["code_revision"]
        assert metadata["model"] == protocol["model"]
        assert metadata["split"] == "final"
        assert metadata["task_id"] == row["task_id"] and metadata["mode"] == row["mode"]
        assert runner["editable"] == ["solution.py"]
        assert runner["max_steps"] == protocol["max_steps"]
        assert metadata["steps"] <= runner["max_steps"]
        assert runner["wall_seconds"] == protocol["wall_seconds"]
        assert runner["seed"] == row["seed"] == 2701
        assert runner["response_failure_policy"] == "verify-current-code-v1"
        assert runner["agent_prompt_version"] == "forkrsi-next-action-v1"
        repo = episode / "repo"
        roots = subprocess.check_output(
            ["git", "rev-list", "--max-parents=0", "HEAD"], cwd=repo, text=True
        ).splitlines()
        assert len(roots) == 1
        initial_commit = roots[0]
        names = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", initial_commit], cwd=repo, text=True
        ).splitlines()
        assert set(names) == set(task["files"]), "initial file set differs"
        file_hashes = {}
        for name, body in task["files"].items():
            blob = subprocess.check_output(
                ["git", "show", initial_commit + ":" + name], cwd=repo
            )
            assert blob == body.encode(), (row["mode"], row["task_id"], name)
            file_hashes[name] = digest(blob)
            if name != "solution.py":
                assert (repo / name).read_bytes() == blob, "protected fixture changed"
        assert digest(runner["memory_prompt"].encode()) == memory["memory_sha256"]
        assert row["candidate_positive_ids"] == memory["candidate_positive_ids"]
        assert row["candidate_positive_ids"] == pools[row["task_id"]]["candidate_positive_ids"]
        assert row["injected_positive_ids"] == memory["injected_positive_ids"]
        assert set(row["injected_positive_ids"]) <= set(row["candidate_positive_ids"])
        assert memory["tokens"] == row["memory_tokens"]
        if row["mode"] == "none":
            cap = 0
            assert not runner["memory_prompt"] and not row["injected_positive_ids"]
        elif row["mode"] in {"flat_verified", "fork_verified"}:
            cap = protocol["original_token_cap"]
        else:
            cap = protocol["compiler_token_cap"]
        assert row["memory_tokens"] <= cap
        llm = episode.with_name(episode.name + "-llm.jsonl")
        calls = [json.loads(line) for line in llm.read_text().splitlines()]
        attempts = defaultdict(list)
        for call in calls:
            assert call["model"] == protocol["model"]
            assert call["prompt_version"] == "forkrsi-json-instance-repair-v3"
            assert call["json_protocol"] == "strict" and call["schema"] == "Action"
            assert row["seed"] <= call["seed"] < row["seed"] + protocol["max_steps"]
            attempts[call["seed"]].append(call["attempt"])
        for seed, values in attempts.items():
            assert values == list(range(len(values))) and len(values) <= 4, (
                "repair budget or attempt ordering changed", row["episode_id"], seed, values
            )
        if row["success"]:
            assert row["observation"]["case_total"] == entry["runtime_case_count"]
            assert row["observation"]["case_successes"] == entry["runtime_case_count"]
            log = episode / "logs" / (row["execution_id"] + ".log")
            assert digest(log.read_bytes()) == row["log_sha256"]
            lines = log.read_text().splitlines()
            assert lines[-1] == "FORKMEM_VERIFIER_COMPLETE"
            cases = [
                json.loads(line.split("=", 1)[1])
                for line in lines if line.startswith("FORKMEM_WORKFLOW_CASE=")
            ]
            assert len(cases) == entry["runtime_case_count"]
            assert {case["case_id"] for case in cases} == set(range(entry["runtime_case_count"]))
            assert all(case["success"] for case in cases)
        key = (logical_mode, row["task_id"], row["seed"])
        assert key not in cells, "duplicate physical final cell"
        cells.add(key)
        checks.append({
            "episode_id": row["episode_id"], "task_id": row["task_id"],
            "logical_final_mode": logical_mode, "evidence_mode": evidence_mode,
            "compiler_id": row["compiler_id"],
            "task_definition_sha256": entry["sha256"], "verifier_sha256": digest(verifier),
            "initial_file_hashes": file_hashes, "protected_initial_files_unchanged": True,
            "code_revision": metadata["code_commit"], "seed": row["seed"],
            "max_steps": runner["max_steps"], "wall_seconds": runner["wall_seconds"],
            "candidate_positive_ids": row["candidate_positive_ids"],
            "injected_positive_ids": row["injected_positive_ids"],
            "memory_tokens": row["memory_tokens"], "memory_sha256": memory["memory_sha256"],
            "cap": cap, "recorded_json_calls": len(calls),
            "prompt_version": "forkrsi-json-instance-repair-v3", "json_parser_policy": "strict",
            "repair_attempt_order_and_budget_match": True,
            "whole_case_grid_checked_for_success": row["success"],
        })
    if args.require_complete:
        status = load(campaign / "status.json")
        assert status["state"] == "complete" and status["final_outcomes_opened"]
        expected = {
            (mode, task_id, seed)
            for mode in protocol["final_modes"]
            for task_id in tasks
            for seed in protocol["task_seeds"]
        }
        assert cells == expected, "whole frozen final grid not present"
        assert len({row["episode_id"] for row in checks}) == len(expected)
    output = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "actual completed physical final cells; input alignment and successful case coverage",
        "final_campaign_complete": bool(args.require_complete),
        "completed_cells_checked": len(checks),
        "all_recorded_invariants_match": True, "checks": checks,
        "label_policy": "Logical final arms are mapped from evidence_mode plus frozen compiler_id, following the unchanged final driver. Physical directories use success_only/paired for both initial and evolved arms.",
        "audit_script_sha256": digest(Path(__file__).read_bytes()),
        "limitations": [
            "Seed is a controlled input, not a proof of deterministic GPU outputs.",
            "Memory token counts use the recorded exact-tokenizer measurement; this audit checks body hashes and caps.",
            "Original AST/manual reviews and official authenticated summarization remain separate required gates.",
        ],
    }
    (campaign / "final-control-invariants-progress.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps({
        "completed_cells_checked": len(checks),
        "all_invariants_match": True,
        "whole_grid_required": args.require_complete,
    }))


if __name__ == "__main__":
    main()
