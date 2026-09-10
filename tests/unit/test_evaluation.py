import json
from pathlib import Path

import pytest

from forkmem.evaluation import clustered_interval, load_complete


def test_bootstrap_keeps_repeated_task_cluster() -> None:
    rows = [{"task_id": "a", "success": False} for _ in range(3)] + [
        {"task_id": "b", "success": True} for _ in range(3)
    ]
    interval = clustered_interval(rows, "success", samples=1000)
    assert interval == (0.5, 0.0, 1.0)
    assert clustered_interval([], "success") is None


def test_incomplete_report_rejected(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "status.json").write_text(json.dumps({"state": "running"}))
    with pytest.raises(ValueError, match="incomplete"):
        load_complete(tmp_path)
