import json
from pathlib import Path

from forkmem.environment import RepoEnvironment
from forkmem.memory import update_evidence
from forkmem.models import (
    Action,
    Applicability,
    Branch,
    DecisionFork,
    EvidenceStatus,
    StateFingerprint,
)
from forkmem.rsi.compiler import source_packet
from forkmem.rsi.models import INITIAL_COMPILER


def test_success_only_compiler_never_receives_failed_source_code(
    tmp_path: Path,
) -> None:
    # Executable infrastructure fixture only, never added to the research corpus.
    task = json.loads(
        Path("data/v2/workflow_dev1/resumable_ingestion_train_011.json").read_text()
    )
    verifier = tmp_path / "verifier.py"
    verifier.write_text(task["verifier"])
    env = RepoEnvironment.create(
        tmp_path / "repo", task["files"], verifier, tmp_path / "logs"
    )
    checkpoint = env.checkpoint()
    bad = Action(tool="write", path="solution.py", content=task["files"]["solution.py"])
    failed = env.verify(checkpoint)
    good = Action(tool="write", path="solution.py", content=task["reference_solution"])
    env.execute(good)
    passed = env.verify(checkpoint)
    assert not failed.success and passed.success
    factual = Branch(
        kind="factual",
        first_action=bad,
        trajectory_ref="test-only",
        evidence_status=EvidenceStatus.OBSERVED,
        outcomes=[failed],
    )
    positive = update_evidence(
        Branch(
            kind="counterfactual",
            first_action=good,
            trajectory_ref="test-only",
            evidence_status=EvidenceStatus.IMAGINED,
        ),
        passed,
        0,
    )
    falsified = update_evidence(
        Branch(
            kind="counterfactual",
            first_action=bad,
            trajectory_ref="test-only",
            predicted_outcome="would succeed",
            evidence_status=EvidenceStatus.IMAGINED,
        ),
        failed,
        0,
    )
    fork = DecisionFork(
        source_episode_id="test-only",
        pivot_step=0,
        state=StateFingerprint(
            task_family=task["family"],
            features=task["features"],
            checkpoint=checkpoint,
            summary=task["description"],
        ),
        factual=factual,
        alternatives=[positive, falsified],
        applicability=Applicability(requires=task["features"]),
        lesson="test-only",
    )
    success, allowed = source_packet(fork, positive, INITIAL_COMPILER, "success_only")
    paired, paired_allowed = source_packet(fork, positive, INITIAL_COMPILER, "paired")
    assert success["positive_program_id"] == paired["positive_program_id"]
    assert allowed == {success["positive_program_id"]}
    assert "factual_failure" not in success and "falsified_alternatives" not in success
    assert len(paired_allowed) == 3
    assert paired["factual_failure"]["execution"]["success"] is False
    assert paired["falsified_alternatives"][0]["execution"]["success"] is False
