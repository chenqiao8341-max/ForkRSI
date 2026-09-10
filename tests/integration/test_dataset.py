import json
from pathlib import Path

import pytest

from forkmem.environment import RepoEnvironment, git
from forkmem.models import Action

MANIFEST = json.loads(Path("data/task_manifest.json").read_text())["tasks"]


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda entry: entry["task_id"])
def test_task_is_solvable_and_initial_code_fails(
    entry: dict[str, str], tmp_path: Path
) -> None:
    task = json.loads(Path(entry["path"]).read_text())
    verifier = tmp_path / "verifier.py"
    verifier.write_text(task["verifier"])
    env = RepoEnvironment.create(
        tmp_path / "repo", task["files"], verifier, tmp_path / "logs"
    )
    checkpoint = git(env.root, "rev-parse", "HEAD")
    assert not env.verify(checkpoint).success
    reference = Path("data/reference_solutions") / (entry["task_id"] + ".py")
    env.execute(Action(tool="write", path="solution.py", content=reference.read_text()))
    outcome = env.verify(checkpoint)
    assert outcome.success, Path(outcome.log_path).read_text()
