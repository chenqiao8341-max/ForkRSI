"""Append-only strategy lineage, separate from task-code DecisionFork evidence."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()

class StrategyLedger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connection()) as db, db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS versions(
                version_id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('C','I')),
                parent_id TEXT REFERENCES versions(version_id), content_json TEXT NOT NULL,
                content_sha256 TEXT NOT NULL, evidence_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL, created_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS comparisons(
                comparison_id TEXT PRIMARY KEY, parent_c TEXT NOT NULL REFERENCES versions(version_id),
                candidate_c TEXT NOT NULL REFERENCES versions(version_id),
                improver_i TEXT NOT NULL REFERENCES versions(version_id),
                protocol_sha256 TEXT NOT NULL, results_json TEXT NOT NULL,
                costs_json TEXT NOT NULL, created_utc TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS versions_no_update BEFORE UPDATE ON versions
            BEGIN SELECT RAISE(ABORT, 'strategy versions are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS versions_no_delete BEFORE DELETE ON versions
            BEGIN SELECT RAISE(ABORT, 'strategy versions are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS comparisons_no_update BEFORE UPDATE ON comparisons
            BEGIN SELECT RAISE(ABORT, 'strategy comparisons are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS comparisons_no_delete BEFORE DELETE ON comparisons
            BEGIN SELECT RAISE(ABORT, 'strategy comparisons are append-only'); END;
            """)

    def connection(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        return db

    def get(self, version_id: str) -> dict[str, Any]:
        with closing(self.connection()) as db:
            row = db.execute("SELECT * FROM versions WHERE version_id=?", (version_id,)).fetchone()
        if row is None:
            raise ValueError("unknown strategy version: " + version_id)
        return {**dict(row), "content": json.loads(row["content_json"]),
                "input_evidence": json.loads(row["evidence_json"]),
                "provenance": json.loads(row["provenance_json"])}

    def add_version(self, kind: Literal["C", "I"], content: dict[str, Any], *,
                    parent_id: str | None = None, input_evidence: list[str] | None = None,
                    provenance: dict[str, Any] | None = None) -> str:
        from forkmem.rsi.models import CompilerSpec, ImproverSpec
        validated = (CompilerSpec if kind == "C" else ImproverSpec).model_validate(content)
        body = validated.model_dump(mode="json")
        if kind not in {"C", "I"}:
            raise ValueError("strategy kind must be C or I")
        if parent_id is not None and self.get(parent_id)["kind"] != kind:
            raise ValueError("parent must have the same strategy kind")
        evidence = list(input_evidence or [])
        provenance = dict(provenance or {})
        identity = {"kind": kind, "parent": parent_id, "content": body,
                    "evidence": evidence, "provenance": provenance}
        version_id = kind + "-" + sha(identity)[:24]
        with closing(self.connection()) as db, db:
            db.execute("INSERT OR IGNORE INTO versions VALUES(?,?,?,?,?,?,?,?)",
                       (version_id, kind, parent_id, canonical(body), sha(body),
                        canonical(evidence), canonical(provenance), datetime.now(timezone.utc).isoformat()))
        return version_id

    def add_comparison(self, parent_c: str, candidate_c: str, improver_i: str, *,
                       protocol: dict[str, Any], results: dict[str, Any],
                       costs: dict[str, Any]) -> str:
        for version_id, expected in [(parent_c, "C"), (candidate_c, "C"), (improver_i, "I")]:
            if self.get(version_id)["kind"] != expected:
                raise ValueError("comparison strategy kind mismatch")
        if self.get(candidate_c)["parent_id"] != parent_c:
            raise ValueError("candidate must descend from the recorded compiler parent")
        if not protocol or not results:
            raise ValueError("a comparison requires protocol and actual results")
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if name not in costs or not isinstance(costs[name], int) or isinstance(costs[name], bool) or costs[name] < 0:
                raise ValueError("missing or negative token cost: " + name)
        if costs["total_tokens"] != costs["prompt_tokens"] + costs["completion_tokens"]:
            raise ValueError("total token cost is inconsistent")
        value = {"parent_c": parent_c, "candidate_c": candidate_c, "improver_i": improver_i,
                 "protocol": protocol, "results": results, "costs": costs}
        identifier = "cmp-" + sha(value)[:24]
        with closing(self.connection()) as db, db:
            db.execute("INSERT OR IGNORE INTO comparisons VALUES(?,?,?,?,?,?,?,?)",
                       (identifier, parent_c, candidate_c, improver_i, sha(protocol),
                        canonical(results), canonical(costs), datetime.now(timezone.utc).isoformat()))
        return identifier
