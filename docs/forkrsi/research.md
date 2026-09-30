# ForkRSI research notes — 2026-09-30

Primary papers and official model documentation were checked as design inputs.

- [MemEvolve](https://arxiv.org/html/2512.18746v1) evolves encode/store/retrieve/manage
  implementations using performance, tokens and latency. Architecture evolution is prior art;
  ForkRSI must test the extra value of executed paired evidence with matched positive sources.
  Official code: https://github.com/bingreeky/MemEvolve
- [EvolveMem](https://arxiv.org/html/2605.13941v1) diagnoses task failures to change retrieval
  configuration, reverting regressions and exploring after stagnation. First fix ForkRSI's
  retrieval candidate pool to isolate compiler changes and diagnostic evidence.
- [GEPA](https://arxiv.org/abs/2507.19457) uses reflection over execution trajectories to propose
  and evaluate prompt updates. Use measured comparisons rather than plausible reflection alone.
  The v2 full PDF was retrieved; use its methods as the detailed reference.
- [MetaSkill-Evolve](https://arxiv.org/html/2607.05297v1) makes improvement policies evolvable,
  tracks lineage and evaluates descendant productivity. I must actually generate later C proposals.
  Reset I0/I1 from the same C on new development tasks.
- [Hyperagents](https://arxiv.org/html/2603.19461v1) modifies improvement mechanisms alongside
  task agents. Use bounded C/I objects while keeping verification and authenticity fixed.
- [Qwen official card](https://huggingface.co/Qwen/Qwen3.5-4B) supports local inference and
  enable_thinking=false. ForkMem already requests JSON schemas and disables thinking; actual local
  model/schema smoke tests are still needed.

Design hypothesis: use a separate append-only strategy ledger, cache source compilation by
corpus and C hashes, and preserve matched positive program IDs. Record all failed descendants,
actual prompts/responses, complete verifier results, tokens and rental costs.

Container adaptation: unshare is denied. Chroot + unprivileged UID + seccomp is being tested as
an explicit execution backend, leaving the workflow oracle unchanged. Never silently run task
code without isolation; verify isolation probes and archived replay first.

## Additional directly related work checked

- [CF-Evolve, 2026-09-26](https://arxiv.org/html/2609.32870v1) trains a proposer
  to edit reasoning evidence while keeping solver/verifier frozen, with accepted
  counterfactual context stored as memory. ForkRSI freezes all model weights and
  intervenes on executable programs at the same code checkpoint, then verifies
  full continuation and recovery. This difference is a hypothesis about evidence
  value, not a claim of novelty or established superiority.
- [Recuris](https://arxiv.org/html/2608.24876v1) couples execution-state working
  memory with experiential skills and validation-gated updates under a fixed
  meta-agent. Check how its bounded loop differs from evolving I.
- [EvoUndo](https://arxiv.org/html/2608.28363v1) emphasizes recoverability for
  model-generated harness changes across counterfactual states. Keep recovery
  obligations in ForkRSI's immutable verification and expose regressions.
- [Fragility of self-improving agents](https://arxiv.org/abs/2608.18066)
  highlights variance, task ordering and underspecification. Record all
  seeds/orderings and limitations; a fixed seed alone is insufficient.
