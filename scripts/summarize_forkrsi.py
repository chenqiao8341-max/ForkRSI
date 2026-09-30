"""Verify and summarize the sealed pilot; no outcome-driven strategy changes."""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from statistics import mean
from typing import Any

from audit_workflow_programs import audit

from forkmem.environment import digest
from forkmem.models import DecisionFork
from forkmem.rsi.campaign import authenticated_result, load, save, usage
from forkmem.rsi.ledger import sha
from forkmem.workflows.memory import final_code

Json = dict[str, Any]


def paired_interval(first: list[Json], second: list[Json]) -> Json:
    left = {(r["task_id"], r["seed"]): r for r in first}
    right = {(r["task_id"], r["seed"]): r for r in second}
    if left.keys() != right.keys():
        raise ValueError("paired task/seed cells differ")
    grouped: dict[str, list[float]] = defaultdict(list)
    cells = []
    for key, old in left.items():
        new = right[key]
        delta = float(new["success"]) - float(old["success"])
        grouped[key[0]].append(delta)
        cells.append(
            {
                "task_id": key[0],
                "seed": key[1],
                "before": old["success"],
                "after": new["success"],
            }
        )
    differences = [mean(v) for v in grouped.values()]
    rng = random.Random(6101)
    boot = sorted(
        mean(rng.choices(differences, k=len(differences))) for _ in range(2000)
    )
    return {
        "task_cluster_mean_success_delta": mean(differences),
        "bootstrap_95_interval": [boot[49], boot[1949]],
        "bootstrap_policy": "2000 paired semantic-task resamples, seed6101; exploratory small sample",
        "repairs": sum(not c["before"] and c["after"] for c in cells),
        "negative_transfer": sum(c["before"] and not c["after"] for c in cells),
        "cells": cells,
    }


def statistics(rows: list[Json], none: list[Json]) -> Json:
    tasks = {r["task_id"] for r in rows}
    grouped: dict[str, list[Json]] = defaultdict(list)
    for r in rows:
        grouped[r["task_id"]].append(r)
    return {
        "semantic_tasks": len(tasks),
        "episode_cells": len(rows),
        "complete_safe_successes": sum(r["success"] for r in rows),
        "complete_safe_success_rate": mean(
            mean(float(r["success"]) for r in group) for group in grouped.values()
        ),
        "first_validation_success_rate": mean(
            mean(float(r["first_validation_success"]) for r in group)
            for group in grouped.values()
        ),
        "mean_memory_tokens": mean(r["memory_tokens"] for r in rows),
        "mean_episode_prompt_tokens": mean(r["usage"]["prompt_tokens"] for r in rows),
        "mean_episode_completion_tokens": mean(
            r["usage"]["completion_tokens"] for r in rows
        ),
        "mean_episode_total_tokens": mean(r["usage"]["total_tokens"] for r in rows),
        "total_episode_tokens": sum(r["usage"]["total_tokens"] for r in rows),
        "negative_transfer_vs_none": paired_interval(none, rows)["negative_transfer"],
        "repairs_vs_none": paired_interval(none, rows)["repairs"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--campaign", type=Path, default=Path("runs/forkrsi/campaign-v1")
    )
    parser.add_argument("--source", type=Path, default=Path("runs/forkrsi/source-package-v1"))
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/forkrsi/pilot-v1")
    )
    args = parser.parse_args()
    root, source, out = args.campaign, args.source, args.output
    if load(root / "status.json")["state"] != "complete":
        raise ValueError("final grid is not complete")
    final = load(root / "final-result.json")
    seal = load(root / "final-freeze.json")
    if (
        final["seal_sha256"] != seal["seal_sha256"]
        or sha(seal["value"]) != seal["seal_sha256"]
    ):
        raise ValueError("final seal mismatch")
    frozen = seal["value"]
    protocol = frozen["protocol"]
    manifest_path = Path(protocol["manifest"])
    if digest(manifest_path.read_bytes()) != frozen["inputs"]["manifest_sha256"]:
        raise ValueError("frozen task manifest changed")
    if (
        digest((source / "corpus.json").read_bytes())
        != frozen["inputs"]["corpus_sha256"]
    ):
        raise ValueError("frozen corpus changed")
    manifest = load(manifest_path)
    expected = {
        (e["task_id"], s)
        for e in manifest["tasks"]
        if e["split"] == "final"
        for s in protocol["task_seeds"]
    }
    pools = load(root / "pools.json")["pools"]
    if list(final["results"]) != protocol["final_modes"]:
        raise ValueError("final mode grid changed")
    actual_episodes = {}
    results = final["results"]
    for mode, result in results.items():
        rows = result["rows"]
        keys = {(r["task_id"], r["seed"]) for r in rows}
        if keys != expected or len(rows) != len(keys):
            raise ValueError("incomplete or duplicate final cells")
        for row in rows:
            path = Path(row["episode_dir"])
            observed = authenticated_result(path)
            if (
                observed["success"] != row["success"]
                or observed["log_sha256"] != row["log_sha256"]
            ):
                raise ValueError("final authentication mismatch")
            if (
                row["candidate_positive_ids"]
                != pools[row["task_id"]]["candidate_positive_ids"]
            ):
                raise ValueError(
                    "final controls changed the successful source candidate IDs"
                )
            if not set(row["injected_positive_ids"]) <= set(
                row["candidate_positive_ids"]
            ):
                raise ValueError("injected evidence outside fixed candidate pool")
            if (
                mode not in {"none", "flat_verified", "fork_verified"}
                and row["memory_tokens"] > 1500
            ):
                raise ValueError("compiler memory budget exceeded")
            actual_episodes[row["episode_id"]] = path

    # Apply the UNCHANGED original AST screen to all generated source/downstream writes.
    audit(source, source / "program-audit.json")
    adapter = root / "program-audit-adapter"
    adapter.mkdir(parents=True, exist_ok=True)
    indexed = {}
    for metrics in (root / "evaluations").rglob("metrics.json"):
        row = load(metrics)
        indexed[row["episode_id"]] = Path(row["episode_dir"])
    save(adapter / "status.json", {"state": "complete"})
    (adapter / "results.jsonl").write_text(
        "".join(json.dumps({"episode_dir": str(p)}) + "\n" for p in indexed.values())
    )
    audit(adapter, root / "program-audit.json")
    source_flags = load(source / "program-audit.json")
    target_flags = load(root / "program-audit.json")
    review_paths = [
        source / "program-audit-review.json",
        root / "program-audit-review.json",
    ]
    reviews = [load(p) if p.exists() else {"reviews": []} for p in review_paths]
    unresolved = []
    for label, screen, review in zip(
        ("source", "campaign"), (source_flags, target_flags), reviews, strict=True
    ):
        reviewed = {r["sha256"]: r for r in review["reviews"]}
        for flag in screen["flags"]:
            if flag["sha256"] not in reviewed:
                unresolved.append({"stage": label, **flag})
    if unresolved:
        save(out / "unresolved-program-flags.json", unresolved)
        raise ValueError("original program-screen flags require recorded manual review")

    none = results["none"]["rows"]
    table = {mode: statistics(result["rows"], none) for mode, result in results.items()}
    pairs = {}
    for before, after in (
        ("flat_verified", "fork_verified"),
        ("success_only_evolved", "paired_evolved"),
        ("success_only_initial", "success_only_evolved"),
        ("paired_initial", "paired_evolved"),
    ):
        pairs[before + " -> " + after] = paired_interval(
            results[before]["rows"], results[after]["rows"]
        )
    search = load(root / "search-result.json")
    reset = {
        label: {
            "initial_C": r["initial_C"],
            "I": r["I"],
            "selected_C": r["selected_C"],
            "candidate_budget": r["candidate_budget"],
            "score": r["result"]["score"],
            "candidate_records": r["history"],
        }
        for label, r in search["reset"].items()
    }
    if (
        reset["I0"]["initial_C"] != reset["I1"]["initial_C"]
        or reset["I0"]["candidate_budget"] != reset["I1"]["candidate_budget"]
    ):
        raise ValueError("I reset is not aligned")
    reset["paired_difference"] = paired_interval(
        search["reset"]["I0"]["result"]["rows"], search["reset"]["I1"]["result"]["rows"]
    )
    with closing(sqlite3.connect(root / "strategies.sqlite")) as db:
        db.row_factory = sqlite3.Row
        versions = [
            dict(r) for r in db.execute("SELECT * FROM versions ORDER BY created_utc")
        ]
        comparisons = [
            dict(r)
            for r in db.execute("SELECT * FROM comparisons ORDER BY created_utc")
        ]
    by_id = {v["version_id"]: v for v in versions}
    for mode, selection in search["selections"].items():
        i1 = selection["I"]
        history = search["histories"][mode]["candidates"]
        if not any(
            r["improver_id"] == i1
            and r.get("candidate_c")
            and json.loads(by_id[r["candidate_c"]]["provenance_json"])["generated_by_i"]
            == i1
            for r in history
        ):
            raise ValueError("new I was not actually used for C generation")
    source_runs = []
    for p in sorted(source.parent.glob("source-v*")):
        if p.is_dir() and (p / "llm.jsonl").exists():
            source_runs.append(
                {
                    "path": str(p),
                    "usage": usage(p / "llm.jsonl"),
                    "status": load(p / "status.json"),
                }
            )
    extraction_calls = [
        json.loads(s) for s in (root / "strategy-llm.jsonl").read_text().splitlines()
    ]
    strategy_costs = {}
    for schema in ("RuleSet", "CompilerProposal", "ImproverProposal"):
        calls = [c for c in extraction_calls if c["schema"] == schema]
        strategy_costs[schema] = {
            "requests": len(calls),
            **{
                k: sum(int(c.get("usage", {}).get(k, 0)) for c in calls)
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
        }
    execution_costs = {}
    for stage in ("development", "selection", "reset", "final"):
        files = list((root / "evaluations" / stage).rglob("*-llm.jsonl"))
        execution_costs[stage] = {
            "files": len(files),
            **{
                k: sum(usage(p)[k] for p in files)
                for k in (
                    "requests",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                )
            },
        }
    corpus = load(source / "corpus.json")
    forks = [DecisionFork.model_validate(f) for f in corpus["forks"]]
    source_summary = {
        "forks": len(forks),
        "factual_failures": len(corpus["negative_lessons"]),
        "verified_alternatives": sum(
            b.evidence_status.value in {"replay_verified", "repeatedly_verified"}
            for f in forks
            for b in f.alternatives
        ),
        "falsified_alternatives": sum(
            b.evidence_status.value == "falsified"
            for f in forks
            for b in f.alternatives
        ),
        "source_program_ids": [
            f.fork_id + ":" + b.branch_id
            for f in forks
            for b in f.alternatives
            if b.evidence_status.value in {"replay_verified", "repeatedly_verified"}
        ],
    }
    summary = {
        "scope": "frozen-weight single-GPU exploratory pilot; semantic task is statistical unit",
        "seal": seal,
        "final_statistics": table,
        "paired_comparisons": pairs,
        "I_reset": reset,
        "source_summary": source_summary,
        "source_collection_costs_including_failed_calibration": source_runs,
        "strategy_costs_by_schema": strategy_costs,
        "execution_costs_by_stage": execution_costs,
        "C0": search["C0"],
        "I0": search["I0"],
        "selected": search["selections"],
        "versions": versions,
        "comparisons": comparisons,
        "program_screen": {
            "source": source_flags,
            "campaign": target_flags,
            "reviews": reviews,
            "limitation": "original AST screen/manual review is not adversarial Python proof",
        },
        "unique_final_executions": len(actual_episodes),
        "final_arm_cell_count": sum(len(v["rows"]) for v in results.values()),
        "alias_disclosure": "identical selected/initial C cells reused; alias cells are not new replicates",
        "limitations": [
            "small hand-designed task sample",
            "one recorded seed per task in protocol-v1",
            "fixed seeds do not eliminate stochastic inference",
            "Python3.12 runtime adaptation",
            "GPU runtime and package versions are recorded; bitwise reproducibility not asserted",
        ],
    }
    save(out / "summary.json", summary)
    save(out / "final-cells.json", {mode: res["rows"] for mode, res in results.items()})
    save(out / "search-records.json", search)
    save(
        out / "source-programs.json",
        [
            {
                "program_id": f.fork_id + ":" + b.branch_id,
                "code": final_code(b),
                "status": b.evidence_status.value,
                "outcomes": [o.model_dump(mode="json") for o in b.outcomes],
            }
            for f in forks
            for b in [f.factual, *f.alternatives]
        ],
    )
    print(
        json.dumps(
            {
                "final_statistics": table,
                "source": source_summary,
                "reset": reset["paired_difference"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
