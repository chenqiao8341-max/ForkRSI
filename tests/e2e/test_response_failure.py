import json
from pathlib import Path

import httpx
import pytest

from forkmem.agent import run_task
from forkmem.llm import LLMClient


async def test_exhausted_response_verifies_existing_code_without_extra_request(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.json"
    task.write_text(
        json.dumps(
            {
                "task_id": "protocol_failure",
                "family": "toy",
                "split": "train",
                "description": "Return the number 42.",
                "features": {},
                "files": {"solution.py": "def answer():\n    return 0\n"},
                "verifier": "from solution import answer\nassert answer() == 42\n",
            }
        )
    )
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "invalid JSON"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 1,
                    "total_tokens": 11,
                },
            },
        )

    client = LLMClient(
        tmp_path / "llm.jsonl", request_budget=4, transport=httpx.MockTransport(respond)
    )
    try:
        row = await run_task(task, tmp_path / "episode", client)
    finally:
        await client.close()
    assert calls == 4
    assert row["success"] is False
    assert row["steps"] == 1
    assert row["decision_failure"]["error_type"] == "ModelResponseError"
    events = [
        json.loads(line)
        for line in (tmp_path / "episode/trajectory.jsonl").read_text().splitlines()
    ]
    assert len(events) == 1
    assert events[0]["action"]["tool"] == "finish"
    assert events[0]["action_origin"] == "protocol_failure_finalization"
    assert events[0]["outcome"]["success"] is False
    assert (tmp_path / "episode/graph_checkpoints.json").exists()


async def test_exhausted_source_proposal_is_retained_without_positive_memory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import yaml

    from forkmem import benchmark
    from forkmem.environment import digest

    original_git = benchmark.git
    monkeypatch.setattr(
        benchmark,
        "git",
        lambda root, *args: "" if args[0] == "status" else original_git(root, *args),
    )
    fixture = json.loads(Path("data/task_specs/config_smoke.json").read_text())
    fixture.update(task_id="source_failure", split="train")
    task = tmp_path / "source.json"
    task.write_text(json.dumps(fixture))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": fixture["task_id"],
                        "split": "train",
                        "path": str(task),
                        "sha256": digest(task.read_bytes()),
                    }
                ]
            }
        )
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "task_manifest": str(manifest),
                "training_seeds": [0],
                "evaluation_seeds": [],
                "modes": [],
                "max_steps": 1,
                "branches": 2,
                "concurrency": 1,
                "episode_concurrency": 1,
                "request_budget": 5,
            }
        )
    )
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = json.dumps(fixture["factual_action"]) if calls == 1 else "bad JSON"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
            },
        )

    monkeypatch.setattr(
        benchmark,
        "LLMClient",
        lambda path, **kwargs: LLMClient(
            path,
            transport=httpx.MockTransport(respond),
            **kwargs,
        ),
    )
    output = tmp_path / "source"
    await benchmark.benchmark(config, output)
    assert calls == 5
    assert json.loads((output / "status.json").read_text())["state"] == "complete"
    corpus = json.loads((output / "corpus.json").read_text())
    assert corpus["forks"] == []
    assert len(corpus["negative_lessons"]) == 1
    failures = list((output / "proposal-failures").glob("*.json"))
    assert len(failures) == 1
    assert json.loads(failures[0].read_text())["error_type"] == "ModelResponseError"
    (output / "status.json").write_text(
        json.dumps(
            {
                "state": "interrupted_or_failed",
                "completed_episodes": 1,
            }
        )
    )
    await benchmark.benchmark(config, output, resume=True)
    assert calls == 5  # Resume must not replenish the exhausted proposal slot.


async def test_cancelled_sibling_resumes_same_remaining_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import asyncio

    import yaml
    from langgraph.errors import NodeCancelledError

    from forkmem import benchmark
    from forkmem.environment import digest

    original_git = benchmark.git
    monkeypatch.setattr(
        benchmark,
        "git",
        lambda root, *args: "" if args[0] == "status" else original_git(root, *args),
    )
    fixture = json.loads(Path("data/task_specs/config_smoke.json").read_text())
    fixture.update(task_id="cancelled", split="train")
    task = tmp_path / "source.json"
    task.write_text(json.dumps(fixture))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "cancelled",
                        "split": "train",
                        "path": str(task),
                        "sha256": digest(task.read_bytes()),
                    }
                ]
            }
        )
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "task_manifest": str(manifest),
                "training_seeds": [0],
                "evaluation_seeds": [],
                "modes": [],
                "max_steps": 2,
                "branches": 2,
                "concurrency": 1,
                "episode_concurrency": 1,
                "request_budget": 10,
            }
        )
    )
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise asyncio.CancelledError()
        action = (
            {"tool": "read", "path": "README.md"} if calls == 1 else {"tool": "finish"}
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(action)}}],
            },
        )

    monkeypatch.setattr(
        benchmark,
        "LLMClient",
        lambda path, **kwargs: LLMClient(
            path,
            transport=httpx.MockTransport(respond),
            **kwargs,
        ),
    )
    output = tmp_path / "source"
    with pytest.raises(NodeCancelledError):
        await benchmark.benchmark(config, output)
    original = output / "training/seed_0/none/cancelled"
    prefix = (original / "trajectory.jsonl").read_bytes()
    assert len(prefix.splitlines()) == 1
    result = await benchmark.benchmark(config, output, resume=True)
    row = json.loads(result.read_text())
    assert calls == 3
    assert row["steps"] == 2
    assert row["native_resume_source"] == str(original)
    trace = [
        json.loads(s)
        for s in (Path(row["episode_dir"]) / "trajectory.jsonl")
        .read_text()
        .splitlines()
    ]
    assert [e["action"]["tool"] for e in trace] == ["read", "finish"]
    assert (original / "trajectory.jsonl").read_bytes() == prefix


async def test_cancelled_before_start_preserves_untouched_initial_repo(
    tmp_path: Path,
) -> None:
    from forkmem.agent import resume_episode
    from forkmem.environment import RepoEnvironment

    source = tmp_path / "source"
    source.mkdir()
    verifier = source / "verifier.py"
    verifier.write_text("from solution import answer\nassert answer() == 42\n")
    env = RepoEnvironment.create(
        source / "repo",
        {"solution.py": "def answer():\n    return 0\n"},
        verifier,
        source / "logs",
    )
    (source / "checkpoints.sqlite").touch()
    (source / "runner.json").write_text(
        json.dumps(
            {
                "task": "Return 42",
                "repo": str(env.root),
                "verifier": str(verifier),
                "editable": ["solution.py"],
                "max_steps": 2,
                "wall_seconds": 240,
                "seed": 0,
                "run_id": "agent",
                "episode_id": "cancelled-before-start",
                "memory_prompt": "",
            }
        )
    )
    client = LLMClient(
        tmp_path / "calls.jsonl",
        request_budget=1,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"tool":"finish"}',
                            }
                        }
                    ]
                },
            )
        ),
    )
    try:
        result = await resume_episode(source, tmp_path / "resumed", client)
    finally:
        await client.close()
    assert result["step"] == 1
    assert result["outcome"]["success"] is False
    assert json.loads((tmp_path / "resumed/resume.json").read_text())[
        "empty_initial_checkpoint"
    ]
    assert (source / "repo/solution.py").read_text() == "def answer():\n    return 0\n"
