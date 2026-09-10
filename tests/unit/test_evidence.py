import pytest
from pydantic import ValidationError

from forkmem.llm import parse_json
from forkmem.memory import update_evidence
from forkmem.models import Action, Applicability, Branch, EvidenceStatus, Outcome


def evidence(success: bool, execution_id: str = "one") -> Outcome:
    return Outcome(
        success=success,
        reward=float(success),
        exit_code=0 if success else 1,
        checkpoint="commit",
        execution_id=execution_id,
        log_path="log",
        output_sha256="hash",
        tree_sha256="hash",
    )


def imagined() -> Branch:
    return Branch(
        kind="counterfactual",
        first_action=Action(tool="write", path="solution.py"),
        trajectory_ref="trace",
        evidence_status=EvidenceStatus.IMAGINED,
    )


def test_promotion_demotion_and_duplicate() -> None:
    b = update_evidence(imagined(), evidence(True), 0)
    assert b.evidence_status == EvidenceStatus.REPLAY_VERIFIED
    with pytest.raises(ValueError, match="duplicate"):
        update_evidence(b, evidence(True), 0)
    b = update_evidence(b, evidence(True, "two"), 0)
    b = update_evidence(b, evidence(True, "three"), 0)
    assert b.evidence_status == EvidenceStatus.REPEATEDLY_VERIFIED
    assert (
        update_evidence(b, evidence(False, "four"), 0).evidence_status
        == EvidenceStatus.FALSIFIED
    )


def test_cannot_claim_verification_without_evidence() -> None:
    with pytest.raises(ValidationError):
        Branch(
            **{
                **imagined().model_dump(),
                "evidence_status": EvidenceStatus.REPLAY_VERIFIED,
            }
        )
    with pytest.raises(ValidationError):
        Branch(**{**imagined().model_dump(), "outcomes": [evidence(True)]})


def test_applicability() -> None:
    rule = Applicability(requires={"manager": "uv"}, excludes={"mode": "legacy"})
    assert rule.matches({"manager": "uv"})
    assert not rule.matches({"manager": "pip"})
    assert not rule.matches({"manager": "uv", "mode": "legacy"})


def test_parser() -> None:
    assert parse_json('```json\n{"tool":"read", "path":"x"}\n```', Action).path == "x"
    with pytest.raises(ValidationError):
        parse_json('{"tool":"sudo"}', Action)
    with pytest.raises(ValidationError):
        parse_json("broken", Action)
