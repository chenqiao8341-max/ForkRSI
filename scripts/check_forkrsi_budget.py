"""Conservative rental accounting; fail closed before new experiment batches."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

def check(path: Path, reserve_hours: float = 0.0) -> dict[str, object]:
    ledger = json.loads(path.read_text())
    baseline = datetime.fromisoformat(ledger["baseline_utc"])
    now = datetime.now(timezone.utc)
    elapsed = max(0.0, (now - baseline).total_seconds() / 3600)
    spent = ledger["conservative_accrued_baseline_cny"] + elapsed * ledger["hourly_cny"]
    projected = spent + reserve_hours * ledger["hourly_cny"]
    result = {"checked_utc": now.isoformat(), "estimated_spent_cny": round(spent, 4),
              "remaining_cny": round(ledger["limit_cny"] - spent, 4),
              "requested_reserve_hours": reserve_hours, "projected_total_cny": round(projected, 4),
              "allowed": projected < ledger["limit_cny"]}
    if reserve_hours < 0:
        raise ValueError("reserve must be nonnegative")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("artifacts/forkrsi/budget.json"))
    parser.add_argument("--reserve-hours", type=float, default=0)
    args = parser.parse_args()
    result = check(args.ledger, args.reserve_hours)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["allowed"] else 2)
