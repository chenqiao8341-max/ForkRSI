"""Sandbox reference audit for every frozen context, with exact fixture hashes."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from forkmem.environment import RepoEnvironment, digest
from forkmem.models import Action
from forkmem.workflows.analysis import read_workflow_cases

manifest = json.loads(Path("data/v2/frozen1/manifest.json").read_text())
rows = []
with TemporaryDirectory(prefix="forkmem-frozen-audit-") as root:
    for i, entry in enumerate(manifest["tasks"]):
        spec = json.loads(Path(entry["path"]).read_text())
        base = Path(root) / str(i)
        base.mkdir()
        verifier = base / "verifier.py"
        verifier.write_text(spec["verifier"])
        env = RepoEnvironment.create(
            base / "repo", spec["files"], verifier, base / "logs"
        )
        checkpoint = env.checkpoint()
        initial = env.verify(checkpoint)
        assert not initial.success
        env.execute(
            Action(tool="write", path="solution.py", content=spec["reference_solution"])
        )
        outcome = env.verify(checkpoint)
        cases = read_workflow_cases(outcome)
        assert outcome.success and len(cases) == entry["runtime_case_count"]
        rows.append(
            {
                "task_id": entry["task_id"],
                "fixture_sha256": digest(Path(entry["path"]).read_bytes()),
                "initial_fails": True,
                "reference_passes": True,
                "runtime_cases": len(cases),
                "reference_log_sha256": outcome.output_sha256,
                "reference_tree_sha256": outcome.tree_sha256,
            }
        )
summary = {
    "tasks": len(rows),
    "runtime_cases": sum(r["runtime_cases"] for r in rows),
    "all_pass": True,
    "rows": rows,
    "scope": "Independent execution of initial and reference programs, not model evaluation or a claimed task success sample.",
}
output = Path("artifacts/v2/frozen1_reference_audit.json")
output.write_text(json.dumps(summary, indent=2) + "\n")
print({k: v for k, v in summary.items() if k != "rows"})
