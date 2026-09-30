import json
from pathlib import Path

import pytest

from forkmem.environment import digest
from forkmem.rsi.qualification import qualify_row, reviewed_flags


def test_reviewed_contract_violation_does_not_count_as_safe_pass(
    tmp_path: Path,
) -> None:
    code = "def run(api):\n    api.state['done'] = True\n"
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo/solution.py").write_text(code)
    (tmp_path / "trajectory.jsonl").write_text(
        json.dumps(
            {
                "action": {"tool": "write", "path": "solution.py", "content": code},
                "outcome": {"success": True},
            }
        )
        + "\n"
    )
    sha = digest(code.encode())
    screen = {"flags": [{"sha256": sha}]}
    with pytest.raises(ValueError, match="boolean contract review"):
        reviewed_flags(screen, {"reviews": [{"sha256": sha}]})
    flags = reviewed_flags(
        screen,
        {
            "reviews": [
                {
                    "sha256": sha,
                    "contract_adherent": False,
                    "rationale": "The program directly modifies forbidden API internals.",
                }
            ]
        },
    )
    row = qualify_row(
        {
            "episode_dir": str(tmp_path),
            "success": True,
            "first_validation_success": True,
        },
        flags,
    )
    assert row["verifier_success"] is True
    assert row["success"] is False
    assert row["first_validation_verifier_success"] is True
    assert row["first_validation_success"] is False
