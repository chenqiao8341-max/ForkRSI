"""Authenticate the uniform vLLM replication and all retained original costs."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from collections import defaultdict
from contextlib import closing
from itertools import pairwise
from pathlib import Path
from typing import Any

from audit_workflow_programs import audit
from summarize_forkrsi import paired_interval, source_cost_record, statistics
from transformers import AutoTokenizer

from forkmem.environment import digest
from forkmem.models import DecisionFork
from forkmem.rsi.campaign import authenticated_result, load, save, usage
from forkmem.rsi.ledger import sha
from forkmem.rsi.qualification import qualify_row, reviewed_flags
from forkmem.workflows.memory import final_code

Json = dict[str, Any]


def verify_vllm_usage(root: Path) -> Json:
    """Join actual requests; fail closed on unmatched or cancelled traffic."""
    service = root.parent / "model-service-vllm"
    deployment = root.parent / "vllm-deployment"
    server = [
        json.loads(s) for s in (service / "requests.jsonl").read_text().splitlines()
    ]
    accepted = [
        json.loads(s) for s in (service / "accepted.jsonl").read_text().splitlines()
    ]
    by_id = {r["service_request_id"]: r for r in server}
    assert len(by_id) == len(server) == len(accepted)
    assert by_id.keys() == {r["service_request_id"] for r in accepted}
    assert all(r["status"] == "complete" for r in server), (
        "Failed/cancelled backend requests require explicit measured-usage reconciliation"
    )
    for record in accepted:
        assert all(
            by_id[record["service_request_id"]][k] == v for k, v in record.items()
        )
    for client_id in {r["client_request_id"] for r in server}:
        sequence = sorted(
            [r for r in server if r["client_request_id"] == client_id],
            key=lambda r: r["accepted_unix"],
        )
        assert all(
            a["finished_unix"] <= b["accepted_unix"]
            for a, b in pairwise(sequence)
        ), "Repairs sharing client ID must be serial"
    tokenizer = AutoTokenizer.from_pretrained(
        "/root/autodl-tmp/models/Qwen3.5-4B", local_files_only=True
    )
    unmatched = dict(by_id)
    joins = []
    probe_usage = defaultdict(int)

    def match(
        messages: list,
        content: str,
        measured: dict,
        seed: int,
        client_id: str | None = None,
        service_id: str | None = None,
    ) -> dict:
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        ids = tokenizer.encode(prompt, add_special_tokens=True)
        prompt_sha = digest(prompt.encode())
        ids_sha = digest(json.dumps(ids, separators=(",", ":")).encode())
        matches = [
            r
            for r in unmatched.values()
            if (service_id is None or r["service_request_id"] == service_id)
            and (client_id is None or r["client_request_id"] == client_id)
            and r["seed"] == seed
            and r["prompt_sha256"] == prompt_sha
            and r["response_sha256"] == digest(content.encode())
        ]
        if client_id is not None:
            sequence = sorted(
                [r for r in unmatched.values() if r["client_request_id"] == client_id],
                key=lambda r: r["accepted_unix"],
            )
            assert sequence and sequence[0] in matches, (
                "Client attempt must match the next actual serial server request"
            )
            r = sequence[0]
        else:
            assert len(matches) == 1, "Exact probe response service ID must be unique"
            r = matches[0]
        assert r["prompt_token_ids_sha256"] == ids_sha and r["prompt_tokens"] == len(
            ids
        )
        assert (
            r["usage"] == measured
            and measured["total_tokens"]
            == measured["prompt_tokens"] + measured["completion_tokens"]
        )
        unmatched.pop(r["service_request_id"])
        return r

    for path in sorted((root / "evaluations/final").rglob("*-llm.jsonl")):
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            call = json.loads(line)
            assert call.get("usage") and call.get("response") is not None
            r = match(
                call["messages"],
                call["response"],
                call["usage"],
                call["seed"],
                client_id=call["request_id"],
            )
            assert (
                r["max_tokens"] == call["max_tokens"]
                and r["temperature"] == call["temperature"]
                and r["top_p"] == call["top_p"]
            )
            joins.append(
                {
                    "client_log": str(path),
                    "line_1based": line_number,
                    "client_record_sha256": digest(line.encode()),
                    "client_request_id": call["request_id"],
                    "attempt": call["attempt"],
                    "service_request_id": r["service_request_id"],
                    "backend_response_id": r["backend_response_id"],
                    "usage": r["usage"],
                    "prompt_sha256": r["prompt_sha256"],
                    "response_sha256": r["response_sha256"],
                }
            )
    for name in ["concurrency-benchmark.json", "original-schema-smoke.json"]:
        artifact = load(deployment / name)
        for row in artifact["records"]:
            request, response = row["request"], row["response"]
            service_id = response["id"].removeprefix("forkrsi-vllm-")
            r = match(
                request["messages"],
                response["choices"][0]["message"]["content"],
                response["usage"],
                request["seed"],
                service_id=service_id,
            )
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                probe_usage[k] += r["usage"][k]
    assert not unmatched, "Unassigned vLLM adapter completions"
    direct = load(deployment / "concurrency-long-output.json")
    raw = [
        json.loads(s)
        for s in (deployment / "concurrency-long-output-requests.jsonl")
        .read_text()
        .splitlines()
    ]
    assert raw == direct["records"] and len(raw) == 25
    assert len({r["response"]["id"] for r in raw}) == len(raw)
    direct_usage = {
        k: sum(r["response"]["usage"][k] for r in raw)
        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    assert direct_usage == direct["total_measured_usage"]
    assert all(
        r["request"]["ignore_eos"]
        and r["request"]["min_tokens"]
        == r["request"]["max_tokens"]
        == r["response"]["usage"]["completion_tokens"]
        for r in raw
    )
    return {
        "adapter_usage": {
            k: sum(r["usage"][k] for r in server)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
        "adapter_completion_records": len(server),
        "task_client_request_joins": joins,
        "adapter_probe_tokens": dict(probe_usage),
        "direct_engine_benchmark_tokens": direct_usage,
        "adapter_log_sha256": digest((service / "requests.jsonl").read_bytes()),
        "accepted_log_sha256": digest((service / "accepted.jsonl").read_bytes()),
        "direct_raw_log_sha256": digest(
            (deployment / "concurrency-long-output-requests.jsonl").read_bytes()
        ),
        "all_accepted_adapter_requests_closed_and_joined": True,
        "unassigned_adapter_completions": 0,
        "policy": "Task attempts joined by client ID and serial request ordinal plus exact original-rendered prompt/output hashes and usage; probe requests joined by exact response service ID. Direct synthetic engine requests are a separately authenticated usage supplement.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--campaign", type=Path, default=Path("runs/forkrsi/campaign-vllm-final-v1")
    )
    parser.add_argument(
        "--source", type=Path, default=Path("runs/forkrsi/source-package-v1")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/forkrsi/pilot-vllm-v1")
    )
    parser.add_argument(
        "--search-campaign", type=Path, default=Path("runs/forkrsi/campaign-v2")
    )
    args = parser.parse_args()
    root, source, out = args.campaign, args.source, args.output
    origin = args.search_campaign
    subprocess.run(
        [sys.executable, str(root / "audit_final_inputs.py"), "--require-complete"],
        check=True,
    )
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
    for campaign_root in (origin, root):
        for metrics in (campaign_root / "evaluations").rglob("metrics.json"):
            row = load(metrics)
            indexed[row["episode_id"]] = Path(row["episode_dir"])
    assert len(indexed) == 62 + 32 + 56, (
        "All actual search, closed legacy final and vLLM final episodes must be audited"
    )
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

    source_review = reviewed_flags(source_flags, reviews[0])
    campaign_review = reviewed_flags(target_flags, reviews[1])
    raw_results = results
    results = {
        mode: {
            **result,
            "rows": [qualify_row(row, campaign_review) for row in result["rows"]],
        }
        for mode, result in raw_results.items()
    }
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
        [
            qualify_row(r, campaign_review)
            for r in search["reset"]["I0"]["result"]["rows"]
        ],
        [
            qualify_row(r, campaign_review)
            for r in search["reset"]["I1"]["result"]["rows"]
        ],
    )
    with closing(sqlite3.connect(origin / "strategies.sqlite")) as db:
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
        if (
            p.is_dir()
            and (p / "status.json").exists()
            and (p / "manifest.json").exists()
        ):
            source_runs.append(source_cost_record(p))
    prior_campaign_trials = [
        {
            "path": str(p),
            "status": load(p / "status.json"),
            "strategy_usage": usage(p / "strategy-llm.jsonl"),
            "task_episode_records": len(list(p.rglob("episode.json"))),
        }
        for p in sorted(root.parent.glob("campaign-v*"))
        if p.is_dir()
        and p.resolve() not in {root.resolve(), origin.resolve()}
        and (p / "status.json").exists()
    ]
    extraction_calls = [
        json.loads(s) for s in (origin / "strategy-llm.jsonl").read_text().splitlines()
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
        stage_root = root if stage == "final" else origin
        files = list((stage_root / "evaluations" / stage).rglob("*-llm.jsonl"))
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
    runtime_probe_costs = [
        {
            "path": str(root.parent / name),
            "usage": usage(root.parent / name / "llm.jsonl"),
            "scope": "infrastructure/calibration before strategy comparisons",
        }
        for name in ("model-smoke", "agent-calibration")
    ]
    phase_usages = (
        [r["usage"] for r in source_runs]
        + [r["strategy_usage"] for r in prior_campaign_trials]
        + list(strategy_costs.values())
        + list(execution_costs.values())
        + [r["usage"] for r in runtime_probe_costs]
    )
    phase_tokens = {
        key: sum(r[key] for r in phase_usages)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    legacy_files = sorted((origin / "evaluations/final").rglob("*-llm.jsonl"))
    legacy_usage = {
        k: sum(usage(p)[k] for p in legacy_files)
        for k in ("requests", "prompt_tokens", "completion_tokens", "total_tokens")
    }
    closed = load(origin / "transformers-backend-closed-cost.json")
    assert (
        digest((root.parent / "model-service/requests.jsonl").read_bytes())
        == closed["model_service_log_sha256"]
    )
    assert {k: legacy_usage[k] for k in phase_tokens} == closed["partial_final_usage"]
    old_phase = {
        k: phase_tokens[k] - execution_costs["final"][k] + legacy_usage[k]
        for k in phase_tokens
    }
    assert old_phase == closed["model_service_usage"], (
        "Original costs must still reconcile exactly"
    )
    new_reconciliation = verify_vllm_usage(root)
    new_probe = new_reconciliation["adapter_probe_tokens"]
    direct_probe = new_reconciliation["direct_engine_benchmark_tokens"]
    phase_tokens = {
        k: old_phase[k] + execution_costs["final"][k] + new_probe[k] + direct_probe[k]
        for k in phase_tokens
    }
    service_usage = {
        k: closed["model_service_usage"][k]
        + new_reconciliation["adapter_usage"][k]
        + direct_probe[k]
        for k in phase_tokens
    }
    service_difference = {k: service_usage[k] - phase_tokens[k] for k in phase_tokens}
    assert not any(service_difference.values()), (
        "Every measured model token must be assigned"
    )
    reconciliation = {
        "recorded_phase_tokens_including_probes_and_cancelled_completion": phase_tokens,
        "actual_model_service_usage": service_usage,
        "server_tokens_not_assigned_to_recorded_phases": service_difference,
        "all_model_tokens_assigned": True,
        "legacy_closed": closed,
        "vllm": new_reconciliation,
        "policy": "Legacy aggregate reconciliation plus vLLM per-request client-ID/prompt/output/usage join. Direct synthetic engine benchmark counted separately once. GPT subscription provider tokens unknown.",
    }
    save(out / "vllm-request-cost-join.json", new_reconciliation)
    legacy_rows = [
        load(p) for p in (origin / "evaluations/final").rglob("metrics.json")
    ]
    legacy_by_mode = defaultdict(list)
    for row in legacy_rows:
        mode = row["mode"]
        if mode in {"success_only", "paired"}:
            mode += "_initial" if row["compiler_id"] == search["C0"] else "_evolved"
        legacy_by_mode[mode].append(qualify_row(row, campaign_review))
    assert len(legacy_rows) == 32
    legacy_passes = load(origin / "passing-program-reviews-final.json")["reviews"]
    assert {r["episode_id"] for r in legacy_rows if r["success"]} == {
        r["episode_id"] for r in legacy_passes
    }
    legacy_statistics = {
        m: statistics(rows, legacy_by_mode["none"])
        for m, rows in legacy_by_mode.items()
        if len(rows) == 8
    }
    new_passes = load(root / "passing-program-reviews-final.json")["reviews"]
    new_passing_rows = {
        r["episode_id"]: r
        for result in raw_results.values()
        for r in result["rows"]
        if r["success"]
    }
    assert len(new_passes) == len({r["episode_id"] for r in new_passes})
    assert new_passing_rows.keys() == {r["episode_id"] for r in new_passes}, (
        "Every complete pass needs its manual code review"
    )
    for review in new_passes:
        row = new_passing_rows[review["episode_id"]]
        assert review["code_sha256"] == digest(row["final_code"].encode())
        assert (
            review["log_sha256"] == row["log_sha256"]
            and review["contract_adherent"] is True
            and review["rationale"]
        )
    assert (
        digest((source / "program-audit.json").read_bytes())
        == frozen["inputs"]["source_program_audit_sha256"]
    )
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
        "scope": "Frozen-weight single-GPU pilot; vLLM replication of the same final tasks and preselected strategies, not a new unseen sample. Semantic task remains statistical unit.",
        "backend_migration": load(
            root.parent / "vllm-deployment/user-requested-migration.json"
        ),
        "legacy_partial_final": {
            "complete_cells": 32,
            "expected_whole_grid": 56,
            "scope": "Closed separately for explicit user backend migration; not a complete seven-arm result",
            "statistics_for_fully_completed_arms": legacy_statistics,
            "usage": legacy_usage,
            "manual_passing_program_reviews": legacy_passes,
        },
        "manual_vllm_passing_program_reviews": new_passes,
        "original_search_campaign": str(origin.resolve()),
        "selected_strategy_characterization": load(
            origin / "selected-strategy-characterization.json"
        ),
        "vllm_synthetic_throughput": {
            k: v
            for k, v in load(
                root.parent / "vllm-deployment/concurrency-long-output.json"
            ).items()
            if k != "records"
        },
        "seal": seal,
        "final_statistics": table,
        "paired_comparisons": pairs,
        "I_reset": reset,
        "source_summary": source_summary,
        "source_collection_costs_including_failed_calibration": source_runs,
        "prior_campaign_trials_including_failed_extraction": prior_campaign_trials,
        "strategy_costs_by_schema": strategy_costs,
        "runtime_probe_costs": runtime_probe_costs,
        "model_service_cost_reconciliation": reconciliation,
        "execution_costs_by_stage": execution_costs,
        "C0": search["C0"],
        "I0": search["I0"],
        "selected": search["selections"],
        "versions": versions,
        "comparisons": comparisons,
        "qualification_policy": {
            "safe_success": "authenticated complete verifier success plus unchanged screen/manual flag review",
            "raw_selection": "fixed search/selection objective uses raw verifier results; no outcome-driven strategy reselection",
            "source_reviewed_flags": source_review,
            "raw_final_results_path": str(root / "final-result.json"),
        },
        "program_screen": {
            "source": source_flags,
            "campaign": target_flags,
            "reviews": reviews,
            "limitation": "original AST screen/manual review is not adversarial Python proof",
        },
        "unique_final_executions": len(actual_episodes),
        "final_arm_cell_count": sum(len(v["rows"]) for v in results.values()),
        "alias_disclosure": "All 56 vLLM cells are distinct executions. The 32 closed legacy backend cells remain separate; neither repetitions nor nested cases are independent semantic tasks.",
        "limitations": [
            "Same final task identities used for explicit backend replication after 32 legacy outcomes opened; no strategy reselection or unseen-sample claim",
            "C/I search and compiled RuleSets retain their original Transformers inference provenance; only final task execution uses vLLM",
            "Paired evolved selected C removes factual/falsified blocks; its actual extraction input is positive-only, so final gains cannot demonstrate a direct counterfactual injection benefit",
            "Nominal 240-second task wall budget is checked between actions; JSON repair calls can exceed it equally across arms",
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
