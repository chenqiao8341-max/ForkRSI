"""Audit actual strategy generation against immutable raw model responses.

This reads the ledger without creating or updating tables. It does not run tasks,
change strategies, or reinterpret unsuccessful proposal slots as generated versions.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from forkmem.environment import digest
from forkmem.rsi.improver import FIXED, CompilerProposal, ImproverProposal
from forkmem.rsi.ledger import canonical, sha

Json = dict[str, Any]


def generation_matches(
    version: Json, by_id: dict[str, Json], calls: list[Json]
) -> list[Json]:
    provenance = version["provenance"]
    parent = by_id[version["parent_id"]]
    generator = by_id[provenance["generated_by_i"]]
    if parent["kind"] != version["kind"] or generator["kind"] != "I":
        raise ValueError("incorrect strategy parent/generator kind")
    changes = {
        key: {"before": parent["content"][key], "after": value}
        for key, value in version["content"].items()
        if parent["content"][key] != value
    }
    if changes != provenance["actual_changes"]:
        raise ValueError("strategy changes disagree with the actual parent")
    method = generator["content"]
    prefix = (
        method["diagnosis_prompt"] + "\n" + method["proposal_prompt"] + "\n" + FIXED
    )
    is_c = version["kind"] == "C"
    schema = CompilerProposal if is_c else ImproverProposal
    if is_c:
        prefix += "\nCurrent C: " + canonical(parent["content"])
        expected_run = "evolve-C-" + provenance["evidence_mode"]
    else:
        prefix += (
            "\nThe object to improve is now I, the method that diagnoses and proposes compiler "
            "modifications. Use the actual candidate comparison history, including rejected "
            "and regressing candidates, to revise both diagnostic and proposal methods. "
            "The new I will be used for subsequent C generation and an independent reset comparison."
        )
        prefix += "\nCurrent I: " + canonical(parent["content"])
        expected_run = "evolve-I"
    matches = []
    for call in calls:
        if (
            call.get("schema") != schema.__name__
            or call.get("status") != "ok"
            or call.get("episode_id") != generator["version_id"]
            or call.get("run_id") != expected_run
            or call.get("seed") != provenance["seed"]
            or is_c
            and call.get("branch_id") != parent["version_id"]
        ):
            continue
        parsed = schema.model_validate_json(call["response"]).model_dump(mode="json")
        if parsed != provenance["proposal"]:
            continue
        prompts = [m["content"] for m in call["messages"] if m["role"] == "user"]
        if not prompts or not prompts[0].startswith(prefix + "\n"):
            raise ValueError(
                "raw request did not consume the recorded I and parent strategy"
            )
        allowed = json.loads(prompts[0].rsplit("\nAllowed evidence IDs: ", 1)[1])
        if not set(parsed["evidence_ids"]) <= set(allowed):
            raise ValueError("proposal cites evidence outside its actual request")
        content = parsed["compiler" if is_c else "improver"]
        if content != version["content"] or sha(content) != version["content_sha256"]:
            raise ValueError(
                "raw response does not generate the recorded strategy content"
            )
        if parsed["evidence_ids"] != version["evidence"]:
            raise ValueError(
                "ledger strategy evidence differs from its actual proposal"
            )
        matches.append(
            {
                "request_id": call["request_id"],
                "log_line": call["_line_number"],
                "log_line_sha256": call["_line_sha256"],
                "response_sha256": digest(call["response"].encode()),
                "prompt_sha256": digest(prompts[0].encode()),
                "seed": call["seed"],
                "usage": call["usage"],
                "prompt_version": call["prompt_version"],
                "actual_I_fields_and_parent_in_request": True,
                "response_matches_proposal_and_content_hash": True,
            }
        )
    if not matches:
        raise ValueError(
            "generated strategy has no matching actual successful model call"
        )
    return matches


def audit(root: Path, require_complete: bool = False) -> Json:
    root = root.resolve()
    with closing(
        sqlite3.connect((root / "strategies.sqlite").as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.row_factory = sqlite3.Row
        versions = [
            dict(row)
            for row in db.execute("SELECT * FROM versions ORDER BY created_utc")
        ]
    for row in versions:
        row["content"] = json.loads(row["content_json"])
        row["evidence"] = json.loads(row["evidence_json"])
        row["provenance"] = json.loads(row["provenance_json"])
        if sha(row["content"]) != row["content_sha256"]:
            raise ValueError("strategy content hash mismatch")
        identity = {
            "kind": row["kind"],
            "parent": row["parent_id"],
            "content": row["content"],
            "evidence": row["evidence"],
            "provenance": row["provenance"],
        }
        if row["version_id"] != row["kind"] + "-" + sha(identity)[:24]:
            raise ValueError("strategy version identity mismatch")
    by_id = {row["version_id"]: row for row in versions}
    calls = []
    for line_number, line in enumerate(
        (root / "strategy-llm.jsonl").read_text().splitlines(), 1
    ):
        call = json.loads(line)
        calls.append(
            {**call, "_line_number": line_number, "_line_sha256": digest(line.encode())}
        )
    generated = {}
    for row in versions:
        if row["parent_id"] is not None:
            generated[row["version_id"]] = {
                "kind": row["kind"],
                "parent": row["parent_id"],
                "generated_by_i": row["provenance"]["generated_by_i"],
                "actual_changes": row["provenance"]["actual_changes"],
                "matching_actual_requests": generation_matches(row, by_id, calls),
            }
    completed = (root / "search-result.json").exists()
    recursive_arms = {}
    if completed:
        search = json.loads((root / "search-result.json").read_text())
        for mode, history in search["histories"].items():
            i1 = search["selections"][mode]["I"]
            children = [
                record["candidate_c"]
                for record in history["candidates"]
                if record["improver_id"] == i1 and record.get("candidate_c")
            ]
            recursive_arms[mode] = {
                "I1": i1,
                "I_changed": bool(generated[i1]["actual_changes"]),
                "generated_C_after_I_change": children,
                "actual_C_changes": {
                    cid: generated[cid]["actual_changes"] for cid in children
                },
            }
            if require_complete and (
                not recursive_arms[mode]["I_changed"]
                or not any(generated[cid]["actual_changes"] for cid in children)
            ):
                raise ValueError(
                    "complete audit requires changed I actually generating changed C"
                )
    if require_complete and (
        not completed or set(recursive_arms) != {"success_only", "paired"}
    ):
        raise ValueError("complete two-arm recursive search records are required")
    return {
        "campaign": str(root),
        "search_complete_record_present": completed,
        "strategy_versions": len(versions),
        "generated_versions": generated,
        "recursive_arms": recursive_arms,
        "scope": "raw successful request/response, parent/content/identity/evidence authentication; strategy effectiveness requires independent measured comparisons",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--campaign", type=Path, default=Path("runs/forkrsi/campaign-v2")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    result = audit(args.campaign, args.require_complete)
    output = args.output or args.campaign / "actual-generation-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "versions": result["strategy_versions"],
                "generated": len(result["generated_versions"]),
                "search_complete_record_present": result[
                    "search_complete_record_present"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
