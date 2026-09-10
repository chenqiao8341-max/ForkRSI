import json
from pathlib import Path

from forkmem.environment import RepoEnvironment
from forkmem.memory import SQLiteForkStore, update_evidence
from forkmem.models import (
    Action,
    Applicability,
    Branch,
    DecisionFork,
    EvidenceStatus,
    NegativeLesson,
    StateFingerprint,
)
from forkmem.workflows.memory import views


def test_matched_verified_programs_and_unverified_outcome_separation(tmp_path):
    task = json.loads(
        Path("data/v2/frozen1/resumable_ingestion_train_011.json").read_text()
    )
    verifier = tmp_path / "verifier.py"
    verifier.write_text(task["verifier"])
    env = RepoEnvironment.create(
        tmp_path / "repo", task["files"], verifier, tmp_path / "logs"
    )
    checkpoint = env.checkpoint()
    failure = env.verify(checkpoint)
    assert not failure.success
    bad_action = Action(
        tool="write", path="solution.py", content=task["files"]["solution.py"]
    )
    good_action = Action(
        tool="write", path="solution.py", content=task["reference_solution"]
    )
    env.execute(good_action)
    success = env.verify(checkpoint)
    assert success.success
    factual = Branch(
        kind="factual",
        first_action=bad_action,
        trajectory_ref="observed",
        evidence_status=EvidenceStatus.OBSERVED,
        outcomes=[failure],
    )
    bad = Branch(
        kind="counterfactual",
        first_action=bad_action,
        trajectory_ref="bad",
        evidence_status=EvidenceStatus.IMAGINED,
        predicted_outcome="will work",
    )
    bad = update_evidence(bad, failure, 0)
    good = Branch(
        kind="counterfactual",
        first_action=good_action,
        trajectory_ref="good",
        evidence_status=EvidenceStatus.IMAGINED,
        predicted_outcome="will work",
    )
    good = update_evidence(good, success, 0)
    state = StateFingerprint(
        task_family=task["family"],
        features=task["features"],
        summary=task["description"],
        checkpoint=checkpoint,
    )
    fork = DecisionFork(
        source_episode_id="source",
        pivot_step=0,
        state=state,
        factual=factual,
        alternatives=[bad, good],
        applicability=Applicability(requires=task["features"]),
        lesson="test",
    )
    store = SQLiteForkStore(tmp_path / "memory.sqlite")
    try:
        store.put(fork)
        store.put_negative(
            NegativeLesson(
                lesson_id="negative",
                source_episode_id="source",
                state=state,
                action=bad_action,
                outcome=failure,
                summary="incomplete workflow",
            )
        )
        target = state.model_copy(
            update={"features": {**state.features, "transactional": "false"}}
        )
        result = views(store, target, len, token_cap=100000)
        flat, flat_ids = result["flat_verified"]
        pair, pair_ids = result["fork_verified"]
        assert flat_ids == pair_ids and flat_ids
        assert (
            json.loads(flat)[0]["successful_code"]
            == json.loads(pair)[0]["successful_code"]
            == good_action.content
        )
        assert "matched_case_contrasts" not in flat
        assert "matched_case_contrasts" in pair
        assert result["legacy_verified"] == ("", [])
        imagined = json.loads(result["imagined"][0])[0]
        assert imagined["predicted_code"] == bad_action.content
        assert "observed_obligations" not in imagined
        assert "successful_code" not in imagined
        assert result["negative"][1] == ["negative"]
        tiny = views(store, target, len, token_cap=1)
        assert all(prompt == "" and ids == [] for prompt, ids in tiny.values())
    finally:
        store.close()
