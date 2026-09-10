"""Matched verified-code controls and paired, case-aligned operational evidence."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from forkmem.environment import digest
from forkmem.memory import ForkStore, render_memory, retrieve
from forkmem.models import Branch, EvidenceStatus, StateFingerprint
from forkmem.workflows.analysis import aligned_contrasts, read_workflow_outcome

MODES = [
    "none",
    "negative",
    "imagined",
    "paired_unverified",
    "flat_verified",
    "fork_verified",
    "legacy_verified",
    "unguarded_verified",
]
VERIFIED = {EvidenceStatus.REPLAY_VERIFIED, EvidenceStatus.REPEATEDLY_VERIFIED}


def final_code(branch: Branch) -> str:
    writes = [
        a.content
        for a in [branch.first_action, *branch.continuation_actions]
        if a.tool == "write" and a.path == "solution.py"
    ]
    return writes[-1] if writes else ""


def views(
    store: ForkStore,
    state: StateFingerprint,
    count_tokens: Callable[[str], int],
    *,
    token_cap: int = 6000,
    limit: int = 2,
    character_cap: int = 20000,
) -> dict[str, tuple[str, list[str]]]:
    """Select source contexts without target outcomes; pair/flat share positive IDs.

    Budget inclusion uses the largest paired view, so the flat verified control
    receives exactly the same final successful programs, not more examples.
    Unverified views are selected before outcome eligibility is considered.
    """
    forks = [
        f
        for f in store.all()
        if f.state.environment == state.environment
        and f.state.task_family == state.task_family
    ]
    forks.sort(
        key=lambda f: (
            -sum(state.features.get(k) == v for k, v in f.state.features.items()),
            f.source_episode_id,
            int(f.provenance.get("seed", 0)),
        )
    )
    packed: dict[str, list[dict[str, Any]]] = {mode: [] for mode in MODES}
    ids: dict[str, list[str]] = {mode: [] for mode in MODES}

    def fits(mode: str, entry: dict[str, Any]) -> bool:
        body = json.dumps([*packed[mode], entry], ensure_ascii=False)
        return len(body) <= character_cap and count_tokens(body) <= token_cap

    negatives = [
        n
        for n in store.negatives()
        if n.state.environment == state.environment
        and n.state.task_family == state.task_family
    ]
    negatives.sort(
        key=lambda n: (
            -sum(state.features.get(k) == v for k, v in n.state.features.items()),
            n.source_episode_id,
        )
    )
    negative_contexts: set[str] = set()
    hypothesis_contexts: set[str] = set()
    positive_contexts: set[str] = set()
    for lesson in negatives:
        context_key = json.dumps(lesson.state.features, sort_keys=True)
        if context_key in negative_contexts:
            continue
        entry = {
            "source_context": lesson.state.features,
            "evidence": "observed failure only",
            "source_failed_code": lesson.action.content,
            "observed_failure": lesson.summary,
        }
        if len(ids["negative"]) < limit and fits("negative", entry):
            packed["negative"].append(entry)
            ids["negative"].append(lesson.lesson_id)
            negative_contexts.add(context_key)
    for fork in forks:
        context_key = json.dumps(fork.state.features, sort_keys=True)
        source = {
            "source_context": fork.state.features,
            "scope": "Observed only in this source context; new combinations require checking the current contract.",
        }
        factual_code = final_code(fork.factual)
        factual_outcome = fork.factual.outcomes[-1]
        raw = Path(factual_outcome.log_path).read_bytes()
        if digest(raw) != factual_outcome.output_sha256:
            raise ValueError("factual source log digest mismatch")
        has_runtime_observation = any(
            line.startswith(b"FORKMEM_WORKFLOW_RESULT=") for line in raw.splitlines()
        )
        actual: dict[str, Any] = (
            read_workflow_outcome(factual_outcome)
            if has_runtime_observation
            else {
                "obligations": {"program_entered_and_completed": False},
                "trace": [
                    {
                        "failure_before_structured_result": raw.decode(
                            errors="replace"
                        )[-2000:]
                    }
                ],
            }
        )

        failed_observation = {
            "source_failed_code": factual_code,
            "failed_obligations": [
                k for k, v in actual["obligations"].items() if not v
            ],
            "first_failure_trace": actual["trace"][-4:],
        }
        # Original proposal order is retained, without consulting their outcomes.
        proposed = next(
            (
                b
                for b in fork.alternatives
                if b.evidence_status
                not in {EvidenceStatus.SUPERSEDED, EvidenceStatus.EXPIRED}
            ),
            None,
        )
        if (
            proposed is not None
            and len(ids["imagined"]) < limit
            and context_key not in hypothesis_contexts
        ):
            imaginary = {
                **source,
                "evidence": "UNVERIFIED hypothesis; outcome unknown",
                "predicted_code": proposed.first_action.content,
                "prediction": proposed.predicted_outcome,
            }
            paired = {**imaginary, **failed_observation}
            if fits("paired_unverified", paired) and fits("imagined", imaginary):
                for mode, entry in [
                    ("imagined", imaginary),
                    ("paired_unverified", paired),
                ]:
                    packed[mode].append(entry)
                    ids[mode].append(fork.fork_id)
                hypothesis_contexts.add(context_key)
        positive = next(
            (b for b in fork.alternatives if b.evidence_status in VERIFIED), None
        )
        if (
            positive is None
            or len(ids["fork_verified"]) >= limit
            or context_key in positive_contexts
        ):
            continue
        observed = read_workflow_outcome(positive.outcomes[-1])
        if not observed["success"]:
            raise ValueError("verified source program lacks complete workflow success")
        flat = {
            **source,
            "evidence": "execution-verified in the source context only",
            "successful_code": final_code(positive),
            "observed_obligations": observed["obligations"],
            "runtime_cases_passed": observed.get("case_successes", 1),
        }
        changes = (
            aligned_contrasts(factual_outcome, positive.outcomes[-1])
            if has_runtime_observation
            else []
        )
        repaired = [
            c
            for c in changes
            if c["repaired_obligations"] or c["regressed_obligations"]
        ]
        pair = {
            **flat,
            **failed_observation,
            "matched_case_contrasts": repaired[:3],
            "instruction": "Use the observed failure/success decision differences to adapt the controller. Preserve already passing obligations and verify restart/cleanup paths; do not transplant source-profile decisions blindly.",
        }
        unguarded = {
            k: v
            for k, v in pair.items()
            if k not in {"source_context", "scope", "instruction"}
        }
        if (
            fits("fork_verified", pair)
            and fits("flat_verified", flat)
            and fits("unguarded_verified", unguarded)
        ):
            for mode, entry in [
                ("fork_verified", pair),
                ("flat_verified", flat),
                ("unguarded_verified", unguarded),
            ]:
                packed[mode].append(entry)
                ids[mode].append(fork.fork_id + ":" + positive.branch_id)
            positive_contexts.add(context_key)
    result = {
        mode: (
            json.dumps(packed[mode], ensure_ascii=False) if packed[mode] else "",
            ids[mode],
        )
        for mode in MODES
    }
    legacy = retrieve(store, state, "verified", limit)
    while legacy and (
        len(render_memory(legacy, "verified")) > character_cap
        or count_tokens(render_memory(legacy, "verified")) > token_cap
    ):
        legacy.pop()
    result["legacy_verified"] = (
        render_memory(legacy, "verified"),
        [f.fork_id for f, _, _ in legacy],
    )
    return result
