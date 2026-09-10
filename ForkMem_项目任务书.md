# ForkMem 项目任务书

> **执行更新（2026-09-09）**：按用户后续指令，以 20 小时内交付 P0 为目标，忽略原“一周”安排；实际推理服务最大并发为 8，不能使用下文示例中的 32 并发。完整需求范围保持不变。当前进度和实验证据见 `PROGRESS.md`、`EXPERIMENTS.md`。

> **项目全名**：ForkMem — Execution-Verified Counterfactual Memory for Self-Improving Agents  
> **中文名**：分叉记忆：面向自改进 Agent 的执行验证反事实记忆  
> **任务类型**：一周内完成的研究型 Agent 项目，要求同时具备可运行系统、可复现实验、清晰创新点和简历展示价值  
> **工作目录**：`work/ForkMem/`  
> **主要底模**：本机 GPU 4～7 上由 vLLM 提供服务的 `Qwen3.8-27B`，支持高并发推理  
> **任务书版本**：v0.1  
> **日期**：2026-09-09

---

## 0. 给执行 Agent 的总指令

你负责在 `work/ForkMem/` 中从零实现、测试、评估并整理 ForkMem 项目。不要只输出计划、架构图、文献综述或伪代码；必须实际创建代码仓库，跑通端到端流程，完成对照实验，并留下可复现的运行命令和结果文件。

所有项目代码、配置、脚本、测试、实验索引、研究日志和最终报告均放在：

```bash
work/ForkMem/
```

不得把模型权重、大型系统缓存、Docker 基础镜像或无关数据复制进项目目录。可以在系统临时目录中创建隔离运行环境，但必须在仓库中保存生成方式、哈希、配置和结果索引。

工作原则：

1. **优先跑通最小闭环，再扩大功能。**第一优先级不是前端、论文排版或复杂框架集成，而是完成“失败轨迹 → 反事实候选 → 同状态分叉执行 → 验证 → 写入类型化记忆 → 后续任务检索复用”的端到端闭环。
2. **反事实不是事实。**任何没有经过真实环境执行、测试或确定性 oracle 验证的替代决策，只能作为假设存储，禁止伪装成成功经历。
3. **可执行证据优先于 LLM 判断。**单元测试、退出码、环境 reward、状态断言和确定性比较是主要验证器；LLM-as-a-judge 只能作为辅助指标。
4. **所有实验必须可复现。**记录模型 ID、vLLM 地址、prompt 版本、采样参数、随机种子、代码 commit、数据版本、超时、并发度和执行预算。
5. **不过度宣称新颖性。**项目开始时用不超过总工作量 10% 的时间核验近邻工作；最终报告准确说明 ForkMem 与 hindsight rewriting、reflection、counterfactual repair、experience verification 的区别。
6. **发现路线停滞时切换。**若连续两轮只在重构、改 prompt 或增加抽象层，却没有新增端到端通过用例、稳定指标或真实错误案例，应立即缩小范围，切换到更简单的可执行环境，保住完整实验闭环。
7. **持续维护状态文件。**至少维护：
   - `PROGRESS.md`：当前状态、已完成事项、下一步；
   - `DECISIONS.md`：架构选择及理由；
   - `EXPERIMENTS.md`：实验登记、命令、配置和结果；
   - `RISKS.md`：已知缺陷、未验证假设和范围限制；
   - `artifacts/latest_status.json`：机器可读的最新节点。
8. 每完成一个可运行里程碑即做一次 git commit；不要等到最后一次性提交。

---

## 1. 项目动机与核心研究命题

普通 Agent 在决策造成负向结果后，常见做法是把以下内容写入长期记忆：

```text
在状态 s 中执行动作 a，造成了负向结果；以后避免这样做。
```

这种记忆主要提供负向约束：

\[
Q(s,a^-) \text{ 较差}.
\]

ForkMem 要进一步让 Agent 思考并检验：

```text
在同一个关键状态中，若改选另一个动作 a'，是否可能获得更好的结果？
```

目标不是让 LLM 编造一个“本可以成功”的故事，而是构造、执行和管理一个决策分叉：

\[
\text{actual branch}
\quad\leftrightarrow\quad
\text{counterfactual branches}.
\]

当可回滚环境允许时，从失败轨迹中的同一个 checkpoint 出发，并行执行若干替代动作及其后续轨迹，估计：

\[
\Delta(s;a',a)
=
\mathbb E[R\mid do(a')] - \mathbb E[R\mid do(a)].
\]

ForkMem 的核心命题是：

> 与“只保存失败教训”或“保存未经验证的正向想象”相比，成对保存现实分支与经过执行验证的替代分支，并显式管理证据等级、适用条件和置信度，能够减少同类错误复发，提高跨任务样本效率，同时降低错误反事实造成的负迁移。

---

## 2. 项目的创新焦点

项目不得把创新点简单写成“失败以后多生成一条正向建议”。近邻方法已经涉及反思、失败轨迹重写、反事实修复和经验验证。ForkMem 应围绕以下组合创新进行实现和评估。

### 2.1 成对的 Decision Fork，而非孤立经验文本

每条记忆同时保留：

- 原状态与上下文；
- 实际选择的动作；
- 实际观察到的负向结果；
- 一个或多个替代动作；
- 每个替代动作的预测结果；
- 从同一 checkpoint 分叉执行后的真实结果；
- 现实分支与替代分支之间的 reward / verifier 差异；
- 适用条件、排除条件和来源环境。

记忆的基本单元不是一句 lesson，而是一个可审计的局部决策比较。

### 2.2 认识论类型：经历、想象和验证必须分开

反事实分支必须具有明确证据状态，例如：

```text
IMAGINED
    ↓
SANDBOX_TESTED
    ↓
REPLAY_VERIFIED
    ↓
REPEATEDLY_VERIFIED
```

并允许进入：

```text
FALSIFIED
SUPERSEDED
EXPIRED
```

最低要求：

- `OBSERVED`：现实分支，确实执行过；
- `IMAGINED`：仅由模型提出，未执行；
- `REPLAY_VERIFIED`：从同状态 checkpoint 分叉并成功执行；
- `REPEATEDLY_VERIFIED`：在多个相似实例或随机种子中验证；
- `FALSIFIED`：执行结果不支持原假设；
- `SUPERSEDED`：被更精确的新记忆替代。

检索时禁止把 `IMAGINED` 记忆以确定事实口吻注入 Agent。

### 2.3 可证伪、可降级、可修订的记忆生命周期

一条反事实假设不是写入后永久有效。新的执行证据应能够：

- 提高或降低置信度；
- 将宽泛规律收窄为有条件规律；
- 添加排除条件；
- 标记为被证伪；
- 合并重复分叉；
- 保留来源和版本历史。

### 2.4 Experiment Debt：无法立即验证的反事实进入实验债务队列

当环境不可回滚、验证成本过高或风险过大时，不应把替代决策丢弃，也不应把它写成事实。将其保存为待验证假设：

```text
在未来遇到足够相似且风险可控的状态时，优先安排一次小成本实验，检验替代策略是否优于旧策略。
```

形成闭环：

\[
\text{negative outcome}
\rightarrow
\text{counterfactual hypothesis}
\rightarrow
\text{low-risk experiment}
\rightarrow
\text{verified / falsified memory}.
\]

`ExperimentDebtScheduler` 属于 P1 功能；P0 至少需要定义数据结构和基本队列接口。

---

## 3. 成功标准

### 3.1 P0：一周内必须完成

1. 一个可运行的 Agent 环境和轨迹记录器；
2. 负向结果检测；
3. 关键决策点候选定位；
4. 调用本机 Qwen3.8-27B 生成多个替代动作；
5. 从同一环境 checkpoint 分叉执行替代动作及后续轨迹；
6. 通过可执行 oracle 比较实际与替代分支；
7. 类型化 `DecisionFork` 记忆结构及持久化；
8. 基于证据等级、适用条件和收益差的检索；
9. 将检索到的 ForkMem 注入后续相似任务；
10. 至少四组核心基线的受控对比；
11. 完整 pytest 测试、CLI、README 和实验报告；
12. 至少一个可录屏展示的端到端案例。

### 3.2 建议的定量最低交付

在计算与环境允许的前提下，目标至少完成：

- 24 个以上可执行任务实例；
- 至少 4 类潜在错误模式；
- 每类包含已见任务与 held-out 变体；
- 每个主要条件至少 3 个随机种子或等价重复；
- 至少 100 个实际 Agent episode；
- 至少 50 个被真实执行的 counterfactual branch；
- 至少 10 条稳定、可复现的 Decision Fork；
- 一个汇总表和两个以上核心图表；
- 对主要指标给出 bootstrap 95% 置信区间或明确的重复运行分布。

这些数字不是为了堆量。若完整真实实验只能覆盖更少实例，应优先保证严格对照、可重复验证和高质量案例，并在报告中如实说明。

### 3.3 P1：完成 P0 后再做

- `ExperimentDebtScheduler` 主动选择未来低风险验证机会；
- Mem0 OSS adapter；
- mini-swe-agent 或 SWE-agent adapter；
- 多随机种子置信度更新；
- 轻量 Counterfactual Utility Critic；
- 简单可视化 dashboard；
- SWE-bench Verified 小规模案例。

### 3.4 非目标

第一周不要把以下事项设为完成 P0 的前置条件：

- 训练一个大型新模型；
- 支持五种以上 Agent 框架；
- 跑完整 SWE-bench；
- 构建复杂多 Agent 社会；
- 开发重型前端；
- 把 ForkMem 做成通用知识图谱；
- 用 LLM judge 替代真实环境验证；
- 声称已经证明因果关系或达到人类式反事实认知。

---

## 4. 本机推理环境与资源约束

### 4.1 已知资源

本机 **GPU 4～7** 已通过 vLLM 运行：

```text
Qwen3.8-27B
```

该服务是本项目的主要底模，并支持高并发推理。优先将其用于：

- 主 Agent 策略生成；
- 失败归因和 pivot 候选生成；
- counterfactual action proposal；
- memory distillation；
- 结构化适用条件抽取；
- 辅助语义评判。

### 4.2 不得破坏现有 vLLM 服务

执行 Agent 必须先发现服务地址和模型 ID，不得假设端口，不得擅自停止、重启、重新加载或占用 GPU 4～7 上的服务。

建议检查：

```bash
nvidia-smi -i 4,5,6,7
ps -ef | grep -E 'vllm|api_server|Qwen3.8-27B' | grep -v grep
ss -ltnp 2>/dev/null | grep -E '8000|vllm|python'
```

找到候选端口后检查 OpenAI-compatible API：

```bash
curl -s http://127.0.0.1:<PORT>/v1/models | python -m json.tool
```

把实际配置写入项目根目录的 `.env.example`，真实 `.env` 不提交：

```bash
FORKMEM_LLM_BASE_URL=http://127.0.0.1:<PORT>/v1
FORKMEM_LLM_API_KEY=EMPTY
FORKMEM_LLM_MODEL=<MODEL_ID_FROM_V1_MODELS>
FORKMEM_LLM_MAX_CONCURRENCY=32
FORKMEM_LLM_TIMEOUT_SECONDS=180
```

若服务未监听 loopback，应根据现有启动参数确定地址；不得自行重启服务来图省事。

### 4.3 推理客户端要求

使用异步 OpenAI-compatible 客户端；所有请求必须支持：

- 并发 semaphore；
- 指数退避；
- 明确超时；
- 请求 ID；
- prompt / schema 版本；
- token 与 latency 统计；
- JSON 解析失败后的有限次数修复；
- 可取消任务；
- 错误日志中不泄漏敏感环境变量。

建议初始参数：

| 用途 | temperature | 并发特点 |
|---|---:|---|
| 主 Agent 决策 | 0.2～0.4 | 中等并发，强调稳定性 |
| 替代动作生成 | 0.7～1.0 | 高并发，强调多样性 |
| 失败归因 / 结构化抽取 | 0～0.2 | 强制 JSON schema |
| 辅助 judge | 0 | 只作辅助，不作唯一 oracle |

如果 Qwen3.8-27B 的原生 tool calling 在当前服务配置下不稳定，改用严格的 JSON action protocol：模型输出 `{"thought_summary": ..., "action": ..., "arguments": ...}`，通过 Pydantic 校验和有限重试解析。不要因 tool calling 兼容性问题阻塞主项目。

### 4.4 高并发使用方式

GPU 优势主要用于并行探索而不是第一周训练：

- 对一个失败状态并行生成 8～32 个候选动作；
- 先去重，再选择 2～8 个候选实际分叉执行；
- 多 episode 并行运行；
- 对随机环境并行多个 seed；
- shrink / replay 任务异步排队。

必须设置全局预算和背压，避免一个错误循环无限请求模型。

---

## 5. 推荐框架选型

## 5.1 主实现：LangGraph 原生 Checkpointer + Store API

**推荐结论：ForkMem 主系统建立在 LangGraph 上，但核心记忆语义必须自行实现。**

使用方式：

- LangGraph `checkpointer`：保存单个 episode / thread 的状态快照，用于恢复、时间旅行和从历史节点分叉；
- LangGraph `Store`：保存跨 episode 的长期 Decision Fork；
- 自定义 `ForkMemoryStore`、`ForkRetriever`、`EvidenceUpdater`：负责 ForkMem 的类型化 schema、证据生命周期、适用性匹配和检索排序；
- LangGraph graph：组织 Agent 执行、失败检测、分叉验证和 memory write pipeline。

推荐理由：

1. ForkMem 需要从任意 checkpoint 回到相同状态并探索替代轨迹，LangGraph 的 checkpoint / time-travel / fork 能力天然适配；
2. 长期 Store 保存任意 JSON 文档，并支持 namespace，适合保存结构化 Decision Fork；
3. checkpointer 与 long-term store 分离，能够明确区分“本次轨迹状态”和“跨任务长期经验”；
4. LangGraph 足够底层，可控制每次 memory write，而不会强行把 ForkMem 压缩成普通事实文本；
5. 后续容易添加 Mem0、LangMem 或其他系统 adapter 做对照。

开发阶段：

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
```

持久化集成阶段优先：

```python
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
```

若本机 Docker / PostgreSQL 环境造成明显阻塞，可先实现一个 SQLite-backed adapter，但接口必须与项目定义的 `ForkStore` Protocol 解耦，确保之后可切换 Postgres。

## 5.2 LangMem 的定位：可选组件，不作为 ForkMem 真值层

LangMem 可以用于：

- 从长轨迹中抽取候选 lesson；
- 对文本记忆做摘要；
- 作为普通 semantic / procedural memory baseline；
- 比较高层 memory manager 与 ForkMem 类型化写入的差异。

但不要让 LangMem 的高层 memory manager 直接决定 ForkMem schema、证据状态或 promotion 规则。ForkMem 的核心是“反事实假设与已验证经验的认识论隔离”，这需要完全显式的写入控制。

## 5.3 Mem0 OSS 的定位：外部基线

完成 P0 后接入 Mem0 OSS，建立一个 text-memory baseline：

- 保存失败 lesson；
- 保存未经验证的替代建议；
- 搜索并注入后续任务；
- 与 ForkMem 的结构化、证据加权记忆比较。

不建议第一天把 Mem0 作为核心存储，因为 ForkMem 需要保存成对分支、原始证据、版本和多级状态，直接使用通用 add/search/update 抽象可能隐藏关键实验变量。

## 5.4 Letta 的定位：暂不作为主框架

Letta 的 memory blocks 和 archival memory 适合构建长期 stateful agent，但第一周接入完整 Agent runtime 会增加额外约束。可在后续将 ForkMem 作为 archival memory 或外部工具接入，不作为 P0 依赖。

## 5.5 Agent harness 选择

P0 建议直接用 LangGraph 构建一个最小 coding agent，工具仅需：

- 查看文件；
- 搜索文本；
- 写入 patch；
- 执行受控 shell 命令；
- 运行测试；
- 提交最终答案。

mini-swe-agent 可作为 P1 adapter。它支持本地 OpenAI-compatible 模型且结构简洁，但不要让外部 harness 的兼容性问题阻塞 ForkMem 核心实验。

---

## 6. 推荐仓库结构

```text
work/ForkMem/
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── docker-compose.yml                 # 可选：Postgres / pgvector
├── Makefile
├── PROGRESS.md
├── DECISIONS.md
├── EXPERIMENTS.md
├── RISKS.md
│
├── src/forkmem/
│   ├── __init__.py
│   ├── config.py
│   ├── cli.py
│   │
│   ├── llm/
│   │   ├── client.py                  # 异步 vLLM/OpenAI-compatible 客户端
│   │   ├── schemas.py
│   │   ├── prompts.py
│   │   └── retry.py
│   │
│   ├── agent/
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── policy.py
│   │   ├── tools.py
│   │   └── trajectory.py
│   │
│   ├── memory/
│   │   ├── models.py                  # DecisionFork 等 Pydantic schema
│   │   ├── store.py                   # ForkStore Protocol
│   │   ├── langgraph_store.py
│   │   ├── sqlite_store.py            # 可选 fallback
│   │   ├── retrieval.py
│   │   ├── confidence.py
│   │   ├── lifecycle.py
│   │   └── consolidation.py
│   │
│   ├── counterfactual/
│   │   ├── failure_detector.py
│   │   ├── pivot_locator.py
│   │   ├── proposer.py
│   │   ├── branch_executor.py
│   │   ├── evaluator.py
│   │   └── debt_scheduler.py
│   │
│   ├── environments/
│   │   ├── base.py
│   │   ├── repo_env.py
│   │   ├── worktree.py
│   │   └── safety.py
│   │
│   ├── benchmarks/
│   │   ├── microrepo/
│   │   ├── tasks.py
│   │   ├── runner.py
│   │   └── splits.py
│   │
│   ├── baselines/
│   │   ├── no_memory.py
│   │   ├── negative_only.py
│   │   ├── imagined_positive.py
│   │   ├── paired_unverified.py
│   │   └── mem0_adapter.py             # P1
│   │
│   └── evaluation/
│       ├── metrics.py
│       ├── bootstrap.py
│       ├── reports.py
│       └── plots.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── configs/
│   ├── default.yaml
│   ├── baselines/
│   └── experiments/
│
├── data/
│   ├── task_specs/                     # 小型、可提交的任务定义
│   └── schemas/
│
├── runs/                               # gitignore 大体积逐步日志
├── artifacts/
│   ├── latest_status.json
│   ├── summaries/
│   ├── tables/
│   ├── figures/
│   └── cases/
│
├── scripts/
│   ├── inspect_vllm.sh
│   ├── smoke_test.py
│   ├── run_benchmark.py
│   ├── replay_case.py
│   └── build_report.py
│
└── docs/
    ├── architecture.md
    ├── environment.md
    ├── memory_schema.md
    ├── benchmark.md
    ├── evaluation.md
    └── final_report.md
```

---

## 7. 核心数据模型

使用 Pydantic v2 定义严格 schema。下面是建议起点，可根据实现调整，但不得退化为一段无结构文本。

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    OBSERVED = "observed"
    IMAGINED = "imagined"
    SANDBOX_TESTED = "sandbox_tested"
    REPLAY_VERIFIED = "replay_verified"
    REPEATEDLY_VERIFIED = "repeatedly_verified"
    FALSIFIED = "falsified"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class StateFingerprint(BaseModel):
    environment: str
    task_family: str
    structured_features: dict[str, Any] = Field(default_factory=dict)
    textual_summary: str
    artifact_hashes: dict[str, str] = Field(default_factory=dict)


class ActionRecord(BaseModel):
    action_type: str
    content: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_name: str | None = None


class OutcomeEvidence(BaseModel):
    reward: float | None = None
    success: bool
    verifier_name: str
    verifier_payload: dict[str, Any] = Field(default_factory=dict)
    stdout_digest: str | None = None
    stderr_digest: str | None = None
    artifact_hashes: dict[str, str] = Field(default_factory=dict)


class BranchRecord(BaseModel):
    branch_id: str
    kind: Literal["factual", "counterfactual"]
    first_action: ActionRecord
    trajectory_ref: str
    predicted_outcome: str | None = None
    evidence_status: EvidenceStatus
    outcomes: list[OutcomeEvidence] = Field(default_factory=list)
    mean_reward: float | None = None
    reward_delta_vs_factual: float | None = None
    confidence: float = 0.0


class ApplicabilityRule(BaseModel):
    requires: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    structured_predicates: dict[str, Any] = Field(default_factory=dict)


class DecisionFork(BaseModel):
    fork_id: str
    schema_version: str = "0.1"
    created_at: datetime
    updated_at: datetime
    source_episode_id: str
    pivot_step: int
    state: StateFingerprint
    factual_branch: BranchRecord
    counterfactual_branches: list[BranchRecord]
    applicability: ApplicabilityRule
    lesson: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    version: int = 1
```

### 7.1 存储原则

- 原始 trajectory 不直接塞入检索 prompt，只保存引用、摘要和哈希；
- 原始日志以 JSONL / Parquet 保存，DecisionFork 中保留稳定引用；
- 任何 memory 更新保留旧版本或 append-only event；
- 禁止原地覆盖后失去来源；
- factual branch 必须引用真实 execution record；
- imagined branch 不得拥有伪造的 `OutcomeEvidence`；
- promotion 必须由程序化验证器触发，而不是模型自己声称“验证成功”。

### 7.2 置信度

第一版可采用透明规则，不必使用复杂神经模型：

```text
IMAGINED                -> 0.10
SANDBOX_TESTED          -> 0.45
REPLAY_VERIFIED once    -> 0.70
REPLAY_VERIFIED 3+ runs -> 0.85
REPEATEDLY_VERIFIED     -> 0.95
FALSIFIED               -> 0.00
```

随机环境可用 Beta-Bernoulli 或 reward bootstrap 更新。报告中必须说明 confidence 是工程分数还是经过校准的概率，禁止混淆。

---

## 8. 端到端工作流

### 8.1 正常执行

```text
任务输入
  ↓
检索当前状态适用的 ForkMem
  ↓
按证据等级和适用条件整理成决策提示
  ↓
Agent 执行动作
  ↓
轨迹、checkpoint、工具结果持续记录
  ↓
环境 verifier 给出成功 / 失败与 reward
```

### 8.2 失败后的 Fork 构造

```text
检测负向结果
  ↓
定位 1～3 个可能的 pivotal decision
  ↓
对每个 pivot 生成多样化替代动作
  ↓
语义去重、合法性过滤、风险过滤
  ↓
从 pivot 前的相同 checkpoint 创建隔离分支
  ↓
执行替代动作，并从新状态重新 rollout 后续步骤
  ↓
运行真实测试 / verifier
  ↓
比较 factual 与 counterfactual reward
  ↓
写入、更新或证伪 DecisionFork
```

### 8.3 关键约束

1. 替代动作后必须从新状态重新生成后续轨迹，不能机械拼接原失败后缀；
2. “动作 A 之后失败”不等于“A 是唯一原因”，因此 pivot 只能称为候选，除非分叉验证显示替换它能够稳定翻转结果；
3. 多个步骤共同导致失败时，允许保存组合 intervention，但 P0 优先处理单 pivot；
4. 分叉必须共享相同前缀和环境状态，避免比较不同初始条件；
5. 所有分支运行有明确的步数、token、wall-clock 和 shell 预算。

### 8.4 检索和注入

检索采用“结构过滤优先、文本相似度次之、证据加权”的策略：

\[
\operatorname{score}(m\mid s)
=
\alpha\,\operatorname{structuredMatch}(m,s)
+
\beta\,\operatorname{textSimilarity}(m,s)
+
\gamma\,\operatorname{evidenceWeight}(m)
+
\delta\,\operatorname{utilityGain}(m)
-
\lambda\,\operatorname{mismatchRisk}(m,s).
\]

第一版不要求神经 embedding。可先使用：

- task family / environment / tool / error class 精确过滤；
- BM25 或 token overlap；
- 规则化 evidence 权重；
- applicability predicates。

之后再增加本地 embedding。

注入 Agent 的格式必须保留不确定性，例如：

```text
Verified decision fork:
- Applicable when: repository contains uv.lock and pyproject.toml.
- Observed failure: running `pip install -U ...` changed dependency state and tests failed.
- Verified alternative: `uv sync` restored the pinned environment; 3/3 replays passed.
- Exclusion: do not apply to pip-only repositories.
```

未经验证的假设只能写成：

```text
Unverified hypothesis; do not treat as established:
- In a similar state, action B may outperform action A.
- Evidence: none; consider only as a low-risk experiment.
```

---

## 9. 首选实验环境：可回滚的 Coding Agent MicroRepo

为了在一周内获得强、真实、可解释的证据，P0 首选构建小型可执行代码仓库任务集，而不是直接跑完整 SWE-bench。

### 9.1 环境机制

每个任务仓库必须：

- 是独立 git repo；
- 有初始 commit；
- 有确定性测试或 verifier；
- Agent 每一步 patch / command 都被记录；
- 失败节点可由 git commit、worktree、文件快照和进程环境复现；
- counterfactual branch 在独立临时 worktree 或容器中执行；
- 分支之间不得共享可变工作目录。

推荐：

```text
same base commit
├── factual worktree
├── counterfactual-1 worktree
├── counterfactual-2 worktree
└── counterfactual-k worktree
```

### 9.2 任务族设计

至少设计 4 类，每类包含多个表面变化、相同潜在规律的任务。示例：

1. **依赖管理器错误**
   - uv 项目误用 pip 全局升级；
   - poetry 项目绕过 lockfile；
   - 使用错误 extras；
   - held-out 变体改变包名和目录结构。

2. **配置优先级错误**
   - 环境变量覆盖配置文件；
   - CLI 参数覆盖默认值；
   - 相对路径依赖当前工作目录；
   - held-out 变体更换配置键名。

3. **边界与数据契约错误**
   - off-by-one；
   - 空列表 / None；
   - serialization schema 漏字段；
   - 时间边界和时区。

4. **异步 / 资源管理错误**
   - async 函数中阻塞调用；
   - 忘记 await；
   - 文件句柄或临时目录泄漏；
   - retry 导致重复副作用。

5. **工具使用策略错误（可选）**
   - 未先读测试即盲改；
   - 错误删除失败测试；
   - 大范围重构而非局部修复；
   - 忽略 lint/type checker 给出的直接证据。

每类应有：

- train / memory-building tasks；
- held-out transfer tasks；
- 至少一个容易产生负迁移的 near-miss 任务，用于测试 applicability 与 exclusions。

### 9.3 任务不能人为泄露答案

任务文本不直接提示“应该使用 uv sync”之类答案。潜在规律必须通过环境文件、测试输出和工具反馈推断。

---

## 10. Pivot 定位与替代动作生成

### 10.1 P0 Pivot Locator

第一版采用混合规则：

1. 收集最终失败前最近 N 个具有环境影响的动作；
2. 排除纯读取动作；
3. 根据测试输出、diff 和工具错误生成 1～3 个候选 pivot；
4. 让 Qwen3.8-27B 输出结构化归因，但不把其结论视为事实；
5. 实际替换候选动作并重放，以验证归因。

建议输出 schema：

```json
{
  "candidates": [
    {
      "step": 7,
      "suspected_mechanism": "Upgraded dependencies outside the lockfile",
      "confidence": 0.62,
      "minimal_intervention": "Replace command with uv sync"
    }
  ]
}
```

### 10.2 Counterfactual Proposer

输入：

- pivot 前状态摘要；
- 已选动作；
- 后续失败证据；
- 可用工具；
- 安全约束；
- 已检索 memory。

输出 K 个互相有实质差异的替代动作，并附：

- 预期机制；
- 预期结果；
- 前提；
- 风险；
- 与原动作的最小差异。

先生成较多候选，再执行：

- JSON 校验；
- 命令安全过滤；
- 语义去重；
- 与原动作等价性过滤；
- 预算排序。

### 10.3 分支选择

P0 可用简单分数：

\[
\text{priority}
=
\text{predictedGain}
+
\eta\cdot\text{diversity}
-
\rho\cdot\text{risk}
-
\kappa\cdot\text{executionCost}.
\]

真实执行 2～8 个候选；数量由预算配置决定。

---

## 11. 基线与消融

所有条件必须使用相同主模型、任务顺序、工具、上下文预算和最大步数。至少实现：

### B0. No Memory

每个任务独立执行，不读取过去经验。

### B1. Negative-Only Memory

失败后只保存：

```text
在类似状态下，不要再执行动作 A，因为它导致结果 Y。
```

这是用户原始观察中的传统做法。

### B2. Imagined Positive Memory

失败后保存模型提出的：

```text
改用动作 B 也许会成功。
```

但不执行验证。该基线用于直接测量“帮助 Agent 补出反事实思考”本身的收益和 memory poisoning 风险。

### B3. Paired but Unverified

同时保存事实失败分支和替代分支，但替代分支仍只有模型预测。用于分离“成对结构”与“执行验证”的作用。

### B4. ForkMem Verified

完整系统：同 checkpoint 分叉执行、证据状态、适用条件、置信度和检索门控。

### B5. Oracle Fork（可选上界）

在所有实际执行过的替代分支中，直接向后续 Agent 提供最佳分支，不计生成与检索错误。用于估计当前任务中反事实记忆的潜在上限。

### 必做消融

在计算允许时至少做两项：

- ForkMem 去掉 evidence weighting；
- ForkMem 去掉 applicability / exclusion；
- 只保存正向替代，不保存 factual failure；
- 单候选分支 vs 多候选分支；
- 不更新被证伪 memory；
- 只看语义相似度，不看结构化状态。

---

## 12. 评测指标

### 12.1 主要指标

1. **Held-out Task Success Rate**  
   在未用于形成 memory 的相似任务上的成功率。

2. **Repeated Failure Rate**  
   同一潜在错误模式在记忆形成后再次发生的比例。

3. **Counterfactual Precision**

\[
P(\Delta > 0\mid \widehat{\Delta}>0).
\]

模型预测某替代决策更好时，真实分叉执行中它实际更好的比例。

4. **Negative Transfer Rate**  
   由于检索并采用 memory，使原本可成功任务失败或 reward 降低的比例。

5. **Cumulative Regret**

\[
\sum_t (R_t^* - R_t).
\]

6. **Sample Efficiency**  
   达到给定成功率或错误复发率所需 episode 数。

### 12.2 系统指标

- branch validation yield；
- 每个有效 memory 的模型 token 成本；
- 每次失败平均执行分支数；
- wall-clock 和环境执行成本；
- memory 数量与 token 体积；
- retrieval precision；
- promotion / falsification 数量；
- 同一 memory 被复用次数；
- 置信度校准：Brier score / ECE（若样本足够）。

### 12.3 案例分析

最终报告至少展示：

- 一个 ForkMem 成功避免重复错误的案例；
- 一个未经验证反事实造成负迁移、而 ForkMem 阻止它的案例；
- 一个反事实被真实执行证伪并降级的案例；
- 一个 near-miss 状态因 exclusion 条件而没有错误套用 memory 的案例。

---

## 13. 工程与安全要求

### 13.1 Shell 执行

- 所有 coding task 在隔离 worktree、临时目录或容器中执行；
- 默认禁止 `sudo`、磁盘格式化、用户管理、kill 系统进程和访问敏感目录；
- 设置命令超时和最大输出；
- 对网络访问显式配置，benchmark 默认可关闭网络；
- 记录 exit code、stdout/stderr 摘要和完整日志路径；
- 不允许 Agent 通过删除或修改测试来“成功”，除非任务明确要求修改测试。

### 13.2 测试

必须包含：

- schema validation；
- evidence promotion / demotion；
- imagined memory 不得被当作 verified；
- 检索 applicability 和 exclusion；
- checkpoint 分叉共享同一前缀；
- worktree 隔离；
- failed branch 不污染其他 branch；
- deterministic replay；
- LLM JSON parser 异常处理；
- CLI smoke test；
- 一个最小 e2e 测试。

测试命令统一：

```bash
uv run pytest -q
```

代码质量：

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

如果 mypy 全量阻塞，可先限定核心模块，但需在 `RISKS.md` 说明。

### 13.3 日志和 provenance

每次模型调用记录：

- run_id；
- episode_id；
- branch_id；
- model ID；
- base URL 的非敏感部分；
- prompt template version；
- temperature / top_p / max_tokens；
- latency；
- token usage；
- parse / retry 状态。

每条 DecisionFork 记录：

- 代码 commit；
- 环境初始哈希；
- checkpoint ID；
- factual / counterfactual trajectory 路径；
- verifier 版本；
- memory schema version。

---

## 14. 七日执行纲领

该纲领用于控制范围，不要求机械按天分割。若某阶段提前完成，直接进入下一阶段。

### Day 1：环境核验与最小骨架

- 创建 `work/ForkMem/` 仓库；
- 核验 vLLM 服务、模型 ID 和高并发稳定性；
- 初始化 uv、pytest、ruff、mypy；
- 实现异步模型客户端和结构化输出；
- 写 `docs/environment.md`；
- 完成 LangGraph 最小 Agent graph；
- 创建 2 个 microrepo smoke tasks。

**退出标准**：Agent 可调用本机模型，在隔离 repo 中读取文件、修改代码并运行测试。

### Day 2：轨迹、checkpoint 与基础记忆

- 实现 trajectory recorder；
- 接入 checkpointer；
- 实现 `DecisionFork` schema；
- 实现 `ForkStore` Protocol 和开发存储；
- 实现 No Memory / Negative-Only baseline。

**退出标准**：一次失败 episode 可完整重放，负向 lesson 可跨 episode 检索。

### Day 3：反事实分叉闭环

- failure detector；
- pivot locator；
- counterfactual proposer；
- git worktree / 环境 checkpoint 分叉；
- branch executor；
- executable evaluator。

**退出标准**：从一个真实失败状态生成至少 3 个候选，并实际执行至少 2 个分支，形成第一条 DecisionFork。

### Day 4：证据生命周期与检索

- evidence promotion / falsification；
- applicability / exclusion；
- 结构化检索与注入；
- Imagined Positive / Paired Unverified / ForkMem Verified 基线；
- 针对 memory poisoning 的测试。

**退出标准**：未验证反事实与验证反事实在行为上有不同权限；证伪后不会继续以正向建议注入。

### Day 5：扩展 MicroRepo 与批量实验

- 扩展到至少 4 个任务族；
- 创建 train / held-out / near-miss split；
- 实现异步 benchmark runner；
- 并行运行主要基线；
- 检查实验是否存在明显混杂变量。

**退出标准**：形成第一版完整结果表，而不是只有单案例。

### Day 6：消融、稳定性与案例

- 运行随机种子或重复实验；
- 做至少两个消融；
- 计算 confidence interval；
- 选取成功、证伪、负迁移和 exclusion 案例；
- 修复可复现性问题；
- 视进度接入 Mem0 或 mini-swe-agent。

**退出标准**：主要结论有定量证据，至少一个结果不依赖单次随机输出。

### Day 7：整理成可展示项目

- 完善 README；
- 生成架构图；
- 完成 `docs/final_report.md`；
- 生成表格和图；
- 提供 3～5 分钟 demo 脚本；
- 清理仓库和一键复现命令；
- 写简历表述；
- 最终运行全部测试和 smoke benchmark。

---

## 15. CLI 目标

至少提供以下等价能力，命令名可调整：

```bash
# 检查本机模型服务
uv run forkmem inspect-vllm

# 跑一个任务
uv run forkmem run-task \
  --task data/task_specs/dependency_uv_01.yaml \
  --memory-mode verified

# 从已有失败轨迹生成并验证分叉
uv run forkmem fork \
  --episode runs/<episode_id>/trajectory.jsonl \
  --branches 4

# 运行主要基线
uv run forkmem benchmark \
  --config configs/experiments/core.yaml

# 重放最小案例
uv run forkmem replay \
  --case artifacts/cases/verified_uv_sync.json

# 构建报告
uv run forkmem report \
  --runs runs/ \
  --output docs/final_report.md
```

README 中必须给出从 clone / install 到 smoke test 的完整命令。

---

## 16. 配置建议

`configs/default.yaml` 建议包含：

```yaml
project:
  seed: 42
  run_dir: runs

llm:
  base_url_env: FORKMEM_LLM_BASE_URL
  api_key_env: FORKMEM_LLM_API_KEY
  model_env: FORKMEM_LLM_MODEL
  max_concurrency: 32
  timeout_seconds: 180
  max_retries: 3

agent:
  max_steps: 20
  max_context_tokens: 24000
  temperature: 0.3

counterfactual:
  pivot_candidates: 3
  proposed_actions: 12
  executed_branches: 4
  branch_max_steps: 12
  proposal_temperature: 0.8

memory:
  backend: langgraph
  max_retrieved: 4
  min_evidence_status: imagined
  verified_only_for_direct_advice: true
  preserve_versions: true

execution:
  shell_timeout_seconds: 120
  max_stdout_chars: 30000
  network_access: false
  use_git_worktrees: true

evaluation:
  repeats: 3
  bootstrap_samples: 2000
```

实际参数须依据模型上下文和机器环境校准，不要照抄后不验证。

---

## 17. 最终交付物

仓库最终至少包含：

1. **可运行代码**：完整 P0 pipeline；
2. **测试**：unit、integration、e2e；
3. **MicroRepo benchmark**：任务定义、split 和 deterministic verifier；
4. **实验配置与日志索引**；
5. **结果表格与图**；
6. **至少四个代表性案例**；
7. **架构文档**；
8. **最终研究报告**；
9. **一键 smoke demo**；
10. **简历描述**；
11. **已知限制和失败路线登记**；
12. **最终 manifest**，记录关键文件、commit 和结果摘要。

建议最终 manifest：

```json
{
  "project": "ForkMem",
  "commit": "<git-sha>",
  "model": "<served-model-id>",
  "core_experiment": "<config-path>",
  "main_table": "artifacts/tables/main_results.csv",
  "final_report": "docs/final_report.md",
  "tests_passed": true,
  "known_limitations": []
}
```

---

## 18. 最终报告必须回答的问题

1. 未验证的向上反事实记忆是否比 negative-only memory 更有帮助？
2. 它是否也更容易造成负迁移或错误自我确认？
3. 执行验证对 counterfactual precision 提升多少？
4. 成对保存 factual / counterfactual branch 是否比只保存正向 lesson 更有效？
5. applicability 和 exclusion 能否阻止 near-miss 任务上的错误迁移？
6. ForkMem 的收益是否值得额外 branch execution 成本？
7. 哪些失败最适合形成 ForkMem，哪些失败不适合？
8. 当前证据支持什么结论，不支持什么结论？

报告应明确区分：

- 观察到的事实；
- 程序化验证结果；
- LLM 预测；
- 统计不确定性；
- 推测性解释。

---

## 19. 建议的项目主张与简历表述

### 项目主张

> Existing agents remember what went wrong. ForkMem also explores the roads not taken, but stores them as evidence-graded hypotheses rather than invented facts.

中文：

> 现有 Agent 记住走错的路；ForkMem 进一步探索没走的路，但通过证据分级、环境分叉和真实执行，避免把想象伪装成经历。

### 简历模板

> **ForkMem — Execution-Verified Counterfactual Memory for LLM Agents**  
> Built a stateful agent memory system that turns failed decisions into paired factual and counterfactual branches. Implemented checkpoint-based environment forking, parallel alternative rollouts, evidence-graded memory promotion, applicability-aware retrieval, and falsification of incorrect memories. Evaluated against no-memory, negative-only, and unverified-counterfactual baselines using a local Qwen3.8-27B vLLM deployment on 4×A100 GPUs, measuring held-out task success, repeated failure, counterfactual precision, negative transfer, and inference cost.

最终数字必须来自真实实验，不得使用占位结果冒充完成情况。

---

## 20. 近邻工作与框架资料

执行 Agent 应在项目开始时进一步核验最新版本、后续论文和代码，但以下资料可作为起点。

### 近邻研究

- Reflexion: Language Agents with Verbal Reinforcement Learning  
  https://arxiv.org/abs/2303.11366
- ECHO: Sample-Efficient Online Learning in LM Agents via Hindsight Trajectory Rewriting  
  https://arxiv.org/abs/2510.10304
- CausalFlow: Causal Attribution and Counterfactual Repair for LLM Agent Failures  
  https://arxiv.org/abs/2605.25338
- EDV: Escaping the Self-Confirmation Trap: An Execute-Distill-Verify Paradigm for Agentic Experience Learning  
  https://arxiv.org/abs/2606.24428
- MERIT: Causal Episodic Memory for Feedback-Driven Agent Repair  
  https://arxiv.org/abs/2608.05906

重点比较维度：

- 是否保留 factual 与 counterfactual 的永久配对；
- counterfactual 是否通过同状态真实重放验证；
- 是否有长期证据状态和可证伪生命周期；
- 是否支持未来 experiment debt；
- 是否系统评测未验证反事实造成的 memory poisoning / negative transfer。

### 框架资料

- LangGraph Persistence  
  https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph Checkpointers  
  https://docs.langchain.com/oss/python/langgraph/checkpointers
- LangGraph Stores  
  https://docs.langchain.com/oss/python/langgraph/stores
- LangGraph Memory  
  https://docs.langchain.com/oss/python/concepts/memory
- LangMem  
  https://github.com/langchain-ai/langmem
- Mem0  
  https://docs.mem0.ai/introduction
- Letta Memory  
  https://docs.letta.com/agent-sdk/memory/
- mini-swe-agent local model guide  
  https://mini-swe-agent.com/latest/models/local_models/

---

## 21. 立即开始时的首轮动作

执行 Agent 收到本任务书后，应直接执行以下流程：

```bash
mkdir -p work/ForkMem
cd work/ForkMem
git init
```

然后：

1. 检查当前目录是否已有文件，避免覆盖用户工作；
2. 检查 Python、uv、git、Docker、PostgreSQL 可用性；
3. 发现并 smoke-test GPU 4～7 上的 vLLM Qwen3.8-27B 服务；
4. 创建 `docs/environment.md` 和 `.env.example`；
5. 初始化 Python 项目和测试；
6. 写出最小 `DecisionFork` schema；
7. 创建第一个确定性 microrepo；
8. 跑通一个不带 memory 的 Agent episode；
9. 制造或观察一次真实失败；
10. 从失败节点分叉执行两个替代动作；
11. 保存项目第一条经过执行验证的 ForkMem。

首轮成功标志不是“项目目录已搭好”，而是：

> 同一失败 checkpoint 被成功分成至少两个隔离分支，其中一个替代分支由真实测试验证，并以正确证据等级写入长期 DecisionFork store。

