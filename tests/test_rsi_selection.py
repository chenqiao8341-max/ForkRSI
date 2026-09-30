"""Regression coverage for a generated C whose development evaluation failed."""

from pathlib import Path

import pytest

from forkmem.rsi.campaign import selection_candidates
from forkmem.rsi.ledger import StrategyLedger
from forkmem.rsi.models import INITIAL_COMPILER


def test_failed_evaluation_keeps_changed_candidate_in_selection(tmp_path: Path) -> None:
    ledger = StrategyLedger(tmp_path / "strategies.sqlite")
    content = INITIAL_COMPILER.model_dump(mode="json")
    initial = ledger.add_version("C", content)
    changed = ledger.add_version(
        "C", {**content, "memory_token_cap": 1024}, parent_id=initial
    )
    noop = ledger.add_version("C", content, parent_id=initial)
    history = [
        {
            "parent_c": initial,
            "candidate_c": changed,
            "status": "proposal_or_evaluation_failed",
            "error": "model JSON repair budget exhausted",
        },
        {
            "parent_c": initial,
            "candidate_c": None,
            "status": "proposal_or_evaluation_failed",
        },
        {"parent_c": initial, "candidate_c": noop, "proposal": {"actual_changes": {}}},
        {"parent_c": initial, "candidate_c": changed},
    ]
    assert selection_candidates(ledger, initial, history) == [initial, changed]


def test_selection_rejects_a_candidate_with_a_different_parent(tmp_path: Path) -> None:
    ledger = StrategyLedger(tmp_path / "strategies.sqlite")
    content = INITIAL_COMPILER.model_dump(mode="json")
    initial = ledger.add_version("C", content)
    other = ledger.add_version(
        "C", {**content, "memory_token_cap": 1024}, parent_id=initial
    )
    changed = ledger.add_version(
        "C", {**content, "memory_token_cap": 512}, parent_id=other
    )
    with pytest.raises(ValueError, match="parent"):
        selection_candidates(
            ledger, initial, [{"parent_c": initial, "candidate_c": changed}]
        )
