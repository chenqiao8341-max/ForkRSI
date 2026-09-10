"""Git checkpoints and network-isolated execution of untrusted task code."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from forkmem.models import Action, Outcome


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.STDOUT, text=True
    ).strip()


def git_blob(root: Path, checkpoint: str, name: str) -> str:
    """Read a snapshot file without stripping whitespace from its content."""
    return subprocess.check_output(
        ["git", "-C", str(root), "show", f"{checkpoint}:{name}"], text=True
    )


class RepoEnvironment:
    def __init__(
        self,
        root: Path,
        verifier: Path,
        log_dir: Path,
        editable: tuple[str, ...] = ("solution.py",),
    ):
        self.root = root.resolve()
        self.verifier = verifier.resolve()
        self.log_dir = log_dir.resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.editable = editable

    @classmethod
    def create(
        cls,
        root: Path,
        files: dict[str, str],
        verifier: Path,
        log_dir: Path,
        editable: tuple[str, ...] = ("solution.py",),
    ) -> RepoEnvironment:
        root.mkdir(parents=True, exist_ok=False)
        for name, content in files.items():
            path = root / name
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("unsafe fixture path")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        git(root, "init", "-q")
        git(root, "config", "user.name", "ForkMem")
        git(root, "config", "user.email", "forkmem@localhost")
        git(root, "add", ".")
        git(root, "commit", "-qm", "initial task")
        return cls(root, verifier, log_dir, editable)

    def checkpoint(self) -> str:
        git(self.root, "add", "--", *self.editable)
        git(self.root, "commit", "--allow-empty", "-qm", "agent checkpoint")
        return git(self.root, "rev-parse", "HEAD")

    def fork(self, checkpoint: str, target: Path, logs: Path) -> RepoEnvironment:
        target = target.resolve()
        git(self.root, "worktree", "add", "--detach", str(target), checkpoint)
        return RepoEnvironment(target, self.verifier, logs, self.editable)

    def safe_path(self, name: str, *, write: bool = False) -> Path:
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root) or ".git" in Path(name).parts:
            raise ValueError("path outside allowed task files")
        if write and name not in self.editable:
            raise ValueError(
                "only task source files are editable; verifier is immutable"
            )
        return path

    def tree_hash(self) -> str:
        parts = []
        for name in sorted(git(self.root, "ls-files").splitlines()):
            path = self.safe_path(name)
            parts.append(name.encode() + b"\0" + path.read_bytes())
        return digest(b"\0".join(parts))

    def execute(self, action: Action) -> str:
        if action.tool == "read":
            return self.safe_path(action.path).read_text()[:20000]
        if action.tool == "search":
            found = []
            for name in git(self.root, "ls-files").splitlines():
                for number, line in enumerate(
                    self.safe_path(name).read_text().splitlines(), 1
                ):
                    if action.content in line:
                        found.append(f"{name}:{number}:{line}")
            return "\n".join(found)[:20000]
        if action.tool == "write":
            if len(action.content) > 30000:
                raise ValueError("source file exceeds action budget")
            self.safe_path(action.path, write=True).write_text(action.content)
            return "source updated"
        if action.tool == "finish":
            return "submitted"
        raise ValueError("test actions must invoke verify with a checkpoint")

    def verify(self, checkpoint: str, seed: int = 0, timeout: float = 10) -> Outcome:
        execution_id = uuid4().hex
        output = self.log_dir / f"{execution_id}.log"
        token = uuid4().hex
        marker = ("\nFORKMEM_DONE:" + token + "\n").encode()
        wrapper = self.log_dir / f"{execution_id}.guard.py"
        wrapper.write_text(
            "import runpy, sys, os\nrunpy.run_path('/verifier.py', run_name='__main__')\nsys.stdout.flush()\nos.write(1, "
            + repr(marker)
            + ")\n"
        )
        # Do not expose .git (which references host directories), logs, home, or credentials.
        cmd = [
            "bwrap",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "PYTHONHASHSEED",
            str(seed),
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/lib64",
            "/lib64",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/task",
            "--ro-bind",
            str(self.verifier),
            "/verifier.py",
            "--ro-bind",
            str(wrapper),
            "/guard.py",
        ]
        for name in git(self.root, "ls-files").splitlines():
            cmd.extend(["--ro-bind", str(self.safe_path(name)), f"/task/{name}"])
        cmd.extend(["--chdir", "/task", "/usr/bin/python3", "-B", "/guard.py"])
        cmd = [
            "prlimit",
            "--as=536870912",
            "--fsize=1048576",
            "--cpu=10",
            "--nofile=128",
            "--",
            *cmd,
        ]
        start = time.monotonic()
        with output.open("wb") as handle:
            process = subprocess.Popen(
                cmd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            )
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                exit_code = 124
        data = output.read_bytes()
        if data.startswith((b"bwrap:", b"prlimit:")):
            raise RuntimeError(
                "sandbox infrastructure failure: "
                + data.decode(errors="replace")[:1000]
            )
        process_exit_code = exit_code
        raw_path = output.with_suffix(".raw.log")
        raw_path.write_bytes(data)
        raw_digest = digest(data)
        completed = data.endswith(marker)
        if completed:
            data = data[: -len(marker)]
        elif exit_code == 0:
            exit_code = 125
            data += b"\nForkMem: verifier completion was not observed.\n"
        output.write_bytes(data)
        outcome = Outcome(
            verifier="microrepo-v2-completion",
            success=exit_code == 0,
            reward=float(exit_code == 0),
            exit_code=exit_code,
            checkpoint=checkpoint,
            execution_id=execution_id,
            log_path=str(output),
            output_sha256=digest(data),
            tree_sha256=self.tree_hash(),
            seed=seed,
        )
        output.with_suffix(".json").write_text(
            json.dumps(
                {
                    **outcome.model_dump(),
                    "wall_seconds": time.monotonic() - start,
                    "process_exit_code": process_exit_code,
                    "completion_observed": completed,
                    "raw_log_path": str(raw_path),
                    "raw_output_sha256": raw_digest,
                },
                indent=2,
            )
        )
        return outcome
