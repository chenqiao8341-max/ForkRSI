import json
from pathlib import Path

import httpx

from forkmem.agent import run_task
from forkmem.counterfactual import fork_episode
from forkmem.llm import LLMClient
from forkmem.models import DecisionFork, EvidenceStatus


async def test_failed_episode_common_prefix_and_branch_budget(tmp_path: Path) -> None:
    wrong = "def resolve_port(config, environ):\n    return environ.get('APP_PORT') or config.get('port', 8080)\n"
    correct = "def resolve_port(config, environ):\n    return environ.get('APP_PORT', config.get('port', 8080))\n"
    proposal = {
        "action": {"tool": "write", "path": "solution.py", "content": correct},
        "mechanism": "zero is present",
        "predicted_outcome": "passes",
    }
    bad_proposal = {
        "action": {
            "tool": "write",
            "path": "solution.py",
            "content": "def resolve_port(config, environ):\n    return 8080\n",
        },
        "mechanism": "default may satisfy contract",
        "predicted_outcome": "passes",
    }
    responses = iter(
        [
            {"tool": "read", "path": "README.md"},
            {"tool": "write", "path": "solution.py", "content": wrong},
            {"tool": "finish"},
            {"proposals": [proposal, bad_proposal]},
            {"tool": "test"},
            {"tool": "test"},
        ]
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(next(responses))}}]},
        )

    client = LLMClient(tmp_path / "llm.jsonl", transport=httpx.MockTransport(respond))
    try:
        failed = await run_task(
            Path("data/task_specs/config_smoke.json"),
            tmp_path / "episode",
            client,
            max_steps=3,
        )
        assert not failed["success"]
        destination = await fork_episode(
            tmp_path / "episode", tmp_path / "fork", client, branches=2
        )
    finally:
        await client.close()
    fork = DecisionFork.model_validate_json(destination.read_text())
    assert [b.evidence_status for b in fork.alternatives] == [
        EvidenceStatus.REPLAY_VERIFIED,
        EvidenceStatus.FALSIFIED,
    ]
    for i in range(2):
        rollout = json.loads((tmp_path / f"fork/rollout_{i}/result.json").read_text())
        assert rollout["step"] == 3
        assert rollout["messages"][0]["action"] == {
            "tool": "read",
            "path": "README.md",
            "content": "",
            "thought_summary": "",
        }
        assert rollout["messages"][1]["checkpoint"] == fork.state.checkpoint
    assert (
        len(
            {
                o.checkpoint
                for b in [fork.factual, *fork.alternatives]
                for o in b.outcomes
            }
        )
        == 1
    )
