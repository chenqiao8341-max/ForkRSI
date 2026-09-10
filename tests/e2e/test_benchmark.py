import json
from pathlib import Path

import httpx
import yaml

import forkmem.benchmark as module
from forkmem.environment import digest
from forkmem.llm import LLMClient


async def test_benchmark_keeps_exposure_and_conditions_separate(
    tmp_path: Path, monkeypatch
) -> None:
    original_git = module.git
    monkeypatch.setattr(
        module,
        "git",
        lambda root, *args: "" if args[0] == "status" else original_git(root, *args),
    )
    fixture = json.loads(Path("data/task_specs/config_smoke.json").read_text())
    entries = []
    for split in ["train", "held_out", "near_miss"]:
        task = {**fixture, "task_id": split, "split": split}
        path = tmp_path / (split + ".json")
        path.write_text(json.dumps(task))
        entries.append(
            {
                "task_id": split,
                "split": split,
                "path": str(path),
                "sha256": digest(path.read_bytes()),
            }
        )
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"tasks": entries}))
    config = {
        "task_manifest": str(manifest),
        "training_seeds": [0],
        "evaluation_seeds": [1],
        "modes": ["none", "negative", "imagined", "paired", "verified"],
        "max_steps": 3,
        "branches": 2,
        "concurrency": 1,
        "episode_concurrency": 1,
        "request_budget": 50,
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config))
    wrong = fixture["factual_action"]
    correct = {
        "tool": "write",
        "path": "solution.py",
        "content": "def resolve_port(config,environ):\n    return environ.get('APP_PORT',config.get('port',8080))\n",
    }
    other = {
        **correct,
        "content": "def resolve_port(config,environ):\n    if 'APP_PORT' in environ: return environ['APP_PORT']\n    return config.get('port',8080)\n",
    }
    proposals = {
        "proposals": [
            {
                "action": a,
                "mechanism": "presence preserves zero",
                "predicted_outcome": "pass",
            }
            for a in [correct, other]
        ]
    }
    actions = [
        {"tool": "read", "path": "README.md"},
        wrong,
        {"tool": "finish"},
        proposals,
        {"tool": "test"},
        {"tool": "test"},
    ]
    for _ in range(len(config["modes"]) * 2):
        actions.extend(
            [{"tool": "read", "path": "README.md"}, correct, {"tool": "test"}]
        )
    responses = iter(actions)

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(next(responses))}}]},
        )

    monkeypatch.setattr(
        module,
        "LLMClient",
        lambda path, **kwargs: LLMClient(
            path, transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    output = tmp_path / "run"
    result = await module.benchmark(config_path, output)
    rows = [json.loads(line) for line in result.read_text().splitlines()]
    assert len(rows) == 11 and not rows[0]["success"]
    assert all(row["success"] for row in rows[1:])
    assert len({row["episode_id"] for row in rows}) == 11
    negative = json.loads(
        (output / "evaluation/seed_1/negative/held_out/retrieval.json").read_text()
    )["prompt"]
    assert "Observed" not in negative or "alternative" not in negative
    assert "observed_failed_action" in negative and "prediction" not in negative
    imagined = json.loads(
        (output / "evaluation/seed_1/imagined/held_out/retrieval.json").read_text()
    )["prompt"]
    assert "UNVERIFIED HYPOTHESIS" in imagined and "Execution-verified" not in imagined
    assert json.loads((output / "status.json").read_text())["state"] == "complete"

    from forkmem.reporting import build_report

    report = build_report(output, tmp_path / "report.md", tmp_path / "artifacts")
    assert report.exists()
    assert (tmp_path / "artifacts/figures/success_rates.svg").exists()
    assert (tmp_path / "artifacts/figures/reference_regret.png").exists()
    assert (tmp_path / "artifacts/tables/main_results.csv").exists()

    # Simulate an orchestration interruption after completed cells; no cell reruns.
    recorded = result.read_bytes()
    (output / "status.json").write_text(
        json.dumps({"state": "interrupted_or_failed", "completed_episodes": len(rows)})
    )
    resumed = await module.benchmark(config_path, output, resume=True)
    assert resumed.read_bytes() == recorded
    assert json.loads((output / "manifest.json").read_text())["resume_history"]
