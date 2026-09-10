from itertools import product

import pytest

from forkmem.workflows.engine import WorkflowAPI
from forkmem.workflows.resumable import (
    ResumableAPI,
    SimulatedCrash,
    resumable_reference,
)
from forkmem.workflows.scenarios import FACTORIES, reference


@pytest.mark.parametrize("family", list(FACTORIES))
def test_every_single_and_adjacent_double_crash(family):
    for bits in product([False, True], repeat=3):
        scenario = FACTORIES[family](bits)
        scenario["budget"] += 10
        base = WorkflowAPI(scenario)
        reference(family, base)
        operations = base.decisions
        schedules = (
            [[]]
            + [[x] for x in operations]
            + [operations[i : i + 2] for i in range(len(operations) - 1)]
        )
        for schedule in schedules:
            api = ResumableAPI(scenario, schedule)
            for _ in range(len(schedule) + 1):
                try:
                    resumable_reference(family, api)
                    break
                except SimulatedCrash:
                    continue
            assert api.result()["success"], (family, bits, schedule, api.result())
            assert api.crashes == len(schedule)
