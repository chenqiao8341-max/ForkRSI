import json
from pathlib import Path

import httpx
import pytest
import yaml

from forkmem.environment import digest
from forkmem.llm import LLMClient
from forkmem.workflows import benchmark as module
from forkmem.workflows.evaluation import load_transfer, summarize_transfer


async def test_exact_input_aliases_are_one_real_episode(tmp_path, monkeypatch):
    fixture = json.loads(
        Path("data/v2/frozen1/resumable_compensation_held_out_001.json").read_text()
    )
    path = tmp_path / "task.json"
    path.write_text(json.dumps(fixture))
    dataset = {
        "tasks": [
            {
                "task_id": fixture["task_id"],
                "family": fixture["family"],
                "split": "held_out",
                "path": str(path),
                "sha256": digest(path.read_bytes()),
                "semantic_context": "compensation-001",
            }
        ]
    }
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps(dataset))
    source = tmp_path / "source"
    source.mkdir()
    (source / "corpus.json").write_text(
        json.dumps({"forks": [], "negative_lessons": []})
    )
    monkeypatch.setattr(
        module,
        "load_complete",
        lambda _: ({"dataset": dataset, "revision": "source"}, []),
    )
    real_git = module.git
    monkeypatch.setattr(
        module,
        "git",
        lambda root, *args: "" if args[0] == "status" else real_git(root, *args),
    )
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        action = {
            "tool": "write",
            "path": "solution.py",
            "content": fixture["reference_solution"],
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(action)}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
            },
        )

    first_client = True

    def make_client(path, **kwargs):
        nonlocal first_client
        client = LLMClient(path, **kwargs, transport=httpx.MockTransport(respond))
        if first_client:
            client.remaining = 0
            first_client = False
        return client

    monkeypatch.setattr(module, "LLMClient", make_client)

    class FakeTokenizer:
        def __init__(self, *args):
            self.ledger = {}
            self.client = httpx.Client(trust_env=False)

        def count(self, body):
            value = len(body)
            self.ledger[digest(body.encode())] = {"tokens": value, "characters": value}
            return value

    monkeypatch.setattr(module, "MemoryTokenizer", FakeTokenizer)
    config = {
        "task_manifest": str(manifest),
        "evaluation_seeds": [101],
        "action_budgets": [1, 2],
        "modes": ["none", "flat_verified", "fork_verified", "legacy_verified"],
        "memory_token_cap": 6000,
        "memory_records": 2,
        "concurrency": 2,
        "episode_concurrency": 2,
        "request_budget": 20,
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config))
    output = tmp_path / "output"
    with pytest.raises(RuntimeError, match="budget exhausted"):
        await module.transfer(source, config_path, output)
    assert (
        json.loads((output / "status.json").read_text())["state"]
        == "interrupted_or_failed"
    )
    result = await module.transfer(source, config_path, output, resume=True)
    rows = [json.loads(x) for x in result.read_text().splitlines()]
    assert len(rows) == 8
    assert len({r["episode_id"] for r in rows}) == 2
    assert sum(bool(r.get("reuse_of")) for r in rows) == 6
    assert all(r["success"] for r in rows)
    assert len(requests) == 3
    assert json.loads((output / "status.json").read_text())["state"] == "complete"

    _, checked, _ = load_transfer(output)
    assert len(checked) == 8
    assert all(row["structured_available"] for row in checked)
    summary = summarize_transfer(output)
    assert summary["actual_model_tokens"] == 60
    assert sum(r["incremental_model_tokens"] for r in summary["table"]) == 60
    assert all(
        r["difference_vs_flat_verified"] == (0.0, 0.0, 0.0) for r in summary["table"]
    )
    original_rows = result.read_text()
    swapped = [json.loads(line) for line in original_rows.splitlines()]
    for row in swapped:
        row["action_budget"] = 3 - row["action_budget"]
    result.write_text("\n".join(json.dumps(row) for row in swapped) + "\n")
    with pytest.raises(ValueError, match="episode settings"):
        load_transfer(output)
    result.write_text(original_rows)
    memories = json.loads((output / "prepared_memories.json").read_text())
    memories[fixture["task_id"]]["legacy_verified"][0] = "different body"
    (output / "prepared_memories.json").write_text(json.dumps(memories))
    with pytest.raises(ValueError, match="rendered memory"):
        load_transfer(output)
