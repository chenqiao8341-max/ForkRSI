import json
from pathlib import Path

import httpx

from forkmem.llm import LLMClient
from forkmem.rsi.improver import propose_compiler
from forkmem.rsi.ledger import StrategyLedger
from forkmem.rsi.models import INITIAL_COMPILER, INITIAL_IMPROVER


async def test_evolved_improver_is_used_in_next_actual_request(tmp_path: Path) -> None:
    ledger = StrategyLedger(tmp_path / "strategies.sqlite")
    c0 = ledger.add_version("C", INITIAL_COMPILER.model_dump())
    i0 = ledger.add_version("I", INITIAL_IMPROVER.model_dump())
    method = INITIAL_IMPROVER.model_copy(
        update={
            "diagnosis_prompt": "Explicitly inspect post-cleanup omissions from measured failed episodes.",
            "proposal_prompt": "Revise applicability using observed cleanup failures and preserve source evidence.",
        }
    )
    i1 = ledger.add_version(
        "I",
        method.model_dump(),
        parent_id=i0,
        input_evidence=["dev-failure"],
        provenance={"generated_by_i": i0, "origin": "synthetic unit test"},
    )
    prompts = []

    def reply(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompts.append(body["messages"][1]["content"])
        proposal = {
            "compiler": INITIAL_COMPILER.model_copy(
                update={"rendering": "compact"}
            ).model_dump(),
            "diagnosis": "Measured injected memory is verbose.",
            "rationale": "Use compact conditional rules.",
            "evidence_ids": ["dev-failure"],
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(proposal)}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    client = LLMClient(
        tmp_path / "llm.jsonl", transport=httpx.MockTransport(reply), request_budget=1
    )
    try:
        c1, record = await propose_compiler(
            ledger,
            client,
            i1,
            c0,
            {"success": False},
            ["dev-failure"],
            seed=23,
            evidence_mode="paired",
        )
    finally:
        await client.close()
    assert method.diagnosis_prompt in prompts[0]
    assert method.proposal_prompt in prompts[0]
    assert ledger.get(c1)["provenance"]["generated_by_i"] == i1
    assert record["actual_changes"]["rendering"] == {
        "before": "structured",
        "after": "compact",
    }
