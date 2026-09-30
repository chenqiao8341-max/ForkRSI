import json
from pathlib import Path
from typing import cast

import httpx
import pytest

from forkmem.llm import LLMClient
from forkmem.models import Branch, DecisionFork
from forkmem.rsi import compiler as module
from forkmem.rsi.compiler import MemoryCompiler
from forkmem.rsi.ledger import StrategyLedger
from forkmem.rsi.models import INITIAL_COMPILER


async def test_extraction_seed_is_shared_and_render_only_change_reuses_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Synthetic source is limited to this cache/seed unit test, never a corpus.
    def packet(fork, positive, spec, mode):
        value = {
            "positive_program_id": "unit-source-only",
            "source_scope": {"k": "true"},
            "positive": {"code": "unit-test-only"},
        }
        if mode == "paired":
            value["factual_failure"] = {"code": "different input"}
        return value, {"unit-source-only"}

    monkeypatch.setattr(module, "source_packet", packet)
    ledger = StrategyLedger(tmp_path / "strategy.sqlite")
    c0 = ledger.add_version("C", INITIAL_COMPILER.model_dump())
    c1 = ledger.add_version(
        "C",
        INITIAL_COMPILER.model_copy(update={"rendering": "compact"}).model_dump(),
        parent_id=c0,
    )
    calls = []

    def reply(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        rules = {
            "rules": [
                {
                    "rule": "Check durable stages separately.",
                    "applicability": "Only declared source context",
                    "obligations": ["durability"],
                    "evidence_ids": ["unit-source-only"],
                    "caveat": "Target applicability remains unverified.",
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(rules)}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    client = LLMClient(
        tmp_path / "llm.jsonl", transport=httpx.MockTransport(reply), request_budget=2
    )
    compiler = MemoryCompiler(ledger, client, tmp_path / "cache", len)
    try:
        a = await compiler.compile_source(
            c0, cast(DecisionFork, None), cast(Branch, None), "success_only"
        )
        b = await compiler.compile_source(
            c1, cast(DecisionFork, None), cast(Branch, None), "success_only"
        )
        assert len(calls) == 1
        assert a["rules"] == b["rules"] and a["extraction_seed"] == b["extraction_seed"]
        assert a["compiler_id"] != b["compiler_id"]
        c = await compiler.compile_source(
            c1, cast(DecisionFork, None), cast(Branch, None), "paired"
        )
        assert (
            len(calls) == 2
            and calls[0]["seed"] == calls[1]["seed"] == c["extraction_seed"]
        )
        assert a["prompt_sha256"] != c["prompt_sha256"]
    finally:
        await client.close()
