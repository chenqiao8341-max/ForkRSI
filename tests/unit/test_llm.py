import json
from pathlib import Path

import httpx
import pytest

from forkmem.llm import LLMClient
from forkmem.models import Action


async def test_json_repair_and_provenance(tmp_path: Path) -> None:
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "bad json" if calls == 1 else '{"tool":"finish"}'
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"total_tokens": 10},
            },
        )

    client = LLMClient(
        tmp_path / "calls.jsonl",
        transport=httpx.MockTransport(respond),
        request_budget=2,
    )
    try:
        assert (await client.generate("test", Action)).tool == "finish"
        with pytest.raises(RuntimeError, match="budget"):
            await client.generate("test", Action)
    finally:
        await client.close()
    logs = [
        json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()
    ]
    assert [e["status"] for e in logs] == ["parse_error", "ok"]
    assert logs[0]["request_id"] == logs[1]["request_id"]
    assert all(e["prompt_version"] and e["usage"]["total_tokens"] == 10 for e in logs)


async def test_no_retry_for_auth_error(tmp_path: Path) -> None:
    client = LLMClient(
        tmp_path / "calls.jsonl",
        transport=httpx.MockTransport(lambda request: httpx.Response(401)),
    )
    try:
        with pytest.raises(RuntimeError, match="401"):
            await client.generate("test", Action)
    finally:
        await client.close()
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 1


def test_proposal_wrapper_normalization_preserves_values() -> None:
    from forkmem.llm import parse_json
    from forkmem.models import Proposals

    content = "def f():\n    return 0\n"
    flat = {
        "proposals": [
            {
                "tool": "write",
                "path": "solution.py",
                "content": content,
                "mechanism": "zero",
                "predicted_outcome": "pass",
            }
        ]
    }
    parsed = parse_json(json.dumps(flat), Proposals)
    assert parsed.proposals[0].action.content == content
    nested = {
        "proposals": [
            {
                "action": {
                    "tool": "write",
                    "path": "solution.py",
                    "content": content,
                    "mechanism": "zero",
                    "predicted_outcome": "pass",
                }
            }
        ]
    }
    assert parse_json(json.dumps(nested), Proposals) == parsed
    nested["proposals"][0]["mechanism"] = "contradiction"
    with pytest.raises(ValueError, match="ambiguous"):
        parse_json(json.dumps(nested), Proposals)
    flat["proposals"][0]["evidence_status"] = "replay_verified"
    with pytest.raises(ValueError):
        parse_json(json.dumps(flat), Proposals)
