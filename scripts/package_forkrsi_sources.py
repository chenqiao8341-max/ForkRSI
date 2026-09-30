"""Freeze all completed source batches without rewriting their executions."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from forkmem.environment import digest, git
from forkmem.memory import SQLiteForkStore
from forkmem.models import DecisionFork, NegativeLesson
from forkmem.rsi.compiler import observation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batches",
        nargs="+",
        type=Path,
        default=[
            Path("runs/forkrsi/source-v1"),
            Path("runs/forkrsi/source-v2"),
            Path("runs/forkrsi/source-v3"),
        ],
    )
    parser.add_argument(
        "--output", type=Path, default=Path("runs/forkrsi/source-package-v1")
    )
    args = parser.parse_args()
    inputs = []
    episode_lines = []
    forks = []
    negatives = []
    seen = set()
    for run in args.batches:
        run = run.resolve()
        status = json.loads((run / "status.json").read_text())
        if status["state"] not in {"complete", "interrupted_or_failed"}:
            raise ValueError("source batch is still live: " + str(run))
        corpus_path = run / "corpus.json"
        if not corpus_path.exists():
            store = SQLiteForkStore(run / "memory.sqlite")
            try:
                corpus = {
                    "forks": [f.model_dump(mode="json") for f in store.all()],
                    "negative_lessons": [
                        n.model_dump(mode="json") for n in store.negatives()
                    ],
                }
            finally:
                store.close()
            corpus_path = run / "corpus-snapshot.json"
            corpus_path.write_text(json.dumps(corpus, indent=2) + "\n")
        corpus = json.loads(corpus_path.read_text())
        episode_lines.extend((run / "results.jsonl").read_text().splitlines())
        inputs.append(
            {
                "path": str(run),
                "status": status,
                "corpus_path": str(corpus_path),
                "corpus_sha256": digest(corpus_path.read_bytes()),
                "manifest_sha256": digest((run / "manifest.json").read_bytes()),
                "policy_note": "source-v1 original public prompt; later source-v2 common calibrated prompt",
            }
        )
        for obj in corpus["forks"]:
            fork = DecisionFork.model_validate(obj)
            if fork.fork_id in seen:
                raise ValueError("duplicate original fork ID")
            seen.add(fork.fork_id)
            for branch in [fork.factual, *fork.alternatives]:
                observation(branch)
            forks.append(fork)
        for obj in corpus["negative_lessons"]:
            lesson = NegativeLesson.model_validate(obj)
            # Preserve original lesson text/outcome; namespace only its store key.
            negatives.append(
                lesson.model_copy(
                    update={"lesson_id": run.name + "::" + lesson.lesson_id}
                )
            )
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "results.jsonl").write_text("\n".join(episode_lines) + "\n")
    store = SQLiteForkStore(args.output / "memory.sqlite")
    try:
        for fork in forks:
            store.put(fork)
        for lesson in negatives:
            store.put_negative(lesson)
        corpus = {
            "forks": [f.model_dump(mode="json") for f in store.all()],
            "negative_lessons": [n.model_dump(mode="json") for n in store.negatives()],
        }
        (args.output / "corpus.json").write_text(json.dumps(corpus, indent=2) + "\n")
    finally:
        store.close()
    (args.output / "manifest.json").write_text(
        json.dumps(
            {
                "design": "all terminal pre-search source batches; only fully completed forks; partial trial state preserved",
                "inputs": inputs,
                "revision": git(Path.cwd(), "rev-parse", "HEAD"),
                "frozen_unix": time.time(),
                "negative_key_policy": "batch namespace; original full outcomes unchanged",
            },
            indent=2,
        )
        + "\n"
    )
    (args.output / "status.json").write_text(
        json.dumps(
            {
                "state": "complete",
                "forks": len(forks),
                "negative_lessons": len(negatives),
                "origin": "immutable package of real executed batches; not new executions",
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "package": str(args.output),
                "forks": len(forks),
                "negative_lessons": len(negatives),
            }
        )
    )


if __name__ == "__main__":
    main()
