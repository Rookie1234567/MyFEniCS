# 任务流转索引

`docs/taskXXX_*/` 保存 ChatGPT 任务书、Codex outcomes 和审查报告；`notes/` 只保存理论、学习和解释性文档。Task28 从干净 master 选择性归档 Task021-Task027 的核心闭环文件，不复制 raw runs。

<!-- REPOSITORY_WORK_PRINCIPLES_BEGIN -->

## 工作规则（不得删除）

> 本节是仓库治理保护区。完整规则见 [`repository_work_principles.md`](repository_work_principles.md)，并由 `src/test/test_24_repository_work_principles.py` 检查；文档整理时不得删除。

1. 开始新一轮前，读取上一轮任务目录中的 `review_report*.md`、`response*.md`（若存在）或 outcomes summary。
2. 同时读取本轮任务目录中的 `task.md`。
3. 完成工作后，把本轮结果写入该任务目录的 `outcomes/`。
4. 审查后，把 `review_report_vN.md` 提交到同一个任务目录；Codex 通过 `response_vN.md` 回应并在同一分支修正。
5. 普通大体积计算结果保留在 `results/`，Benchmark 重型 artifact 保留在 `benchmarks/artifacts/`，均不提交 Git。
6. **ChatGPT 不创建执行分支；执行分支由 Codex 创建。**
7. **failed solver code 默认留在对应 research branch，不合并 production；docs / review / 精简 outcomes 可以 selective merge。**
8. 禁止整体合并大型 research branch；ordinary solver default 不得静默改变；未通过最终 review 前不合并 `master`。
9. Codex 不得删除或改写 ChatGPT 的 `task.md`、`review_report*.md`；需要纠正时新增 response，而不是覆盖审查记录。
10. solver 成功使用 full explicit true residual 判断，official R/T/A 只能从通过 residual Gate 的场计算。

<!-- REPOSITORY_WORK_PRINCIPLES_END -->

## 项目总览

| 文件 | 内容 |
|---|---|
| [`repository_work_principles.md`](repository_work_principles.md) | 不得删除的分支、任务、审查、合并、结果与数值可信度规则 |
| [`development_progress.md`](development_progress.md) | Task000-Task028 分阶段开发内容、关键结果、失败路线、当前能力与未完成事项 |
| [`capability_matrix.md`](capability_matrix.md) | 当前 2D/3D 功能状态与限制；Task28 V1 要求继续补全 |
| [`quick_start.md`](quick_start.md) | 用户运行入口；Task28 V1 要求继续扩充环境、结果读取和可视化流程 |
| [`architecture_overview.md`](architecture_overview.md) | 当前模块边界与主要数据流 |
| [`solver_guide.md`](solver_guide.md) | direct/iterative 求解器选择与边界；Task28 V1 要求补全 OOC/BLR/condensed 路线 |
| [`benchmark.md`](benchmark.md) | Benchmark 分层设计和当前结果 |

## 阶段索引

| 范围 | 主题 | 阶段结论 |
|---|---|---|
| Task000-Task004 | 初始审查、功率修正、小单元回归 | 基础工程链稳定 |
| Task005-Task008 | 内存诊断、official RTA、目标 direct | p2 h2 direct reference |
| Task009-Task014a | 黑盒迭代、BLR、AMS/HX real split | direct备用成立，最小AMS block失败 |
| Task015-Task019 | 边界慢方向与 sampled-Schur | p1正信号不迁移p2 |
| Task020-Task025 | wave-aware、FE response、Schur、cached-Q | 研究机制与基础设施，未达production |
| Task026 | auxiliary-free exact condensation | 稳定算子基础 |
| Task027 | fixed coarse physical-slab MPI4 | h5/h3/h2 production residual候选 |
| Task028 | 阶段收口、选择性整合、benchmark | 核心整合通过；V1 要求修正文档、环境与 benchmark 自动化 |

## 当前任务

| 任务 | 目录 | 状态 |
|---|---|---|
| Task026 | `task026_auxiliary_free_3d_modal_port/` | 已审查；稳定凝聚组件由Task28抽取 |
| Task027 | `task027_mesh_independent_spectral_schwarz_pc/` | 已审查；fixed coarse成功，spectral失败 |
| Task028 | `task028_stage_consolidation_master_integration_benchmarks/` | `response_v1.md` 已完成；六个P0已关闭，等待Review V2，暂不合并master |

## Task28 审计入口

| 文件 | 内容 |
|---|---|
| `outcomes/task000_task027_progress.csv` | 逐任务结构化状态 |
| `outcomes/task000_task027_summary.md` | 阶段结论与纠偏 |
| `outcomes/selective_merge_manifest.csv` | 文件级整合决策 |
| `outcomes/benchmark_gate.csv` | 分层benchmark gate |
| `outcomes/merge_recommendation.md` | Codex 首轮合并建议 |
| `review_report_v1.md` | ChatGPT V1 正式审查；要求修正 benchmark 边界、脚本、自动 Gate、环境、文档和 sm2 测试 |
| `response_v1.md` | Codex逐项回应；58项自动Gate、统一限定环境、扩充文档和sm2测试均完成 |

完整任务目录仍按 `task.md -> outcomes -> review_report/response` 闭环。Codex 不生成或改写 ChatGPT task/review 内容；发现问题后在同一分支提交 `response_v1.md` 并继续修正。
