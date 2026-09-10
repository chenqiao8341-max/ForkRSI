"""Complete-grid, provenance-checked workflow statistics and paired intervals."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from forkmem.environment import digest
from forkmem.evaluation import clustered_interval
from forkmem.models import Outcome
from forkmem.workflows.analysis import read_workflow_cases, read_workflow_outcome


def failure_site(case: dict[str, Any]) -> str:
    for event in case["trace"]:
        if event.get("error"):
            return str(event.get("operation", "observation"))
    if case.get("error"):
        attempts = [e for e in case["trace"] if e["kind"] == "apply"]
        if attempts and "after" not in attempts[-1]:
            return str(attempts[-1]["operation"])
        return "controller_exception"
    missing = sorted(k for k, value in case["obligations"].items() if not value)
    return "unfinished:" + ",".join(missing)


def episode_metrics(directory: Path) -> dict[str, Any]:
    result = json.loads((directory / "result.json").read_text())
    outcome = Outcome.model_validate(result["outcome"])
    raw = Path(outcome.log_path).read_bytes()
    if digest(raw) != outcome.output_sha256:
        raise ValueError("episode log hash mismatch")
    if outcome.success and not raw.rstrip().endswith(b"FORKMEM_VERIFIER_COMPLETE"):
        raise ValueError("successful workflow oracle did not complete")
    events = [
        json.loads(x) for x in (directory / "trajectory.jsonl").read_text().splitlines()
    ]
    tested = [event for event in events if event.get("outcome")]
    first = tested[0] if tested else None
    base = {
        "success": outcome.success,
        "first_verifier_success": bool(first and first["outcome"]["success"]),
        "first_verifier_step": first["step"] + 1 if first else None,
        "steps": result["step"],
        "first_success_step": next(
            (e["step"] + 1 for e in tested if e["outcome"]["success"]), None
        ),
    }
    if not any(
        line.startswith(b"FORKMEM_WORKFLOW_RESULT=") for line in raw.splitlines()
    ):
        if outcome.success:
            raise ValueError("successful episode lacks workflow evidence")
        return {
            **base,
            "structured_available": False,
            "case_success_fraction": None,
            "normal_path_success": None,
            "obligations": {},
            "operations": None,
            "operation_cost": None,
            "first_failing_operations": [],
        }
    stats = read_workflow_outcome(outcome)
    cases = read_workflow_cases(outcome)
    return {
        **base,
        "structured_available": True,
        "case_success_fraction": sum(c["success"] for c in cases.values()) / len(cases),
        "normal_path_success": cases[0]["success"],
        "obligations": stats["obligations"],
        "operations": stats["operations"],
        "operation_cost": stats["cost"],
        "first_failing_operations": [
            failure_site(c) for c in cases.values() if not c["success"]
        ],
    }


def load_transfer(
    directory: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = json.loads((directory / "manifest.json").read_text())
    status = json.loads((directory / "status.json").read_text())
    if status["state"] != "complete":
        raise ValueError("final statistics require complete transfer")
    source = Path(manifest["source"])
    if (
        digest((source / "corpus.json").read_bytes())
        != manifest["source_corpus_sha256"]
    ):
        raise ValueError("source corpus changed")
    rows = [
        json.loads(x) for x in (directory / "results.jsonl").read_text().splitlines()
    ]
    config = manifest["config"]
    expected = {
        (t["task_id"], seed, budget, mode)
        for t in manifest["dataset"]["tasks"]
        if t["split"] == "held_out"
        for seed in config["evaluation_seeds"]
        for budget in config["action_budgets"]
        for mode in config["modes"]
    }
    keys = Counter(
        (r["task_id"], r["seed"], r["action_budget"], r["mode"]) for r in rows
    )
    if set(keys) != expected or any(n != 1 for n in keys.values()):
        raise ValueError("incomplete/duplicate/unexpected transfer cells")
    prepared = json.loads((directory / "prepared_memories.json").read_text())
    tasks = {entry["task_id"]: entry for entry in manifest["dataset"]["tasks"]}
    for task_views in prepared.values():
        if task_views["flat_verified"][1] != task_views["fork_verified"][1]:
            raise ValueError("primary evidence IDs differ")
        flat = json.loads(task_views["flat_verified"][0] or "[]")
        paired = json.loads(task_views["fork_verified"][0] or "[]")
        if [item["successful_code"] for item in flat] != [
            item["successful_code"] for item in paired
        ]:
            raise ValueError("primary successful programs differ")
    canonical = {}
    for row in rows:
        target = Path(row["episode_dir"])
        if row["episode_id"] not in canonical:
            canonical[row["episode_id"]] = episode_metrics(target)
        metadata = json.loads((target / "episode.json").read_text())
        runner = json.loads((target / "runner.json").read_text())
        if (
            metadata["task_id"] != row["task_id"]
            or metadata["seed"] != row["seed"]
            or metadata["max_steps"] != row["action_budget"]
            or metadata["episode_id"] != row["episode_id"]
        ):
            raise ValueError("episode settings disagree with condition cell")
        if runner["seed"] != row["seed"] or runner["max_steps"] != row["action_budget"]:
            raise ValueError("executed runner settings disagree with condition cell")
        task_bytes = Path(metadata["task_path"]).read_bytes()
        if digest(task_bytes) != tasks[row["task_id"]]["sha256"]:
            raise ValueError("executed task differs from frozen dataset")
        if Path(metadata["verifier"]).read_text() != json.loads(task_bytes)["verifier"]:
            raise ValueError("executed verifier differs from frozen task")
        alias = row.get("reuse_of")
        if row["mode"] == metadata["mode"]:
            if alias:
                raise ValueError("canonical cell incorrectly marked as alias")
        elif not alias or alias != {
            "task_id": row["task_id"],
            "seed": row["seed"],
            "action_budget": row["action_budget"],
            "mode": metadata["mode"],
            "episode_id": row["episode_id"],
        }:
            raise ValueError("alias does not name the executed canonical cell")
        metrics = canonical[row["episode_id"]]
        if metrics["success"] != row["success"]:
            raise ValueError("summary and execution disagree")
        body, ids = prepared[row["task_id"]][row["mode"]]
        actual = json.loads((target / "retrieval.json").read_text())
        if (
            body != actual["prompt"]
            or body != runner["memory_prompt"]
            or digest(body.encode()) != row["memory_body_sha256"]
            or ids != row["memory_ids"]
        ):
            raise ValueError("rendered memory or alias does not match executed prompt")
        row.update(metrics)
    calls = [json.loads(x) for x in (directory / "llm.jsonl").read_text().splitlines()]
    canonical_counts = Counter(r["episode_id"] for r in rows if not r.get("reuse_of"))
    if set(canonical_counts) != {r["episode_id"] for r in rows} or any(
        n != 1 for n in canonical_counts.values()
    ):
        raise ValueError("each actual episode requires exactly one canonical cell")
    first_calls: dict[str, dict[str, Any]] = {}
    for call in calls:
        first_calls.setdefault(call["episode_id"], call)
    for row in rows:
        call = first_calls.get(row["episode_id"])
        if call is None or call["seed"] != row["seed"] or call["model"] != row["model"]:
            raise ValueError("missing or mismatched initial model request")
        body = prepared[row["task_id"]][row["mode"]][0]
        marker = (
            "Prior-task memory (may be inapplicable; check the current contract):\n"
        )
        content = call["messages"][1]["content"]
        if marker not in content:
            raise ValueError("actual model request lacks the memory section")
        actual_body = content.split(marker, 1)[1].split("\nCurrent trajectory:\n", 1)[0]
        if body != actual_body:
            raise ValueError("prepared memory differs from actual model request")
    return manifest, rows, calls


def summarize_transfer(directory: Path) -> dict[str, Any]:
    manifest, rows, calls = load_transfer(directory)
    config = manifest["config"]
    ledger = json.loads((directory / "memory_tokens.json").read_text())["items"]
    costs: dict[str, dict[str, float]] = {}
    for call in calls:
        totals = costs.setdefault(
            call["episode_id"], {"tokens": 0, "calls": 0, "latency": 0}
        )
        totals["tokens"] += call.get("usage", {}).get("total_tokens", 0)
        totals["calls"] += 1
        totals["latency"] += call["latency_seconds"]
    lookup = {(r["task_id"], r["seed"], r["action_budget"], r["mode"]): r for r in rows}
    table = []
    for budget in config["action_budgets"]:
        for mode in config["modes"]:
            selected = [
                r for r in rows if r["action_budget"] == budget and r["mode"] == mode
            ]
            paired = []
            regressions = 0
            for row in selected:
                baseline = lookup[
                    (row["task_id"], row["seed"], budget, "flat_verified")
                ]
                paired.append(
                    {
                        "task_id": row["semantic_context"],
                        "difference": int(row["success"]) - int(baseline["success"]),
                    }
                )
                none = lookup[(row["task_id"], row["seed"], budget, "none")]
                regressions += (
                    bool(row["memory_ids"]) and none["success"] and not row["success"]
                )
            structured = [r for r in selected if r["structured_available"]]
            family_rates = {
                family: clustered_interval(
                    [r for r in selected if r["family"] == family], "success"
                )
                for family in sorted({r["family"] for r in selected})
            }
            components = {}
            for family in family_rates:
                group = [r for r in structured if r["family"] == family]
                components[family] = {
                    name: {
                        "successes": sum(r["obligations"][name] for r in group),
                        "observed_n": len(group),
                    }
                    for name in sorted({key for r in group for key in r["obligations"]})
                }
            table.append(
                {
                    "mode": mode,
                    "action_budget": budget,
                    "n": len(selected),
                    "success": clustered_interval(selected, "success"),
                    "difference_vs_flat_verified": clustered_interval(
                        paired, "difference"
                    ),
                    "first_verifier_success": clustered_interval(
                        selected, "first_verifier_success"
                    ),
                    "clean_path_success": clustered_interval(
                        structured, "normal_path_success"
                    ),
                    "case_success_fraction": clustered_interval(
                        structured, "case_success_fraction"
                    ),
                    "recovery_only_failures": sum(
                        r["normal_path_success"] and not r["success"]
                        for r in structured
                    ),
                    "failure_site_episode_counts": dict(
                        Counter(
                            site
                            for r in selected
                            for site in set(r["first_failing_operations"])
                        )
                    ),
                    "structured_n": len(structured),
                    "retrieved_n": sum(bool(r["memory_ids"]) for r in selected),
                    "regressions_vs_none_with_retrieval": regressions,
                    "family_success": family_rates,
                    "components": components,
                    "attributable_model_tokens": sum(
                        costs[r["episode_id"]]["tokens"] for r in selected
                    ),
                    "incremental_model_tokens": sum(
                        costs[r["episode_id"]]["tokens"]
                        for r in selected
                        if not r.get("reuse_of")
                    ),
                    "mean_memory_body_tokens": float(
                        np.mean(
                            [
                                ledger[r["memory_body_sha256"]]["tokens"]
                                for r in selected
                            ]
                        )
                    ),
                    "mean_steps": float(np.mean([r["steps"] for r in selected])),
                    "seed_success_rates": {
                        str(seed): float(
                            np.mean(
                                [r["success"] for r in selected if r["seed"] == seed]
                            )
                        )
                        for seed in config["evaluation_seeds"]
                    },
                    "alias_cells": sum(bool(r.get("reuse_of")) for r in selected),
                }
            )
    return {
        "manifest": manifest,
        "primary_contrast": "fork_verified minus flat_verified at eight actions",
        "table": table,
        "cells": len(rows),
        "unique_episodes": len({r["episode_id"] for r in rows}),
        "actual_model_tokens": sum(
            c.get("usage", {}).get("total_tokens", 0) for c in calls
        ),
        "actual_model_calls": len(calls),
        "unassigned_interrupted_episode_tokens": sum(
            c.get("usage", {}).get("total_tokens", 0)
            for c in calls
            if c["episode_id"] not in {r["episode_id"] for r in rows}
        ),
        "cost_definition": "Attributable tokens reuse canonical execution cost per condition; incremental tokens charge an alias zero. Sum actual raw usage for total compute, never sum attributable columns across aliased conditions.",
        "missing_structure_definition": "Import/early execution failure still fails the primary outcome; unavailable component observations remain missing, with structured_n reported.",
        "rows": rows,
    }
