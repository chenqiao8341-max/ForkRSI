"""Typed memory. Validation prevents epistemic promotion through text alone."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceStatus(StrEnum):
    OBSERVED = "observed"
    IMAGINED = "imagined"
    SANDBOX_TESTED = "sandbox_tested"
    REPLAY_VERIFIED = "replay_verified"
    REPEATEDLY_VERIFIED = "repeatedly_verified"
    FALSIFIED = "falsified"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class Action(StrictModel):
    tool: Literal["read", "search", "write", "test", "finish"]
    path: str = ""
    content: str = ""
    thought_summary: str = ""


class Outcome(StrictModel):
    success: bool
    reward: float = Field(ge=0, le=1)
    exit_code: int
    verifier: str = "microrepo-v1"
    checkpoint: str
    execution_id: str
    log_path: str
    output_sha256: str
    tree_sha256: str
    seed: int = 0

    @model_validator(mode="after")
    def coherent(self) -> Outcome:
        if self.success != (self.exit_code == 0):
            raise ValueError("success must agree with verifier exit code")
        return self


class Branch(StrictModel):
    branch_id: str = Field(default_factory=lambda: uuid4().hex)
    kind: Literal["factual", "counterfactual"]
    first_action: Action
    trajectory_ref: str
    predicted_outcome: str | None = None
    continuation_actions: list[Action] = Field(default_factory=list)
    evidence_status: EvidenceStatus
    outcomes: list[Outcome] = Field(default_factory=list)
    reward_delta: float | None = None
    confidence: float = Field(default=0.1, ge=0, le=1)

    @model_validator(mode="after")
    def evidence_integrity(self) -> Branch:
        status = self.evidence_status
        if self.kind == "factual" and (
            status != EvidenceStatus.OBSERVED or not self.outcomes
        ):
            raise ValueError("factual branch requires observed execution")
        if self.kind == "counterfactual" and status == EvidenceStatus.OBSERVED:
            raise ValueError("counterfactual branch cannot be factual observation")
        if status == EvidenceStatus.IMAGINED and self.outcomes:
            raise ValueError("imagined branch cannot contain executed evidence")
        if status in {
            EvidenceStatus.REPLAY_VERIFIED,
            EvidenceStatus.REPEATEDLY_VERIFIED,
        }:
            if not self.outcomes or not all(o.success for o in self.outcomes):
                raise ValueError("verified branch requires successful executions")
            if self.reward_delta is None or self.reward_delta <= 0:
                raise ValueError("verified alternative requires positive comparison")
        if (
            status == EvidenceStatus.REPEATEDLY_VERIFIED
            and len({o.execution_id for o in self.outcomes}) < 3
        ):
            raise ValueError("repeated verification requires 3 independent executions")
        if status == EvidenceStatus.FALSIFIED and not self.outcomes:
            raise ValueError("falsification requires execution evidence")
        return self


class StateFingerprint(StrictModel):
    environment: str = "microrepo"
    task_family: str
    features: dict[str, str] = Field(default_factory=dict)
    summary: str
    checkpoint: str


class Applicability(StrictModel):
    requires: dict[str, str] = Field(default_factory=dict)
    excludes: dict[str, str] = Field(default_factory=dict)

    def matches(self, features: dict[str, str]) -> bool:
        return all(features.get(k) == v for k, v in self.requires.items()) and not any(
            features.get(k) == v for k, v in self.excludes.items()
        )


class DecisionFork(StrictModel):
    fork_id: str = Field(default_factory=lambda: uuid4().hex)
    schema_version: str = "0.1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_episode_id: str
    pivot_step: int = Field(ge=0)
    state: StateFingerprint
    factual: Branch
    alternatives: list[Branch] = Field(min_length=1)
    applicability: Applicability
    lesson: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def paired(self) -> DecisionFork:
        if self.factual.kind != "factual":
            raise ValueError("factual slot must contain factual branch")
        for branch in [self.factual, *self.alternatives]:
            if branch is not self.factual and branch.kind != "counterfactual":
                raise ValueError("alternative slot must contain counterfactual")
            if any(o.checkpoint != self.state.checkpoint for o in branch.outcomes):
                raise ValueError("all compared executions must share pivot checkpoint")
        return self


class Proposal(StrictModel):
    action: Action
    mechanism: str
    predicted_outcome: str
    requires: dict[str, str] = Field(default_factory=dict)
    excludes: dict[str, str] = Field(default_factory=dict)
    risk: float = Field(default=0, ge=0, le=1)


class Proposals(StrictModel):
    proposals: list[Proposal] = Field(min_length=1, max_length=12)


class ExperimentDebt(StrictModel):
    debt_id: str = Field(default_factory=lambda: uuid4().hex)
    fork_id: str
    branch_id: str
    reason: str
    status: Literal["pending", "claimed", "resolved"] = "pending"
    max_cost: int = Field(default=1, ge=1)


class NegativeLesson(StrictModel):
    lesson_id: str
    source_episode_id: str
    state: StateFingerprint
    action: Action
    outcome: Outcome
    summary: str

    @model_validator(mode="after")
    def failed(self) -> NegativeLesson:
        if self.outcome.success:
            raise ValueError("negative lesson requires an observed failure")
        return self
