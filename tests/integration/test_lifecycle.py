import json
from pathlib import Path

import pytest

from forkmem.lifecycle import add_execution, narrow_applicability, supersede
from forkmem.memory import SQLiteForkStore, retrieve
from forkmem.models import Applicability, DecisionFork, EvidenceStatus


def test_revisions_preserve_history_and_stop_stale_advice(tmp_path: Path) -> None:
    fork = DecisionFork.model_validate(
        json.loads(
            Path("artifacts/v2/cases/partial_repair_falsified.json").read_text()
        )["fork"]
    )
    store = SQLiteForkStore(tmp_path / "memory.sqlite")
    store.put(fork)
    failure = fork.factual.outcomes[0].model_copy(
        update={"execution_id": "fresh-failure"}
    )
    revised = add_execution(
        store, fork.fork_id, fork.alternatives[0].branch_id, failure
    )
    assert revised.alternatives[0].evidence_status == EvidenceStatus.FALSIFIED
    assert (
        store.history(fork.fork_id)[0].alternatives[0].evidence_status
        == EvidenceStatus.REPLAY_VERIFIED
    )
    rule = Applicability(
        requires=fork.applicability.requires, excludes={"deployment": "legacy"}
    )
    revised = narrow_applicability(
        store, fork.fork_id, rule, "legacy contract excludes this rule"
    )
    assert not retrieve(
        store,
        fork.state.model_copy(
            update={"features": {**fork.state.features, "deployment": "legacy"}}
        ),
    )
    with pytest.raises(ValueError, match="weaken"):
        narrow_applicability(
            store, fork.fork_id, Applicability(), "unsupported widening"
        )
    replacement = fork.model_copy(update={"fork_id": "replacement"})
    store.put(replacement)
    revised = supersede(store, fork.fork_id, "replacement")
    assert all(
        branch.evidence_status == EvidenceStatus.SUPERSEDED
        for branch in revised.alternatives
    )
    with pytest.raises(ValueError, match="terminal"):
        add_execution(store, fork.fork_id, fork.alternatives[0].branch_id, failure)
    assert len(store.history(fork.fork_id)) == 4
    store.close()


def test_exact_consolidation_keeps_evidence_and_provenance(tmp_path: Path) -> None:
    from forkmem.lifecycle import consolidate_exact

    fork = DecisionFork.model_validate(
        json.loads(
            Path("artifacts/v2/cases/partial_repair_falsified.json").read_text()
        )["fork"]
    )
    store = SQLiteForkStore(tmp_path / "memory.sqlite")
    store.put(fork)
    duplicate = fork.model_copy(
        deep=True, update={"fork_id": fork.fork_id + "-duplicate"}
    )
    for branch in duplicate.alternatives:
        branch.outcomes[0].execution_id += "-independent"
    store.put(duplicate)
    assert consolidate_exact(store) == 1
    assert consolidate_exact(store) == 0
    retained = store.history(fork.fork_id)[-1]
    assert all(len(branch.outcomes) == 2 for branch in retained.alternatives)
    retired = store.history(duplicate.fork_id)[-1]
    assert retired.provenance["superseded_by"] == fork.fork_id
    assert all(
        branch.evidence_status == EvidenceStatus.SUPERSEDED
        for branch in retired.alternatives
    )
    store.close()
