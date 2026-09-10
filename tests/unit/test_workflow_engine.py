import pytest

from forkmem.workflows.engine import ProtocolViolation, WorkflowAPI


def scenario():
    return {
        "initial": {"durable": False, "acknowledged": False},
        "budget": 6,
        "operations": {
            "persist": {"effects": {"durable": True}},
            "ack": {"requires": {"durable": True}, "effects": {"acknowledged": True}},
            "unsafe_ack": {"effects": {"acknowledged": True}},
        },
        "invariants": [
            {
                "name": "ack_after_durability",
                "when": {"acknowledged": True},
                "requires": {"durable": True},
            }
        ],
        "goals": {
            "durability": {"durable": True},
            "completion": {"acknowledged": True},
        },
    }


def test_local_completion_is_not_safe_success():
    api = WorkflowAPI(scenario())
    with pytest.raises(ProtocolViolation):
        api.apply("unsafe_ack")
    api.apply("persist")
    result = api.result()
    assert result["obligations"]["durability"]
    assert result["obligations"]["completion"]
    assert not result["success"]
    assert result["trace"][0]["error"].startswith("safety invariant")


def test_same_checkpoint_different_order_has_different_outcome():
    original = scenario()
    factual, alternative = WorkflowAPI(original), WorkflowAPI(original)
    with pytest.raises(ProtocolViolation):
        factual.apply("ack")
    alternative.apply("persist")
    alternative.apply("ack")
    assert alternative.result()["success"]
    assert not factual.result()["success"]
    assert original["initial"]["durable"] is False


def test_observations_are_detached_and_budget_is_enforced():
    api = WorkflowAPI(scenario())
    observation = api.inspect()
    observation["durable"] = True
    assert api.state["durable"] is False
    for _ in range(5):
        api.inspect()
    with pytest.raises(ProtocolViolation):
        api.inspect()
    assert not api.result()["success"]


@pytest.mark.parametrize(
    "family", ["migration", "release", "ingestion", "compensation"]
)
def test_all_contract_combinations_and_order_mutations(family):
    from itertools import product

    from forkmem.workflows.scenarios import FACTORIES, reference

    rejected = 0
    for bits in product([False, True], repeat=3):
        scenario = FACTORIES[family](bits)
        api = WorkflowAPI(scenario)
        reference(family, api)
        assert api.result()["success"], (family, bits)
        # Reverse successful plans: same local operations, incompatible order.
        mutated = WorkflowAPI(scenario)
        for operation in reversed(api.decisions):
            try:
                mutated.apply(operation)
            except ProtocolViolation:
                break
        rejected += not mutated.result()["success"]
    assert rejected == 8


def test_contrast_reports_partial_repair_and_new_regression():
    from forkmem.workflows.analysis import contrast

    before = {
        "success": False,
        "obligations": {"durability": False, "cleanup": True},
        "trace": [{"kind": "apply", "operation": "ack"}],
    }
    after = {
        "success": False,
        "obligations": {"durability": True, "cleanup": False},
        "trace": [
            {"kind": "apply", "operation": "persist"},
            {"kind": "apply", "operation": "ack"},
        ],
    }
    result = contrast(before, after)
    assert result["repaired_obligations"] == ["durability"]
    assert result["regressed_obligations"] == ["cleanup"]
    assert result["downstream_regression"]
    assert not result["globally_successful"]
