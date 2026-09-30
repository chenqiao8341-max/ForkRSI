"""Export complete research records after authenticated final reporting."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--campaign", type=Path, default=Path("runs/forkrsi/campaign-v2")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("artifacts/forkrsi/pilot-v1")
    )
    parser.add_argument("--output", type=Path, default=Path("runs/forkrsi/delivery-v1"))
    args = parser.parse_args()
    root = Path.cwd().resolve()
    campaign = args.campaign.resolve()
    status = json.loads((campaign / "status.json").read_text())
    if status["state"] != "complete" or not status.get("final_outcomes_opened"):
        raise ValueError("final evaluation must be complete before delivery")
    for name in ("final-freeze.json", "final-result.json", "search-result.json"):
        if not (campaign / name).exists():
            raise ValueError("required actual campaign record missing: " + name)
    for name in (
        "summary.json",
        "final-cells.json",
        "search-records.json",
        "source-programs.json",
    ):
        if not (args.report / name).exists():
            raise ValueError("authenticated report export missing: " + name)
    if not Path("docs/forkrsi/report.md").exists():
        raise ValueError("the research report must be written before delivery")
    worker = json.loads((campaign / "worker.json").read_text())
    proc = Path(f"/proc/{worker['pid']}/cmdline")
    if proc.exists() and b"run_forkrsi_campaign.py" in proc.read_bytes():
        raise ValueError("wait for the campaign worker to finish closing its records")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("commit the final research artifacts before packaging")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    bundle = output / "forkrsi-history.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"], check=True)
    subprocess.run(["git", "bundle", "verify", str(bundle)], check=True)
    paths = {
        root / name.decode()
        for name in subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
        if name
    }
    for folder in ("runs/forkrsi", "artifacts/forkrsi"):
        paths.update(
            p for p in (root / folder).rglob("*") if p.is_file() or p.is_symlink()
        )
    paths = sorted(
        p
        for p in paths
        if output not in p.parents
        and p != output
        and not any(
            part in {".ruff_cache", ".mypy_cache", ".pytest_cache", "__pycache__"}
            for part in p.relative_to(root).parts
        )
    )
    entries = []
    for path in paths:
        relative = str(path.relative_to(root))
        if path.is_symlink():
            entries.append(
                {"path": relative, "type": "symlink", "target": str(path.readlink())}
            )
        else:
            entries.append(
                {
                    "path": relative,
                    "type": "file",
                    "bytes": path.stat().st_size,
                    "sha256": digest_file(path),
                }
            )
    archive = output / "forkrsi-records.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        for path in paths:
            stream.add(path, arcname=str(path.relative_to(root)), recursive=False)
    # A complete snapshot requires the source files to remain unchanged during export.
    for row in entries:
        path = root / row["path"]
        if row["type"] == "symlink":
            stable = path.is_symlink() and str(path.readlink()) == row["target"]
        else:
            stable = path.is_file() and digest_file(path) == row["sha256"]
        if not stable:
            raise RuntimeError("record changed during export: " + row["path"])
    seal = json.loads((campaign / "final-freeze.json").read_text())
    manifest = {
        "created_utc": datetime.now(UTC).isoformat(),
        "origin_root": str(root),
        "code_revision": revision,
        "frozen_final_code_revision": seal["value"]["inputs"]["code_revision"],
        "final_seal_sha256": seal["seal_sha256"],
        "archive": {
            "name": archive.name,
            "bytes": archive.stat().st_size,
            "sha256": digest_file(archive),
        },
        "git_bundle": {"name": bundle.name, "sha256": digest_file(bundle)},
        "files": entries,
        "model_weights_included": False,
        "model_reproduction": "Download the recorded ModelScope model and verify artifacts/forkrsi/model-files.json. Restore the original absolute root for historical log/checkpoint references.",
        "replay_policy": "Use the frozen final code revision for sealed final resume; later report-only commits do not authorize strategy changes or new selection.",
        "status": "complete stable snapshot",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "delivery": str(output),
                "files": len(entries),
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": manifest["archive"]["sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
