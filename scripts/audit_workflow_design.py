"""Reference and omission-mutation audit without any model outcomes."""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

from forkmem.workflows.analysis import contrast
from forkmem.workflows.engine import ProtocolViolation, WorkflowAPI
from forkmem.workflows.scenarios import FACTORIES, reference

rows = []
for family, factory in FACTORIES.items():
    for bits in product([False, True], repeat=3):
        scenario = factory(bits)
        api = WorkflowAPI(scenario)
        reference(family, api)
        actual = api.result()
        assert actual["success"]
        mutations = []
        for skip, operation in enumerate(api.decisions):
            mutant = WorkflowAPI(scenario)
            for i, name in enumerate(api.decisions):
                if i == skip:
                    continue
                try:
                    mutant.apply(name)
                except ProtocolViolation:
                    break
            outcome = mutant.result()
            mutations.append(
                {
                    "omitted_operation": operation,
                    "detected": not outcome["success"],
                    "comparison": contrast(actual, outcome),
                    "outcome": outcome,
                }
            )
        rows.append(
            {
                "family": family,
                "bits": bits,
                "reference_operations": api.decisions,
                "critical_operation_count": sum(m["detected"] for m in mutations),
                "mutations": mutations,
            }
        )
summary = {
    "contexts": len(rows),
    "references_passed": len(rows),
    "omission_mutations": sum(len(r["mutations"]) for r in rows),
    "detected_omissions": sum(r["critical_operation_count"] for r in rows),
    "rows": rows,
    "interpretation": "Omitting optional/idempotent cleanup operations may remain valid; no requirement to match the reference plan exactly.",
}
output = Path("artifacts/v2/design_audit_dev0.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(summary, indent=2) + "\n")
print({k: v for k, v in summary.items() if k != "rows"})
