# Multi-decision ForkMem research revision

## New task unit: operational protocol microrepositories

The agent implements `run(api)` for a deterministic local operational simulator. It must inspect context and issue a sequence of operations, with explicit preconditions, state changes, resource costs and recovery obligations. The usual read/search/write/test tools and checkpointed coding agent remain. The benchmark measures decisions made by the resulting program during execution; these must not be confused with the number of LLM tool calls.

Four concrete scenario families:

- **Online schema migration:** protect concurrent writes, backfill and validate, retain compatibility for old readers, switch traffic, retire obsolete state. A locally valid backfill may still lose concurrent writes or break readers at cutover.
- **Service release:** artifact validation, resource allocation, warm-up/health checking, traffic transition and retirement or rollback. Limited capacity and failed health checks change which sequence is safe.
- **Durable event consumption:** claim, transactional application, publication, delivery and acknowledgement; duplicate delivery and replay change when checkpointing is safe.
- **Order compensation:** reserve inventory, authorize/capture payment, arrange fulfilment, and release/refund on failure. Prepaid versus postpaid and recoverable versus final failures create different valid continuations.

These are controlled simulations of operational decisions, not deployments to external services. Action rules and relevant contract facts are documented in task files. The oracle executes state transitions and checks independent safety, completion and cleanup obligations. It accepts every behavior satisfying the contract, not just one reference action list. Runtime cases include both success and recovery paths.

## Mechanisms to distinguish

H1: Some plausible local repairs pass a local obligation but violate downstream safety. Execution evidence can reject those candidates. Measure proposal-level obligation vectors and prospective transfer separately; accepted precision is not independent evidence.

H2: Paired failure/success traces help distinguish conditional repair rules from isolated positive advice. Compare paired verified with flat verified memory containing the SAME successful source executions and equal context allowance.

H3: In a new combination of familiar constraints, exact full-profile retrieval can miss useful lessons. Contextual retrieval should expose source guards and conflicting evidence while avoiding unqualified code transplantation. Include exact-filter and guard-removed ablations.

H4: Multiple changed decisions interact. Report whether an intervention fixes its target, preserves previously passing obligations and completes the whole workflow. Partial fixes never become globally verified successes.

A negative or null result for any hypothesis is a valid result. No implementation may optimize against final held-out outcomes.

## Split and development policy

Use separate development instances for difficulty calibration, source training instances for memory, and untouched transfer instances. Split by constraint combinations and recovery branches, not only renamed variables. Include matched single-constraint flips and unseen combinations of familiar constraints. Publish each task's decision axes and potential interaction pairs before inference.

Before final inference, freeze task bytes, initial programs, simulator/oracle, references, config, model settings, memory rendering and analysis code. Pilot only development tasks. If the pilot shows a ceiling/floor, retain its results and justify a new dataset version; never silently replace unfavorable final tasks. All references must pass and targeted semantic mutations must fail the corresponding oracle obligations.

## Comparisons and budgets

Keep no-memory, negative-only, imagined-positive, paired-unverified, legacy verified, flat verified and upgraded contextual verified conditions. The flat verified condition controls access to successful code/outcomes; it is a stronger baseline than unverified text alone. Add a guard-removed ablation. Retrieval evidence eligibility, candidate budget, context-token cap, model, task order, tools and action budget are explicit per condition. Charge discovery/verification cost separately and also report total amortized cost.

Use the same frozen source experiences and candidate pool where applicable. Include three transfer seeds. Persist every condition's task-level result, decision trace and memory use. No held-out outcome updates the store. Equivalent empty-memory prompts can share a recorded execution cell when their inputs are exactly equal; label reuse to avoid treating duplicate inference noise as a memory effect.

## Outcomes and analysis

Primary: complete safe workflow success, with paired task-cluster intervals, broken down by family and transfer stratum. Secondary: named obligation pass rates, downstream regressions after local improvement, invalid operation/ordering rate, recovery completion, decision interactions, first failing transition, and operation/LLM costs. Preserve per-runtime-case traces and distinguish failure diagnosis from proof of memory adoption.

Report mechanism-level comparisons as well as aggregate rates. Do not conclude superiority from a single favorable task family or accepted-branch filtering. The final report must say where verification/pairing/context guards helped, tied or hurt and how much they cost.

## Implementation checkpoints

1. Independently tested deterministic workflow engine, full trace and bounded operations.
2. Four scenario generators, references, targeted mutation checks, task/split manifest.
3. Development-only baseline pilot; freeze final task suite after documented calibration.
4. Fine-grained oracle result ingestion and guard-aware paired memory upgrade, without promoting partial success.
5. Frozen fair baseline/ablation experiment, case replays, uncertainty and final report.

## Development findings before final protocol freeze

Static dev0 passed 8/8 with no memory and was retained as an unsuccessful difficulty design. Resumable dev1 adds atomic-service operation interruption, rollback of open transactions and fresh controller invocations; source/transfer semantic contexts remain separated. Sixteen training-side development fixtures passed 13/16 at their first verifier call and 15/16 by eight coding actions. One of the first failures also failed the clean path; two were specifically exposed by restart schedules. These data motivate measuring both first-attempt decisions and repair-budget success, rather than only final success after generous self-repair. This publication presents the eight-action condition; that presentation focus was selected after the original experiment.

For crash cases, compare factual/alternative traces only at identical runtime case IDs and crash schedules. Comparing the factual failing restart case with the alternative's clean run would confound the intervention with a different environment. `workflows.analysis.aligned_contrasts` enforces this alignment. Whole-episode promotion still requires every runtime case to succeed.
