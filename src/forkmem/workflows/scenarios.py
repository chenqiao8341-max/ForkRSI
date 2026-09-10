"""Operational contracts with interacting decisions and explicit recovery paths."""

from __future__ import annotations

from typing import Any


def op(
    requires: dict[str, Any], effects: dict[str, Any], cost: int = 1
) -> dict[str, Any]:
    return {"requires": requires, "effects": effects, "cost": cost}


def migration(bits: tuple[bool, bool, bool]) -> dict[str, Any]:
    live, legacy, healthy = bits
    state = {
        "old_writers": live,
        "legacy_readers": legacy,
        "healthy": healthy,
        "old_schema": True,
        "expanded": False,
        "capturing": False,
        "copied": False,
        "audited": False,
        "compatibility": False,
        "new_traffic": False,
    }
    operations = {
        "expand": op({"expanded": False}, {"expanded": True}),
        "capture_changes": op({"expanded": True}, {"capturing": True}),
        "backfill": op({"expanded": True}, {"copied": True}),
        "audit_backfill": op({"copied": True}, {"audited": True}),
        "install_compatibility": op({"expanded": True}, {"compatibility": True}),
        "cutover": op(
            {"audited": True, "healthy": True},
            {"new_traffic": True, "old_writers": False},
        ),
        "drain_legacy_readers": op({"new_traffic": True}, {"legacy_readers": False}),
        "drop_old_schema": op(
            {"new_traffic": True, "legacy_readers": False}, {"old_schema": False}
        ),
        "remove_capture": op({"old_schema": False}, {"capturing": False}),
        "remove_compatibility": op({"legacy_readers": False}, {"compatibility": False}),
        "rollback_expansion": op(
            {"audited": True, "healthy": False, "new_traffic": False},
            {
                "expanded": False,
                "copied": False,
                "capturing": False,
                "compatibility": False,
            },
        ),
    }
    invariants = [
        {
            "name": "no_concurrent_write_loss",
            "when": {"copied": True, "old_writers": True},
            "requires": {"capturing": True},
        },
        {
            "name": "reader_compatibility",
            "when": {"new_traffic": True, "legacy_readers": True},
            "requires": {"compatibility": True},
        },
    ]
    goals = {
        "validated": {"audited": True},
        "service": {"new_traffic": healthy, "old_schema": not healthy},
        "cleanup": {"capturing": False, "compatibility": False},
        "schema": {"expanded": healthy},
    }
    return {
        "initial": state,
        "operations": operations,
        "invariants": invariants,
        "goals": goals,
        "budget": 16,
    }


def release(bits: tuple[bool, bool, bool]) -> dict[str, Any]:
    spare, sticky, healthy = bits
    state = {
        "capacity": spare,
        "sticky_sessions": sticky,
        "healthy": healthy,
        "signed": False,
        "workers_paused": False,
        "green": False,
        "warm": False,
        "probed": False,
        "drained": False,
        "new_traffic": False,
        "blue": True,
    }
    operations = {
        "verify_artifact": op({}, {"signed": True}),
        "pause_batch_workers": op(
            {"capacity": False, "workers_paused": False},
            {"capacity": True, "workers_paused": True},
            2,
        ),
        "allocate_green": op({"capacity": True, "signed": True}, {"green": True}),
        "warm_green": op({"green": True}, {"warm": True}),
        "probe_health": op({"warm": True}, {"probed": True}),
        "drain_sticky_sessions": op({"probed": True, "blue": True}, {"drained": True}),
        "switch_traffic": op({"probed": True, "healthy": True}, {"new_traffic": True}),
        "retire_blue": op({"new_traffic": True}, {"blue": False}),
        "resume_workers_after_release": op({"blue": False}, {"workers_paused": False}),
        "discard_green": op(
            {"probed": True, "healthy": False, "new_traffic": False},
            {"green": False, "warm": False},
        ),
        "resume_workers_after_abort": op(
            {"green": False, "blue": True}, {"workers_paused": False}
        ),
    }
    invariants = [
        {
            "name": "session_continuity",
            "when": {"new_traffic": True, "sticky_sessions": True},
            "requires": {"drained": True},
        },
        {
            "name": "validated_traffic",
            "when": {"new_traffic": True},
            "requires": {"signed": True, "warm": True, "healthy": True},
        },
    ]
    goals = {
        "health_checked": {"probed": True},
        "service": {"new_traffic": healthy, "blue": not healthy},
        "resources": {"green": healthy, "workers_paused": False},
    }
    return {
        "initial": state,
        "operations": operations,
        "invariants": invariants,
        "goals": goals,
        "budget": 15,
    }


def ingestion(bits: tuple[bool, bool, bool]) -> dict[str, Any]:
    transactional, dedupe, replay = bits
    state = {
        "transactional": transactional,
        "deduplicating_sink": dedupe,
        "replayed": replay,
        "leased": False,
        "transaction": False,
        "applied": replay,
        "outbox": replay,
        "committed": replay,
        "delivered": replay,
        "receipt_checked": False,
        "acknowledged": False,
    }
    operations = {
        "claim": op({"leased": False}, {"leased": True}),
        "begin": op(
            {"transactional": True, "leased": True, "applied": False},
            {"transaction": True},
        ),
        "apply_transactional": op(
            {"transaction": True, "applied": False}, {"applied": True}
        ),
        "apply_direct": op(
            {"transactional": False, "leased": True, "applied": False},
            {"applied": True},
        ),
        "stage_outbox": op({"applied": True, "committed": False}, {"outbox": True}),
        "commit_transaction": op(
            {"transaction": True, "outbox": True},
            {"committed": True, "transaction": False},
        ),
        "persist_direct": op(
            {"transactional": False, "outbox": True}, {"committed": True}
        ),
        "deliver_idempotently": op(
            {"committed": True, "deduplicating_sink": True}, {"delivered": True}
        ),
        "check_delivery_receipt": op({"committed": True}, {"receipt_checked": True}),
        "deliver_once": op(
            {"committed": True, "receipt_checked": True, "delivered": False},
            {"delivered": True},
        ),
        "acknowledge": op(
            {"leased": True, "committed": True, "delivered": True},
            {"acknowledged": True},
        ),
        "release_lease": op({"acknowledged": True}, {"leased": False}),
    }
    goals = {
        "durability": {"applied": True, "committed": True, "outbox": True},
        "delivery": {"delivered": True, "acknowledged": True},
        "cleanup": {"leased": False, "transaction": False},
    }
    return {
        "initial": state,
        "operations": operations,
        "invariants": [],
        "goals": goals,
        "budget": 15,
    }


def compensation(bits: tuple[bool, bool, bool]) -> dict[str, Any]:
    prepaid, shipping, available = bits
    state = {
        "prepaid": prepaid,
        "shipping_available": shipping,
        "stock_available": available,
        "stock_checked": False,
        "reserved": False,
        "authorized": False,
        "captured": False,
        "shipment_attempted": False,
        "shipped": False,
        "settled": False,
        "rejected": False,
    }
    operations = {
        "check_stock": op({}, {"stock_checked": True}),
        "reject_unavailable": op(
            {"stock_checked": True, "stock_available": False}, {"rejected": True}
        ),
        "reserve": op(
            {"stock_checked": True, "stock_available": True}, {"reserved": True}
        ),
        "authorize": op({"reserved": True}, {"authorized": True}),
        "capture_prepaid": op(
            {"authorized": True, "prepaid": True}, {"captured": True}
        ),
        "ship": op(
            {"authorized": True}, {"shipment_attempted": True, "shipped": shipping}
        ),
        "capture_postpaid": op(
            {"authorized": True, "prepaid": False, "shipped": True}, {"captured": True}
        ),
        "settle": op(
            {"captured": True, "shipped": True},
            {"settled": True, "reserved": False, "authorized": False},
        ),
        "refund": op(
            {"shipment_attempted": True, "shipped": False, "captured": True},
            {"captured": False, "authorized": False},
        ),
        "void_authorization": op(
            {"shipment_attempted": True, "shipped": False, "captured": False},
            {"authorized": False},
        ),
        "release_reservation": op(
            {
                "shipment_attempted": True,
                "shipped": False,
                "captured": False,
                "authorized": False,
            },
            {"reserved": False, "rejected": True},
        ),
    }
    invariants = [
        {
            "name": "prepayment_before_shipping",
            "on": ["ship"],
            "when": {"shipment_attempted": True, "prepaid": True},
            "requires": {"captured": True},
        }
    ]
    fulfilled = shipping and available
    goals = {
        "inventory": {"stock_checked": True, "reserved": False},
        "payment": {"captured": fulfilled, "authorized": False},
        "resolution": {
            "settled": fulfilled,
            "rejected": not fulfilled,
            "shipped": fulfilled,
        },
    }
    return {
        "initial": state,
        "operations": operations,
        "invariants": invariants,
        "goals": goals,
        "budget": 13,
    }


FACTORIES = {
    "migration": migration,
    "release": release,
    "ingestion": ingestion,
    "compensation": compensation,
}
AXES = {
    "migration": ("old_writers", "legacy_readers", "healthy"),
    "release": ("capacity", "sticky_sessions", "healthy"),
    "ingestion": ("transactional", "deduplicating_sink", "replayed"),
    "compensation": ("prepaid", "shipping_available", "stock_available"),
}


def reference(family: str, api: Any) -> None:
    """An executable witness, not the oracle or a prescribed action sequence."""
    s = api.inspect()
    do = api.apply
    if family == "migration":
        do("expand")
        if s["old_writers"]:
            do("capture_changes")
        do("backfill")
        do("audit_backfill")
        if not s["healthy"]:
            do("rollback_expansion")
            return
        if s["legacy_readers"]:
            do("install_compatibility")
        do("cutover")
        if s["legacy_readers"]:
            do("drain_legacy_readers")
        do("drop_old_schema")
        if s["old_writers"]:
            do("remove_capture")
        if s["legacy_readers"]:
            do("remove_compatibility")
    elif family == "release":
        do("verify_artifact")
        if not s["capacity"]:
            do("pause_batch_workers")
        do("allocate_green")
        do("warm_green")
        do("probe_health")
        if not s["healthy"]:
            do("discard_green")
            if not s["capacity"]:
                do("resume_workers_after_abort")
            return
        if s["sticky_sessions"]:
            do("drain_sticky_sessions")
        do("switch_traffic")
        do("retire_blue")
        if not s["capacity"]:
            do("resume_workers_after_release")
    elif family == "ingestion":
        do("claim")
        if not s["replayed"]:
            if s["transactional"]:
                do("begin")
                do("apply_transactional")
            else:
                do("apply_direct")
            do("stage_outbox")
            do("commit_transaction" if s["transactional"] else "persist_direct")
            if s["deduplicating_sink"]:
                do("deliver_idempotently")
            else:
                do("check_delivery_receipt")
                do("deliver_once")
        do("acknowledge")
        do("release_lease")
    elif family == "compensation":
        do("check_stock")
        if not s["stock_available"]:
            do("reject_unavailable")
            return
        do("reserve")
        do("authorize")
        if s["prepaid"]:
            do("capture_prepaid")
        do("ship")
        if s["shipping_available"]:
            if not s["prepaid"]:
                do("capture_postpaid")
            do("settle")
        else:
            do("refund" if s["prepaid"] else "void_authorization")
            do("release_reservation")
    else:
        raise ValueError(family)
