import json
from pathlib import Path

import httpx

from forkmem.agent import run_task
from forkmem.llm import LLMClient


async def test_checkpointed_agent_end_to_end(tmp_path: Path) -> None:
    actions = iter(
        [
            {"tool": "read", "path": "solution.py"},
            {
                "tool": "write",
                "path": "solution.py",
                "content": "def resolve_port(config, environ):\n    return environ.get('APP_PORT', config.get('port', 8080))\n",
            },
            {"tool": "test"},
        ]
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(next(actions))}}]}
        )

    client = LLMClient(tmp_path / "llm.jsonl", transport=httpx.MockTransport(respond))
    try:
        result = await run_task(
            Path("data/task_specs/config_smoke.json"), tmp_path / "episode", client
        )
    finally:
        await client.close()
    assert result["success"]
    trace = [
        json.loads(line)
        for line in (tmp_path / "episode/trajectory.jsonl").read_text().splitlines()
    ]
    assert len(trace) == 3
    assert trace[-1]["outcome"]["success"]
    checkpoints = json.loads((tmp_path / "episode/graph_checkpoints.json").read_text())
    assert len(checkpoints) >= 6
    assert any(c["next"] == ["execute"] for c in checkpoints)


async def test_native_checkpoint_fork_restores_files_and_pending_action(
    tmp_path: Path,
) -> None:
    from forkmem.agent import resume_episode

    actions = iter(
        [
            {"tool": "read", "path": "solution.py"},
            {
                "tool": "write",
                "path": "solution.py",
                "content": "def resolve_port(config,environ):\n    return environ.get('APP_PORT',config.get('port',8080))\n",
            },
            {"tool": "test"},
            {"tool": "test"},
        ]
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(next(actions))}}]}
        )

    client = LLMClient(tmp_path / "llm.jsonl", transport=httpx.MockTransport(respond))
    try:
        await run_task(
            Path("data/task_specs/config_smoke.json"),
            tmp_path / "original",
            client,
            max_steps=3,
        )
        history = json.loads((tmp_path / "original/graph_checkpoints.json").read_text())
        chosen = next(
            snapshot
            for snapshot in history
            if snapshot["next"] == ["execute"]
            and snapshot["values"]["action"]["tool"] == "write"
        )
        # Current source may diverge from the old graph snapshot. Resume must not reuse it.
        (tmp_path / "original/repo/solution.py").write_text(
            'raise RuntimeError("later unrelated edit")\n'
        )
        result = await resume_episode(
            tmp_path / "original",
            tmp_path / "resumed",
            client,
            chosen["config"]["configurable"]["checkpoint_id"],
        )
        assert result["outcome"]["success"] and result["step"] == 3
        assert (
            "later unrelated edit"
            in (tmp_path / "original/repo/solution.py").read_text()
        )
        trace = [
            json.loads(line)
            for line in (tmp_path / "resumed/trajectory.jsonl").read_text().splitlines()
        ]
        assert [event["action"]["tool"] for event in trace] == ["write", "test"]
        assert trace[0]["step"] == 1
    finally:
        await client.close()


async def test_policy_prompt_excludes_provenance_noise(tmp_path: Path) -> None:
    captured = []
    actions = iter([{"tool": "read", "path": "solution.py"}, {"tool": "finish"}])

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content)["messages"][-1]["content"])
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(next(actions))}}]}
        )

    client = LLMClient(tmp_path / "llm.jsonl", transport=httpx.MockTransport(respond))
    try:
        await run_task(
            Path("data/task_specs/config_smoke.json"),
            tmp_path / "episode",
            client,
            max_steps=2,
        )
    finally:
        await client.close()
    assert "tree_sha256" not in captured[-1]
    assert "checkpoint" not in captured[-1]
    assert str(tmp_path) not in captured[-1]
    assert "def resolve_port" in captured[-1]
