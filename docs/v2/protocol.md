# Eight-action feasibility protocol

The displayed primary comparison is `fork_verified minus flat_verified` at eight coding actions. This presentation focus was chosen after the original experiment; the archived dataset, eight-action condition and outputs themselves were frozen before inference. The selection is exploratory and does not become a preregistered superiority test through relabeling.

Four deterministic workflow families contain 32 frozen semantic contexts: 16 source and 16 held out, with 358 nested runtime cases across both splits. Held-out combinations have three single-constraint-flip source neighbors. Development used training-side contexts. Programs implement `run(api)`; each verifier tests normal execution and recovery after single/adjacent interruptions. Every required obligation in every runtime case must pass. Runtime operations are decisions of the generated program, not independent online LLM calls.

Shared source collection used 80 episodes and its original action budget, five seeds and up to three alternatives per natural failure. Exact code duplicates were excluded before execution. No held-out outcome updated the corpus. Source costs are separate from transfer costs.

Transfer config: `configs/experiments/v2/transfer.yaml`. Eight modes × 16 contexts × seeds 101/211/307 × one eight-action budget = 384 cells. Modes are none, negative, imagined, paired_unverified, flat_verified, fork_verified, legacy_verified and unguarded_verified. Identical task/seed/budget/memory-body inputs share explicitly labelled executions: 264 actual archived episodes.

Flat and paired verified views use identical successful program bytes and source IDs. Paired views add factual failure/code and matched-case diagnostics. Context similarity uses public deployment facts; source verification is not a guarantee of target applicability. Prepared views are capped at 6,000 memory tokens and 20,000 characters, selecting up to two distinct source contexts. Code/traces retain contextual clues even in the explicit-guard ablation.

Statistics retain all eight-action task/seed cells, use paired task-cluster bootstrap intervals, and report initial verifier results, full recovery completion, obligations, failure sites and attributable/incremental/actual token accounting. Nested runtime cases and aliases do not inflate independent samples. Intervals can degenerate for all-success samples; this does not establish certain population success. Other condition contrasts are exploratory without multiplicity correction.

Portable examples select the first lexicographic task/seed for paired wins, losses, equal outcomes with different repair cost, and either direction of the guard comparison. Missing categories remain empty. The eight-action case selection was performed for this publication and is descriptive, not evidence of a preregistered mechanism claim.
