"""Execute the actual injected positive programs on their source contracts."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from forkmem.environment import RepoEnvironment, digest
from forkmem.models import Action, DecisionFork


def audit(run: Path, output: Path):
    manifest = json.loads((run / "manifest.json").read_text())
    source = Path(manifest["source"])
    raw = (source / "corpus.json").read_bytes()
    assert digest(raw) == manifest["source_corpus_sha256"]
    corpus = json.loads(raw)
    lookup = {
        f.fork_id + ":" + b.branch_id: (f, b)
        for obj in corpus["forks"]
        for f in [DecisionFork.model_validate(obj)]
        for b in f.alternatives
    }
    prepared = json.loads((run / "prepared_memories.json").read_text())
    programs = {}
    for task, conditions in prepared.items():
        flat, flat_ids = conditions["flat_verified"]
        paired, paired_ids = conditions["fork_verified"]
        assert flat_ids == paired_ids
        left, right = json.loads(flat or "[]"), json.loads(paired or "[]")
        assert len(left) == len(right) == len(flat_ids)
        for identity, a, b in zip(flat_ids, left, right, strict=True):
            assert a["successful_code"] == b["successful_code"]
            assert (
                a["source_context"]
                == b["source_context"]
                == lookup[identity][0].state.features
            )
            code = a["successful_code"]
            if identity in programs:
                assert programs[identity]["code"] == code
            programs.setdefault(identity, {"code": code, "targets": []})[
                "targets"
            ].append(task)
    results = []
    with TemporaryDirectory(prefix="forkmem-injection-audit-") as root:
        for i, (identity, record) in enumerate(programs.items()):
            fork, branch = lookup[identity]
            assert branch.outcomes[-1].success
            task = json.loads(Path(fork.provenance["task_path"]).read_text())
            base = Path(root) / str(i)
            base.mkdir()
            verifier = base / "verifier.py"
            verifier.write_text(task["verifier"])
            env = RepoEnvironment.create(
                base / "repo", task["files"], verifier, base / "logs"
            )
            checkpoint = env.checkpoint()
            env.execute(
                Action(tool="write", path="solution.py", content=record["code"])
            )
            outcome = env.verify(checkpoint)
            assert (
                outcome.success
                and outcome.tree_sha256 == branch.outcomes[-1].tree_sha256
            ), identity
            results.append(
                {
                    "identity": identity,
                    "source_task": task["task_id"],
                    "rendered_code_sha256": digest(record["code"].encode()),
                    "source_tree_matches": True,
                    "source_oracle_passes": True,
                    "target_contexts_receiving_record": record["targets"],
                }
            )
    summary = {
        "distinct_injected_source_programs": len(results),
        "all_source_reexecutions_pass": True,
        "flat_and_paired_program_ids_and_bytes_match": True,
        "rows": results,
        "scope": "Source-contract validation only; no target outcomes inspected, no transfer memory updated, and no new distinct hypotheses counted.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    print({k: v for k, v in summary.items() if k != "rows"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.runs, args.output)
