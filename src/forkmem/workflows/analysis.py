"""Decision-level observations, separate from whole-episode evidence promotion."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from forkmem.environment import digest
from forkmem.models import Outcome

PREFIX = "FORKMEM_WORKFLOW_RESULT="


def read_workflow_outcome(outcome: Outcome) -> dict[str, Any]:
    raw = Path(outcome.log_path).read_bytes()
    if digest(raw) != outcome.output_sha256:
        raise ValueError("workflow log digest mismatch")
    records = [
        json.loads(line[len(PREFIX) :])
        for line in raw.decode().splitlines()
        if line.startswith(PREFIX)
    ]
    if len(records) != 1:
        raise ValueError("expected exactly one workflow observation record")
    result: dict[str, Any] = records[0]
    if not isinstance(result.get("obligations"), dict) or not all(
        type(v) is bool for v in result["obligations"].values()
    ):
        raise ValueError("invalid obligation observations")
    expected = bool(result["obligations"]) and all(result["obligations"].values())
    if result["success"] != expected or result["success"] != outcome.success:
        raise ValueError("workflow and external outcome disagree")
    return result


def contrast(factual: dict[str, Any], alternative: dict[str, Any]) -> dict[str, Any]:
    before, after = factual["obligations"], alternative["obligations"]
    if before.keys() != after.keys():
        raise ValueError("cannot compare different obligation definitions")
    old = [e["operation"] for e in factual["trace"] if e["kind"] == "apply"]
    new = [e["operation"] for e in alternative["trace"] if e["kind"] == "apply"]
    edits = [
        {"kind": tag, "factual": old[a:b], "alternative": new[c:d]}
        for tag, a, b, c, d in SequenceMatcher(
            a=old, b=new, autojunk=False
        ).get_opcodes()
        if tag != "equal"
    ]
    repaired = [name for name in before if not before[name] and after[name]]
    regressed = [name for name in before if before[name] and not after[name]]
    return {
        "repaired_obligations": repaired,
        "regressed_obligations": regressed,
        "preserved_passes": [name for name in before if before[name] and after[name]],
        "local_improvement_without_complete_success": bool(repaired)
        and not alternative["success"],
        "downstream_regression": bool(repaired and regressed),
        "globally_successful": alternative["success"],
        "operation_edits": edits,
        "interpretation": "Observed full-program contrast, not isolated causal attribution to each edit.",
    }


def read_workflow_cases(outcome: Outcome) -> dict[int, dict[str, Any]]:
    """Read aligned runtime cases; never compare different crash schedules."""
    aggregate = read_workflow_outcome(outcome)
    raw = Path(outcome.log_path).read_text()
    prefix = "FORKMEM_WORKFLOW_CASE="
    records = [
        json.loads(line[len(prefix) :])
        for line in raw.splitlines()
        if line.startswith(prefix)
    ]
    if not records:
        return {0: aggregate}
    cases = {record["case_id"]: record for record in records}
    if len(cases) != len(records) or len(cases) != aggregate["case_total"]:
        raise ValueError("duplicate or missing workflow runtime cases")
    if sum(case["success"] for case in cases.values()) != aggregate["case_successes"]:
        raise ValueError("aggregate workflow case count mismatch")
    for name, value in aggregate["obligations"].items():
        if value != all(case["obligations"][name] for case in cases.values()):
            raise ValueError("aggregate obligation mismatch")
    return cases


def aligned_contrasts(factual: Outcome, alternative: Outcome) -> list[dict[str, Any]]:
    before, after = read_workflow_cases(factual), read_workflow_cases(alternative)
    if before.keys() != after.keys():
        raise ValueError("different runtime case sets")
    result = []
    for key in before:
        old, new = before[key], after[key]
        if old.get("scheduled_crashes") != new.get("scheduled_crashes"):
            raise ValueError("different runtime crash schedule")
        result.append(
            {
                "case_id": key,
                "scheduled_crashes": old.get("scheduled_crashes", []),
                **contrast(old, new),
            }
        )
    return result
