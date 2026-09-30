"""Verify the downloaded ModelScope snapshot against the recorded file hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def verify(model: Path, manifest: Path) -> dict[str, Any]:
    root = model.resolve()
    expected = json.loads(manifest.read_text())
    names = [row["name"] for row in expected["files"]]
    if not names or len(names) != len(set(names)):
        raise ValueError("model manifest must contain distinct recorded files")
    checks = []
    for row in expected["files"]:
        path = (root / row["name"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("model manifest contains a path outside its snapshot")
        measured = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                while chunk := handle.read(8 * 1024 * 1024):
                    measured.update(chunk)
            size = path.stat().st_size
            actual_sha = measured.hexdigest()
            ok = size == row["bytes"] and actual_sha == row["sha256"]
            checks.append(
                {
                    **row,
                    "actual_bytes": size,
                    "actual_sha256": actual_sha,
                    "matches": ok,
                }
            )
        except OSError as exc:
            checks.append({**row, "matches": False, "error": str(exc)})
    return {
        "checked_utc": datetime.now(UTC).isoformat(),
        "model": expected["model"],
        "origin": expected["origin"],
        "model_dir": str(root),
        "manifest": str(manifest.resolve()),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "files": checks,
        "all_recorded_files_match": all(row["matches"] for row in checks),
        "expected_bytes": sum(row["bytes"] for row in checks),
        "scope": "all files listed in this manifest; the research manifest records 14 non-hidden snapshot files including both weight shards; resident model freeze is recorded separately",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-dir", type=Path, default=Path("/root/autodl-tmp/models/Qwen3.5-4B")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("artifacts/forkrsi/model-files.json")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/forkrsi/model-verification-latest.json"),
    )
    args = parser.parse_args()
    result = verify(args.model_dir, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "all_recorded_files_match": result["all_recorded_files_match"],
                "file_count": len(result["files"]),
                "expected_bytes": result["expected_bytes"],
                "output": str(args.output),
            }
        )
    )
    raise SystemExit(0 if result["all_recorded_files_match"] else 2)


if __name__ == "__main__":
    main()
