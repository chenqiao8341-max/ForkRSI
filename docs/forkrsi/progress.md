# Progress

2026-09-30: Goal created; original target persisted; baseline copied with Git provenance; budget recorded. No experiment results yet. Missing raw historical corpus requires new collection. Container namespace support is an infrastructure obstacle under investigation.

Infrastructure: system Python3.10/Bubblewrap installed; native Bubblewrap fails due to prohibited namespaces. Explicit chroot-seccomp backend passes host isolation, read-only verifier, TCP/UDP and process-spawning probes; result at runs/forkrsi/sandbox-probe/result.json. C/I typed objects and append-only ledger implemented; tests pending Python3.13 environment install. Frozen local model service and rental budget check prepared. No new model experiment or RSI claim yet.

Python3.13 downloader PID 4152 confirmed live but on its third network retry. It remains running. An isolated system-site-packages Python3.12 runtime is being prepared in parallel to reuse the existing Torch installation and enable integration checks. This is an explicit runtime adaptation; project requires-python is unchanged, actual versions will be recorded, and Python3.13 validation remains planned. All experimental conditions will use the same recorded runtime. Inference output ceiling fixed to 8192 to support the original fork proposal max_tokens=6000.

- Python 3.13 official standalone download failed after three transport/extraction retries (bootstrap.log preserved); no incomplete archive is used. Independent Python 3.12.3 runtime installation remains live. This adaptation is infrastructure, not a relaxation of execution evidence or an experiment result.

## Current status, 2026-10-01

Python3.12 research runtime completed; exact dependency freeze and constraints saved. Original >=3.13 metadata/lock unchanged; Python3.13 validation unverified. Local frozen Qwen3.5-4B service ready, GPU resident ~8975MiB. Toy Action and Proposals requests parse first attempt; throughput ~16–21 tokens/sec, usage logged, no paid API.

Seccomp originally blocked asyncio socket pairs: eight original async tasks failed. It now allows Unix socket pairs and destination-free sends; external connect/listening/addressed UDP remains denied. Isolation probes pass again; original full suite73/73 and two added I1 consumption/source isolation tests2/2 pass. Strict mypy passes7 new/affected files.

All18 new tasks pass full witness verifier (146 nested cases). Archived partial-repair/falsified case replay matches4 branches: failure/success/failure/success. These are infrastructure results only.

C extraction/rendering, actual I-driven C/I proposals, append-only lineage, paired comparisons, independent selection, I reset and sealed final grid implemented. Protocol:4 development,2 selection,4 reset,8 final tasks; each arm3 C proposals (2 by I0,1 by actual I1),<=1500 cap,shared positive candidate IDs. Reset:2 proposals per I from C0. Final includes initial C controls.

Next: collect/audit new source episodes and branches, run search/reset, seal final. No model task-result or RSI improvement claim yet. Reproduction: docs/forkrsi/reproduce.md.

Source-v1 began at revision0ac1346 with the original agent prompt. Source-side execution exposed repeated unchanged source reads (16 failed episodes; terminal count/corpus audited separately). A logged next-action calibration request correctly read README instead of repeating solution.py. The common agent prompt now explicitly summarizes already-read and missing public files, requests one next action, then write/test/repair. Model/verifier/tool/action budgets are unchanged; this is a pre-evaluation public-policy calibration applied to every control. Source-v2 will collect fresh data with the calibrated policy; source-v1 is retained and charged, never fabricated as positive evidence.

Before any C/I search, extraction seeds were fixed per source positive ID across C versions and evidence arms. Identical extraction prompt+seed results are shared, preventing provenance-only/no-op changes from creating fresh random memory samples. No-op candidates retain outcomes/costs and consume a proposal slot but cannot be selected as changed C. Statistics/audit code is written before final outcomes.

Source-v1 terminal failure: {"status": {"state": "interrupted_or_failed", "error_type": "ValueError", "completed_episodes": 16}, "completed_forks": 2, "verified": 0, "falsified": 4, "corpus_snapshot_sha256": "4ab8e2f3614fb40f03e25f494dc5dffb5e52c4d6251bc5b5b1bb22b4bb47f1d2", "termination": "four Proposals JSON repair attempts exhausted; original failed status preserved"}
No whole verified alternative is available from this trial; four completed alternatives are falsified. Remaining incomplete comparisons are not promoted. Corpus snapshot is explicitly partial; original interrupted_or_failed status is unchanged. JSON repair now includes bounded concrete validation errors (without input values); strict parsing/code preservation and four-attempt cap unchanged. All17 relevant tests and8-file strict type check pass. Fresh source-v2 uses the common calibrated agent/protocol; all terminal source batches will be packaged with their original state and actual complete forks, never fabricated as complete executions.

### 2026-10-01 协议失败的统一终止规则

source-v2 在第4个训练任务耗尽四次 Action JSON 修复预算（输出重复注释并截断）后终止；此前3个完整任务中1个通过。所有日志与费用保留。统一规则 verify-current-code-v1：解析修复耗尽时，不再调用模型或改写代码，消耗下一个终止动作并以原 verifier 验证已有代码。源分叉提案若耗尽修复预算，仅保留失败槽位与事实失败，无未执行正向记忆；恢复不会补充这个槽位。规则对源任务、分叉延续及全部后续对照一致；不改变严格解析、四次重试、动作预算、冻结模型、验证器或最终任务。中断任务仅在检查实际四次失败、原生检查点、代码树及剩余预算吻合后按此规则封存，并备份原检查点。

Contract qualification is fixed before C/I search and final outcomes: the unchanged original AST screen and recorded boolean/rationale review gate positive source eligibility. Failed programs and all raw verifier results remain recorded. Final and first-validation safe success exclude actual reviewed contract violations, with raw verifier success separately reported. Search/selection records retain the predeclared verifier objective; audit qualification never triggers post-final strategy tuning or reselection. No AST-screen result is claimed to prove adversarial Python safety.

Terminal batch recovery also preserves cancelled sibling episodes. benchmark resumes their matching native graph/filesystem checkpoint into a new directory, keeping the same remaining action budget and seed; the existing resume API grants a fresh per-invocation wall timeout. Full trajectory prefixes retain original execution references and are not counted as extra replicates. Source-v2 had two newly created release101 repositories with zero executed actions when its sibling failed; the original folders remain intact.

<!-- FORKRSI_CURRENT_STATE_BEGIN -->
## 当前状态（2026-09-30T18:00:20.361858+00:00）

权威工作目录：/root/autodl-tmp/ForkRSI；已提交版本：f928c164ad7fce361c67ec2f9f9a8f86b55545fe。ModelScope Qwen3.5-4B 权重已下载完整，冻结单卡本地服务运行中。source-v1 失败校准记录及成本保留；source-v2 当前状态 running，已完整执行 6 个训练任务，其中 2 个完整通过。训练成功尚不等于同检查点正向分叉；C/I 比较和最终评测尚未开始，等待真实分叉的合格证据。协议耗尽与原生检查点恢复均已实现并通过相关集成测试，原验证器未更改。原始 verifier 通过和审查后安全成功分别报告。最新预算与阶段详情见 artifacts/forkrsi/budget.json 与 artifacts/forkrsi/pre-search-status.json。

持久目标仍 active；后续继续源分叉、C/I 演化、公平对照、I 重置比较、冻结最终评测与研究报告，不以当前训练通过宣称 RSI。
<!-- FORKRSI_CURRENT_STATE_END -->

### 2026-10-01 完整回归验证

协议失败终止、原生检查点恢复和安全成功资格判定的当前实现完整回归：81 passed in 46.83s。原 verifier 未修改。日志及哈希见 artifacts/forkrsi/checks-current.json；这些结果仅证明基础实现的回归检查，不作为 C/I 自改进效果。

### 2026-10-01 JSON 修复上下文

source-v2 的首个实际 Proposals 调用连续出现 JSON 语法错误。原修复对话只追加错误位置，未给模型上一份错误输出，无法定位要修正的对象。后续公共协议 forkrsi-json-response-repair-v2 在原四次尝试和严格解析不变的条件下，仅带回上一份真实错误输出（最多16000字符，按原字符预算进一步收缩），要求生成完整紧凑 JSON；不改写程序值或放宽解析。实时 source-v2 仍使用已加载的 v1，未因这一修改重启；所有对照将在 C/I 搜索与最终评测前统一冻结到 v2。原始输出、修复提示、版本和失败成本保留。此为源侧协议诊断后的公共工程修复，不算 C/I 学习效果。

### 2026-10-01 修复协议后的源分叉批次

source-v2 的16个训练任务均已完整执行，2个通过，14个失败。旧 v1 的两个提案槽位已耗尽四次尝试，随后提案仍有语法/字段错误；为使用已修复的对话上下文，结束旧分叉阶段并完整保留实际数据，不重跑训练。source-v3 预先记录这14个真实失败任务的原检查点、文件/任务/verifier哈希，使用统一 v2 公共协议生成新分叉；最多104个模型请求由各剩余动作预算的最坏情况推导，每任务最多2个实际替代分支。原耗尽槽位不补充；新批次是新的源提案预算，全部旧/新增成本报告。source-v3 results.jsonl仅引用原任务供审查，不是14次新训练或新独立样本。使用 python scripts/run_forkrsi_repaired_sources.py；三批次终结后用 package_forkrsi_sources.py 合并完整实际分叉，再审查正向资格、冻结候选池并启动 C/I 搜索。

### 2026-09-30T19:19:49.566117+00:00 实际旧批次终止及修复源运行

核对旧 worker21968 时它已因 no distinct valid candidate 自行终止；未发信号、没有新引入的取消调用。source-v2 16训练/2完整通过/14失败，154调用均有usage，无完整新分叉。source-v3 worker27869、loaded revision61b7ad88，104新请求上限，引用14失败父任务不是新训练。公共v2全回归82 passed in49.79s，记录在checks-current.json。C/I搜索、重置及最终尚未开始，目标继续active。

### 2026-10-01 低频订阅辅助的共用源提案

source-v1/v2无合格正向分叉，修复v2的source-v3首槽仍耗尽严格解析。按照启动文档允许的GPT订阅低频辅助，为两个家族各一个真实失败父任务记录一组两分支假说：最小修复的剩余风险与按独立义务重构。输入只用原检查点公共README/deployment/solution和实际失败；未复制见证程序，不读取最终结果。准确提示/输出与哈希保存于configs/forkrsi/subscription-source-v1。source-v4-subscription以原检查点/剩余动作预算实际执行全部完整恢复用例；原父任务引用不算新训练。提案明确标记subscription_assistant，任务Qwen冻结不变；所选pivot后已无继续动作，无新增Qwen请求。只有实际完整通过且人工契约审查合格的程序进入所有对照共用候选池。订阅推理token不可测，报告为未知而非零；这是辅助系统实验，不能声称完全自主Qwen源改进。

### 2026-10-01 源封存与计数更正

权威SQLite打包发现source-v2已完成2个分叉：1个失败摄取替代、1个通过10/10恢复病例的Qwen发布替代。此前状态摘要错误写0，现纠正；不改写旧原始记录或已提交辅助提示。辅助提案的决策依据包含这一不完整摘要；摄取家族仍无正向Qwen源，额外发布辅助假说全部保留并共用。source-v3在第3个耗尽槽位后封存，已开始第4个请求被取消；随后服务器完成的唯一调用实测7838tokens，精确行/哈希/隔离区间归属另存usage-supplement.json，无遗漏或重复请求计数。完整打包source-v1/v2/v3/v4：6分叉、3正向程序、24失败lesson；51提交程序版本含15AST标记，全部布尔/理由审查完成。辅助正向分支通过14/14发布、16/16摄取，两个风险分支仅7/14、11/16，不视为正向。下一步实际C/I搜索和同C0的I重置，随后冻结新最终任务。

### 2026-09-30T19:34:50.615933+00:00 C/I实际搜索启动

worker30783已核对存活，loaded code1ffc779，所有18个任务的候选池固定成功源IDs：发布两个、摄取一个，原flat/fork表示实际token766/3537与428/1373。C/I提案、开发选择及I重置由同一持久进程推进，最终未打开；详情campaign-live-start.json。

### 2026-09-30T19:37:01.171115+00:00 实例对象协议与新批次

campaign-v1在首个开发任务前因第二源RuleSet提炼反复输出Schema+实例而失败，0任务执行；六次调用全部保留，见pre-development-json-trial.json。原修复提示“Return the exact schema”存在实例/Schema歧义。公共v3明确只输出符合规范的实例、不要复制Schema；严格解析、四次尝试、模型和所有预算不变。新campaign-v2不复用旧编译缓存，全对照统一v3，源6分叉和成功程序IDs不变。此为公共工程修复，不能算C/I效果。最终仍未打开。

2026-09-30T19:38:30.826838+00:00 新worker31328确认存活，loaded revision96b1f3e，v3相关9项回归21.37s通过；首个RuleSet一次严格通过。旧campaign-v1所有成本保留；源候选池不变。

### 2026-09-30T19:59:21.316904+00:00 实际首个C候选及行为变化

初始success-only C4开发任务全部失败、原日志认证通过；9提交版本无原AST标记。I0真实生成C-ef123e9bd953c8b8866de6e8，两个字段实质改变。首项配对任务固定同候选IDs，实际记忆sha不同且458→242tokens，双方完整任务均失败。四任务完整比较仍在运行，后续I演化/重置/最终/报告仍待完成；目标active。

### 2026-09-30T20:23:11.347942+00:00 新I实际驱动C与完整开发比较

success-only两次I0候选已完整比较：第一0/4且成本较父版本上升，拒绝；第二1/4、首次1，执行tokens144975→117397，开发暂选。新I两字段改变，实际request468a1c1f7b7249d79563b2b9b6a21d7e包含新提示并产生C-836c5a6f65460114f3943b8e；配对评估继续。具体一条因果描述与healthy=true日志不符，diagnostic-faithfulness-observation.json保留该问题，不改写模型输出。I重置与最终效果尚待完成。交付导出守卫已实测拒绝当前未完成批次。


### 2026-09-30T20:45:17.786513+00:00 success-only开发递归完成与只读核验

## 当前状态（2026-09-30T20:45:17.786513+00:00）

权威工作目录 /root/autodl-tmp/ForkRSI；冻结单卡 Qwen3.5-4B 服务运行。源包固定为6完整分叉/3正向程序（Qwen1、订阅辅助2），全部失败/取消成本保留，订阅 token 未知。
campaign-v2 worker31328 存活，统一 JSON 实例协议 v3，实验核心 loaded code96b1f3e。success-only 开发完成：C0=0/4，首候选0/4且154290任务 tokens 被拒绝；第二候选1/4、首次验证1、117397任务 tokens，暂选 C-a46dece9de0a834edf84632b。改变后的 I-7e2bb7b9402a4c3c7893854b 确实生成第三候选 C-836c5a6f65460114f3943b8e；该候选开发0/4、170731任务 tokens、1次退步，被拒绝。不是新 I 改善的证据。
原始成功响应、实际新 I 双字段及父 C、内容/版本哈希/证据引用已由 scripts/audit_forkrsi_generation.py 对全部4个生成版本核验，内存中篡改提示/输出均被拒绝；只读检查未改变模型或选择策略。
进入独立选择，C0已完成0/2；其余实际候选继续按固定规则评测。实时状态 stage=selection，compiler=C-68a369f29b2cb662c2b11ea0，completed=2，不把开发选择当作最终迁移结论。
后续须完成 paired 路线、同 C0 的 I 重置、冻结最终8新任务/七对照、安全审查、研究报告与实际完整归档。最终未打开，目标 active。保守租卡累计 9.3293 元，剩余 190.6707 元。


### 2026-09-30T20:53:57.839700+00:00 权重下载记录及完整文件复核

原 ModelScope 下载工具为 modelscope-hub==0.4.5 / ms-hub download，独立环境；已归档原脚本、安装/下载日志、完成状态和依赖版本。14个原记录文件全量 SHA256 复核一致，包括两片 safetensors，共9342905771字节；权重两片9319828096字节。原下载未捕获不可变 hub commit，按默认 master 获取；复现必须满足记录哈希，不允许静默替换。新增只读 verify_forkrsi_model.py，缺失/哈希错误/路径越界/空清单均被负向检查拒绝。此为复现与冻结证据，不是策略效果。


### Pre-final selection eligibility correction

The terminal first search omitted valid C-023548c3f9f6215213c7bb69 from paired independent selection after its development RuleSet extraction exhausted JSON repair. The predeclared policy requires all actual changed C candidates. Selection now reads typed content/parent from the append-only ledger, so a later evaluation failure cannot erase a generated candidate. The original search-result cut and failure are preserved; resume reuses every existing proposal, I version, completed selection/reset cell and cost. Only this missing candidate receives its originally required selection attempt. No new proposal slots, changed objectives, source IDs, prompts or task budgets. Final outcomes remain unopened.


### 2026-10-01T00:08:18.768625+00:00 完整搜索审计及最终封存前状态

## 当前状态（2026-10-01T00:08:18.768625+00:00）

主工作目录固定 /root/autodl-tmp/ForkRSI，源包6完整分叉/3正向程序（Qwen1、订阅辅助2），所有失败/取消成本保留。冻结单卡 Qwen3.5-4B 服务运行，14个记录文件最新全量 SHA256 一致，原 ModelScope 下载完整日志、工具版本与复现入口已纳入归档。
两条真实 C/I 开发路线均完成各3个 C 提案；两个改变后的 I 均在实际原始请求/响应中生成改变的 C，14策略版本/12生成版本全部内容、父版本、证据与哈希核验。两条新 I 后代各产生一次开发退步（1/4→0/4），不是改进方法改善的证据。
独立选择已对每路 C0和全部3实际改变候选尝试：可评测候选均0/2；paired首候选的提炼/选择 JSON 耗尽，保留失败，无可评测得分。曾遗漏该候选的记录入口缺陷已在最终打开前修复，原搜索切片及全部原结果保留，未追加任何 C/I 提案。按预定次级 tokens 规则选择 success-only C-a46dece9de0a834edf84632b（65155）、paired C-b7a2faf01a4854e94dc3ee28（72700）。
同 C0、新4任务、每个 I 各2修改预算的重置已完成：I0后代2/4完整及首次通过、123003任务tokens；演化paired I1后代1/4完整及首次通过、113634 tokens；I1第二槽为无实质修改，费用和实际执行保留、不替换预算。只能作小样本负向/不确定观察。
62真实搜索执行（28开发/14选择/20重置），8完整通过执行已逐程序核对；120提交程序版本含13 AST标记均审查为未公开 API 直接方法，不改写原始结果。84项完整回归通过52.31秒，严格类型检查通过。351万以下累计实测 Qwen tokens 精确数3497408，与851条服务完成日志全量对齐；订阅辅助 token 仍未知。
当前最终任务执行数0，封存策略和新最终8任务/七对照即将启动；完成后仍须全部安全审查、最终统计、简短研究报告及实际完整归档，目标 active。最近保守租卡累计 14.3496 元，剩余 185.6504 元，6小时预留允许。

## 用户要求的 vLLM 后端迁移（2026-10-01）

原服务为 Transformers 5.17.0 / Torch 2.8.0+cu128、bf16、按请求串行采样。用户在原最终评估期间明确要求改用 vLLM 及高并发。原 worker 在第32个完整 cell 的原子 metrics 写入后暂停并关闭；已完成四组各8任务，保留原结果、全部费用和一个尚未开始模型动作的后续初始化目录。旧服务1107条完成日志共4770667 Qwen tokens，与3497408前期+1273259部分最终执行精确对应，关闭边界无新增/取消模型调用。原七组网格没有完成，不混入 vLLM 后端结果。

已安装独立 /root/autodl-tmp/forkrsi-vllm-runtime，固定 vllm==0.21.0 / Torch2.11.0+cu130 / Transformers4.57.6；与任务/编译程序仍用的 Python3.12.3/Transformers5.17.0 环境隔离。GPU引擎以 bf16、单卡、text-only、32768总上下文、16活动序列、8192分块prefill、0.90显存比例运行，开启prefix caching/CUDA graphs。带请求种子时 vLLM 本来使用 native sampler；显式 VLLM_USE_FLASHINFER_SAMPLER=0 避免无用的无种子FlashInfer预热编译。启动失败原日志保留，PATH已包括环境ninja及CUDA工具；无量化或权重修改，14文件全量SHA再次一致。

服务入口 http://127.0.0.1:8000/v1 经8并发异步适配层进入 http://127.0.0.1:8002/v1 的vLLM引擎。适配层用原tokenizer生成精确thinking-disabled提示token IDs，调用vLLM completions接口；固定seed/temperature/top_p及EOS248044，无top-k截断及惩罚；不转发原客户端response_format，因为原服务也忽略它。保持提示式JSON与原严格四次修复，不引入guided JSON解码。

并发复测固定原已选C/I、成功源IDs、全部56个记忆正文/元数据、任务/verifier/初始代码、seed2701、8动作及名义240秒预算。封存输入 runs/forkrsi/vllm-deployment/frozen-task-memories.json，值SHA fff20303bd07cda6c7183bf33edaa7711d609b472466287290eaf2d91f07e2d3，封存时0模型调用。32个原src文件与原冻结提交逐字相同，输入/网格/选中策略篡改守卫通过。C提炼复用已有Transformers输出，最终任务推理由vLLM统一完成，不追加C/I提案或选择。新入口 scripts/run_forkrsi_parallel_final.py，独立 runs/forkrsi/campaign-vllm-final-v1。按任务轮换七组，最多8个独立任务同时运行，任务计时在取得并发槽后开始；单任务内部模型/工具动作仍按依赖顺序。未完成目录必须做原生检查点审计，不静默新建重跑。

这是用户要求的同任务、既选策略后端复测；原最终结果已经部分打开，不能称作一组新未见任务或新的独立语义样本。原评估及新评估按后端分别报告并合计全系统费用。新后端完成后仍需完整认证、逐程序审查、报告和全量归档；目标保持active。

2026-10-01 02:32 UTC：vLLM原始Action/Proposals解析通过。固定八个合成长输出请求（各256输出token）实测1/4/8并发墙钟25.1468/6.7211/3.5722秒，输出吞吐81.44/304.71/573.32 token/s；8并发相对该vLLM串行测量约7.04倍，不是Transformers对vLLM的直接比较，也不是任务准确率或RSI收益。基于该测量选择已预定的8并发完整复测；此前短请求测量仅2输出token，不作为持续解码吞吐证据。长输出测试7808 tokens以独立原始记录补入费用。
