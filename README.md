# FEniCSx 周期 Maxwell / Floquet Demo

本项目用于验证二维、三维频域 Maxwell 有限元、Floquet 周期约束、DtN 模态端口、official R/T/A 与材料体吸收。当前阶段已经具备目标三维 EUV 光栅的 direct reference，以及显式 opt-in 的 MPI4 workstation 迭代候选。

<!-- REPOSITORY_WORK_PRINCIPLES_BEGIN -->

## 仓库工作原则（不得删除）

> 本节属于仓库治理契约，README 精简、文档重构和阶段合并时均不得删除或弱化。完整解释见 [`docs/repository_work_principles.md`](docs/repository_work_principles.md)，并由 `src/test/test_24_repository_work_principles.py` 自动检查。

1. 开始新一轮前，读取上一轮任务目录中的 `review_report*.md`、`response*.md`（若存在）或 `outcomes/summary.md`。
2. 同时读取本轮任务目录中的 `task.md`，不得只根据旧 README、聊天摘要或任务名称执行。
3. 完成工作后，把本轮结果、测试、Gate 和下一步判断写入该任务目录的 `outcomes/`。
4. 审查报告保存在同一任务目录；发现问题后在同一执行分支提交 `response_vN.md` 并继续修正。
5. 普通大体积结果保存在 `results/`；Benchmark 重型 artifact 保存在 `benchmarks/artifacts/`；二者均不提交 Git。
6. **ChatGPT 不创建执行分支；执行分支由 Codex 创建。** Codex 不得删除或改写 ChatGPT 已提交的 `task.md` 和 `review_report*.md`。
7. **failed solver code 默认留在对应 research branch，不合并 production；docs、review、精简 outcomes 和理论笔记可以 selective merge。**
8. 禁止整体合并大型 research branch；必须从 clean base 使用 `selective_merge_manifest` 抽取已验证组件。
9. ordinary solver default 不得静默改变；新求解器在审查通过前必须保持显式 opt-in，未通过最终 review 前不合并 `master`。
10. solver 成功必须以 full explicit true residual 为准；official R/T/A 只能从通过 residual Gate 的场计算，probe/flux 近似量默认仅作 diagnostic。
11. 从 Task029 起，每个新 Task 必须同时维护结构化 `outcomes/summary.md` 和 `docs/development_progress.md`；两者分别承担详细技术档案与项目级回顾，一句状态或纯链接不构成完成。完整框架见 [`docs/task_retrospective_standard.md`](docs/task_retrospective_standard.md)。
12. 从 Task032 起，中型和大型算法、物理或性能任务的 `outcomes/summary.md` 必须以表格作为主要信息载体；至少包含最终状态/范围、实施或实验矩阵、关键数值结果、资源或性能结果、失败与未运行项、合并和下一步决策表。每张表必须标明单位、baseline、数据身份（`measured` / `derived` / `predicted` / `not_run`）和证据入口；叙述用于解释表格，不得替代表格。
13. **Markdown 公式和表格的可渲染性属于交付 Gate。** 独立公式使用空行隔开的 `$$` block；不得把需要渲染的公式放进代码围栏；表格列数必须一致，单元格竖线必须转义或改写，多行公式不得放进表格。ChatGPT 与 Codex 提交前都必须检查 GitHub rendered view；原始 LaTeX、破损表格或错位列均视为文档 Gate 失败。详见 [`docs/markdown_rendering_standard.md`](docs/markdown_rendering_standard.md)。

<!-- REPOSITORY_WORK_PRINCIPLES_END -->

## 当前能力

| 能力 | 状态 |
|---|---|
| 2D Floquet + DtN | 稳定；具体组合和 backend 限制见能力矩阵 |
| 3D Stage1-Stage4 staged workflow | 稳定 |
| p=2 topological-trace Floquet MPC | 稳定 |
| p=3/p=4 sparse distributed Floquet MPC | Case090 144 PDE 核心资格通过；显式高阶入口 |
| p=3/p=4 cross-section QEP | MPI1 数值分片通过；全局 aggregate 尚未资格化 |
| complex refractive index 与 A_volume | 稳定 |
| DtN modal official R/T/A | 稳定 |
| p=2 h=2 direct reference | 已验证 |
| exact auxiliary condensation | 稳定模块 |
| p=2 h=5/3/2 MPI4 physical-slab iterative | 显式 opt-in 候选 |
| Hybrid FEM–Modal h5/h3 direct reference | 13.5 nm 工程成功；Case080 302/302；显式 opt-in |
| Hybrid vs full3D | p2/h5、p2/h3 同阶同网格一致；p3/p4 同阶 reference 尚无 |
| Hybrid h2 direct | `not_run_by_gate` |
| 当前 direct Hybrid at 0.7 nm | 不具资源可行性；需 h/p + scalable modal core + iterative |
| h=1.5 production solve | 未完成 |
| spectral/GenEO/HPDDM research routes | 不进入普通 API |

## 快速入口

普通入口保持既有 direct 默认：

```bash
python -m src.runners.run_cases
python -m src.runners.run_3d_cases --stage-case stage1_airbox
python -m src.runners.run_3d_cases --stage-case stage4_block_grating
```

经过验证的 workstation profile 必须显式调用：

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --h-nm 2 \
  --record benchmarks/records/workstation_p2_h2_mpi4.json
```

普通运行的完整网格、场和日志写入 `results/`，不提交 Git。正式 benchmark 重型输出写入 `benchmarks/artifacts/`，轻量摘要放在 `benchmarks/records/`。Task032 已在 13.5 nm h5/h3 上证明 Hybrid 与同网格 full3D 等价并降低 rows/NNZ；h3 memory-minimal simultaneous RSS 为 3.224 GiB，h2 因两类预测未过 4/5 GiB Gate 而未运行，1–10° S/P 的 30/30 仅是接口 smoke。Task033 已完成 p3/p4 高阶 Floquet、QEP/匹配迹和 p3/h5 同阶 closure；Review V5 的 fixed-p 减缩研究进一步得到 p3/h10 精度负结果和 p3/h7.5 带资格的等精度工程正结果，后者相对 p2/h3 将 FE DoF/local-system rows/total rows/factor-inventory NNZ/memory/time 分别改善 2.571x/2.567x/2.548x/3.557x/1.606x/1.331x。p4 target 当前主机资源受限，native variable-p H(curl) 未资格化；p2 h-adaptive、buffer 和 1 TiB 更新仍未完成。ordinary default 未改变。

## 文档导航

| 文档 | 内容 |
|---|---|
| [仓库工作原则](docs/repository_work_principles.md) | 不得删除的分支、审查、结果、合并和数值可信度规则 |
| [Markdown 渲染标准](docs/markdown_rendering_standard.md) | 公式、表格、delimiter、竖线、预览和文档 Gate |
| [Task 阶段回顾标准](docs/task_retrospective_standard.md) | 从 Task029 起所有新 Task 的强制 outcomes 与 development progress 写作/审查合同 |
| [开发进度](docs/development_progress.md) | Task000-Task032 分阶段开发内容、关键结果、失败路线与当前进展 |
| [快速开始](docs/quick_start.md) | Windows Docker、2D/3D、direct/workstation完整命令与资源边界 |
| [架构概览](docs/architecture_overview.md) | 模块边界与数据流 |
| [求解器指南](docs/solver_guide.md) | direct/iterative 选择与限制 |
| [能力矩阵](docs/capability_matrix.md) | 2D/3D逐能力状态、qualification范围与研究边界 |
| [结果 schema](docs/result_schema.md) | JSON、RSS、R/T/A 字段 |
| [Benchmark](docs/benchmark.md) | 分层验证与当前记录 |
| [任务索引](docs/README.md) | Task000-Task033 闭环、Review 与下一阶段入口 |
| [理论笔记](notes/README.md) | 物理和数值解释 |

## 重要边界

当前 workstation profile 针对固定目标几何、p=2、MPI4 和已审查参数。h=5/3/2 均通过显式真残差 `1e-6` gate，但迭代数不单调，因此称为 mesh-robust production candidate，而不是数学意义上的 mesh-independent solver。新角度、波长、材料或几何必须重新与 direct reference 交叉验证。
