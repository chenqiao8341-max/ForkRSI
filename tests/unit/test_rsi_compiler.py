import pytest

from forkmem.rsi.compiler import validate_references
from forkmem.rsi.models import MemoryRule, RuleSet


def test_compiler_rejects_fabricated_evidence() -> None:
    rules = RuleSet(
        rules=[
            MemoryRule(
                rule="Check each durable stage",
                applicability="Direct ingestion",
                obligations=["durability"],
                evidence_ids=["invented-positive"],
                caveat="Test on new context",
            )
        ]
    )
    with pytest.raises(ValueError, match="fabricated"):
        validate_references(rules, {"real-positive", "real-falsified"})
    rules.rules[0].evidence_ids = ["real-positive", "real-falsified"]
    validate_references(rules, {"real-positive", "real-falsified"})


def test_corrupt_structured_failure_is_not_treated_as_unstructured(tmp_path) -> None:
    import json

    from forkmem.environment import digest
    from forkmem.models import Action, Branch, EvidenceStatus, Outcome
    from forkmem.rsi.compiler import observation

    log = tmp_path / "failure.log"
    # Intentionally inconsistent synthetic test fixture, not research evidence.
    log.write_text(
        "FORKMEM_WORKFLOW_RESULT="
        + json.dumps(
            {"success": False, "obligations": {"valid_execution": True}, "trace": []}
        )
        + "\n"
    )
    raw = tmp_path / "failure.raw.log"
    raw.write_bytes(log.read_bytes())
    log.with_suffix(".json").write_text(
        json.dumps(
            {
                "raw_log_path": str(raw),
                "raw_output_sha256": digest(raw.read_bytes()),
                "completion_observed": False,
            }
        )
    )
    outcome = Outcome(
        success=False,
        reward=0,
        exit_code=1,
        checkpoint="test",
        execution_id="synthetic-test",
        log_path=str(log),
        output_sha256=digest(log.read_bytes()),
        tree_sha256="test",
    )
    branch = Branch(
        kind="factual",
        first_action=Action(tool="write", path="solution.py", content=""),
        trajectory_ref="synthetic-test",
        evidence_status=EvidenceStatus.OBSERVED,
        outcomes=[outcome],
    )
    with pytest.raises(ValueError, match="disagree"):
        observation(branch)
    log.write_text("SyntaxError: synthetic invalid program\n")
    raw.write_bytes(log.read_bytes())
    log.with_suffix(".json").write_text(
        json.dumps(
            {
                "raw_log_path": str(raw),
                "raw_output_sha256": digest(raw.read_bytes()),
                "completion_observed": False,
            }
        )
    )
    branch.outcomes[0] = outcome.model_copy(
        update={"output_sha256": digest(log.read_bytes())}
    )
    assert observation(branch)["structured_observation"] is False
