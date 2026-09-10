"""Rebuild workflow result tables and plots only from a complete audited grid."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from forkmem.workflows.evaluation import summarize_transfer


def interval(value):
    return (
        "N/A"
        if value is None
        else f"{100 * value[0]:.1f}% [{100 * value[1]:.1f}, {100 * value[2]:.1f}]"
    )


def points(value):
    if value is None:
        return "N/A"
    return f"{100 * value[0]:+.1f} pp [{100 * value[1]:+.1f}, {100 * value[2]:+.1f}]"


def report(run: Path, output: Path, artifacts: Path):
    summary = summarize_transfer(run)
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fields = [
        "action_budget",
        "mode",
        "n",
        "success",
        "difference_vs_flat_verified",
        "first_verifier_success",
        "clean_path_success",
        "case_success_fraction",
        "structured_n",
        "retrieved_n",
        "regressions_vs_none_with_retrieval",
        "attributable_model_tokens",
        "incremental_model_tokens",
        "mean_memory_body_tokens",
        "mean_steps",
        "alias_cells",
    ]
    with (artifacts / "main_results.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["table"])
    config = summary["manifest"]["config"]
    budgets = config["action_budgets"]
    modes = config["modes"]
    fig, axes = plt.subplots(
        1, len(budgets), figsize=(15, 5), layout="constrained", squeeze=False
    )
    for ax, budget in zip(axes[0], budgets, strict=True):
        rows = [r for r in summary["table"] if r["action_budget"] == budget]
        means = [r["success"][0] for r in rows]
        error = [
            [max(0, r["success"][0] - r["success"][1]) for r in rows],
            [max(0, r["success"][2] - r["success"][0]) for r in rows],
        ]
        ax.bar(
            np.arange(len(rows)),
            means,
            yerr=error,
            capsize=3,
            color=[
                "#de8f05" if r["mode"] == "fork_verified" else "#4477aa" for r in rows
            ],
        )
        ax.set(
            xticks=np.arange(len(rows)),
            xticklabels=[r["mode"] for r in rows],
            ylim=(0, 1.08),
            title=f"{budget} coding actions",
            ylabel="Complete safe workflow success",
        )
        ax.tick_params(axis="x", rotation=50)
    for ext in ["png", "svg"]:
        fig.savefig(artifacts / f"success_budgets.{ext}", dpi=180)
    plt.close(fig)
    primary = [r for r in summary["table"] if r["action_budget"] == 8]
    families = sorted(primary[0]["family_success"])
    matrix = np.array(
        [[r["family_success"][family][0] for r in primary] for family in families]
    )
    fig, ax = plt.subplots(figsize=(11, 4), layout="constrained")
    im = ax.imshow(matrix, vmin=0, vmax=1, cmap="YlGnBu", aspect="auto")
    for i in range(len(families)):
        for j in range(len(modes)):
            ax.text(
                j,
                i,
                f"{matrix[i, j]:.0%}",
                ha="center",
                va="center",
                color="white" if matrix[i, j] > 0.65 else "black",
            )
    ax.set(
        xticks=range(len(modes)),
        xticklabels=modes,
        yticks=range(len(families)),
        yticklabels=families,
        title="Eight-action success by operational family (descriptive)",
    )
    ax.tick_params(axis="x", rotation=40)
    fig.colorbar(im, ax=ax)
    for ext in ["png", "svg"]:
        fig.savefig(artifacts / f"family_success.{ext}", dpi=180)
    plt.close(fig)
    import os

    relative = lambda name: os.path.relpath(artifacts / name, output.parent)
    lines = [
        "# Multi-decision ForkMem: frozen workflow results",
        "",
        f"Source revision `{summary['manifest']['source_revision']}`; transfer revision `{summary['manifest']['revision']}`. {summary['cells']} condition cells represent {summary['unique_episodes']} actual model episodes; exact-input aliases are labeled.",
        "",
        "The presentation primary comparison is paired diagnostic ForkMem versus a flat verified-code control at eight actions. Both receive the same successful programs and source IDs. All rates below require safe completion of every runtime recovery case.",
        "",
        "| Budget | Condition | Complete success [95% CI] | Difference vs flat [95% CI] | First verifier success | Retrieved | Attributable tokens |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["table"]:
        lines.append(
            f"| {row['action_budget']} | {row['mode']} | {interval(row['success'])} | {points(row['difference_vs_flat_verified'])} | {interval(row['first_verifier_success'])} | {row['retrieved_n']}/{row['n']} | {row['attributable_model_tokens']:.0f} |"
        )
    lines += [
        "",
        f"![Budget frontier]({relative('success_budgets.png')})",
        "",
        f"![Families]({relative('family_success.png')})",
        "",
        "## Interpretation boundaries",
        "",
        "Task-cluster 95% bootstrap intervals preserve matched seeds and keep runtime cases within semantic contexts. Family summaries are descriptive small-sample breakdowns. This eight-action presentation focus was selected after the original experiment; it is exploratory, not a preregistered superiority claim.",
        "",
        summary["cost_definition"],
        "",
        summary["missing_structure_definition"],
        "",
        f"Actual transfer requests: {summary['actual_model_calls']}; actual transfer tokens: {summary['actual_model_tokens']}. Source discovery costs are separate and must be added before making amortized efficiency claims.",
        "",
        "The dataset is a deterministic operational simulator, not production deployments. Contextual retrieval exposes source evidence and guards; it does not prove applicability to unseen combinations. Guard removal removes explicit scoping while code/traces retain contextual clues. Exact-profile retrieval is a coverage ablation, not the primary strong baseline.",
        "",
        f"Full per-task, per-seed, component and cost records: [summary JSON]({relative('summary.json')}). Source stability, concrete cases and requirement audit are separate delivery artifacts; this generated table alone does not certify completion.",
    ]
    lines += [
        "",
        "## Observed recovery and decision failures",
        "",
        "Counts below are episodes, not independent crash cases. Failure sites identify an observed rejected operation, a budget-exhausting operation, or unfinished terminal obligations; they do not establish a causal memory mechanism by themselves.",
        "",
        "| Budget | Condition | Recovery-only failures | Mean coding actions | Frequent observed failure sites (episodes) |",
        "|---:|---|---:|---:|---|",
    ]
    for row in summary["table"]:
        sites = sorted(
            row["failure_site_episode_counts"].items(),
            key=lambda item: (-item[1], item[0]),
        )[:3]
        label = (
            "; ".join(f"{name}: {count}" for name, count in sites) or "none observed"
        )
        if row["structured_n"] < row["n"]:
            label += f"; {row['n'] - row['structured_n']} episodes lack structured runtime observations"
        lines.append(
            f"| {row['action_budget']} | {row['mode']} | {row['recovery_only_failures']} | {row['mean_steps']:.2f} | {label} |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/v2/final_report.md"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/v2/frozen1"))
    args = parser.parse_args()
    report(args.runs, args.output, args.artifacts)
