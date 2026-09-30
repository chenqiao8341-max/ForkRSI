"""Execute each task witness through the unchanged external verifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forkmem.environment import RepoEnvironment, digest, git
from forkmem.models import Outcome
from forkmem.workflows.analysis import read_workflow_cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/forkrsi/semantic_v1/manifest.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("runs/forkrsi/task-witnesses")
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    rows = []
    for entry in manifest["tasks"]:
        task_path = Path(entry["path"])
        if digest(task_path.read_bytes()) != entry["sha256"]:
            raise ValueError("task manifest mismatch")
        task = json.loads(task_path.read_text())
        root = args.output / task["task_id"]
        if (root / "outcome.json").is_file():
            outcome = Outcome.model_validate_json((root / "outcome.json").read_text())
        else:
            root.mkdir(parents=True, exist_ok=False)
            verifier = root / "verifier.py"
            verifier.write_text(task["verifier"])
            files = {**task["files"], "solution.py": task["reference_solution"]}
            env = RepoEnvironment.create(root / "repo", files, verifier, root / "logs")
            outcome = env.verify(git(env.root, "rev-parse", "HEAD"))
            (root / "outcome.json").write_text(outcome.model_dump_json(indent=2))
        cases = read_workflow_cases(outcome)
        if not outcome.success or len(cases) != task["runtime_case_count"]:
            raise ValueError("invalid complete witness: " + task["task_id"])
        rows.append(
            {
                "task_id": task["task_id"],
                "task_sha256": entry["sha256"],
                "runtime_cases": len(cases),
                "outcome": outcome.model_dump(mode="json"),
            }
        )
    (args.output / "summary.json").write_text(
        json.dumps(
            {
                "manifest_sha256": digest(args.manifest.read_bytes()),
                "purpose": "infrastructure and solvability check only; not model/source/RSI evidence",
                "tasks": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "complete_tasks": len(rows),
                "nested_cases": sum(r["runtime_cases"] for r in rows),
            }
        )
    )


if __name__ == "__main__":
    main()
