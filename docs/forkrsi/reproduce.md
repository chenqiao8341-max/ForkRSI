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

## Actual recursive-generation authentication

Run python scripts/audit_forkrsi_generation.py to inspect the current append-only strategy ledger using read-only SQLite. It checks version/content identity, actual parent differences, successful raw proposal responses, the actual versioned I fields in the submitted request, evidence references and generation seeds. Failed proposal attempts remain in the logs; they do not become generated versions. After search completes, add --require-complete to require both changed I versions to have actually generated changed C children. This authenticates generation, not effectiveness; independent measured selection and I reset still determine the empirical conclusions.

## ModelScope snapshot download and verification

The original completed downloader used modelscope-hub==0.4.5 and ms-hub download, separate from the inference runtime. Its exact shell script, install log, download log/status and dependency freeze are preserved under runs/forkrsi/model-download. The download completed 2026-09-30T22:39:51+08:00. No immutable hub commit was captured: the original CLI omitted --revision and used its default master. Recorded SHA256 values define the expected files; any changed download must fail verification instead of silently replacing the research model.

~~~bash
cd /root/autodl-tmp/ForkRSI
python3 -m venv /root/autodl-tmp/modelscope-download-env
/root/autodl-tmp/modelscope-download-env/bin/python -m pip install -r configs/forkrsi/modelscope-download-requirements.txt
MODELSCOPE_ENDPOINT=https://modelscope.cn /root/autodl-tmp/modelscope-download-env/bin/ms-hub download Qwen/Qwen3.5-4B --local-dir /root/autodl-tmp/models/Qwen3.5-4B --max-workers 4
python3 scripts/verify_forkrsi_model.py
~~~

The verifier reads all 14 files in artifacts/forkrsi/model-files.json, including both safetensors shards, and checks sizes plus full SHA256. The listed files total 9,342,905,771 bytes; both weight shards total 9,319,828,096 bytes. The downloader also wrote .gitattributes, outside that original 14-file manifest. Current full verification is recorded in runs/forkrsi/model-verification-latest.json. These disk hashes and the server's weights_frozen/inference-mode startup record establish separate parts of the fixed-model evidence.


### Pre-final selection eligibility correction

The terminal first search omitted valid C-023548c3f9f6215213c7bb69 from paired independent selection after its development RuleSet extraction exhausted JSON repair. The predeclared policy requires all actual changed C candidates. Selection now reads typed content/parent from the append-only ledger, so a later evaluation failure cannot erase a generated candidate. The original search-result cut and failure are preserved; resume reuses every existing proposal, I version, completed selection/reset cell and cost. Only this missing candidate receives its originally required selection attempt. No new proposal slots, changed objectives, source IDs, prompts or task budgets. Final outcomes remain unopened.


Cost reporting also includes the two model JSON smoke requests (901 Qwen tokens) and one source-side agent calibration request (467 tokens). Aggregate phase usage, including failed trials and the cancelled source completion supplement, is reconciled against the full model-service tokenizer ledger. A service without request IDs supports aggregate reconciliation only, not a request-ID join; subscription assistance usage remains unknown.


### vLLM 单卡服务与并发后端复测

用户明确要求迁移后，旧 Transformers 最终网格在32完整cell处封存为部分结果；不得用其余vLLM cell补成一个混合后端的56网格。已有C/I与56个记忆输入不变，不根据已打开最终结果产生新提案或重新选择。完整迁移、原始失败及费用见 runs/forkrsi/vllm-deployment/ 和 campaign-v2/transformers-backend-closed-cost.json。

独立安装可参照 runs/forkrsi/vllm-deployment/install-vllm.sh 和 artifacts/forkrsi/vllm-runtime-freeze.txt；安装时选择CUDA13.0 PyTorch wheel，服务器驱动580.76.05。任务代码仍用原 scripts/forkrsi_env.sh 环境，vLLM包不装入该环境。原权重保持同一ModelScope快照，先运行 scripts/verify_forkrsi_model.py。

在 /root/autodl-tmp/ForkRSI，以 screen/nohup 持久启动 bash scripts/start_forkrsi_vllm.sh（引擎8002），再用原运行环境 python scripts/serve_forkrsi_vllm.py（兼容入口8000）。服务只监听本机。启动参数与环境见 configs/forkrsi/vllm-service.json；首次可能需要CUDA/Triton编译。保留原始启动日志。接口 /health 必须 ready=true、backend=vllm；/tokenize保留原tokenizer行为。python scripts/benchmark_forkrsi_vllm.py 是短输出接口探针，实际每条只生成2 token，不能用于持续解码吞吐结论。python scripts/benchmark_forkrsi_vllm_long.py 使用相同八提示和种子，在引擎8002直接测1/4/8并发，每条强制生成256 token；min_tokens/ignore_eos仅用于合成吞吐测量，不进入研究任务。结果及逐请求原始内容见 concurrency-long-output.json 和 concurrency-long-output-requests.jsonl；该直接引擎测试的7808 tokens绕过适配层用量日志，汇总费用时必须单独加一次。

后台任务开始前提交新增部署文件、保持代码干净，确认原worker已关闭及新服务空闲。python scripts/run_forkrsi_parallel_final.py freeze --concurrency 8 使用提供的冻结记忆输入；然后 python -u scripts/run_forkrsi_parallel_final.py final。按新封存后端统一执行七组，不改变既选策略及提示。若恢复，只有已完整认证的cell可复用；有目录而无metrics时入口拒绝自动重跑，先审计原生检查点与剩余动作/请求。统计单位仍为八语义任务，恢复病例及另一后端的重复不能当作独立任务。

适配层预先用原Transformers tokenizer构造token IDs，并检查引擎报告输入tokens严格吻合。response_format不转发，四次严格JSON修复仍在原LLMClient。带种子请求使用vLLM native sampler，与该版本源码默认seeded path一致；FlashAttention2、Triton/FLA、连续批处理、prefix caching、CUDA graphs仍由vLLM执行。固定种子不保证数值或GPU位级复现。文献支持参照 [Qwen3.5-4B官方说明](https://huggingface.co/Qwen/Qwen3.5-4B) 与 [vLLM官方GPU安装文档](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/)。


### 已完成结果的认证汇总和全量交付

本轮统一vLLM网格在2026-10-01 02:46 UTC正常结束，56个独立cell齐全；源码冻结提交d4dbb5107317793db51d178297206e0ae9357049。后续报告代码不是新的策略或执行规则。仅需统计复核时使用：

~~~
cd /root/autodl-tmp/ForkRSI
source scripts/forkrsi_env.sh
python scripts/summarize_forkrsi_vllm.py
~~~

该入口必须有完整原始runs：包括campaign-v2的策略SQLite、源包、两个服务日志、迁移记录及直接引擎吞吐JSON/JSONL；原始生成/筛查/资格化不被替换。它先运行campaign-vllm-final-v1/audit_final_inputs.py --require-complete，再用原AST与reviewed_flags接口核验所有实际来源/下游写入。所有完整通过代码都有独立人工阅读记录。436个最终请求按客户端ID及串行修复次序连接真实服务请求，逐提示/输出哈希、精确token IDs和usage一致。不能漏算不经适配层的7808长输出测试tokens。

全量交付目录ForkRSI_delivery_20261001包含forkrsi-records.tar.gz、forkrsi-history.bundle和manifest.json；包外acceptance-final.json记录实际传输、逐tar entry/整包SHA256、bundle verify/clone及13项目标验收。manifest是归档时点的完整快照；线上服务后续运行产生的日志增长不属于该快照。模型权重不包含，先按本说明ModelScope下载后逐文件SHA验证。

~~~
git clone forkrsi-history.bundle /root/autodl-tmp/ForkRSI
tar -xzf forkrsi-records.tar.gz -C /root/autodl-tmp/ForkRSI
cd /root/autodl-tmp/ForkRSI
source scripts/forkrsi_env.sh
python scripts/summarize_forkrsi_vllm.py
~~~

需在目标机器重新建立记录的两个独立运行环境（系统CUDA/驱动也需兼容）；bundle/tar不会打包venv或GPU驱动。历史轨迹、SQLite与checkpoint含绝对路径，以上原根最可靠。重新执行封存评估必须先恢复冻结提交、符合封存backend startup/输入条件，不能在报告提交或更换在线服务epoch后直接新跑。已有不完整目录不得自动从头重试。归档主要保证所有输入、代码与原始执行证据可核验，不承诺跨硬件/采样器位级再生相同输出。

本轮结论与限制见report.md，包括同任务后端复测而非新未见样本、配对演化最终正向输入、预算充足及重置负结果。
