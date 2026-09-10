from pathlib import Path

import pytest

from forkmem.environment import RepoEnvironment, git
from forkmem.models import Action


def test_shared_checkpoint_isolation_replay_and_safety(tmp_path: Path) -> None:
    verifier = tmp_path / "verifier.py"
    verifier.write_text(
        "import sys\nsys.path.insert(0, '/task')\nfrom solution import value\nassert value == 2\n"
    )
    env = RepoEnvironment.create(
        tmp_path / "base", {"solution.py": "value = 0\n"}, verifier, tmp_path / "logs"
    )
    commit = git(env.root, "rev-parse", "HEAD")
    a = env.fork(commit, tmp_path / "a", tmp_path / "a_logs")
    b = env.fork(commit, tmp_path / "b", tmp_path / "b_logs")
    assert a.tree_hash() == b.tree_hash() == env.tree_hash()
    a.execute(Action(tool="write", path="solution.py", content="value = 2\n"))
    assert a.verify(commit).success
    assert not b.verify(commit).success
    assert a.verify(commit).success
    assert b.tree_hash() == env.tree_hash()
    with pytest.raises(ValueError):
        a.execute(Action(tool="write", path="../verifier.py", content=""))
    with pytest.raises(ValueError):
        a.execute(Action(tool="write", path="test.py", content=""))
    a.execute(
        Action(
            tool="write",
            path="solution.py",
            content="import os\nassert not os.path.exists('/home/qingao')\nimport socket\ns = socket.socket()\ntry:\n s.connect(('127.0.0.1', 8000))\n raise AssertionError('network exposed')\nexcept ConnectionRefusedError:\n pass\nvalue = 2\n",
        )
    )
    assert a.verify(commit).success


def test_early_success_exit_cannot_skip_oracle(tmp_path: Path) -> None:
    verifier = tmp_path / "verifier.py"
    verifier.write_text(
        "import sys\nsys.path.insert(0, '/task')\nimport solution\nassert False, 'oracle was not satisfied'\n"
    )
    env = RepoEnvironment.create(
        tmp_path / "base",
        {"solution.py": "import sys\nsys.exit(0)\n"},
        verifier,
        tmp_path / "logs",
    )
    outcome = env.verify(git(env.root, "rev-parse", "HEAD"))
    assert not outcome.success


def test_timeout_is_bounded(tmp_path: Path) -> None:
    import time

    verifier = tmp_path / "verifier.py"
    verifier.write_text("while True: pass\n")
    env = RepoEnvironment.create(
        tmp_path / "base", {"solution.py": ""}, verifier, tmp_path / "logs"
    )
    started = time.monotonic()
    outcome = env.verify(git(env.root, "rev-parse", "HEAD"), timeout=0.1)
    assert not outcome.success and outcome.exit_code == 124
    assert time.monotonic() - started < 3
