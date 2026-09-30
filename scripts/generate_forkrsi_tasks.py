"""Freeze new semantic combinations before any task-model inference."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from generate_workflows import PURPOSE, task

from forkmem.environment import digest
from forkmem.workflows import engine, resumable, scenarios

ROOT = Path(__file__).resolve().parents[1]
# These combinations were chosen from contracts, without model outcomes.
GROUPS = {
    "development": [
        ("release", 0, "fresh", True),
        ("release", 6, "warm", False),
        ("ingestion", 2, "applied", False),
        ("ingestion", 1, "fresh", True),
    ],
    "selection": [
        ("release", 7, "warm", False),
        ("ingestion", 1, "delivered", False),
    ],
    "reset": [
        ("release", 4, "switched", False),
        ("release", 3, "aborted", True),
        ("ingestion", 0, "outbox", False),
        ("ingestion", 3, "delivered", True),
    ],
    "final": [
        ("release", 6, "switched", True),
        ("release", 5, "retired", True),
        ("release", 2, "aborted", True),
        ("release", 1, "warm", True),
        ("ingestion", 0, "applied", True),
        ("ingestion", 2, "outbox", True),
        ("ingestion", 1, "committed", True),
        ("ingestion", 3, "acknowledged", True),
    ],
}


def scenario_for(family: str, index: int, phase: str, audit: bool) -> dict:
    bits = tuple(bool(index & (1 << i)) for i in range(3))
    scenario = scenarios.FACTORIES[family](bits)
    state = scenario["initial"]
    if family == "release":
        if phase in {"warm", "switched", "retired", "aborted"}:
            state.update(signed=True, capacity=True, workers_paused=not bits[0])
        if phase in {"warm", "switched", "retired"}:
            state.update(green=True, warm=True)
        if phase in {"switched", "retired"}:
            if not bits[2]:
                raise ValueError("unhealthy release cannot have switched")
            state.update(probed=True, drained=bits[1], new_traffic=True)
        if phase == "retired":
            state["blue"] = False
        if phase == "aborted":
            if bits[2]:
                raise ValueError("healthy release cannot have aborted")
            state.update(probed=True, green=False, warm=False)
        audit_name = "record_release_audit"
        requires = {
            "probed": True,
            "workers_paused": False,
            "new_traffic": bits[2],
            "blue": not bits[2],
            "green": bits[2],
            "audited": False,
        }
    elif family == "ingestion":
        if phase != "fresh" and bits[2]:
            raise ValueError("partial state must have a non-replayed original event")
        if phase in {"applied", "outbox"}:
            if bits[0]:
                raise ValueError("open transactions do not survive process death")
            state.update(leased=True, applied=True)
        if phase == "outbox":
            state["outbox"] = True
        if phase in {"committed", "delivered", "acknowledged"}:
            state.update(leased=True, applied=True, outbox=True, committed=True)
        if phase in {"delivered", "acknowledged"}:
            state.update(delivered=True, receipt_checked=not bits[1])
        if phase == "acknowledged":
            state["acknowledged"] = True
        audit_name = "record_ingestion_audit"
        requires = {
            "committed": True,
            "delivered": True,
            "acknowledged": True,
            "leased": False,
            "transaction": False,
            "audited": False,
        }
    else:
        raise ValueError("unsupported research family")
    state.update(audit_required=audit, audited=False)
    scenario["operations"][audit_name] = scenarios.op(requires, {"audited": True})
    if audit:
        scenario["goals"]["post_cleanup_audit"] = {"audited": True}
    scenario["budget"] += 15
    return scenario


def reference(family: str) -> str:
    body = inspect.getsource(resumable.resumable_reference).replace(
        "def resumable_reference(family: str, api: Any) -> None:",
        "def resumable_reference(family, api):",
    )
    audit = "record_" + family + "_audit"
    return body + (
        f"\ndef run(api):\n    resumable_reference({family!r}, api)\n"
        "    s = api.inspect('state')\n"
        f"    if s['audit_required'] and not s['audited']:\n        api.apply({audit!r})\n"
    )


def verifier(scenario: dict, schedules: list[list[str]]) -> str:
    # Fixed engine and recovery supervisor copied verbatim from the existing
    # development verifier. Only scenario data and its witness schedules vary.
    body = (
        'from __future__ import annotations\nimport sys\nsys.path.insert(0, "/task")\n'
    )
    body += (
        inspect.getsource(engine).replace("from __future__ import annotations", "")
        + "\n"
    )
    body += inspect.getsource(resumable.SimulatedCrash) + "\n"
    body += inspect.getsource(resumable.ResumableAPI) + "\n"
    body += "import json\nfrom solution import run\n"
    body += "scenario=" + repr(scenario) + "\nschedules=" + repr(schedules) + "\n"
    body += """cases=[]
for case_id,schedule in enumerate(schedules):
    api=ResumableAPI(scenario,schedule)
    error=None
    for invocation in range(len(schedule)+1):
        try:
            run(api)
            break
        except SimulatedCrash:
            continue
        except Exception as exc:
            error=type(exc).__name__+': '+str(exc)
            api.invalid=True
            break
    result=api.result()
    result.update(case_id=case_id,scheduled_crashes=schedule,observed_crashes=api.crashes,error=error)
    cases.append(result)
obligations={key:all(c['obligations'][key] for c in cases) for key in cases[0]['obligations']}
failed=[c for c in cases if not c['success']]
primary=(failed or cases)[0]
summary={'success':all(c['success'] for c in cases),'obligations':obligations,'case_successes':sum(c['success'] for c in cases),'case_total':len(cases),'failed_cases':[{'case_id':c['case_id'],'crash_after':c['scheduled_crashes'],'error':c['error'],'obligations':c['obligations']} for c in failed], 'trace':primary['trace'],'operations':sum(c['operations'] for c in cases),'cost':sum(c['cost'] for c in cases)}
print('FORKMEM_WORKFLOW_RESULT='+json.dumps(summary))
for case in cases:
    print('FORKMEM_WORKFLOW_CASE='+json.dumps(case))
assert summary['success'], summary['obligations']
print('FORKMEM_VERIFIER_COMPLETE')
"""
    return body


def make_task(family: str, index: int, phase: str, audit: bool, split: str) -> dict:
    spec = task(family, index, split)
    scenario = scenario_for(family, index, phase, audit)
    ref = reference(family)
    witness = engine.WorkflowAPI(scenario)
    resumable.resumable_reference(family, witness)
    state = witness.inspect("state")
    if state["audit_required"] and not state["audited"]:
        witness.apply("record_" + family + "_audit")
    if not witness.result()["success"]:
        raise ValueError("invalid normal-path witness")
    operations = witness.decisions
    schedules = (
        [[]]
        + [[op] for op in operations]
        + [operations[i : i + 2] for i in range(len(operations) - 1)]
    )
    identity = f"{family}-{index:03b}-{phase}-audit{int(audit)}"
    spec.update(
        task_id="forkrsi_" + split + "_" + identity,
        semantic_context=identity,
        reference_solution=ref,
        runtime_case_count=len(schedules),
        verifier=verifier(scenario, schedules),
        crash_semantics="atomic external effects persist; open transactions roll back; fresh locals",
        transfer_stratum="new_entry_phase_and_post_cleanup_obligation",
    )
    spec["features"].update(entry_phase=phase, audit_required=str(audit).lower())
    spec["decision_axes"] += ["entry_phase", "audit_required"]
    spec["description"] += (
        " This controller may start with durable work already completed. Resume from the "
        "observable entry state, safely finish every recovery case and any required post-cleanup audit."
    )
    manual = (
        "Implement run(api). api.inspect('state') returns detached current state, costing one unit. "
        "api.apply(operation) atomically executes a documented operation and returns updated state. "
        "A failed precondition or safety invariant invalidates the case, even if caught. "
        "Do not access API internals. Different valid complete plans are accepted.\n\n"
        + PURPOSE[family]
        + "\n\nOperations (all requires predicates must hold):\n"
    )
    for name, rule in scenario["operations"].items():
        manual += (
            f"- {name}: requires {json.dumps(rule['requires'])}; "
            f"effects {json.dumps(rule['effects'])}; cost {rule['cost']}.\n"
        )
    manual += "\nSafety invariants:\n" + json.dumps(scenario["invariants"], indent=2)
    manual += "\nCompletion obligations:\n" + json.dumps(scenario["goals"], indent=2)
    manual += "\nActual initial durable state (overrides historical defaults):\n"
    manual += json.dumps(scenario["initial"], indent=2)
    manual += (
        "\nProcess recovery contract: the supervisor may kill the process after any API operation "
        "and invoke run(api) with fresh local variables. Completed external service effects persist. "
        "An open ingestion transaction rolls back transaction/applied/outbox on death. "
        "Reconstruct progress from api.inspect('state'); never suppress process death. "
        "Safely complete without faults and under up to two interruptions, including after the "
        f"last operation. Total operation budget, including restart inspections: {scenario['budget']}. "
        "An audit, when required, must be recorded after cleanup and itself tolerate restart.\n"
    )
    spec["files"]["README.md"] = manual
    spec["files"]["deployment.json"] = json.dumps(
        {
            **json.loads(spec["files"]["deployment.json"]),
            "entry_phase": phase,
            "audit_required": audit,
        },
        indent=2,
    )
    spec["matched_training_contexts"] = []
    return spec


def generate() -> None:
    destination = ROOT / "data/forkrsi/semantic_v1"
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    contexts = set()
    for split, rows in GROUPS.items():
        for family, index, phase, audit in rows:
            spec = make_task(family, index, phase, audit, split)
            if spec["semantic_context"] in contexts:
                raise ValueError("semantic context overlaps splits")
            contexts.add(spec["semantic_context"])
            path = destination / (spec["task_id"] + ".json")
            text = json.dumps(spec, indent=2) + "\n"
            if path.exists() and path.read_text() != text:
                raise ValueError(
                    "refusing to overwrite changed frozen task: " + str(path)
                )
            path.write_text(text)
            entries.append(
                {
                    "task_id": spec["task_id"],
                    "family": spec["family"],
                    "split": split,
                    "path": str(path.relative_to(ROOT)),
                    "sha256": digest(path.read_bytes()),
                    "semantic_context": spec["semantic_context"],
                    "runtime_case_count": spec["runtime_case_count"],
                }
            )
    source = []
    for family in ("release", "ingestion"):
        for index in (0, 3, 5, 6):
            path = (
                ROOT
                / f"data/v2/workflow_dev1/resumable_{family}_train_{index:03b}.json"
            )
            spec = json.loads(path.read_text())
            source.append(
                {
                    "task_id": spec["task_id"],
                    "family": spec["family"],
                    "path": str(path.relative_to(ROOT)),
                    "sha256": digest(path.read_bytes()),
                    "semantic_context": spec["semantic_context"],
                    "note": "reused source context; new Qwen executions required",
                }
            )
    manifest = {
        "version": "forkrsi-semantic-v1",
        "status": "frozen before model inference",
        "unit": "semantic task; recovery cases are nested observations",
        "engine_sha256": digest(inspect.getsource(engine).encode()),
        "recovery_sha256": digest(inspect.getsource(resumable.ResumableAPI).encode()),
        "source_tasks": source,
        "tasks": entries,
    }
    target = destination / "manifest.json"
    text = json.dumps(manifest, indent=2) + "\n"
    if target.exists() and target.read_text() != text:
        raise ValueError("refusing to change frozen manifest")
    target.write_text(text)
    source_manifest = ROOT / "configs/forkrsi/source-manifest.json"
    source_manifest.parent.mkdir(parents=True, exist_ok=True)
    source_manifest.write_text(
        json.dumps(
            {
                "version": "forkrsi-source-v1",
                "tasks": [dict(e, split="train") for e in source],
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "tasks": len(entries),
                "source_tasks": len(source),
                "manifest_sha256": digest(target.read_bytes()),
            }
        )
    )


if __name__ == "__main__":
    generate()
