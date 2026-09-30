# ForkRSI reproduction

Authoritative workspace: /root/autodl-tmp/ForkRSI on the authorized SSH server. Only the frozen local Qwen3.5-4B is used; no paid API, training or extra GPU.

## Runtime

The server provides Python3.12.3 and Torch2.8.0+cu128. Python3.13 standalone installation failed after three transport/extraction retries. The isolated Python3.12 research runtime reuses system Torch and records exact dependencies. Original Python>=3.13 metadata and uv.lock remain unchanged; Python3.13 compatibility is unverified. Verifier runtime: system Python3.10.12.

Native Bubblewrap cannot create namespaces. The chroot-seccomp backend requires root/CAP_SYS_CHROOT and libseccomp2. It drops to UID/GID65534, exposes immutable runtime/task/verifier files, denies external connect/listening/addressed sends and process creation, and retains original completion markers, hashes and resource limits. Unix socket pairs support asyncio. It is not a proof against adversarial Python.

~~~bash
cd /root/autodl-tmp/ForkRSI
bash scripts/bootstrap_runtime312.sh
source scripts/forkrsi_env.sh
python scripts/probe_forkrsi_sandbox.py
python -m pytest -q
python scripts/generate_forkrsi_tasks.py
python scripts/validate_forkrsi_tasks.py
python scripts/serve_forkrsi_model.py
~~~

Run the service in screen/tmux; it binds 127.0.0.1:8000. Use another shell for python scripts/smoke_forkrsi_model.py. Toy protocol tests and witness programs are infrastructure evidence only. Use new output paths; never overwrite old runs.

## Research stages

Commit code, task definitions, runtime records and protocol first; runners enforce a clean checkout. The budget checker uses 1.5CNY/hour plus conservative prior charge0.75CNY, reserves the next batch and rejects projected total>=200CNY.

~~~bash
source scripts/forkrsi_env.sh
python scripts/check_forkrsi_budget.py --reserve-hours 2
python scripts/run_forkrsi_source.py
python scripts/audit_workflow_programs.py --runs runs/forkrsi/source-v2 --output runs/forkrsi/source-v2/program-audit.json
python scripts/package_forkrsi_sources.py
python scripts/run_forkrsi_campaign.py search
python scripts/run_forkrsi_campaign.py freeze
python scripts/run_forkrsi_campaign.py final
~~~

Review original program-audit flags before asserting contract adherence; also screen downstream writes before reporting. Resume source with --resume only after confirmed terminal failure. Inspect status.json, worker.json and live PID first; never restart a live worker. Campaign uses a file lock and preserves proposals, completed episodes, interrupted attempts and costs.

## Fixed design

configs/forkrsi/protocol-v1.json defines the plan. Eight existing source contexts receive NEW Qwen executions with seeds1701/1702 and two actual alternatives at the same modifying checkpoint. Historical tables and handwritten witnesses never become new positive source evidence.

New tasks add observable entry phases and post-cleanup audit obligations: 4 development, 2 independent selection, 4 I-reset and 8 final. Recovery cases are nested, never independent samples.

Original public-feature retrieval fixes successful source program candidate IDs for every arm. Success-only compilation excludes factual/falsified source data; paired compilation includes it. Extracted rules remain hypotheses. C changes extraction/applicability/injection, never retrieval pool or verifier. Each arm has 2 C proposals by I0, one I evolution, then 1 C proposal actually by I1: equal3-proposal budget and <=1500-token cap. Independent selection evaluates C0 and all actual candidates without further proposals.

Reset gives I0 and paired I1 the same C0, new tasks, pools, seeds and 2 proposals each. Freeze seals selected C/I, source corpus, pools, protocol, runtime and code before final outcomes. Final rejects changed sealed inputs.

Final compares none, flat verified, original ForkMem, initial success-only C, initial paired C, evolved success-only C and evolved paired C. Original representations retain actual costs (6000-token cap); evolved arms share1500 cap. If evolved C selects C0, identical cells are reused and disclosed, never new replicates.

Report full safe success, first validation success, negative transfer and total tokens by semantic task/seed. Separate source, extraction, proposal, development, selection, reset and final costs. Preserve all rejected/no-op/invalid candidates and regressions. Seeds do not guarantee deterministic GPU inference. Small pilot results may be positive, negative or uncertain; final C improvement alone cannot establish better I or validated RSI.

## Source-side calibration record

source-v1 is retained as the original public-agent-prompt trial. Qwen repeated source reads and did not reach useful modifying pivots. The shared next-action prompt was calibrated solely on these source-side observations and a logged one-request probe, before development/selection/reset/final outcomes. Source-v2 uses that same frozen public agent policy for all later controls. Failed trial tokens and rental time are included in the cost ledger. Compiler extraction uses one fixed seed per positive source across all C versions and evidence arms; identical prompt+seed results are reused, so C version IDs cannot introduce additional random samples. No-op proposals are retained and consume their slot but cannot be selected as a changed compiler.

Source-v1 is a terminal failed trial, not a complete collection:16 failed tasks,2 full forks,4 falsified alternatives,0 positive alternatives; later Proposals exhausted strict JSON repair. The package builder preserves the failed state and includes only actual completed forks/recorded negatives. All trial costs are reported. Source-v2 uses bounded field-level repair diagnostics and the same strict schema/four-attempt cap for every route.

If an Action response exhausts four schema attempts, verify-current-code-v1 terminates that episode by applying the unchanged verifier to existing code, consuming a terminal action without another request/edit. It applies equally to every control and rollout. Exhausted source proposal slots are recorded in proposal-failures and never replenished on resume or promoted to evidence. For a previously interrupted Action, the narrow recovery command python scripts/finalize_forkrsi_response_failure.py requires the terminal batch, four actual logged failures, matching native checkpoint/tree and remaining budget; it backs up the original graph and records recovery provenance.
