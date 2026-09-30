"""Persistent paired compiler search, actual I reuse, reset test and sealed final grid."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any, cast

from transformers import AutoTokenizer

from forkmem.agent import run_task
from forkmem.environment import digest, git
from forkmem.llm import LLMClient
from forkmem.memory import SQLiteForkStore
from forkmem.models import Outcome, StateFingerprint
from forkmem.rsi.compiler import EvidenceMode, MemoryCompiler, source_packet
from forkmem.rsi.improver import propose_compiler, propose_improver
from forkmem.rsi.ledger import StrategyLedger, canonical, sha
from forkmem.rsi.models import INITIAL_COMPILER, INITIAL_IMPROVER
from forkmem.workflows.analysis import PREFIX, read_workflow_cases
from forkmem.workflows.memory import views

Json = dict[str, Any]


def as_evidence_mode(mode: str) -> EvidenceMode:
    if mode not in {"success_only", "paired"}:
        raise ValueError("unknown compiler evidence mode")
    return cast(EvidenceMode, mode)


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def usage(path: Path) -> Json:
    events = (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )
    result = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "requests": len(events),
        "parse_errors": 0,
        "transport_errors": 0,
    }
    for event in events:
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            result[name] += int(event.get("usage", {}).get(name, 0))
        if event.get("status") == "parse_error":
            result["parse_errors"] += 1
        if event.get("status") == "transport_error":
            result["transport_errors"] += 1
    if result["total_tokens"] != result["prompt_tokens"] + result["completion_tokens"]:
        raise ValueError("invalid recorded model usage")
    return result


def authenticated_result(episode: Path) -> Json:
    result = load(episode / "result.json")
    outcome = Outcome.model_validate(result["outcome"])
    log = Path(outcome.log_path)
    if digest(log.read_bytes()) != outcome.output_sha256:
        raise ValueError("episode log mismatch")
    meta = load(log.with_suffix(".json"))
    if digest(Path(meta["raw_log_path"]).read_bytes()) != meta["raw_output_sha256"]:
        raise ValueError("episode raw log mismatch")
    if outcome.success and not meta["completion_observed"]:
        raise ValueError("episode skipped verifier completion")
    if any(line.startswith(PREFIX) for line in log.read_text().splitlines()):
        cases = read_workflow_cases(outcome)
        failed = [
            {
                "case_id": i,
                "scheduled_crashes": c.get("scheduled_crashes", []),
                "obligations": c["obligations"],
                "error": c.get("error"),
                "trace_tail": c["trace"][-3:],
            }
            for i, c in cases.items()
            if not c["success"]
        ]
        observation = {
            "case_total": len(cases),
            "case_successes": sum(c["success"] for c in cases.values()),
            "failed_cases": failed[:2],
        }
    else:
        if outcome.success:
            raise ValueError("successful workflow has no structured result")
        observation = {
            "case_total": None,
            "failed_cases": [],
            "error_excerpt": log.read_text()[-2000:],
        }
    events = [
        json.loads(line)
        for line in (episode / "trajectory.jsonl").read_text().splitlines()
    ]
    tests = [e["outcome"] for e in events if e.get("outcome")]
    first_success = bool(tests and tests[0]["success"])
    for tested in tests:
        test_outcome = Outcome.model_validate(tested)
        if (
            digest(Path(test_outcome.log_path).read_bytes())
            != test_outcome.output_sha256
        ):
            raise ValueError("first/intermediate validation log mismatch")
    return {
        "success": outcome.success,
        "first_validation_success": first_success,
        "steps": result["step"],
        "execution_id": outcome.execution_id,
        "log_sha256": outcome.output_sha256,
        "observation": observation,
        "final_code": (episode / "repo/solution.py").read_text(),
    }


def score(rows: list[Json]) -> tuple[int, int, int]:
    return (
        sum(r["success"] for r in rows),
        sum(r["first_validation_success"] for r in rows),
        -sum(r["usage"]["total_tokens"] for r in rows),
    )


def comparison(parent: Json, child: Json) -> Json:
    before = {(r["task_id"], r["seed"]): r for r in parent["rows"]}
    after = {(r["task_id"], r["seed"]): r for r in child["rows"]}
    if before.keys() != after.keys():
        raise ValueError("comparison task/seed cells differ")
    changes = []
    for key, old in before.items():
        new = after[key]
        if old["candidate_positive_ids"] != new["candidate_positive_ids"]:
            raise ValueError("compiler comparison changed source candidate pool")
        changes.append(
            {
                "task_id": key[0],
                "seed": key[1],
                "parent_success": old["success"],
                "child_success": new["success"],
                "parent_first": old["first_validation_success"],
                "child_first": new["first_validation_success"],
                "parent_tokens": old["usage"]["total_tokens"],
                "child_tokens": new["usage"]["total_tokens"],
            }
        )
    return {
        "parent_score": score(parent["rows"]),
        "candidate_score": score(child["rows"]),
        "candidate_selected": score(child["rows"]) > score(parent["rows"]),
        "regressions": sum(
            c["parent_success"] and not c["child_success"] for c in changes
        ),
        "repairs": sum(not c["parent_success"] and c["child_success"] for c in changes),
        "paired_cells": changes,
    }


class Campaign:
    def __init__(self, root: Path, source: Path, protocol_path: Path):
        self.root, self.source = root.resolve(), source.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.protocol_path = protocol_path
        self.protocol = load(protocol_path)
        self.manifest_path = Path(self.protocol["manifest"])
        self.manifest = load(self.manifest_path)
        self.ledger = StrategyLedger(self.root / "strategies.sqlite")
        self.store = SQLiteForkStore(self.source / "memory.sqlite")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.protocol["model_path"], local_files_only=True
        )
        self.client = LLMClient(
            self.root / "strategy-llm.jsonl",
            concurrency=1,
            request_budget=max(
                0,
                self.protocol["request_budget"]
                - usage(self.root / "strategy-llm.jsonl")["requests"],
            ),
        )
        self.compiler = MemoryCompiler(
            self.ledger, self.client, self.root / "compiled", self.count
        )
        self.c0 = self.ledger.add_version(
            "C",
            INITIAL_COMPILER.model_dump(mode="json"),
            provenance={"initial": "protocol-v1"},
        )
        self.i0 = self.ledger.add_version(
            "I",
            INITIAL_IMPROVER.model_dump(mode="json"),
            provenance={"initial": "protocol-v1"},
        )
        self.entries = {e["task_id"]: e for e in self.manifest["tasks"]}
        self.forks = {f.fork_id: f for f in self.store.all()}

    def count(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    def check_inputs(self) -> Json:
        if load(self.source / "status.json")["state"] != "complete":
            raise ValueError("source collection is not terminal complete")
        for e in [*self.manifest["source_tasks"], *self.manifest["tasks"]]:
            if digest(Path(e["path"]).read_bytes()) != e["sha256"]:
                raise ValueError("frozen task changed")
        # JSON snapshot and SQLite must describe precisely the same frozen corpus.
        if load(self.source / "corpus.json")["forks"] != [
            f.model_dump(mode="json") for f in self.store.all()
        ]:
            raise ValueError("source SQLite and JSON disagree")
        return {
            "protocol_sha256": digest(self.protocol_path.read_bytes()),
            "manifest_sha256": digest(self.manifest_path.read_bytes()),
            "corpus_sha256": digest((self.source / "corpus.json").read_bytes()),
            "code_revision": git(Path.cwd(), "rev-parse", "HEAD"),
            "source_manifest_sha256": digest(
                (self.source / "manifest.json").read_bytes()
            ),
        }

    def pools(self) -> Json:
        path = self.root / "pools.json"
        inputs = self.check_inputs()
        if path.exists():
            result = load(path)
            if any(
                result["inputs"][k] != inputs[k] for k in inputs if k != "code_revision"
            ):
                raise ValueError("frozen retrieval inputs changed")
            return cast(Json, result)
        pools = {}
        for e in self.manifest["tasks"]:
            task = load(Path(e["path"]))
            state = StateFingerprint(
                task_family=task["family"],
                features=task["features"],
                summary=task["description"],
                checkpoint="fixed-public-retrieval",
            )
            original = views(
                self.store,
                state,
                self.count,
                token_cap=self.protocol["original_token_cap"],
                limit=self.protocol["candidate_pool_limit"],
            )
            flat, ids = original["flat_verified"]
            paired, pair_ids = original["fork_verified"]
            if ids != pair_ids or not ids:
                raise ValueError(
                    "no shared verified positive pool for " + task["task_id"]
                )
            for identifier in ids:
                fork_id, branch_id = identifier.split(":")
                fork = self.forks[fork_id]
                positive = next(
                    b for b in fork.alternatives if b.branch_id == branch_id
                )
                source_packet(fork, positive, INITIAL_COMPILER, "paired")
            pools[task["task_id"]] = {
                "candidate_positive_ids": ids,
                "flat_verified": flat,
                "fork_verified": paired,
                "flat_tokens": self.count(flat),
                "fork_tokens": self.count(paired),
            }
        result = {"inputs": inputs, "pools": pools}
        save(path, result)
        return result

    async def memory(
        self, compiler_id: str, mode: str, task_id: str
    ) -> tuple[str, list[str], Json]:
        pool = self.pools()["pools"][task_id]
        ids = pool["candidate_positive_ids"]
        if mode == "none":
            return "", [], {"candidate_positive_ids": ids, "tokens": 0}
        if mode in {"flat_verified", "fork_verified"}:
            body = pool[mode]
            return (
                body,
                ids,
                {"candidate_positive_ids": ids, "tokens": self.count(body)},
            )
        compiled = []
        for identifier in ids:
            fork_id, branch_id = identifier.split(":")
            fork = self.forks[fork_id]
            positive = next(b for b in fork.alternatives if b.branch_id == branch_id)
            compiled.append(
                await self.compiler.compile_source(
                    compiler_id, fork, positive, as_evidence_mode(mode)
                )
            )
        return self.compiler.render(
            compiler_id, compiled, load(Path(self.entries[task_id]["path"]))
        )

    async def evaluate(
        self, stage: str, compiler_id: str, mode: str, split: str
    ) -> Json:
        path = self.root / "evaluations" / stage / mode / compiler_id
        rows = []
        for entry in self.manifest["tasks"]:
            if entry["split"] != split:
                continue
            for seed in self.protocol["task_seeds"]:
                body, injected, info = await self.memory(
                    compiler_id, mode, entry["task_id"]
                )
                target = path / f"seed-{seed}" / entry["task_id"]
                target.parent.mkdir(parents=True, exist_ok=True)
                memory_meta = {
                    **info,
                    "memory_sha256": digest(body.encode()),
                    "injected_positive_ids": injected,
                }
                row_path = target / "metrics.json"
                if row_path.exists():
                    row = load(row_path)
                    actual = authenticated_result(Path(row["episode_dir"]))
                    if (
                        row["success"] != actual["success"]
                        or row["log_sha256"] != actual["log_sha256"]
                    ):
                        raise ValueError("cached episode mismatch")
                    if (
                        load(Path(row["episode_dir"]) / "compiler-memory.json")
                        != memory_meta
                    ):
                        raise ValueError("cached memory differs")
                else:
                    if target.exists():
                        # Never overwrite an interrupted trajectory or hide its costs.
                        target = target.with_name(
                            target.name + "-retry-" + str(time.time_ns())
                        )
                    used = usage(self.client.log_path)["requests"] + sum(
                        usage(p)["requests"]
                        for p in (self.root / "evaluations").rglob("*-llm.jsonl")
                    )
                    remaining = self.protocol["request_budget"] - used
                    if remaining <= 0:
                        raise RuntimeError(
                            "campaign-wide model request budget exhausted"
                        )
                    client = LLMClient(
                        target.parent / (target.name + "-llm.jsonl"),
                        concurrency=1,
                        request_budget=min(self.protocol["max_steps"] * 4, remaining),
                    )
                    try:
                        metadata = await run_task(
                            Path(entry["path"]),
                            target,
                            client,
                            mode=mode,
                            seed=seed,
                            max_steps=self.protocol["max_steps"],
                            prepared_memory=(body, injected),
                        )
                    finally:
                        await client.close()
                    save(target / "compiler-memory.json", memory_meta)
                    actual = authenticated_result(target)
                    row = {
                        **actual,
                        "task_id": entry["task_id"],
                        "seed": seed,
                        "mode": mode,
                        "compiler_id": compiler_id,
                        "candidate_positive_ids": info["candidate_positive_ids"],
                        "injected_positive_ids": injected,
                        "memory_tokens": info["tokens"],
                        "usage": usage(client.log_path),
                        "episode_dir": str(target),
                        "episode_id": metadata["episode_id"],
                        "evidence_id": "episode:" + metadata["episode_id"],
                    }
                    save(target / "metrics.json", row)
                    # Canonical index follows retries, without removing failed attempts.
                    if target / "metrics.json" != row_path:
                        save(row_path, row)
                rows.append(row)
                save(
                    self.root / "status.json",
                    {
                        "state": "running",
                        "stage": stage,
                        "mode": mode,
                        "compiler_id": compiler_id,
                        "last_task": entry["task_id"],
                        "success": row["success"],
                        "completed": len(rows),
                    },
                )
                print(
                    canonical(
                        {
                            "stage": stage,
                            "mode": mode,
                            "compiler_id": compiler_id,
                            "task_id": entry["task_id"],
                            "success": row["success"],
                        }
                    ),
                    flush=True,
                )
        result = {
            "stage": stage,
            "compiler_id": compiler_id,
            "mode": mode,
            "split": split,
            "rows": rows,
            "score": score(rows),
        }
        save(path / "summary.json", result)
        return result

    def evidence(self, evaluation: Json, mode: str) -> list[str]:
        ids = [r["evidence_id"] for r in evaluation["rows"]]
        for row in evaluation["rows"]:
            for identifier in row["candidate_positive_ids"]:
                fork_id, branch_id = identifier.split(":")
                fork = self.forks[fork_id]
                positive = next(
                    b for b in fork.alternatives if b.branch_id == branch_id
                )
                _, allowed = source_packet(
                    fork, positive, INITIAL_COMPILER, as_evidence_mode(mode)
                )
                ids += sorted(allowed)
        return list(dict.fromkeys(ids))

    def feedback(self, evaluation: Json, mode: str) -> Json:
        sources = {}
        episodes = []
        for row in evaluation["rows"]:
            for identifier in row["candidate_positive_ids"]:
                fork_id, branch_id = identifier.split(":")
                fork = self.forks[fork_id]
                positive = next(
                    b for b in fork.alternatives if b.branch_id == branch_id
                )
                packet, _ = source_packet(
                    fork, positive, INITIAL_COMPILER, as_evidence_mode(mode)
                )
                # C extraction receives full programs; I gets bounded execution
                # diagnostics plus the actual injected memories. Failed source
                # data is absent in the success-only arm.
                packet["positive"].pop("code")
                if "factual_failure" in packet:
                    packet["factual_failure"].pop("code")
                for failed in packet.get("falsified_alternatives", []):
                    failed.pop("code")
                sources[identifier] = packet
            item = {
                k: row[k]
                for k in (
                    "evidence_id",
                    "task_id",
                    "seed",
                    "success",
                    "first_validation_success",
                    "memory_tokens",
                    "usage",
                    "observation",
                )
            }
            item["final_code_excerpt"] = row["final_code"][:2000]
            item["injected_memory"] = load(Path(row["episode_dir"]) / "retrieval.json")[
                "prompt"
            ]
            episodes.append(item)
        value = {
            "current_evaluation": {
                "mode": mode,
                "split": evaluation["split"],
                "score": evaluation["score"],
                "episodes": episodes,
            },
            "source_diagnostics": list(sources.values()),
        }
        if len(canonical(value)) > 54000:
            # Bounded before inference and independent of which candidate wins.
            # Raw programs/cases remain in immutable run artifacts.
            for item in episodes:
                item["final_code_excerpt"] = item["final_code_excerpt"][:500]
                for case in item["observation"].get("failed_cases", []):
                    case["trace_tail"] = [
                        {
                            k: v
                            for k, v in event.items()
                            if k
                            in {
                                "kind",
                                "operation",
                                "error",
                                "missing",
                                "excluded",
                                "process_crash_after_operation",
                            }
                        }
                        for event in case["trace_tail"]
                    ]
            for source in sources.values():
                for branch in [
                    source["positive"],
                    source.get("factual_failure", {}),
                    *source.get("falsified_alternatives", []),
                ]:
                    execution = branch.get("execution", {})
                    for case in execution.get("failed_cases", []):
                        case["trace_tail"] = [
                            {
                                k: v
                                for k, v in event.items()
                                if k
                                in {"kind", "operation", "error", "missing", "excluded"}
                            }
                            for event in case["trace_tail"]
                        ]
                    if "error_excerpt" in execution:
                        execution["error_excerpt"] = execution["error_excerpt"][-500:]
        if len(canonical(value)) > 54000:
            raise ValueError("diagnostic packet exceeds predefined feedback limit")
        return value

    async def step(
        self, label: str, current: str, improver: str, mode: str, split: str, seed: int
    ) -> tuple[str, Json]:
        record_path = self.root / "search" / (label + ".json")
        if record_path.exists():
            record = load(record_path)
            if record["parent_c"] != current or record["improver_id"] != improver:
                raise ValueError("search resume lineage mismatch")
            return record["selected_c"], record
        parent = await self.evaluate(split, current, mode, split)
        before = usage(self.client.log_path)
        evidence = self.evidence(parent, mode)
        candidate = None
        try:
            candidate, proposal = await propose_compiler(
                self.ledger,
                self.client,
                improver,
                current,
                self.feedback(parent, mode),
                evidence,
                seed=seed,
                evidence_mode=mode,
            )
            child = await self.evaluate(split, candidate, mode, split)
            results = comparison(parent, child)
            proposal_cost = {
                k: usage(self.client.log_path)[k] - before[k] for k in before
            }
            record = {
                "label": label,
                "parent_c": current,
                "improver_id": improver,
                "candidate_c": candidate,
                "proposal": proposal,
                "results": results,
                "selected_c": candidate if results["candidate_selected"] else current,
                "evidence_ids": evidence,
                "strategy_cost_delta": proposal_cost,
            }
            cmp_id = self.ledger.add_comparison(
                current,
                candidate,
                improver,
                protocol={
                    **self.protocol,
                    "split": split,
                    "mode": mode,
                    "seed": seed,
                    "inputs": self.check_inputs(),
                },
                results=results,
                costs=proposal_cost,
            )
            record["comparison_id"] = cmp_id
        except (ValueError, RuntimeError) as exc:
            record = {
                "label": label,
                "parent_c": current,
                "improver_id": improver,
                "candidate_c": candidate,
                "selected_c": current,
                "status": "proposal_or_evaluation_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "evidence_ids": evidence,
                "strategy_cost_delta": {
                    k: usage(self.client.log_path)[k] - before[k] for k in before
                },
            }
        save(record_path, record)
        return record["selected_c"], record

    async def evolve_i(self, mode: str, history: list[Json]) -> tuple[str, Json]:
        path = self.root / "search" / ("I1-" + mode + ".json")
        if path.exists():
            record = load(path)
            return record["candidate_i"], record
        evidence = list(dict.fromkeys(e for h in history for e in h["evidence_ids"]))
        evidence += [h["comparison_id"] for h in history if "comparison_id" in h]
        # Histories contain only this arm's measured comparisons and source packets.
        identifier, proposal = await propose_improver(
            self.ledger,
            self.client,
            self.i0,
            {"evidence_mode": mode, "candidates": history},
            evidence,
            seed=3801,
        )
        save(
            path,
            {"candidate_i": identifier, "proposal": proposal, "evidence_ids": evidence},
        )
        return identifier, load(path)

    async def search(self) -> None:
        self.pools()
        histories = {}
        selections = {}
        for mode in ("success_only", "paired"):
            current = self.c0
            history = []
            for index in range(self.protocol["candidate_budget"]["initial_I"]):
                current, record = await self.step(
                    mode + f"-I0-{index}",
                    current,
                    self.i0,
                    mode,
                    "development",
                    3701 + index,
                )
                history.append(record)
            new_i, i_record = await self.evolve_i(mode, history)
            for index in range(self.protocol["candidate_budget"]["evolved_I"]):
                current, record = await self.step(
                    mode + f"-I1-{index}",
                    current,
                    new_i,
                    mode,
                    "development",
                    3901 + index,
                )
                history.append(record)
            histories[mode] = {"candidates": history, "I_evolution": i_record}
            candidate_ids = list(
                dict.fromkeys(
                    [self.c0]
                    + [r["candidate_c"] for r in history if r.get("candidate_c")]
                )
            )
            selection_results = []
            selected = self.c0
            selected_score = None
            for cid in candidate_ids:
                try:
                    measured = await self.evaluate("selection", cid, mode, "selection")
                    selection_results.append(measured)
                    if (
                        selected_score is None
                        or score(measured["rows"]) > selected_score
                    ):
                        selected, selected_score = cid, score(measured["rows"])
                except (ValueError, RuntimeError) as exc:
                    selection_results.append(
                        {
                            "compiler_id": cid,
                            "status": "failed",
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        }
                    )
            histories[mode]["independent_selection"] = selection_results
            selections[mode] = {
                "C": selected,
                "I": new_i,
                "development_selected_C": current,
            }
        reset = {}
        for label, improver in (("I0", self.i0), ("I1", selections["paired"]["I"])):
            current = self.c0
            history = []
            for index in range(self.protocol["candidate_budget"]["reset_per_I"]):
                current, record = await self.step(
                    "reset-" + label + f"-{index}",
                    current,
                    improver,
                    "paired",
                    "reset",
                    4701 + index,
                )
                history.append(record)
            result = await self.evaluate("reset", current, "paired", "reset")
            reset[label] = {
                "initial_C": self.c0,
                "I": improver,
                "selected_C": current,
                "candidate_budget": len(history),
                "history": history,
                "result": result,
            }
        save(
            self.root / "search-result.json",
            {
                "C0": self.c0,
                "I0": self.i0,
                "selections": selections,
                "histories": histories,
                "reset": reset,
                "inputs": self.check_inputs(),
                "strategy_usage": usage(self.client.log_path),
            },
        )
        save(
            self.root / "status.json",
            {"state": "search_complete", "final_outcomes_opened": False},
        )

    def freeze(self) -> None:
        path = self.root / "final-freeze.json"
        if path.exists():
            raise ValueError("final protocol is already sealed")
        result = load(self.root / "search-result.json")
        value = {
            "inputs": self.check_inputs(),
            "selections": result["selections"],
            "C0": self.c0,
            "I0": self.i0,
            "protocol": self.protocol,
            "pools_sha256": digest((self.root / "pools.json").read_bytes()),
            "model_startup": load(Path("runs/forkrsi/model-service/startup.json")),
            "runtime_sha256": digest(
                Path("artifacts/forkrsi/runtime312-freeze.txt").read_bytes()
            ),
            "created_unix": time.time(),
            "final_outcomes_opened": False,
        }
        save(path, {"seal_sha256": sha(value), "value": value})

    async def final(self) -> None:
        seal = load(self.root / "final-freeze.json")
        value = seal["value"]
        if sha(value) != seal["seal_sha256"] or value["inputs"] != self.check_inputs():
            raise ValueError("sealed final protocol or inputs changed")
        if digest((self.root / "pools.json").read_bytes()) != value["pools_sha256"]:
            raise ValueError("sealed candidate pools changed")
        results = {}
        for mode in self.protocol["final_modes"]:
            if mode == "success_only_evolved":
                c, evidence_mode = (
                    value["selections"]["success_only"]["C"],
                    "success_only",
                )
            elif mode == "paired_evolved":
                c, evidence_mode = value["selections"]["paired"]["C"], "paired"
            elif mode == "success_only_initial":
                c, evidence_mode = self.c0, "success_only"
            elif mode == "paired_initial":
                c, evidence_mode = self.c0, "paired"
            else:
                c, evidence_mode = self.c0, mode
            results[mode] = await self.evaluate("final", c, evidence_mode, "final")
        save(
            self.root / "final-result.json",
            {
                "seal_sha256": seal["seal_sha256"],
                "results": results,
                "strategy_usage": usage(self.client.log_path),
                "completed_unix": time.time(),
            },
        )
        save(
            self.root / "status.json",
            {"state": "complete", "final_outcomes_opened": True},
        )

    async def close(self) -> None:
        await self.client.close()
        self.store.close()


async def run(root: Path, source: Path, protocol: Path, phase: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if git(Path.cwd(), "status", "--porcelain"):
            raise RuntimeError(
                "campaign requires committed clean implementation and task definitions"
            )
        await asyncio.to_thread(
            subprocess.run,
            ["python", "scripts/check_forkrsi_budget.py", "--reserve-hours", "2"],
            check=True,
        )
        campaign = Campaign(root, source, protocol)
        save(
            root / "worker.json",
            {"pid": os.getpid(), "phase": phase, "started_unix": time.time()},
        )
        try:
            if phase == "search":
                await campaign.search()
            elif phase == "freeze":
                campaign.freeze()
            elif phase == "final":
                await campaign.final()
            else:
                raise ValueError("unknown campaign phase")
        except BaseException as exc:
            save(
                root / "status.json",
                {
                    "state": "interrupted_or_failed",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "traceback": traceback.format_exc(),
                },
            )
            raise
        finally:
            await campaign.close()
