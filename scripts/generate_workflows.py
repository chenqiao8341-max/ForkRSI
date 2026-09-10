"""Generate workflow development fixtures and unopened factorial transfer tasks."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from forkmem.environment import digest
from forkmem.workflows import engine, scenarios

ROOT = Path(__file__).resolve().parents[1]
TRAIN = [0, 3, 5, 6]
TRANSFER = [1, 2, 4, 7]
PURPOSE = {
    "migration": "Migrate a live schema without losing concurrent writes or breaking old readers. Audit the backfill. If the target is unhealthy, remove the expansion and retain the old service; otherwise finish cutover and retire old schema. Remove temporary capture and compatibility infrastructure.",
    "release": "Validate and health-check a replacement release. Preserve sticky sessions on successful cutover and retire the old instance. If unhealthy, discard the replacement and retain old service. Resume any paused batch workers on both paths.",
    "ingestion": "Process and acknowledge an event with durable application and delivery, without applying a replay twice. Use the configured transaction and sink semantics. An acknowledged event must already be durable and delivered. Leave no active lease or transaction.",
    "compensation": "Resolve an order: inspect inventory; reject unavailable stock without payment. Otherwise reserve, authorize, respect prepayment requirements and attempt shipment. Settle successful orders; on shipment failure undo financial and inventory reservations. No dangling authorization or reservation may remain.",
}


def task(family: str, index: int, split: str) -> dict:
    bits = tuple(bool(index & (1 << i)) for i in range(3))
    scenario = scenarios.FACTORIES[family](bits)
    axes = scenarios.AXES[family]
    task_id = f"workflow_{family}_{split}_{index:03b}"
    # Effect-level API documentation exposes contracts, never a reference plan.
    manual = """Implement run(api). api.inspect('state') returns a detached state dictionary, costing one unit. api.apply(operation) executes one documented operation, returning the updated state. Each call costs the documented amount (default one). Unknown operations, failed preconditions and transient safety violations make the run invalid even if caught. Do not access API internals. Return once all operational obligations are satisfied. Different valid plans are accepted.\n\n"""
    manual += (
        PURPOSE[family]
        + "\n\nOperations (requires predicates all must hold; effects update fields):\n"
    )
    for name, rule in scenario["operations"].items():
        manual += f"- {name}: requires {json.dumps(rule['requires'])}; effects {json.dumps(rule['effects'])}; cost {rule['cost']}.\n"
    manual += "\nSafety invariants:\n" + json.dumps(scenario["invariants"], indent=2)
    manual += (
        "\nThe deployment profile is in deployment.json. Other state fields start false unless described: migration old_schema starts true; release blue starts true; ingestion replayed events start applied/outbox/committed/delivered true. Operation budget: "
        + str(scenario["budget"])
        + ".\n"
    )
    verifier = "import sys\nsys.path.insert(0, '/task')\n" + inspect.getsource(
        engine
    ).replace("from __future__ import annotations", "")
    # All annotations must be postponed for the sandbox's Python 3.8 runtime.
    verifier = "from __future__ import annotations\n" + verifier
    verifier += "\nimport json\nfrom solution import run\n"
    verifier += "api = WorkflowAPI(" + repr(scenario) + ")\n"
    verifier += "error = None\ntry:\n    run(api)\nexcept Exception as exc:\n    error = type(exc).__name__ + ': ' + str(exc)\n    api.invalid = True\n"
    verifier += "result = api.result()\nprint('FORKMEM_WORKFLOW_RESULT=' + json.dumps(result, sort_keys=True))\nif error: print(error)\nassert result['success'], result['obligations']\nprint('FORKMEM_VERIFIER_COMPLETE')\n"
    reference = inspect.getsource(scenarios.reference).replace(
        "def reference(family: str, api: Any)", "def reference(family, api)"
    )
    reference += f"\ndef run(api):\n    return reference({family!r}, api)\n"
    # Initial policy is deliberately incomplete; formal source-memory provenance
    # must distinguish this seeded code from an autonomous agent failure.
    initial = "def run(api):\n    api.inspect('state')\n"
    features = {key: str(value).lower() for key, value in zip(axes, bits, strict=True)}
    return {
        "task_id": task_id,
        "family": f"workflow_{family}",
        "split": split,
        "description": f"Repair the operational controller in solution.py for the {family} deployment. Read the API contract and deployment context; execute a safe complete workflow through run(api).",
        "features": features,
        "files": {
            "solution.py": initial,
            "README.md": manual,
            "deployment.json": json.dumps(dict(zip(axes, bits, strict=True)), indent=2),
        },
        "verifier": verifier,
        "reference_solution": reference,
        "decision_axes": list(axes),
        "semantic_context": f"{family}-{index:03b}",
        "transfer_stratum": "unseen_constraint_combination_and_matched_single_flip"
        if split == "held_out"
        else split,
        "matched_training_contexts": [
            f"{family}-{j:03b}" for j in TRAIN if (index ^ j).bit_count() == 1
        ]
        if split == "held_out"
        else [],
    }


def generate() -> None:
    destination = ROOT / "data/v2/workflow_dev0"
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for family in scenarios.FACTORIES:
        for split, indices in [
            ("development", [5, 6]),
            ("train", TRAIN),
            ("held_out", TRANSFER),
        ]:
            for index in indices:
                spec = task(family, index, split)
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
                    }
                )
    manifest = {
        "version": "workflow-dev0",
        "status": "development; not a frozen final evaluation",
        "training_combinations": TRAIN,
        "transfer_combinations": TRANSFER,
        "note": "Development tasks reuse training-side contexts only; cluster repeated contexts together. Transfer outcomes must stay unopened during calibration.",
        "tasks": entries,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Generated {len(entries)} tasks; 8 development, 16 training, 16 unopened transfer."
    )


if __name__ == "__main__":
    generate()
