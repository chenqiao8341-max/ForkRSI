# ForkRSI

ForkRSI 在 ForkMem 的执行验证与反事实记忆框架上，研究固定模型权重条件下的递归自改进：记忆编译器 **C** 提炼和注入经验，改进方法 **I** 根据真实执行证据提出 C 的修改，并生成新的 I。版本、父版本、原始提案、执行结果和费用都保留；任务执行器、verifier 和真实性检查不参与自修改。

本轮使用 ModelScope 下载的 **Qwen3.5-4B**，单张 RTX 3090、BF16、vLLM 推理、8 并发，不训练权重。实际递归生成闭环已完成，但本轮结果没有证明反事实证据或演化后的 I 带来更好的迁移效果。

## 研究结果与入口

统一 vLLM 后端完成 7 组 × 8 个语义任务，共 56 项最终评估。flat verified 完整通过 **4/8**，成功源演化 C 为 **2/8**，配对搜索谱系演化 C 为 **1/8**。相同 C0 的 I 重置比较中，I0 选中后代通过 **2/4**，演化 I1 为 **1/4**。这是小样本试验；vLLM 最终评估是已选策略在同一任务组上的后端复测，不能当作新的未见任务或独立样本。

- [目标文档](ForkRSI_目标文档.md)：研究主目标、约束和验收。
- [首轮研究报告](docs/forkrsi/report.md)：完整结果、负结果、费用及适用范围。
- [复现说明](docs/forkrsi/reproduce.md)：运行环境、模型 SHA、封存协议与全量记录恢复。
- [工作记录](docs/forkrsi/progress.md)及[文献核对](docs/forkrsi/research.md)。
- [正式统计](artifacts/forkrsi/pilot-vllm-v1/summary.json)与[逐项结果](artifacts/forkrsi/pilot-vllm-v1/final-cells.json)。

ForkMem 基线的原始说明完整保存在 [README.forkmem.md](README.forkmem.md)，其既往结果与本轮 ForkRSI 结果分别报告。Python 包和 CLI 沿用 `forkmem` 名称，便于保留执行记录及接口兼容性。

## 代码布局

| 路径 | 内容 |
|---|---|
| `src/forkmem/rsi/` | C/I 配置、编译、改进、版本账本及研究流程 |
| `src/forkmem/` | 模型客户端、任务执行、反事实分叉、记忆、沙箱及评估 |
| `scripts/` | 来源收集、搜索/选择/重置、vLLM 服务、并发评估、审计与导出 |
| `configs/forkrsi/` | 固定研究协议、来源配置、模型下载依赖及 vLLM 参数 |
| `data/forkrsi/` | 预先分离的开发、选择、重置和最终任务 |
| `tests/` | 单元、集成与端到端测试 |
| `artifacts/forkrsi/` | 模型文件 SHA、运行环境、审计及正式结果 |
| `artifacts/forkrsi/operational-scripts/` | 实际下载、部署、迁移与封存审计辅助脚本的原样快照及 SHA 清单 |

## 获取与运行

```bash
git clone git@github.com:chenqiao8341-max/ForkRSI.git
cd ForkRSI
```

本地代码仓库位于 `/home/qiao/work/ForkRSI`；GPU 实验工作目录为服务器上的 `/root/autodl-tmp/ForkRSI`。GPU 环境适配和历史检查点包含该服务器绝对路径。下载、部署及原始记录复核请按[复现说明](docs/forkrsi/reproduce.md)执行。

原项目元数据要求 Python 3.13；本轮实际验证的是服务器 Python 3.12.3 适配环境，vLLM 使用独立环境。已建立的服务器任务环境可执行：

```bash
cd /root/autodl-tmp/ForkRSI
source scripts/forkrsi_env.sh
python -m pytest -q
python -m ruff check src scripts tests
python -m mypy src
```

[.env.forkrsi.example](.env.forkrsi.example)记录本轮 OpenAI 兼容接口变量；代码不自动加载 dotenv。服务通过 `scripts/start_forkrsi_vllm.sh` 和 `scripts/serve_forkrsi_vllm.py` 启动，配置见 [vllm-service.json](configs/forkrsi/vllm-service.json)。新实验须先检查预算、使用新输出目录并重新预注册和封存；本轮已打开的最终任务不能用于后续调参。

## 代码与执行记录

Git 保留 ForkMem 基线到 ForkRSI 首轮报告的完整提交历史。`forkrsi-prototype` 保留研究交付提交；`main` 在其上补充仓库说明和辅助脚本快照。这些整理修改不改变已封存的策略、verifier 或实验结果。

原始轨迹、SQLite 账本、失败尝试和原生检查点另存于本地 `/home/qiao/work/ForkRSI_delivery_20261001`，其 `forkrsi-records.tar.gz`、`forkrsi-history.bundle`、`manifest.json` 和 `acceptance-final.json` 可核验完整交付。模型权重、虚拟环境及原始 `runs/` 不纳入 Git；恢复原始记录后才能重新进行认证汇总。模型文件须与 [model-files.json](artifacts/forkrsi/model-files.json) 中的 SHA 逐项匹配。
