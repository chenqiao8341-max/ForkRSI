"""Measure exact memory-body token counts using the discovered local tokenizer API."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from forkmem.environment import digest


def measure(run: Path) -> Path:
    base = os.getenv("FORKMEM_LLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
    endpoint = base.removesuffix("/v1") + "/tokenize"
    model = os.getenv("FORKMEM_LLM_MODEL", "Qwen3.8-27B")
    bodies = {}
    rows = [
        json.loads(line) for line in (run / "results.jsonl").read_text().splitlines()
    ]
    if json.loads((run / "status.json").read_text())["state"] != "complete":
        raise ValueError("token ledger requires a complete experiment")
    for row in rows:
        text = json.loads((Path(row["episode_dir"]) / "retrieval.json").read_text())[
            "prompt"
        ]
        bodies[digest(text.encode())] = text
    corpus = json.loads((run / "corpus.json").read_text())
    stored = json.dumps(corpus, ensure_ascii=False, sort_keys=True)
    corpus_hash = digest(stored.encode())
    bodies[corpus_hash] = stored
    items = {}
    with httpx.Client(timeout=30, trust_env=False) as client:
        for key, text in bodies.items():
            if not text:
                count = 0
            else:
                response = client.post(
                    endpoint,
                    headers={
                        "Authorization": "Bearer "
                        + os.getenv("FORKMEM_LLM_API_KEY", "EMPTY")
                    },
                    json={"model": model, "prompt": text, "add_special_tokens": False},
                )
                response.raise_for_status()
                count = response.json()["count"]
                if not isinstance(count, int) or count < 0:
                    raise ValueError("invalid tokenizer response")
            items[key] = {"tokens": count, "characters": len(text)}
    url = urlsplit(endpoint)
    ledger = {
        "model": model,
        "endpoint": f"{url.scheme}://{url.hostname}:{url.port}{url.path}",
        "add_special_tokens": False,
        "definition": "plain memory body, excluding chat-template role overhead",
        "corpus_body_sha256": corpus_hash,
        "items": items,
    }
    output = run / "memory_tokens.json"
    output.write_text(json.dumps(ledger, indent=2) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    print(measure(parser.parse_args().runs))
