"""Actual consumption of versioned improvement methods in new proposals."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from forkmem.llm import LLMClient
from forkmem.models import StrictModel
from forkmem.rsi.ledger import StrategyLedger, canonical
from forkmem.rsi.models import CompilerSpec, ImproverSpec


class CompilerProposal(StrictModel):
    compiler: CompilerSpec
    diagnosis: str = Field(min_length=1, max_length=3000)
    rationale: str = Field(min_length=1, max_length=3000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class ImproverProposal(StrictModel):
    improver: ImproverSpec
    diagnosis: str = Field(min_length=1, max_length=3000)
    rationale: str = Field(min_length=1, max_length=3000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


FIXED = (
    "Do not change model weights, verifier/authenticity checks, fixed candidate pools, "
    "task splits, seeds, action budget or proposal budget. Propose only the requested "
    "typed object. Token cap may not exceed 1500. Reference only supplied evidence IDs. "
    "Treat partial improvements and plausible explanations as unverified hypotheses."
)


async def propose_compiler(
    ledger: StrategyLedger,
    client: LLMClient,
    improver_id: str,
    compiler_id: str,
    feedback: dict[str, Any],
    evidence_ids: list[str],
    *,
    seed: int,
    evidence_mode: str,
) -> tuple[str, dict[str, Any]]:
    iv, cv = ledger.get(improver_id), ledger.get(compiler_id)
    if iv["kind"] != "I" or cv["kind"] != "C":
        raise ValueError("proposal requires I and C versions")
    method = ImproverSpec.model_validate(iv["content"])
    prompt = method.diagnosis_prompt + "\n" + method.proposal_prompt + "\n" + FIXED
    prompt += "\nCurrent C: " + canonical(cv["content"])
    prompt += "\nActual development feedback: " + canonical(feedback)
    prompt += "\nAllowed evidence IDs: " + canonical(evidence_ids)
    proposal = await client.generate(
        prompt,
        CompilerProposal,
        max_tokens=2200,
        seed=seed,
        temperature=0.7,
        run_id="evolve-C-" + evidence_mode,
        episode_id=improver_id,
        branch_id=compiler_id,
    )
    if not set(proposal.evidence_ids) <= set(evidence_ids):
        raise ValueError("improver fabricated evidence references")
    content = proposal.compiler.model_dump(mode="json")
    changes = {
        k: {"before": cv["content"][k], "after": v}
        for k, v in content.items()
        if cv["content"][k] != v
    }
    identifier = ledger.add_version(
        "C",
        content,
        parent_id=compiler_id,
        input_evidence=proposal.evidence_ids,
        provenance={
            "generated_by_i": improver_id,
            "seed": seed,
            "evidence_mode": evidence_mode,
            "proposal": proposal.model_dump(mode="json"),
            "actual_changes": changes,
        },
    )
    return identifier, {
        "improver_id": improver_id,
        "parent_c": compiler_id,
        "candidate_c": identifier,
        "actual_changes": changes,
        "proposal": proposal.model_dump(mode="json"),
    }


async def propose_improver(
    ledger: StrategyLedger,
    client: LLMClient,
    improver_id: str,
    history: dict[str, Any],
    evidence_ids: list[str],
    *,
    seed: int,
) -> tuple[str, dict[str, Any]]:
    iv = ledger.get(improver_id)
    if iv["kind"] != "I":
        raise ValueError("improver_id must identify I")
    method = ImproverSpec.model_validate(iv["content"])
    prompt = method.diagnosis_prompt + "\n" + method.proposal_prompt + "\n" + FIXED
    prompt += (
        "\nThe object to improve is now I, the method that diagnoses and proposes compiler "
        "modifications. Use the actual candidate comparison history, including rejected "
        "and regressing candidates, to revise both diagnostic and proposal methods. "
        "The new I will be used for subsequent C generation and an independent reset comparison."
    )
    prompt += "\nCurrent I: " + canonical(iv["content"])
    prompt += "\nComparison history: " + canonical(history)
    prompt += "\nAllowed evidence IDs: " + canonical(evidence_ids)
    proposal = await client.generate(
        prompt,
        ImproverProposal,
        max_tokens=2200,
        seed=seed,
        temperature=0.7,
        run_id="evolve-I",
        episode_id=improver_id,
    )
    if not set(proposal.evidence_ids) <= set(evidence_ids):
        raise ValueError("meta-improver fabricated evidence references")
    content = proposal.improver.model_dump(mode="json")
    changes = {
        k: {"before": iv["content"][k], "after": v}
        for k, v in content.items()
        if iv["content"][k] != v
    }
    identifier = ledger.add_version(
        "I",
        content,
        parent_id=improver_id,
        input_evidence=proposal.evidence_ids,
        provenance={
            "generated_by_i": improver_id,
            "seed": seed,
            "proposal": proposal.model_dump(mode="json"),
            "actual_changes": changes,
        },
    )
    return identifier, {
        "parent_i": improver_id,
        "candidate_i": identifier,
        "actual_changes": changes,
        "proposal": proposal.model_dump(mode="json"),
    }
