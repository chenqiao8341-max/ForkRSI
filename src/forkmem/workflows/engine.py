"""Small explicit-state protocol executor, independent of reference policies.

Task programs see only the documented inspect/apply API. A trace records every
attempt, including failed preconditions; an invalid step cannot be hidden by
catching its exception. This simulator executes no external side effects.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class ProtocolViolation(Exception):
    pass


class WorkflowAPI:
    def __init__(self, scenario: dict[str, Any]):
        self.scenario = deepcopy(scenario)
        self.state = deepcopy(scenario["initial"])
        self.trace: list[dict[str, Any]] = []
        self.spent = 0
        self.invalid = False
        self.decisions: list[str] = []

    def inspect(self, resource: str = "state") -> dict[str, Any]:
        if resource != "state":
            self.invalid = True
            raise ProtocolViolation("inspect supports resource 'state'")
        self._charge(1)
        self.trace.append({"kind": "inspect", "state": deepcopy(self.state)})
        return deepcopy(self.state)

    def _charge(self, cost: int) -> None:
        self.spent += cost
        if self.spent > self.scenario["budget"]:
            self.invalid = True
            raise ProtocolViolation("operation budget exceeded")

    def apply(self, operation: str) -> dict[str, Any]:
        before = deepcopy(self.state)
        event: dict[str, Any] = {
            "kind": "apply",
            "operation": operation,
            "before": before,
        }
        self.trace.append(event)
        rule = self.scenario["operations"].get(operation)
        if rule is None:
            self.invalid = True
            event["error"] = "unknown operation"
            raise ProtocolViolation(event["error"])
        self._charge(rule.get("cost", 1))
        missing = {
            key: value
            for key, value in rule.get("requires", {}).items()
            if self.state.get(key) != value
        }
        excluded = {
            key: value
            for key, value in rule.get("excludes", {}).items()
            if self.state.get(key) == value
        }
        if missing or excluded:
            self.invalid = True
            event.update(
                error="precondition violation", missing=missing, excluded=excluded
            )
            raise ProtocolViolation(f"{operation}: precondition violation")
        self.state.update(deepcopy(rule.get("effects", {})))
        self.decisions.append(operation)
        event["after"] = deepcopy(self.state)
        # Invariants are checked after every action, even if later code repairs it.
        for invariant in self.scenario.get("invariants", []):
            if invariant.get("on") and operation not in invariant["on"]:
                continue
            when = invariant.get("when", {})
            if all(self.state.get(k) == v for k, v in when.items()) and not all(
                self.state.get(k) == v for k, v in invariant["requires"].items()
            ):
                self.invalid = True
                event["error"] = "safety invariant: " + invariant["name"]
                raise ProtocolViolation(event["error"])
        return deepcopy(self.state)

    def result(self) -> dict[str, Any]:
        obligations = {
            name: all(self.state.get(key) == value for key, value in predicates.items())
            for name, predicates in self.scenario["goals"].items()
        }
        obligations["valid_execution"] = not self.invalid
        return {
            "success": all(obligations.values()),
            "obligations": obligations,
            "operations": len(self.decisions),
            "cost": self.spent,
            "trace": deepcopy(self.trace),
            "final_state": deepcopy(self.state),
        }
