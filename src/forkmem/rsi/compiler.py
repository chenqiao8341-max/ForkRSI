"""Compile authenticated DecisionFork sources into bounded conditional memories."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

from forkmem.environment import digest
from forkmem.llm import LLMClient
from forkmem.models import Branch, DecisionFork, EvidenceStatus
from forkmem.rsi.ledger import StrategyLedger, canonical, sha
from forkmem.rsi.models import CompilerSpec, RuleSet
from forkmem.workflows.analysis import PREFIX, aligned_contrasts, read_workflow_cases
from forkmem.workflows.memory import final_code

EvidenceMode = Literal["success_only", "paired"]
VERIFIED = {EvidenceStatus.REPLAY_VERIFIED, EvidenceStatus.REPEATEDLY_VERIFIED}


def observation(branch: Branch) -> dict[str, Any]:
    if not branch.outcomes:
        raise ValueError("source branch has no execution")
    outcome = branch.outcomes[-1]
    log = Path(outcome.log_path)
    if digest(log.read_bytes()) != outcome.output_sha256:
        raise ValueError("source log digest mismatch")
    metadata = json.loads(log.with_suffix(".json").read_text())
    if metadata["raw_output_sha256"] != digest(
        Path(metadata["raw_log_path"]).read_bytes()
    ):
        raise ValueError("raw source log digest mismatch")
    if outcome.success and not metadata.get("completion_observed"):
        raise ValueError("positive source lacks complete verifier execution")
    has_record = any(line.startswith(PREFIX) for line in log.read_text().splitlines())
    if not has_record and not outcome.success:
        return {
            "success": False,
            "structured_observation": False,
            "error_excerpt": log.read_text()[:4000],
            "log_sha256": outcome.output_sha256,
        }
    # Structured records must pass the original checks even for failed branches.
    cases = read_workflow_cases(outcome)
    return {
        "success": outcome.success,
        "case_total": len(cases),
        "case_successes": sum(c["success"] for c in cases.values()),
        "obligations": {
            k: all(c["obligations"][k] for c in cases.values())
            for k in next(iter(cases.values()))["obligations"]
        },
        "failed_cases": [
            {
                "case_id": i,
                "scheduled_crashes": c.get("scheduled_crashes", []),
                "obligations": c["obligations"],
                "error": c.get("error"),
                "trace_tail": c["trace"][-4:],
            }
            for i, c in cases.items()
            if not c["success"]
        ][:3],
        "log_sha256": outcome.output_sha256,
    }


def source_packet(
    fork: DecisionFork, positive: Branch, spec: CompilerSpec, mode: EvidenceMode
) -> tuple[dict[str, Any], set[str]]:
    if positive not in fork.alternatives or positive.evidence_status not in VERIFIED:
        raise ValueError("source positive must be an executed verified alternative")
    positive_result = observation(positive)
    if not positive_result["success"] or not all(o.success for o in positive.outcomes):
        raise ValueError("positive source is not complete")
    identifier = fork.fork_id + ":" + positive.branch_id
    allowed = {identifier}
    packet: dict[str, Any] = {
        "positive_program_id": identifier,
        "source_scope": fork.state.features,
        "task_family": fork.state.task_family,
        "positive": {
            "evidence_id": identifier,
            "code": final_code(positive),
            "execution": positive_result,
        },
        "scope_warning": "Execution supports this source program in this source context only. New contexts require testing.",
    }
    if mode == "paired":
        if spec.include_factual_failures:
            factual_id = fork.fork_id + ":" + fork.factual.branch_id
            factual_result = observation(fork.factual)
            packet["factual_failure"] = {
                "evidence_id": factual_id,
                "code": final_code(fork.factual),
                "execution": factual_result,
            }
            allowed.add(factual_id)
            if factual_result.get("structured_observation", True):
                contrasts = aligned_contrasts(
                    fork.factual.outcomes[-1], positive.outcomes[-1]
                )
                packet["aligned_case_total"] = len(contrasts)
                packet["aligned_positive_contrasts"] = [
                    c
                    for c in contrasts
                    if c["repaired_obligations"] or c["regressed_obligations"]
                ][:3]
        if spec.include_falsified_alternatives:
            failed = []
            for branch in fork.alternatives:
                if branch.evidence_status == EvidenceStatus.FALSIFIED:
                    evidence_id = fork.fork_id + ":" + branch.branch_id
                    failed.append(
                        {
                            "evidence_id": evidence_id,
                            "code": final_code(branch),
                            "prediction": branch.predicted_outcome,
                            "execution": observation(branch),
                        }
                    )
                    allowed.add(evidence_id)
            packet["falsified_alternatives"] = failed
    elif mode != "success_only":
        raise ValueError("unknown source evidence mode")
    return packet, allowed


def validate_references(rules: RuleSet, allowed: set[str]) -> None:
    for rule in rules.rules:
        unknown = set(rule.evidence_ids) - allowed
        if unknown:
            raise ValueError(
                "compiler fabricated evidence references: " + str(sorted(unknown))
            )


class MemoryCompiler:
    def __init__(
        self,
        ledger: StrategyLedger,
        client: LLMClient,
        cache: Path,
        count_tokens: Callable[[str], int],
    ):
        self.ledger, self.client, self.cache, self.count_tokens = (
            ledger,
            client,
            cache,
            count_tokens,
        )
        cache.mkdir(parents=True, exist_ok=True)

    async def compile_source(
        self, compiler_id: str, fork: DecisionFork, positive: Branch, mode: EvidenceMode
    ) -> dict[str, Any]:
        version = self.ledger.get(compiler_id)
        if version["kind"] != "C":
            raise ValueError("compiler_id must identify C")
        spec = CompilerSpec.model_validate(version["content"])
        packet, allowed = source_packet(fork, positive, spec, mode)
        key = sha({"compiler": compiler_id, "mode": mode, "packet": packet})
        path = self.cache / (key + ".json")
        if path.is_file():
            saved = json.loads(path.read_text())
            if (
                saved["packet_sha256"] != sha(packet)
                or saved["compiler_id"] != compiler_id
            ):
                raise ValueError("compiled memory cache provenance mismatch")
            validate_references(RuleSet.model_validate(saved["rules"]), allowed)
            return cast(dict[str, Any], saved)
        prompt = (
            spec.extraction_prompt
            + "\nReturn a RuleSet supported only by the supplied execution evidence. "
            "Keep causal claims as hypotheses and distinguish globally passing branches from partial repair. "
            "Use exact evidence_ids from this packet; do not invent identifiers.\n"
            + canonical(packet)
        )
        rules = await self.client.generate(
            prompt,
            RuleSet,
            seed=int(key[:8], 16),
            max_tokens=1800,
            run_id="compile-" + mode,
            episode_id=compiler_id,
            branch_id=packet["positive_program_id"],
        )
        validate_references(rules, allowed)
        saved = {
            "compiler_id": compiler_id,
            "evidence_mode": mode,
            "packet_sha256": sha(packet),
            "positive_program_id": packet["positive_program_id"],
            "source_scope": packet["source_scope"],
            "rules": rules.model_dump(mode="json"),
            "prompt_sha256": digest(prompt.encode()),
            "status": "source-derived hypothesis; not target-verified",
        }
        path.write_text(json.dumps(saved, indent=2))
        return saved

    def render(
        self, compiler_id: str, compiled: list[dict[str, Any]], task: dict[str, Any]
    ) -> tuple[str, list[str], dict[str, Any]]:
        spec = CompilerSpec.model_validate(self.ledger.get(compiler_id)["content"])
        packed: list[str] = []
        injected: list[str] = []
        omitted: list[dict[str, str]] = []
        features = task["features"]
        public_contract = (
            task["description"] + task["files"].get("README.md", "")
        ).lower()
        for source in compiled:
            source_id = source["positive_program_id"]
            scope = source["source_scope"]
            rules = RuleSet.model_validate(source["rules"])
            if spec.applicability == "source_scope":
                applies = all(features.get(k) == v for k, v in scope.items())
            elif spec.applicability == "public_overlap":
                applies = any(features.get(k) == v for k, v in scope.items())
            else:
                applies = any(
                    word.lower() in public_contract
                    for rule in rules.rules
                    for word in rule.obligations
                )
            if not applies:
                omitted.append(
                    {"source_id": source_id, "reason": "compiler applicability gate"}
                )
                continue
            if spec.rendering == "structured":
                piece = canonical(
                    {
                        "source_id": source_id,
                        "source_scope": scope,
                        "status": "source-executed; target applicability untested",
                        "rules": rules.model_dump(mode="json")["rules"],
                    }
                )
            else:
                lines = [
                    "Source " + source_id + "; scope " + canonical(scope),
                    "Source execution is not target proof.",
                ]
                for rule in rules.rules:
                    lines.extend(
                        [
                            "When: " + rule.applicability,
                            "Rule: " + rule.rule,
                            "Preserve: " + ", ".join(rule.obligations),
                            "Evidence: " + ", ".join(rule.evidence_ids),
                            "Caveat: " + rule.caveat,
                        ]
                    )
                piece = "\n".join(lines)
            candidate = "\n\n".join([*packed, piece])
            if (
                len(candidate) > 20000
                or self.count_tokens(candidate) > spec.memory_token_cap
            ):
                omitted.append(
                    {"source_id": source_id, "reason": "compiler memory budget"}
                )
                continue
            packed.append(piece)
            injected.append(source_id)
        body = "\n\n".join(packed)
        return (
            body,
            injected,
            {
                "compiler_id": compiler_id,
                "tokens": self.count_tokens(body),
                "candidate_positive_ids": [s["positive_program_id"] for s in compiled],
                "injected_positive_ids": injected,
                "omitted": omitted,
                "memory_sha256": digest(body.encode()),
            },
        )
