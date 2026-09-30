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
