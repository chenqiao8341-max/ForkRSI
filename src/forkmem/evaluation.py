"""Manifest-checked experiment statistics and task-cluster bootstrap."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from forkmem.environment import digest
from forkmem.models import Applicability


def clustered_interval(
    rows: list[dict[str, Any]],
    value_key: str,
    *,
    samples: int = 2000,
    seed: int = 20260909,
) -> tuple[float, float, float] | None:
    if not rows:
        return None
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row["task_id"], []).append(float(row[value_key]))
    values = list(grouped.values())
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(samples):
        indices = rng.integers(0, len(values), len(values))
        sample = [value for index in indices for value in values[index]]
        means.append(float(np.mean(sample)))
    return (
        float(np.mean([row[value_key] for row in rows])),
        float(np.quantile(means, 0.025)),
        float(np.quantile(means, 0.975)),
    )


def load_complete(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    status = json.loads((run_dir / "status.json").read_text())
    if status.get("state") != "complete":
        raise ValueError("experiment is incomplete; final report is not permitted")
    rows = [
        json.loads(line)
        for line in (run_dir / "results.jsonl").read_text().splitlines()
    ]
    config = manifest["config"]
    tasks = manifest["dataset"]["tasks"]
    expected = {
        (phase, task["task_id"], seed, mode)
        for phase, seeds, modes, splits in [
            ("training", config["training_seeds"], ["none"], {"train"}),
            (
                "evaluation",
                config["evaluation_seeds"],
                config["modes"],
                {"held_out", "near_miss"},
            ),
        ]
        for task in tasks
        if task["split"] in splits
        for seed in seeds
        for mode in modes
    }
    actual = Counter(
        (row["phase"], row["task_id"], row["seed"], row["mode"]) for row in rows
    )
    if set(actual) != expected or any(count != 1 for count in actual.values()):
        raise ValueError("missing, duplicate or unexpected task/seed/condition cells")
    for row in rows:
        result_path = Path(row["episode_dir"]) / "result.json"
        result = json.loads(result_path.read_text())
        if result["outcome"]["success"] != row["success"]:
            raise ValueError("episode summary disagrees with recorded verifier outcome")
        outcome = result["outcome"]
        log_bytes = Path(outcome["log_path"]).read_bytes()
        if (
            outcome["success"]
            and "FORKMEM_VERIFIER_COMPLETE" in Path(row["verifier"]).read_text()
            and not log_bytes.rstrip().endswith(b"FORKMEM_VERIFIER_COMPLETE")
        ):
            raise ValueError("successful benchmark oracle did not complete")
        if digest(log_bytes) != outcome["output_sha256"]:
            raise ValueError("verifier log digest mismatch")
    return manifest, rows


def summarize(run_dir: Path) -> dict[str, Any]:
    manifest, rows = load_complete(run_dir)
    evaluation = [row for row in rows if row["phase"] == "evaluation"]
    training = [row for row in rows if row["phase"] == "training"]
    failure_families = {row["family"] for row in training if not row["success"]}
    baseline = {
        (row["task_id"], row["seed"]): row
        for row in evaluation
        if row["mode"] == "none"
    }
    calls = [
        json.loads(line) for line in (run_dir / "llm.jsonl").read_text().splitlines()
    ]
    corpus = json.loads((run_dir / "corpus.json").read_text())
    branches = [branch for fork in corpus["forks"] for branch in fork["alternatives"]]
    ledger_path = run_dir / "memory_tokens.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else None
    forks_by_id = {fork["fork_id"]: fork for fork in corpus["forks"]}
    negatives_by_id = {
        lesson["lesson_id"]: lesson for lesson in corpus["negative_lessons"]
    }
    table = []
    for mode in manifest["config"]["modes"]:
        selected = [row for row in evaluation if row["mode"] == mode]
        held = [row for row in selected if row["split"] == "held_out"]
        near = [row for row in selected if row["split"] == "near_miss"]
        eligible = [
            {**row, "failure": not row["success"]}
            for row in selected
            if row["family"] in failure_families
        ]
        paired = [
            {
                **row,
                "difference": float(row["success"])
                - float(baseline[(row["task_id"], row["seed"])]["success"]),
            }
            for row in held
        ]
        retrieved = []
        memory_chars = 0
        memory_tokens = 0
        compatible_items = 0
        retrieved_items = 0
        reuse: dict[str, int] = {}
        for row in selected:
            retrieval = json.loads(
                (Path(row["episode_dir"]) / "retrieval.json").read_text()
            )
            memory_chars += len(retrieval["prompt"])
            if ledger:
                memory_tokens += ledger["items"][digest(retrieval["prompt"].encode())][
                    "tokens"
                ]
            features = json.loads(Path(row["task_path"]).read_text())["features"]
            for memory_id in retrieval["fork_ids"]:
                if memory_id in forks_by_id:
                    rule = Applicability.model_validate(
                        forks_by_id[memory_id]["applicability"]
                    )
                    compatible_items += int(rule.matches(features))
                elif memory_id in negatives_by_id:
                    compatible_items += int(
                        all(
                            features.get(k) == v
                            for k, v in negatives_by_id[memory_id]["state"][
                                "features"
                            ].items()
                        )
                    )
                else:
                    raise ValueError("retrieval references unknown source memory")
                retrieved_items += 1
            for memory_id in set(retrieval["fork_ids"]):
                reuse[memory_id] = reuse.get(memory_id, 0) + 1
            if retrieval["fork_ids"]:
                retrieved.append(row)
        regressions = sum(
            not row["success"] and baseline[(row["task_id"], row["seed"])]["success"]
            for row in retrieved
        )
        ids = {row["episode_id"] for row in selected}
        condition_calls = [call for call in calls if call["episode_id"] in ids]
        usage = sum(
            call.get("usage", {}).get("total_tokens", 0) for call in condition_calls
        )
        table.append(
            {
                "mode": mode,
                "held_out_n": len(held),
                "held_out_success": clustered_interval(held, "success"),
                "near_miss_n": len(near),
                "near_miss_success": clustered_interval(near, "success"),
                "paired_success_difference_vs_none": clustered_interval(
                    paired, "difference"
                ),
                "repeated_failure": clustered_interval(eligible, "failure"),
                "repeated_failure_n": len(eligible),
                "negative_transfer_proxy_count": regressions,
                "retrieved_n": len(retrieved),
                "negative_transfer_proxy_rate": regressions / len(retrieved)
                if retrieved
                else None,
                "reference_regret": sum(not row["success"] for row in selected),
                "evaluation_tokens": usage,
                "evaluation_model_calls": len(condition_calls),
                "mean_steps": float(np.mean([row["steps"] for row in selected])),
                "mean_memory_characters": memory_chars / len(selected),
                "mean_memory_body_tokens": memory_tokens / len(selected)
                if ledger
                else None,
                "retrieved_items": retrieved_items,
                "retrieval_condition_precision": compatible_items / retrieved_items
                if retrieved_items
                else None,
                "memory_episode_reuse_counts": reuse,
                "evaluation_model_latency_seconds": sum(
                    call["latency_seconds"] for call in condition_calls
                ),
                "seed_success_rates": {
                    str(seed): float(
                        np.mean(
                            [row["success"] for row in selected if row["seed"] == seed]
                        )
                    )
                    for seed in manifest["config"]["evaluation_seeds"]
                },
            }
        )
    executed = [b for b in branches if b["outcomes"]]
    successful = [
        b for b in executed if b["reward_delta"] is not None and b["reward_delta"] > 0
    ]
    training_ids = {row["episode_id"] for row in training}
    evaluation_ids = {row["episode_id"] for row in evaluation}
    branch_calls = [
        call
        for call in calls
        if call["episode_id"] not in training_ids | evaluation_ids
    ]
    branch_tokens = sum(
        call.get("usage", {}).get("total_tokens", 0) for call in branch_calls
    )
    useful_forks = sum(
        any(
            branch.get("reward_delta", 0) is not None and branch["reward_delta"] > 0
            for branch in fork["alternatives"]
        )
        for fork in corpus["forks"]
    )
    execution_costs = []
    for path in run_dir.rglob("*.json"):
        if path.parent.name.endswith("logs"):
            item = json.loads(path.read_text())
            if "execution_id" in item and "wall_seconds" in item:
                execution_costs.append(item)
    precision_rows = [
        {
            "task_id": fork["source_episode_id"],
            "improves": bool(
                branch.get("reward_delta") is not None and branch["reward_delta"] > 0
            ),
        }
        for fork in corpus["forks"]
        for branch in fork["alternatives"]
        if branch["outcomes"]
    ]
    return {
        "revision": manifest["revision"],
        "original_training_revision": manifest.get(
            "original_training_revision", manifest["revision"]
        ),
        "resume_history": manifest.get("resume_history", []),
        "prompt_versions": sorted({call["prompt_version"] for call in calls}),
        "run_dir": str(run_dir.resolve()),
        "training_episodes": len(training),
        "evaluation_episodes": len(evaluation),
        "training_failures": sum(not row["success"] for row in training),
        "repeated_failure_eligible_families": sorted(failure_families),
        "decision_forks": len(corpus["forks"]),
        "executed_branches": len(executed),
        "successful_branches": len(successful),
        "counterfactual_precision": len(successful) / len(executed)
        if executed
        else None,
        "total_model_tokens": sum(
            call.get("usage", {}).get("total_tokens", 0) for call in calls
        ),
        "counterfactual_precision_interval": clustered_interval(
            precision_rows, "improves"
        ),
        "branch_validation_yield": len(successful) / len(executed)
        if executed
        else None,
        "counterfactual_model_tokens": branch_tokens,
        "counterfactual_model_calls": len(branch_calls),
        "tokens_per_positive_fork": branch_tokens / useful_forks
        if useful_forks
        else None,
        "branches_per_training_failure": len(executed)
        / sum(not row["success"] for row in training)
        if any(not row["success"] for row in training)
        else None,
        "promotion_count": len(successful),
        "falsification_count": sum(
            branch["evidence_status"] == "falsified" for branch in branches
        ),
        "verifier_executions": len(execution_costs),
        "verifier_wall_seconds_sum": sum(
            item["wall_seconds"] for item in execution_costs
        ),
        "experiment_wall_seconds": json.loads(
            (run_dir / "status.json").read_text()
        ).get("wall_seconds"),
        "stored_memory_body_tokens": ledger["items"][ledger["corpus_body_sha256"]][
            "tokens"
        ]
        if ledger
        else None,
        "latency_p50_seconds": float(
            np.quantile([call["latency_seconds"] for call in calls], 0.5)
        ),
        "latency_p95_seconds": float(
            np.quantile([call["latency_seconds"] for call in calls], 0.95)
        ),
        "table": table,
        "online_sample_efficiency": "not identified by this offline frozen-corpus design",
    }


def write_tables(summary: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    rows = []
    for item in summary["table"]:
        rows.append(
            {
                key: json.dumps(value)
                if isinstance(value, (dict, list, tuple))
                else value
                for key, value in item.items()
            }
        )
    with (directory / "main_results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
