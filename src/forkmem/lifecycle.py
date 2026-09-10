"""Auditable memory revision; no evidence status changes from model text."""

from __future__ import annotations

from forkmem.memory import SQLiteForkStore, update_evidence
from forkmem.models import Applicability, Branch, DecisionFork, EvidenceStatus, Outcome


def current(store: SQLiteForkStore, fork_id: str) -> DecisionFork:
    history = store.history(fork_id)
    if not history:
        raise KeyError(fork_id)
    return history[-1]


def add_execution(
    store: SQLiteForkStore, fork_id: str, branch_id: str, outcome: Outcome
) -> DecisionFork:
    fork = current(store, fork_id)
    if outcome.checkpoint != fork.state.checkpoint:
        raise ValueError(
            "execution belongs to a different checkpoint; create a linked fork instead"
        )
    reward = fork.factual.outcomes[0].reward
    found = False
    alternatives = []
    for branch in fork.alternatives:
        if branch.branch_id == branch_id:
            if branch.evidence_status in {
                EvidenceStatus.SUPERSEDED,
                EvidenceStatus.EXPIRED,
            }:
                raise ValueError("terminal memory cannot be silently revived")
            branch = update_evidence(branch, outcome, reward)
            found = True
        alternatives.append(branch)
    if not found:
        raise KeyError(branch_id)
    updated = DecisionFork.model_validate(
        {**fork.model_dump(), "alternatives": alternatives, "version": fork.version + 1}
    )
    store.put(updated)
    return updated


def narrow_applicability(
    store: SQLiteForkStore, fork_id: str, rule: Applicability, reason: str
) -> DecisionFork:
    fork = current(store, fork_id)
    for field in ["requires", "excludes"]:
        old = getattr(fork.applicability, field)
        new = getattr(rule, field)
        if any(new.get(key) != value for key, value in old.items()):
            raise ValueError(
                "revision may narrow but cannot silently weaken old predicates"
            )
    if not reason.strip():
        raise ValueError("revision requires an audit reason")
    changes = list(fork.provenance.get("revisions", []))
    changes.append(
        {
            "kind": "narrow_applicability",
            "reason": reason,
            "previous_version": fork.version,
        }
    )
    updated = DecisionFork.model_validate(
        {
            **fork.model_dump(),
            "applicability": rule,
            "version": fork.version + 1,
            "provenance": {**fork.provenance, "revisions": changes},
        }
    )
    store.put(updated)
    return updated


def supersede(
    store: SQLiteForkStore, fork_id: str, replacement_id: str
) -> DecisionFork:
    if fork_id == replacement_id:
        raise ValueError("a memory cannot supersede itself")
    fork = current(store, fork_id)
    replacement = current(store, replacement_id)
    if replacement.state.task_family != fork.state.task_family:
        raise ValueError("replacement must address the same task family")
    alternatives = [
        Branch.model_validate(
            {**branch.model_dump(), "evidence_status": EvidenceStatus.SUPERSEDED}
        )
        for branch in fork.alternatives
    ]
    updated = DecisionFork.model_validate(
        {
            **fork.model_dump(),
            "alternatives": alternatives,
            "version": fork.version + 1,
            "provenance": {**fork.provenance, "superseded_by": replacement_id},
        }
    )
    store.put(updated)
    return updated


def consolidate_exact(store: SQLiteForkStore) -> int:
    """Merge only identical checkpoint/action plans; preserve every old version."""
    import json

    groups: dict[str, list[DecisionFork]] = {}

    def plan(branch: Branch) -> str:
        return json.dumps(
            {
                "first": branch.first_action.model_dump(),
                "continuation": [a.model_dump() for a in branch.continuation_actions],
            },
            sort_keys=True,
        )

    for fork in store.all():
        if all(
            branch.evidence_status
            in {EvidenceStatus.SUPERSEDED, EvidenceStatus.EXPIRED}
            for branch in fork.alternatives
        ):
            continue
        key = json.dumps(
            {
                "state": fork.state.model_dump(),
                "factual": fork.factual.first_action.model_dump(),
                "factual_reward": fork.factual.outcomes[0].reward,
                "applicability": fork.applicability.model_dump(),
                "plans": sorted(plan(branch) for branch in fork.alternatives),
            },
            sort_keys=True,
        )
        groups.setdefault(key, []).append(fork)
    merged = 0
    for group in groups.values():
        keeper = group[0]
        for duplicate in group[1:]:
            for incoming in duplicate.alternatives:
                keeper = current(store, keeper.fork_id)
                target = next(
                    branch
                    for branch in keeper.alternatives
                    if plan(branch) == plan(incoming)
                )
                seen = {outcome.execution_id for outcome in target.outcomes}
                for outcome in incoming.outcomes:
                    if outcome.execution_id not in seen:
                        add_execution(store, keeper.fork_id, target.branch_id, outcome)
                        seen.add(outcome.execution_id)
            supersede(store, duplicate.fork_id, keeper.fork_id)
            merged += 1
    return merged
