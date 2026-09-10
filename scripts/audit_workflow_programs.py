"""Screen executed programs for simulator-internal access or swallowed crashes.

This is a transparent static screen, not a proof against adversarial Python.
Flags require review; they are never silently removed from outcome statistics.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from forkmem.environment import digest
from forkmem.models import DecisionFork
from forkmem.workflows.memory import final_code


def audit(run: Path, output: Path) -> None:
    if json.loads((run / "status.json").read_text())["state"] != "complete":
        raise ValueError("audit a complete run")
    programs: dict[str, dict] = {}
    for line in (run / "results.jsonl").read_text().splitlines():
        row = json.loads(line)
        episode = Path(row["episode_dir"])
        for text in (episode / "trajectory.jsonl").read_text().splitlines():
            event = json.loads(text)
            action = event["action"]
            if action["tool"] == "write":
                code = action["content"]
                programs.setdefault(
                    digest(code.encode()), {"code": code, "origins": []}
                )["origins"].append(str(episode))
    if (run / "corpus.json").exists():
        corpus = json.loads((run / "corpus.json").read_text())
        for obj in corpus["forks"]:
            fork = DecisionFork.model_validate(obj)
            for branch in fork.alternatives:
                for code in [branch.first_action.content, final_code(branch)]:
                    programs.setdefault(
                        digest(code.encode()), {"code": code, "origins": []}
                    )["origins"].append(fork.fork_id + ":" + branch.branch_id)
    flags = []
    syntax_failures = []
    internal = {
        "state",
        "scenario",
        "trace",
        "invalid",
        "decisions",
        "crashes",
        "crash_after",
        "__dict__",
        "__getattribute__",
    }
    introspection = {
        "getattr",
        "setattr",
        "vars",
        "globals",
        "locals",
        "eval",
        "exec",
        "__import__",
        "hasattr",
        "dir",
    }
    for sha, entry in programs.items():
        try:
            tree = ast.parse(entry["code"])
        except SyntaxError:
            syntax_failures.append(sha)
            continue
        api_names = {"api"}
        for function in ast.walk(tree):
            if (
                isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
                and function.name == "run"
                and function.args.args
            ):
                api_names.add(function.args.args[0].arg)
        for _ in range(3):
            for assignment in ast.walk(tree):
                if (
                    isinstance(assignment, ast.Assign)
                    and isinstance(assignment.value, ast.Name)
                    and assignment.value.id in api_names
                ):
                    api_names.update(
                        t.id for t in assignment.targets if isinstance(t, ast.Name)
                    )
        findings = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in api_names
                and node.attr not in {"inspect", "apply"}
            ):
                findings.append(
                    {
                        "line": node.lineno,
                        "kind": "undocumented_api_attribute",
                        "name": node.attr,
                    }
                )
            if isinstance(node, ast.Global):
                findings.append(
                    {
                        "line": node.lineno,
                        "kind": "global_state_requires_review",
                        "names": node.names,
                    }
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(value, (ast.Dict, ast.List, ast.Set))
                for value in node.args.defaults
            ):
                findings.append(
                    {
                        "line": node.lineno,
                        "kind": "persistent_mutable_default_requires_review",
                    }
                )
            if isinstance(node, ast.Attribute) and node.attr in internal:
                findings.append(
                    {
                        "line": node.lineno,
                        "kind": "possible_internal_attribute",
                        "name": node.attr,
                    }
                )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in introspection
            ):
                findings.append(
                    {
                        "line": node.lineno,
                        "kind": "dynamic_introspection",
                        "name": node.func.id,
                    }
                )
            if isinstance(node, ast.ExceptHandler) and (
                node.type is None
                or isinstance(node.type, ast.Name)
                and node.type.id in {"BaseException", "SimulatedCrash", "SystemExit"}
            ):
                findings.append(
                    {"line": node.lineno, "kind": "possible_crash_suppression"}
                )
        if findings:
            flags.append(
                {
                    "sha256": sha,
                    "origins": entry["origins"],
                    "findings": findings,
                    "code": entry["code"],
                }
            )
    result = {
        "run": str(run.resolve()),
        "distinct_executed_program_versions": len(programs),
        "syntax_failure_versions": syntax_failures,
        "flagged_versions": len(flags),
        "flags": flags,
        "scope": "AST screen for specified internal access, API aliases, global/default state and broad crash catches; not a security proof. Any flags require manual review before asserting contract adherence.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        {
            k: v
            for k, v in result.items()
            if k not in {"flags", "syntax_failure_versions"}
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.runs, args.output)
