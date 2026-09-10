"""A new dataset version after the archived static development ceiling."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from generate_workflows import task

from forkmem.environment import digest
from forkmem.workflows import engine, resumable, scenarios

ROOT = Path(__file__).resolve().parents[1]


def generate():
    destination = ROOT / "data/v2/workflow_dev1"
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for family, factory in scenarios.FACTORIES.items():
        for split, indices in [
            ("development", [0, 3, 5, 6]),
            ("train", [0, 3, 5, 6]),
            ("held_out", [1, 2, 4, 7]),
        ]:
            for index in indices:
                spec = task(family, index, split)
                spec["task_id"] = spec["task_id"].replace("workflow_", "resumable_", 1)
                bits = tuple(bool(index & (1 << i)) for i in range(3))
                scenario = factory(bits)
                scenario["budget"] += 10
                base = engine.WorkflowAPI(scenario)
                scenarios.reference(family, base)
                operations = base.decisions
                schedules = (
                    [[]]
                    + [[name] for name in operations]
                    + [operations[i : i + 2] for i in range(len(operations) - 1)]
                )
                manual = spec["files"]["README.md"]
                manual += f"""\n\nProcess recovery contract: the supervisor may kill the process after any API operation and invoke run(api) again with fresh local variables. Operations on external services are atomic; their completed state is observable on restart. An uncommitted ingestion transaction rolls back on process death (transaction/applied/outbox reset false); committed state, receipts and leases persist. Reconstruct progress from api.inspect('state'); never suppress simulated process death or access API internals. The controller must safely complete without faults and under up to two such interruptions, including a crash after the last operation. Total operation budget including restart inspections is {scenario["budget"]} (this overrides the normal-path budget). Complete every recovery case, not only the clean path.\n"""
                spec["files"]["README.md"] = manual
                spec["description"] += (
                    " The controller must also resume safely after process interruption without repeating harmful side effects or leaking temporary resources."
                )
                verifier = 'from __future__ import annotations\nimport sys\nsys.path.insert(0, "/task")\n'
                verifier += (
                    inspect.getsource(engine).replace(
                        "from __future__ import annotations", ""
                    )
                    + "\n"
                )
                verifier += (
                    inspect.getsource(resumable.SimulatedCrash)
                    + "\n"
                    + inspect.getsource(resumable.ResumableAPI)
                    + "\n"
                )
                verifier += "import json\nfrom solution import run\n"
                verifier += (
                    "scenario="
                    + repr(scenario)
                    + "\nschedules="
                    + repr(schedules)
                    + "\n"
                )
                verifier += """cases=[]
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
                spec["verifier"] = verifier
                ref = inspect.getsource(resumable.resumable_reference).replace(
                    "def resumable_reference(family: str, api: Any) -> None:",
                    "def resumable_reference(family, api):",
                )
                spec["reference_solution"] = (
                    ref
                    + f"\ndef run(api):\n    return resumable_reference({family!r}, api)\n"
                )
                spec["runtime_case_count"] = len(schedules)
                spec["crash_semantics"] = (
                    "external atomic effects persist; open ingestion transaction rolls back; fresh controller locals"
                )
                path = destination / (spec["task_id"] + ".json")
                path.write_text(json.dumps(spec, indent=2) + "\n")
                entries.append(
                    {
                        "task_id": spec["task_id"],
                        "family": spec["family"],
                        "split": split,
                        "path": str(path.relative_to(ROOT)),
                        "sha256": digest(path.read_bytes()),
                        "semantic_context": spec["semantic_context"],
                        "runtime_case_count": len(schedules),
                    }
                )
    manifest = {
        "version": "workflow-dev1",
        "status": "development; transfer outcomes unopened",
        "predecessor": "workflow-dev0: development no-memory 8/8, archived; recovery mechanism added before transfer inference",
        "tasks": entries,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "Generated",
        len(entries),
        "tasks with",
        sum(e["runtime_case_count"] for e in entries),
        "runtime cases (includes reused development contexts).",
    )


if __name__ == "__main__":
    generate()
