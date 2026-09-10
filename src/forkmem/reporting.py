"""Reproducible charts and a conservative experiment report."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from forkmem.evaluation import load_complete, summarize, write_tables


def percent(value: float | None) -> str:
    return "N/A" if value is None else f"{100 * value:.1f}%"


def interval_text(interval: list[float] | tuple[float, ...] | None) -> str:
    return (
        "N/A"
        if interval is None
        else f"{percent(interval[0])} [{percent(interval[1])}, {percent(interval[2])}]"
    )


def plot_results(summary: dict[str, Any], run_dir: Path, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    table = summary["table"]
    labels = [row["mode"] for row in table]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
    for shift, key, label, color in [
        (-0.18, "held_out_success", "Held-out", "#3478a5"),
        (0.18, "near_miss_success", "Near-miss", "#d18a35"),
    ]:
        estimates = [row[key][0] for row in table]
        errors = np.array(
            [
                [max(0, row[key][0] - row[key][1]) for row in table],
                [max(0, row[key][2] - row[key][0]) for row in table],
            ]
        )
        ax.bar(
            x + shift,
            estimates,
            width=0.34,
            label=label,
            color=color,
            yerr=errors,
            capsize=3,
        )
    ax.set_xticks(x, labels, rotation=25, ha="right")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Task success rate")
    ax.set_title("Frozen-memory transfer (task-cluster 95% bootstrap intervals)")
    ax.legend()
    for suffix in ["png", "svg"]:
        fig.savefig(directory / f"success_rates.{suffix}", dpi=180)
    plt.close(fig)
    manifest, rows = load_complete(run_dir)
    task_order = [
        entry["task_id"]
        for entry in manifest["dataset"]["tasks"]
        if entry["split"] in {"held_out", "near_miss"}
    ]
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    for mode in labels:
        curves = []
        for seed in manifest["config"]["evaluation_seeds"]:
            rewards = {
                row["task_id"]: row["success"]
                for row in rows
                if row["phase"] == "evaluation"
                and row["mode"] == mode
                and row["seed"] == seed
            }
            curves.append(np.cumsum([1 - int(rewards[task]) for task in task_order]))
        values = np.asarray(curves)
        ax.plot(np.arange(1, len(task_order) + 1), np.mean(values, axis=0), label=mode)
    ax.set_xlabel("Evaluation task in fixed order")
    ax.set_ylabel("Mean cumulative reference regret")
    ax.set_title(
        "Independent evaluation episodes; frozen memory (not an online learning curve)"
    )
    ax.legend(ncols=2)
    for suffix in ["png", "svg"]:
        fig.savefig(directory / f"reference_regret.{suffix}", dpi=180)
    plt.close(fig)


def build_report(
    run_dir: Path, output: Path, artifact_root: Path = Path("artifacts")
) -> Path:
    summary = summarize(run_dir)
    write_tables(summary, artifact_root / "tables")
    plot_results(summary, run_dir, artifact_root / "figures")
    table = {row["mode"]: row for row in summary["table"]}
    lines = [
        "# ForkMem core experiment report",
        "",
        f"Source revision: `{summary['revision']}`. Raw run: `{summary['run_dir']}`.",
        "",
        f"Completed {summary['training_episodes']} shared training episodes and {summary['evaluation_episodes']} independent transfer evaluations with local Qwen3.8-27B. Training produced {summary['training_failures']} failures and {summary['decision_forks']} DecisionForks; {summary['executed_branches']} alternative rollouts executed, {summary['successful_branches']} improved on their replayed factual branch.",
        "",
        "## Design and results",
        "",
        "32 synthetic MicroRepos over four families, fixed train/held-out/near-miss splits. Nine training seeds build a shared frozen corpus; three independent evaluation seeds use identical tools, model settings and configured action budgets under five core conditions and two ablations. Source experiments run from an immutable git worktree. The 12-episode difficulty pilot is excluded. See [protocol](evaluation.md) and [dataset](benchmark.md).",
        "",
        "| Condition | Held-out success [95% CI] | Near-miss success [95% CI] | Regression proxy / retrieved | Eval tokens |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary["table"]:
        lines.append(
            f"| {row['mode']} | {interval_text(row['held_out_success'])} | {interval_text(row['near_miss_success'])} | {row['negative_transfer_proxy_count']}/{row['retrieved_n']} | {row['evaluation_tokens']} |"
        )
    lines += [
        "",
        "Bootstrap intervals resample task IDs and retain all seeds within each selected task (2,000 draws). They describe this small synthetic sample; an all-success bootstrap interval does not imply certainty on unseen real repositories.",
        "",
        "![Success rates](../artifacts/figures/success_rates.png)",
        "",
        "![Reference regret](../artifacts/figures/reference_regret.png)",
        "",
        "## Required research questions",
        "",
    ]
    if all(
        mode in table
        for mode in [
            "negative",
            "imagined",
            "paired",
            "verified",
            "positive_only",
            "no_applicability",
        ]
    ):

        def held(mode: str) -> float:
            return float(table[mode]["held_out_success"][0])

        def near(mode: str) -> float:
            return float(table[mode]["near_miss_success"][0])

        lines += [
            f"1. **Unverified positive versus negative-only.** Held-out success: imagined {percent(held('imagined'))}, negative-only {percent(held('negative'))}. This is the observed comparison; inspect seed rates and intervals before claiming an advantage.",
            f"2. **Negative transfer/self-confirmation.** Imagined memory had {table['imagined']['negative_transfer_proxy_count']} matched B0-success/memory-failure regressions among {table['imagined']['retrieved_n']} retrieved episodes. Verified memory had {table['verified']['negative_transfer_proxy_count']} among {table['verified']['retrieved_n']}. These are regression proxies, not automatic proof of memory adoption or self-confirmation.",
            f"3. **Execution verification precision.** Raw proposed-rollout improvement rate was {percent(summary['counterfactual_precision'])}. The verified retrieval gate retains only successful positive comparisons, so in-sample accepted precision is 100% by construction when nonempty. That filtering identity is not independent evidence of prospective precision; transfer outcomes provide the independent evaluation.",
            f"4. **Permanent pairing.** Full verified held-out success was {percent(held('verified'))}, versus {percent(held('positive_only'))} without the factual side. B2 versus B3 also changes applicability retrieval, so their difference alone cannot isolate pairing.",
            f"5. **Applicability.** Near-miss success: full verified {percent(near('verified'))}, without structural applicability filtering {percent(near('no_applicability'))}. The ablation still shows applicability text to the policy; it removes the retrieval filter, not the model's ability to inspect contracts.",
            f"6. **Cost.** All requests consumed {summary['total_model_tokens']} tokens, including shared source training and alternative generation/rollout. B4 incurred {summary['executed_branches']} additional executed alternative rollouts. Evaluation-only costs are in the table; shared discovery costs must be accounted for separately. Any small or absent success improvement limits the demonstrated return on that cost.",
            "7. **Suitable failures.** Local deterministic code changes with reproducible pre-action state and a strong oracle fit this implementation. Irreversible external actions, hidden nondeterminism and failures without a modifying pivot require hypothesis/debt storage rather than verified advice.",
            "8. **Scope of conclusions.** These data test compact synthetic repair tasks under a fixed budget. They do not establish general coding-agent improvement, causal identification of the first edit alone, calibrated confidence, or online sample-efficiency gains. The corpus is frozen, and cumulative reference regret is not an online learning curve.",
        ]
    lines += [
        "",
        "## Execution and storage costs",
        "",
        f"Alternative discovery and rollout consumed {summary['counterfactual_model_tokens']} model tokens in {summary['counterfactual_model_calls']} requests; tokens per fork with a successful alternative: {summary['tokens_per_positive_fork']}. Proposal improvement rate with source-episode cluster interval: {interval_text(summary['counterfactual_precision_interval'])}.",
        "",
        f"Recorded verifier executions: {summary['verifier_executions']}; summed verifier wall time: {summary['verifier_wall_seconds_sum']:.2f}s. Request latency p50/p95: {summary['latency_p50_seconds']:.2f}/{summary['latency_p95_seconds']:.2f}s. Parallel sums are not elapsed wall time. Canonical corpus body: {summary['stored_memory_body_tokens']} tokenizer tokens (chat framing excluded).",
        "",
        f"Initial training revision: `{summary['original_training_revision']}`. Resume events: {len(summary['resume_history'])}; prompt versions: {summary['prompt_versions']}. Full resume provenance and per-condition retrieval, reuse, step and cost metrics are preserved in the JSON tables.",
        "",
        "Retrieval condition precision measures predicate compatibility, not semantic relevance. Promotion/falsification counts describe initial corpus evidence decisions; repeated validation is reported separately. Missing tokenizer measurements are represented as null, never estimated as exact tokens.",
    ]
    lines += [
        "",
        "## Evidence and limitations",
        "",
        "- Observations: raw model requests, generated actions and trajectories; model predictions remain explicitly hypothetical until execution.",
        "- Programmatic evidence: immutable deterministic verifier runs in isolated worktrees and Bubblewrap; raw log digests were checked while building this report.",
        "- Statistical uncertainty: task-cluster bootstrap plus seed distributions in `artifacts/tables/summary.json`.",
        "- The principal benchmark does not evaluate online learning sample efficiency; that requires a separate exposure-budget or online experiment.",
        "- The system records replay confidence as an engineering score, not a calibrated probability.",
        "- Additional requirement-specific case studies and the final delivery manifest are maintained separately; this core report alone does not certify full project completion.",
        "",
        "## Related work",
        "",
        "See [primary-source review](related_work.md). ForkMem evaluates paired, evidence-typed counterfactual memories; it does not claim that reflection, counterfactual repair, or experience verification are individually new.",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    for name in ["success_rates.png", "reference_regret.png"]:
        text = text.replace(
            "../artifacts/figures/" + name,
            os.path.relpath(artifact_root / "figures" / name, output.parent),
        )
    output.write_text(text)
    return output
