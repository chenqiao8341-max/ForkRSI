"""Versioned durable store and explicit evidence-based retrieval."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol

from forkmem.models import (
    Branch,
    DecisionFork,
    EvidenceStatus,
    ExperimentDebt,
    NegativeLesson,
    Outcome,
    StateFingerprint,
)


class ForkStore(Protocol):
    def put(self, fork: DecisionFork) -> None: ...
    def all(self) -> list[DecisionFork]: ...
    def negatives(self) -> list[NegativeLesson]: ...


class SQLiteForkStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS forks (id TEXT, version INTEGER, body TEXT, PRIMARY KEY(id,version))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS debt (id TEXT PRIMARY KEY, body TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS negative_lessons (id TEXT PRIMARY KEY, body TEXT)"
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def put(self, fork: DecisionFork) -> None:
        fork = DecisionFork.model_validate_json(fork.model_dump_json())
        with self.db:
            previous = self.db.execute(
                "SELECT MAX(version) FROM forks WHERE id=?", (fork.fork_id,)
            ).fetchone()[0]
            if fork.version != (previous or 0) + 1:
                raise ValueError("append-only versions must increment by one")
            self.db.execute(
                "INSERT INTO forks VALUES (?,?,?)",
                (fork.fork_id, fork.version, fork.model_dump_json()),
            )

    def all(self) -> list[DecisionFork]:
        rows = self.db.execute(
            "SELECT body FROM forks f WHERE version=(SELECT MAX(version) FROM forks WHERE id=f.id) ORDER BY id"
        ).fetchall()
        return [DecisionFork.model_validate_json(row[0]) for row in rows]

    def history(self, fork_id: str) -> list[DecisionFork]:
        return [
            DecisionFork.model_validate_json(row[0])
            for row in self.db.execute(
                "SELECT body FROM forks WHERE id=? ORDER BY version", (fork_id,)
            )
        ]

    def put_negative(self, lesson: NegativeLesson) -> None:
        lesson = NegativeLesson.model_validate_json(lesson.model_dump_json())
        with self.db:
            self.db.execute(
                "INSERT INTO negative_lessons VALUES (?,?)",
                (lesson.lesson_id, lesson.model_dump_json()),
            )

    def negatives(self) -> list[NegativeLesson]:
        return [
            NegativeLesson.model_validate_json(row[0])
            for row in self.db.execute("SELECT body FROM negative_lessons ORDER BY id")
        ]

    def enqueue(self, debt: ExperimentDebt) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO debt VALUES (?,?)", (debt.debt_id, debt.model_dump_json())
            )

    def pending(self) -> list[ExperimentDebt]:
        return [
            d
            for row in self.db.execute("SELECT body FROM debt")
            if (d := ExperimentDebt.model_validate_json(row[0])).status == "pending"
        ]

    def resolve(self, debt_id: str) -> None:
        with self.db:
            row = self.db.execute(
                "SELECT body FROM debt WHERE id=?", (debt_id,)
            ).fetchone()
            if row is None:
                raise KeyError(debt_id)
            debt = ExperimentDebt.model_validate_json(row[0])
            debt.status = "resolved"
            self.db.execute(
                "UPDATE debt SET body=? WHERE id=?", (debt.model_dump_json(), debt_id)
            )


def update_evidence(branch: Branch, outcome: Outcome, factual_reward: float) -> Branch:
    if branch.kind != "counterfactual":
        raise ValueError("only counterfactual evidence can be promoted")
    if any(o.execution_id == outcome.execution_id for o in branch.outcomes):
        raise ValueError("duplicate execution cannot increase confidence")
    outcomes = [*branch.outcomes, outcome]
    delta = sum(o.reward for o in outcomes) / len(outcomes) - factual_reward
    if not all(o.success and o.reward > factual_reward for o in outcomes):
        status, confidence = EvidenceStatus.FALSIFIED, 0.0
    elif len(outcomes) >= 3:
        status, confidence = EvidenceStatus.REPEATEDLY_VERIFIED, 0.95
    else:
        status, confidence = EvidenceStatus.REPLAY_VERIFIED, 0.70
    return Branch.model_validate(
        {
            **branch.model_dump(),
            "outcomes": outcomes,
            "reward_delta": delta,
            "evidence_status": status,
            "confidence": confidence,
        }
    )


def retrieve(
    store: ForkStore, state: StateFingerprint, mode: str = "verified", limit: int = 4
) -> list[tuple[DecisionFork, Branch, float]]:
    if mode not in {
        "none",
        "negative",
        "imagined",
        "paired",
        "verified",
        "no_applicability",
        "no_evidence",
        "positive_only",
    }:
        raise ValueError(f"unknown memory mode: {mode}")
    if mode in {"none", "negative"}:
        return []
    candidates = []
    for fork in store.all():
        if (
            fork.state.environment != state.environment
            or fork.state.task_family != state.task_family
        ):
            continue
        if mode not in {
            "no_applicability",
            "imagined",
        } and not fork.applicability.matches(state.features):
            continue
        for branch in fork.alternatives:
            if branch.evidence_status in {
                EvidenceStatus.SUPERSEDED,
                EvidenceStatus.EXPIRED,
            }:
                continue
            if mode in {"imagined", "paired"}:
                branch = Branch.model_validate(
                    {
                        **branch.model_dump(),
                        "evidence_status": EvidenceStatus.IMAGINED,
                        "outcomes": [],
                        "reward_delta": None,
                        "confidence": 0.1,
                        "continuation_actions": [],
                    }
                )
            if branch.evidence_status in {
                EvidenceStatus.FALSIFIED,
                EvidenceStatus.SUPERSEDED,
                EvidenceStatus.EXPIRED,
            }:
                continue
            if mode in {
                "verified",
                "no_applicability",
                "positive_only",
                "no_evidence",
            } and branch.evidence_status not in {
                EvidenceStatus.REPLAY_VERIFIED,
                EvidenceStatus.REPEATEDLY_VERIFIED,
            }:
                continue
            overlap = len(
                set(state.summary.lower().split())
                & set(fork.state.summary.lower().split())
            ) / max(1, len(set(state.summary.lower().split())))
            score = (
                1
                + overlap
                + (0 if mode == "no_evidence" else branch.confidence)
                + (branch.reward_delta or 0)
            )
            candidates.append((fork, branch, score))
    return sorted(
        candidates, key=lambda item: (-item[2], item[0].fork_id, item[1].branch_id)
    )[:limit]


def render_memory(items: list[tuple[DecisionFork, Branch, float]], mode: str) -> str:
    lines = []
    for fork, branch, _ in items:
        factual = (
            f"Observed failed action: {fork.factual.first_action.model_dump_json()}"
        )
        if mode == "negative":
            lines.append(factual)
            continue
        verified = branch.evidence_status in {
            EvidenceStatus.REPLAY_VERIFIED,
            EvidenceStatus.REPEATEDLY_VERIFIED,
        }
        label = (
            "Execution-verified alternative"
            if verified
            else "UNVERIFIED HYPOTHESIS; do not treat as established"
        )
        entry = {
            "evidence": label,
            "applicable": fork.applicability.model_dump(),
            "lesson": fork.lesson,
            "alternative": branch.first_action.model_dump(),
            "prediction": branch.predicted_outcome,
            "verified_continuation": [
                a.model_dump() for a in branch.continuation_actions
            ]
            if verified
            else [],
            "successful_replays": sum(o.success for o in branch.outcomes),
        }
        if mode not in {"imagined", "positive_only"}:
            entry["factual"] = factual
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)


def negative_context(
    store: ForkStore, state: StateFingerprint, limit: int = 4
) -> tuple[str, list[str]]:
    lessons = [
        lesson
        for lesson in store.negatives()
        if lesson.state.environment == state.environment
        and lesson.state.task_family == state.task_family
    ]
    rows = []
    for lesson in lessons[:limit]:
        rows.append(
            json.dumps(
                {
                    "observed_failed_action": lesson.action.model_dump(),
                    "observed_reward": lesson.outcome.reward,
                    "failure": lesson.summary,
                    "source_context": lesson.state.features,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(rows), [lesson.lesson_id for lesson in lessons[:limit]]
