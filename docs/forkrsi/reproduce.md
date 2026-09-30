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

Contract qualification is fixed before C/I search and final outcomes: the unchanged original AST screen and recorded boolean/rationale review gate positive source eligibility. Failed programs and all raw verifier results remain recorded. Final and first-validation safe success exclude actual reviewed contract violations, with raw verifier success separately reported. Search/selection records retain the predeclared verifier objective; audit qualification never triggers post-final strategy tuning or reselection. No AST-screen result is claimed to prove adversarial Python safety.

Terminal batch recovery also preserves cancelled sibling episodes. benchmark resumes their matching native graph/filesystem checkpoint into a new directory, keeping the same remaining action budget and seed; the existing resume API grants a fresh per-invocation wall timeout. Full trajectory prefixes retain original execution references and are not counted as extra replicates. Source-v2 had two newly created release101 repositories with zero executed actions when its sibling failed; the original folders remain intact.

### 2026-10-01 JSON 修复上下文

source-v2 的首个实际 Proposals 调用连续出现 JSON 语法错误。原修复对话只追加错误位置，未给模型上一份错误输出，无法定位要修正的对象。后续公共协议 forkrsi-json-response-repair-v2 在原四次尝试和严格解析不变的条件下，仅带回上一份真实错误输出（最多16000字符，按原字符预算进一步收缩），要求生成完整紧凑 JSON；不改写程序值或放宽解析。实时 source-v2 仍使用已加载的 v1，未因这一修改重启；所有对照将在 C/I 搜索与最终评测前统一冻结到 v2。原始输出、修复提示、版本和失败成本保留。此为源侧协议诊断后的公共工程修复，不算 C/I 学习效果。

### 2026-10-01 修复协议后的源分叉批次

source-v2 的16个训练任务均已完整执行，2个通过，14个失败。旧 v1 的两个提案槽位已耗尽四次尝试，随后提案仍有语法/字段错误；为使用已修复的对话上下文，结束旧分叉阶段并完整保留实际数据，不重跑训练。source-v3 预先记录这14个真实失败任务的原检查点、文件/任务/verifier哈希，使用统一 v2 公共协议生成新分叉；最多104个模型请求由各剩余动作预算的最坏情况推导，每任务最多2个实际替代分支。原耗尽槽位不补充；新批次是新的源提案预算，全部旧/新增成本报告。source-v3 results.jsonl仅引用原任务供审查，不是14次新训练或新独立样本。使用 python scripts/run_forkrsi_repaired_sources.py；三批次终结后用 package_forkrsi_sources.py 合并完整实际分叉，再审查正向资格、冻结候选池并启动 C/I 搜索。

### 2026-10-01 低频订阅辅助的共用源提案

source-v1/v2无合格正向分叉，修复v2的source-v3首槽仍耗尽严格解析。按照启动文档允许的GPT订阅低频辅助，为两个家族各一个真实失败父任务记录一组两分支假说：最小修复的剩余风险与按独立义务重构。输入只用原检查点公共README/deployment/solution和实际失败；未复制见证程序，不读取最终结果。准确提示/输出与哈希保存于configs/forkrsi/subscription-source-v1。source-v4-subscription以原检查点/剩余动作预算实际执行全部完整恢复用例；原父任务引用不算新训练。提案明确标记subscription_assistant，任务Qwen冻结不变；所选pivot后已无继续动作，无新增Qwen请求。只有实际完整通过且人工契约审查合格的程序进入所有对照共用候选池。订阅推理token不可测，报告为未知而非零；这是辅助系统实验，不能声称完全自主Qwen源改进。

### 2026-10-01 源封存与计数更正

权威SQLite打包发现source-v2已完成2个分叉：1个失败摄取替代、1个通过10/10恢复病例的Qwen发布替代。此前状态摘要错误写0，现纠正；不改写旧原始记录或已提交辅助提示。辅助提案的决策依据包含这一不完整摘要；摄取家族仍无正向Qwen源，额外发布辅助假说全部保留并共用。source-v3在第3个耗尽槽位后封存，已开始第4个请求被取消；随后服务器完成的唯一调用实测7838tokens，精确行/哈希/隔离区间归属另存usage-supplement.json，无遗漏或重复请求计数。完整打包source-v1/v2/v3/v4：6分叉、3正向程序、24失败lesson；51提交程序版本含15AST标记，全部布尔/理由审查完成。辅助正向分支通过14/14发布、16/16摄取，两个风险分支仅7/14、11/16，不视为正向。下一步实际C/I搜索和同C0的I重置，随后冻结新最终任务。

### 2026-09-30T19:37:01.171115+00:00 实例对象协议与新批次

campaign-v1在首个开发任务前因第二源RuleSet提炼反复输出Schema+实例而失败，0任务执行；六次调用全部保留，见pre-development-json-trial.json。原修复提示“Return the exact schema”存在实例/Schema歧义。公共v3明确只输出符合规范的实例、不要复制Schema；严格解析、四次尝试、模型和所有预算不变。新campaign-v2不复用旧编译缓存，全对照统一v3，源6分叉和成功程序IDs不变。此为公共工程修复，不能算C/I效果。最终仍未打开。

## Final record delivery

After the final grid, complete the unchanged AST/manual qualification and run python scripts/summarize_forkrsi.py. Write docs/forkrsi/report.md, commit report-only artifacts, then run python scripts/export_forkrsi_delivery.py with a fresh --output directory. The exporter rejects incomplete final/report records and a live campaign worker. It exports tracked code/config/documents, every raw runs/forkrsi record including failed trials/checkpoints and the strategy SQLite database, research artifacts, and a verified Git history bundle. Per-file SHA256 plus archive/bundle hashes and a stability recheck authenticate the snapshot. Weights are obtained separately from the recorded ModelScope source and verified against model-files.json. Restore /root/autodl-tmp/ForkRSI for historical absolute log/checkpoint paths. Use the frozen final code revision in final-freeze.json for any sealed final resume; later report-only commits do not change the sealed strategies or permit reselection.
