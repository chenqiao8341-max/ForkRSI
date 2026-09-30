"""Versioned compiler/improver objects; they cannot redefine verification."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from forkmem.models import StrictModel


class CompilerSpec(StrictModel):
    extraction_prompt: str = Field(min_length=20, max_length=6000)
    include_factual_failures: bool = True
    include_falsified_alternatives: bool = True
    applicability: Literal["source_scope", "public_overlap", "obligation_match"] = (
        "public_overlap"
    )
    rendering: Literal["structured", "compact"] = "structured"
    memory_token_cap: int = Field(default=1500, ge=256, le=1500)


class ImproverSpec(StrictModel):
    diagnosis_prompt: str = Field(min_length=20, max_length=6000)
    proposal_prompt: str = Field(min_length=20, max_length=6000)


class MemoryRule(StrictModel):
    rule: str = Field(min_length=1, max_length=2000)
    applicability: str = Field(min_length=1, max_length=1000)
    obligations: list[str] = Field(min_length=1, max_length=12)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    caveat: str = Field(min_length=1, max_length=1000)


class RuleSet(StrictModel):
    rules: list[MemoryRule] = Field(min_length=1, max_length=8)


INITIAL_COMPILER = CompilerSpec(
    extraction_prompt="Extract short conditional operational lessons from the supplied source executions. State source applicability, obligations that must remain true, and evidence IDs. Source success is not proof of target applicability. Never label partial repairs as complete success."
)
INITIAL_IMPROVER = ImproverSpec(
    diagnosis_prompt="Use the supplied development episode and candidate comparison feedback to diagnose failures of the current memory compiler. Separate incorrect abstractions, applicability errors, omitted obligations and excess context.",
    proposal_prompt="Propose one concrete CompilerSpec modification motivated by that diagnosis. Preserve evidence references and source-only caveats. Do not change model weights, verifier, fixed candidate pool, evaluation tasks or proposal budget.",
)
