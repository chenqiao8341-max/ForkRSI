import json
from pathlib import Path

import pytest

from forkmem.memory import SQLiteForkStore, render_memory, retrieve
from forkmem.models import DecisionFork, EvidenceStatus


def test_durable_versions_retrieval_and_epistemic_labels(tmp_path: Path) -> None:
    case = json.loads(
        Path("artifacts/v2/cases/partial_repair_falsified.json").read_text()
    )
    fork = DecisionFork.model_validate(case["fork"])
    db = tmp_path / "memory.sqlite"
    store = SQLiteForkStore(db)
    store.put(fork)
    with pytest.raises(ValueError, match="append-only"):
        store.put(fork)
    store.close()
    store = SQLiteForkStore(db)
    assert retrieve(store, fork.state)
    mismatch = fork.state.model_copy(update={"features": {"zero_valid": "no"}})
    assert not retrieve(store, mismatch)
    assert retrieve(store, mismatch, mode="no_applicability")
    imagined_data = fork.model_dump()
    imagined_data["version"] = 2
    for branch in imagined_data["alternatives"]:
        branch.update(
            evidence_status=EvidenceStatus.IMAGINED,
            outcomes=[],
            reward_delta=None,
            confidence=0.1,
        )
    imagined = DecisionFork.model_validate(imagined_data)
    store.put(imagined)
    assert not retrieve(store, fork.state)
    prompt = render_memory(retrieve(store, fork.state, mode="imagined"), "imagined")
    assert "UNVERIFIED HYPOTHESIS" in prompt
    assert "Execution-verified" not in prompt
    assert len(store.history(fork.fork_id)) == 2
    store.close()


def test_unverified_views_cannot_see_future_execution(tmp_path: Path) -> None:
    from forkmem.models import Action, Branch, NegativeLesson

    case = json.loads(
        Path("artifacts/v2/cases/partial_repair_falsified.json").read_text()
    )
    fork = DecisionFork.model_validate(case["fork"])
    bad = fork.alternatives[0].model_dump()
    bad.update(
        evidence_status=EvidenceStatus.FALSIFIED,
        outcomes=[fork.factual.outcomes[0]],
        reward_delta=0,
        confidence=0,
        continuation_actions=[
            Action(tool="write", path="solution.py", content="secret later repair")
        ],
    )
    fork.alternatives = [Branch.model_validate(bad)]
    store = SQLiteForkStore(tmp_path / "memory.sqlite")
    store.put(fork)
    assert not retrieve(store, fork.state, "verified")
    for mode in ["imagined", "paired"]:
        items = retrieve(store, fork.state, mode)
        assert items and items[0][1].evidence_status == EvidenceStatus.IMAGINED
        prompt = render_memory(items, mode)
        assert "secret later repair" not in prompt
        assert "Execution-verified" not in prompt
        assert items[0][1].outcomes == []
    store.put_negative(
        NegativeLesson(
            lesson_id="failure-only",
            source_episode_id="test",
            state=fork.state,
            action=fork.factual.first_action,
            outcome=fork.factual.outcomes[0],
            summary="zero-valued input failed",
        )
    )
    assert len(store.negatives()) == 1
    from forkmem.memory import negative_context

    prompt, ids = negative_context(store, fork.state)
    assert ids == ["failure-only"] and "zero-valued input failed" in prompt
    assert "secret later repair" not in prompt
    store.close()
