"""Durable operation checkpoints with loss of local process state after a crash."""

from __future__ import annotations

from typing import Any

from forkmem.workflows.engine import WorkflowAPI


class SimulatedCrash(BaseException):
    """Infrastructure restarts run(api); task code must not suppress this event."""


class ResumableAPI(WorkflowAPI):
    def __init__(self, scenario: dict[str, Any], crash_after: list[str]):
        super().__init__(scenario)
        self.crash_after = list(crash_after)
        self.crashes = 0

    def apply(self, operation: str) -> dict[str, Any]:
        result = super().apply(operation)
        if self.crash_after and operation == self.crash_after[0]:
            self.crash_after.pop(0)
            self.crashes += 1
            self.trace[-1]["process_crash_after_operation"] = True
            # An open transaction rolls back when its owning process dies.
            # Committed effects and external service receipts remain durable.
            if self.state.get("transaction", False):
                self.state.update(transaction=False, applied=False, outbox=False)
                self.trace[-1]["transaction_rolled_back"] = True
                self.trace[-1]["restart_state"] = dict(self.state)
            raise SimulatedCrash(operation)
        return result


def resumable_reference(family: str, api: Any) -> None:
    """Handwritten phase-aware witness; does not inspect oracle goals/rules."""
    s = api.inspect()

    def do(operation: str) -> None:
        s.update(api.apply(operation))

    if family == "migration":
        if (
            s["healthy"]
            and not s["new_traffic"]
            or not s["healthy"]
            and not (s["audited"] and not s["expanded"])
        ):
            if not s["expanded"]:
                do("expand")
            if s["old_writers"] and not s["capturing"]:
                do("capture_changes")
            if not s["copied"]:
                do("backfill")
            if not s["audited"]:
                do("audit_backfill")
            if not s["healthy"]:
                do("rollback_expansion")
                return
            if s["legacy_readers"] and not s["compatibility"]:
                do("install_compatibility")
            do("cutover")
        if s["healthy"]:
            if s["legacy_readers"]:
                do("drain_legacy_readers")
            if s["old_schema"]:
                do("drop_old_schema")
            if s["capturing"]:
                do("remove_capture")
            if s["compatibility"]:
                do("remove_compatibility")
    elif family == "release":
        if not s["signed"]:
            do("verify_artifact")
        aborted = s["probed"] and not s["healthy"] and not s["green"]
        if not aborted and not s["new_traffic"]:
            if not s["capacity"]:
                do("pause_batch_workers")
            if not s["green"]:
                do("allocate_green")
            if not s["warm"]:
                do("warm_green")
            if not s["probed"]:
                do("probe_health")
        if not s["healthy"]:
            if s["green"]:
                do("discard_green")
            if s["workers_paused"]:
                do("resume_workers_after_abort")
            return
        if not s["new_traffic"]:
            if s["sticky_sessions"] and not s["drained"]:
                do("drain_sticky_sessions")
            do("switch_traffic")
        if s["blue"]:
            do("retire_blue")
        if s["workers_paused"]:
            do("resume_workers_after_release")
    elif family == "ingestion":
        if s["acknowledged"]:
            if s["leased"]:
                do("release_lease")
            return
        if not s["leased"]:
            do("claim")
        if not s["committed"]:
            if not s["applied"]:
                if s["transactional"]:
                    if not s["transaction"]:
                        do("begin")
                    do("apply_transactional")
                else:
                    do("apply_direct")
            if not s["outbox"]:
                do("stage_outbox")
            do("commit_transaction" if s["transactional"] else "persist_direct")
        if not s["delivered"]:
            if s["deduplicating_sink"]:
                do("deliver_idempotently")
            else:
                if not s["receipt_checked"]:
                    do("check_delivery_receipt")
                do("deliver_once")
        do("acknowledge")
        do("release_lease")
    elif family == "compensation":
        if s["settled"] or s["rejected"]:
            return
        if not s["stock_checked"]:
            do("check_stock")
        if not s["stock_available"]:
            do("reject_unavailable")
            return
        if not s["shipment_attempted"]:
            if not s["reserved"]:
                do("reserve")
            if not s["authorized"]:
                do("authorize")
            if s["prepaid"] and not s["captured"]:
                do("capture_prepaid")
            do("ship")
        if s["shipped"]:
            if not s["captured"]:
                do("capture_postpaid")
            do("settle")
        else:
            if s["captured"]:
                do("refund")
            elif s["authorized"]:
                do("void_authorization")
            if s["reserved"]:
                do("release_reservation")
    else:
        raise ValueError(family)
