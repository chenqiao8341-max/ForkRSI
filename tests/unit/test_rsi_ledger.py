from pathlib import Path
import sqlite3
import pytest
from forkmem.rsi.ledger import StrategyLedger
from forkmem.rsi.models import INITIAL_COMPILER, INITIAL_IMPROVER

def test_lineage_and_append_only_failures(tmp_path: Path) -> None:
    ledger = StrategyLedger(tmp_path / "strategies.sqlite")
    c0 = ledger.add_version("C", INITIAL_COMPILER.model_dump())
    i0 = ledger.add_version("I", INITIAL_IMPROVER.model_dump())
    changed = INITIAL_COMPILER.model_copy(update={"rendering": "compact"}).model_dump()
    with pytest.raises(ValueError, match="same strategy kind"):
        ledger.add_version("C", changed, parent_id=i0)
    c1 = ledger.add_version("C", changed, parent_id=c0, input_evidence=["dev-failure"])
    cmp = ledger.add_comparison(c0, c1, i0, protocol={"split": "development", "seed": 23},
          results={"parent_success": False, "candidate_success": False, "accepted": False},
          costs={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14})
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT count(*) FROM comparisons WHERE comparison_id=?", (cmp,)).fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("UPDATE versions SET content_json='{}' WHERE version_id=?", (c0,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM comparisons WHERE comparison_id=?", (cmp,))
    assert ledger.get(c1)["parent_id"] == c0

def test_comparison_rejects_wrong_parent_and_unaccounted_tokens(tmp_path: Path) -> None:
    ledger = StrategyLedger(tmp_path / "strategies.sqlite")
    c0 = ledger.add_version("C", INITIAL_COMPILER.model_dump())
    c1 = ledger.add_version("C", INITIAL_COMPILER.model_dump(), parent_id=c0)
    i0 = ledger.add_version("I", INITIAL_IMPROVER.model_dump())
    args = {"protocol": {"fixed": True}, "results": {"success": False},
            "costs": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 9}}
    with pytest.raises(ValueError, match="inconsistent"):
        ledger.add_comparison(c0, c1, i0, **args)
    args["costs"]["total_tokens"] = 5
    with pytest.raises(ValueError, match="descend"):
        ledger.add_comparison(c1, c0, i0, **args)
