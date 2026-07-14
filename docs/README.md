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
11. 从 Task029 起，每个新 Task 必须同时维护结构化 `outcomes/summary.md` 和 `docs/development_progress.md`；详细档案与项目级回顾都不可省略，一句状态或纯链接不构成完成。完整框架见 [`task_retrospective_standard.md`](task_retrospective_standard.md)。

<!-- REPOSITORY_WORK_PRINCIPLES_END -->

## 项目总览

| 文件 | 内容 |
|---|---|
| [`project_service_requirements_and_forward_model_roadmap.md`](project_service_requirements_and_forward_model_roadmap.md) | 参数反演服务需求、核心观测量、0.7 nm 资源约束、当前能力和 Task031–Task035 前向模型路线；后续任务的上位需求基线 |
| [`project_service_requirements_phase1_scope.md`](project_service_requirements_phase1_scope.md) | 第一阶段冻结范围：13.5 nm、固定 Si 光学常数、1–10° 掠入射角、S/P 偏振；后续前向模型资格化不得越界宣传 |
| [`repository_work_principles.md`](repository_work_principles.md) | 不得删除的分支、任务、审查、合并、结果与数值可信度规则 |
| [`task_retrospective_standard.md`](task_retrospective_standard.md) | 从 Task029 起适用于所有新 Task 的阶段回顾标准：背景、基线、方法、结果、解释、负结果、决策、局限、下一步与证据入口 |
| [`development_progress.md`](development_progress.md) | Task000 起的项目发展时间线；每个新 Task 必须按阶段回顾标准留下可理解的结构化记录 |
| [`capability_matrix.md`](capability_matrix.md) | 当前 2D/3D 功能状态，以及 Quick Start、Theory、Walkthrough、Benchmark 映射 |
| [`quick_start.md`](quick_start.md) | 全局 Docker/benchmark 最短入口；详细功能教程见 [`../notes/quick_start/README.md`](../notes/quick_start/README.md) |
| [`architecture_overview.md`](architecture_overview.md) | 当前模块边界与主要数据流 |
| [`solver_guide.md`](solver_guide.md) | direct/iterative 求解器选择与边界 |
| [`iterative_solver_ports.md`](iterative_solver_ports.md) | Task27/30/31 入口、outer KSP 与 local smoother 合法性、组件 flags、资格化和资源选择规则 |
| [`task032_hybrid_fem_modal_direct_baseline/README.md`](task032_hybrid_fem_modal_direct_baseline/README.md) | Task032 新本地目录迁移、Hybrid FEM–Modal direct 路线、内存约束和执行入口 |
| [`benchmark.md`](benchmark.md) | Benchmark 分层设计和当前结果；编号 cases 见 [`../benchmarks/cases/README.md`](../benchmarks/cases/README.md) |
| [`../notes/theory/README.md`](../notes/theory/README.md) | 从 Maxwell 强/弱式到 DtN、RTA、凝聚、迭代 PC 和 Hybrid FEM–Modal 的规范理论 |
| [`../notes/reference/code_walkthrough.md`](../notes/reference/code_walkthrough.md) | 逐模块/函数、对象生命周期与 equation-to-code 导读 |

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
| Task028 | 阶段收口、选择性整合、benchmark | 已以 merge commit `2f9e56d` 进入 master |
| Task029 | Stage4 direct memory forensics | `diagnostic_success`；Review V2 已关闭并以 `bfb6586e` 合入 master |
| Task030 | H(curl) hierarchy infrastructure + compact physical-slab low-memory profile | `workstation_memory_success_with_qualifications`；已以 merge commit `545165b3` 合入 master；p/h multigrid solver-negative |
| Task031 | compact physical-slab PC memory-first structural optimization | `strong_memory_success_slow_but_memory_efficient`；Review V2 PASS；允许合入 master |
| Task032 | Hybrid FEM–Modal direct baseline | Phase 0/1/2/3 complete；Phase 4 stable propagation next |

## 当前任务

| 任务 | 目录 | 状态 |
|---|---|---|
| Task026 | `task026_auxiliary_free_3d_modal_port/` | 已审查；稳定凝聚组件由Task28抽取 |
| Task027 | `task027_mesh_independent_spectral_schwarz_pc/` | 已审查；fixed coarse成功，spectral失败 |
| Task028 | `task028_stage_consolidation_master_integration_benchmarks/` | V4 完成并已合并 `master` |
| Task029 | `task029_stage4_direct_memory_forensics/` | 已按用户许可合入 master；不提升失败 direct profile |
| Task030 | `task030_multilevel_hcurl_low_memory_iterative_solver/` | V3 最终审查通过并已选择性合入 master；ordinary default 不变 |
| Task031 | `task031_compact_physical_slab_memory_optimization/` | Review V2 PASS；等待用户执行显式 merge commit |
| Task032 | `task032_hybrid_fem_modal_direct_baseline/` | Phase 1/2/3/4 clean records complete；Phase 5 coupling 与 Hybrid pending |

## Task28 审计入口

| 文件 | 内容 |
|---|---|
| `outcomes/task000_task027_progress.csv` | 逐任务结构化状态 |
| `outcomes/task000_task027_summary.md` | 阶段结论与纠偏 |
| `outcomes/selective_merge_manifest.csv` | 文件级整合决策 |
| `outcomes/benchmark_gate.csv` | 分层benchmark gate |
| `outcomes/merge_recommendation.md` | Codex 首轮合并建议 |
| `review_report_v1.md` | ChatGPT V1 审查：benchmark 边界、脚本、自动 Gate、环境、文档和 sm2 测试 |
| `response_v1.md` | Codex V1 回应：六个 P0 基本关闭 |
| `review_report_v2.md` | ChatGPT V2 审查：重构 Quick Start、Code Walkthrough、Theory、main.py PyCharm preset 与编号功能 Benchmark |
| `response_v2.md` | Codex V2 回应：五层文档架构、命名 preset、metadata/checker、测试与 2D lossy RTA 修复 |
| `review_report_v3.md` | ChatGPT V3 审查：修复 Walkthrough 技术错误、扩展可跟随教程、区分 demo/target preset、补 case-contained records/config/run/Gate 和 2D lossy canonical evidence |
| `response_v3.md` | Codex V3 回应：15 项 P0、3 项 P1、Case002/003 canonical、17 preset、115 tests 与 143/143 Gate |
| `review_report_v4.md` | ChatGPT V4 最终验收：核心、文档和 Benchmark 通过；要求 tracked-source-clean Gate、真实 image digest 和最终 head checker；建议 Task029 先做 Stage4 直接法内存剖析与公共装配优化 |
| `response_v4.md` | Codex V4 回应：5 项 tracked-source-clean Gate、runner 强制真实 digest、148/148 checker 与最终实现提交验证 |

## Task029 任务与审查入口

| 文件 | 内容 |
|---|---|
| [`task029_stage4_direct_memory_forensics/task.md`](task029_stage4_direct_memory_forensics/task.md) | 直接法阶段内存剖析、矩阵/factor inventory、对象生命周期与预分配优化；h5/h3 必跑，h2 仅在显著降内存且预测低于安全上限后解锁 |
| [`task029_stage4_direct_memory_forensics/task_comsol_reference_addendum.md`](task029_stage4_direct_memory_forensics/task_comsol_reference_addendum.md) | COMSOL 只能作为另一机器、四面体、零级端口的定性内存参考；FEniCS 保留全传播衍射级，不比较跨机器时间 |
| [`task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md`](task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md) | 用户提供的 COMSOL MUMPS/GMG 内存报告 |
| [`task029_stage4_direct_memory_forensics/outcomes/summary.md`](task029_stage4_direct_memory_forensics/outcomes/summary.md) | baseline、候选筛选、KSPSetUp 主峰、`diagnostic_success` 与 h2 not-run |
| [`task029_stage4_direct_memory_forensics/review_report_v1.md`](task029_stage4_direct_memory_forensics/review_report_v1.md) | 接受内存诊断，要求线程验证和文档收口 |
| [`task029_stage4_direct_memory_forensics/review_report_v1_p0c_addendum.md`](task029_stage4_direct_memory_forensics/review_report_v1_p0c_addendum.md) | Task 回顾长期合同 |
| [`task029_stage4_direct_memory_forensics/response_v1.md`](task029_stage4_direct_memory_forensics/response_v1.md) | 线程审计、结构化回顾和文档同步 |
| [`task029_stage4_direct_memory_forensics/review_report_v2.md`](task029_stage4_direct_memory_forensics/review_report_v2.md) | 停止 direct 微调；基础设施可合并，性能候选不提升 |
| [`task029_stage4_direct_memory_forensics/response_v2.md`](task029_stage4_direct_memory_forensics/response_v2.md) | 最终身份与合并收口 |
| [`task029_stage4_direct_memory_forensics/outcomes/threaded_direct_capability_audit.md`](task029_stage4_direct_memory_forensics/outcomes/threaded_direct_capability_audit.md) | 当前 image threaded direct unavailable |
| [`task029_stage4_direct_memory_forensics/outcomes/merge_recommendation.md`](task029_stage4_direct_memory_forensics/outcomes/merge_recommendation.md) | 合并边界 |
| [`task029_stage4_direct_memory_forensics/outcomes/h2_launch_decision.md`](task029_stage4_direct_memory_forensics/outcomes/h2_launch_decision.md) | h2 not-run Gate |

## Task030 任务与审查入口

| 文件 | 内容 |
|---|---|
| [`task030_multilevel_hcurl_low_memory_iterative_solver/task.md`](task030_multilevel_hcurl_low_memory_iterative_solver/task.md) | 多路线 H(curl) 低内存迭代任务书 |
| [`task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/summary.md`](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/summary.md) | transfer/Galerkin 基础设施、p/h 负结果和 compact profile h5/h3/h2 证据 |
| [`task030_multilevel_hcurl_low_memory_iterative_solver/review_report_v1.md`](task030_multilevel_hcurl_low_memory_iterative_solver/review_report_v1.md) | V1：provenance、数值 Gate、manifest 和准确命名 |
| [`task030_multilevel_hcurl_low_memory_iterative_solver/response_v1.md`](task030_multilevel_hcurl_low_memory_iterative_solver/response_v1.md) | V1 回应：203 项 Gate、统一身份和 factor-nnz 限定 |
| [`task030_multilevel_hcurl_low_memory_iterative_solver/review_report_v2.md`](task030_multilevel_hcurl_low_memory_iterative_solver/review_report_v2.md) | V2：clean h5/h3 加固与 validated infrastructure / failed lanes 选择性合并边界 |
| [`task030_multilevel_hcurl_low_memory_iterative_solver/response_v2.md`](task030_multilevel_hcurl_low_memory_iterative_solver/response_v2.md) | V2 回应：final-HEAD clean h5/h3、historical h2、API 隔离、文档与最终验证 |
| [`task030_multilevel_hcurl_low_memory_iterative_solver/review_report_v3.md`](task030_multilevel_hcurl_low_memory_iterative_solver/review_report_v3.md) | V3 最终审查：通过并允许按边界选择性合并，Task031 可从 clean master 启动 |

## Task031 任务入口

| 文件 | 内容 |
|---|---|
| [`task031_compact_physical_slab_memory_optimization/task.md`](task031_compact_physical_slab_memory_optimization/task.md) | 内存优先结构性优化：低存储 Krylov、assembled-F-free public MPC form action、提前释放、slab factor 精确去重、overlap/slab 重构和选择性局部因子；h2 条件解锁 |
| [`task031_compact_physical_slab_memory_optimization/outcomes/summary.md`](task031_compact_physical_slab_memory_optimization/outcomes/summary.md) | clean h5/h3/h2、7.898 GiB external simultaneous peak、PC/form-action/lifecycle 证据、负结果与合并边界 |
| [`task031_compact_physical_slab_memory_optimization/outcomes/h2_memory_prediction.md`](task031_compact_physical_slab_memory_optimization/outcomes/h2_memory_prediction.md) | 8.501/8.587 GiB 两套中心预测、9.447 GiB 保守上界与实测对照 |
| [`task031_compact_physical_slab_memory_optimization/review_report_v1.md`](task031_compact_physical_slab_memory_optimization/review_report_v1.md) | V1：数值与绝对内存通过；要求同步 master、建立端口文档并收紧 form-action、内存口径和 profile 身份 |
| [`task031_compact_physical_slab_memory_optimization/response_v1.md`](task031_compact_physical_slab_memory_optimization/response_v1.md) | V1 回应：项目规划保护、端口矩阵、术语/口径修正、选择性合并边界和轻量验证 |
| [`task031_compact_physical_slab_memory_optimization/review_report_v2.md`](task031_compact_physical_slab_memory_optimization/review_report_v2.md) | V2 最终验收：PASS，允许合入 master，并批准 clean master 后启动 Task032 |
| [`../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md`](../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md) | Case070 合同、轻量 records、自动 Gate 与复现入口 |

## Task032 任务入口

| 文件 | 内容 |
|---|---|
| [`task032_hybrid_fem_modal_direct_baseline/README.md`](task032_hybrid_fem_modal_direct_baseline/README.md) | 执行顺序、新本地目录、冻结物理边界和入口文件 |
| [`task032_hybrid_fem_modal_direct_baseline/task.md`](task032_hybrid_fem_modal_direct_baseline/task.md) | 新目录迁移、二维截面本征模、稳定双向传播、匹配接口、增广 direct、Modal-Schur、内存 Gate、Case080 与验收标准 |
| [`../notes/theory/hybrid_fem_modal_domain_decomposition.md`](../notes/theory/hybrid_fem_modal_domain_decomposition.md) | Hybrid FEM–Modal 的 Maxwell 分解、QEP、双正交、传播、接口投影、Schur 消元、内存复杂度和验证阶梯 |

完整任务目录仍按 `task.md -> outcomes -> development_progress -> review_report/response` 闭环。从 Task029 起，所有新 Task 都必须遵循 [`task_retrospective_standard.md`](task_retrospective_standard.md)。Task032 只能在 Task031 合入 master 后，从新本地目录的 clean `origin/master` 创建执行分支；旧目录保留为只读历史基线。
