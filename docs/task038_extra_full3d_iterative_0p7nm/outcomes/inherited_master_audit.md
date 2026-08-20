# T0 继承 master 审计

审计日期：2026-08-20。本文是 Task038-extra 的第一阶段 docs-only 审计，不是数值运行报告，也不授权迁移或正式计算。

## 1. 身份与工作树

| 项目 | 只读结果 |
|---|---|
| 执行分支 | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| HEAD | `7114a6b7869a1c8ade29e9cdcba529fc4858e320` |
| upstream | 同上；`HEAD...upstream = 0 0` |
| `origin/master` | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| 工作树 | clean |
| 本地 `master` ref | 不存在；本审计只使用已核验的 `origin/master`，没有创建或修改本地 `master` |
| 本轮代码变化 | 无；T0 只新增本目录三份审计文档 |

当前 HEAD 的提交说明为 `docs(task038-extra): define 0.7nm-scalable Full3D iterative program`，其本身只新增 Task038-extra `task.md`。上述身份满足 `task.md` 的 T0 基线要求。

## 2. 当前 master 继承的 input-driven 闭环

以下文件均在当前树中逐一只读检查，未修改：

| 文件 | 继承到的能力与边界 |
|---|---|
| `docs/task038_input_driven_configuration/task.md` | 单个 `.dat` 输入驱动一次运行、方法合同、物理与输入身份要求 |
| `docs/task038_input_driven_configuration/review_report_v1.md` | 已批准的分阶段选择性迁移顺序；禁止整支研究分支合并 |
| `docs/task038_input_driven_configuration/response_v1.md` | 既有输入驱动阶段的历史状态；不替代本分支 fresh evidence |
| `docs/task038_input_driven_configuration/outcomes/summary.md` | 输入驱动阶段的结果边界与未运行项 |
| `src/io/input_schema.py` | 严格 schema、身份键、方法与 section 合同 |
| `src/io/input_validation.py` | 类型、有限值、重复/未知键、方法相关字段和 source/input hash 的 fail-closed 校验 |
| `src/io/execution_plan.py` | 将已验证输入转换为显式 execution plan，不在普通入口隐式运行 preset |
| `src/runners/task038_input_worker.py` | 输入身份、执行计划和 adapter 的薄编排层 |
| `src/runners/task038_full3d_direct.py` | Full3D direct adapter；未把 0.7nm capacity-only 变成 PDE 入口 |
| `scripts/run_case.py` | 受输入合同约束的统一 launcher |

当前代码与文档的可继承结论是“输入、来源、方法和执行计划必须显式绑定”。这不是对任意 Full3D iterative PC 的数值资格结论；T0 没有运行 pytest、MPI、PDE 或 benchmark。

## 3. 已有结果的证据边界

Task038 input-driven 文档记载了 direct Full3D、Hybrid direct 和 Hybrid iterative 的历史阶段结果：direct residual 达到文档所载的近机器精度；Hybrid iterative 的文档记录了约 1771 次迭代、约 6585 MiB 峰值和 swap=0，并将其标为内存偏高、不能作为普通默认。这里仅继承“结果和限制的记录方式”，不把历史 source-branch 计数或 controlled stop 改写成当前 Task038-extra 的 fresh pass。

因此本阶段明确保留以下边界：

- 正式物理仍固定为 13.5 nm、complex128、Nedelec `H(curl)`、双 Floquet、Fourier-DtN、uncondensed full-space；0.7 nm 只允许容量/通道审计。
- 不得把旧 Task37 的 task-numbered runner、PC、fixed range 或 compact status 当作当前生产默认。
- 不得以历史 action-only、solver residual 或资源预测替代完整 PDE、物理 observable 和最终内存 Gate。
- 未运行项仍记为 `not_run`，历史负结果和受控停止不得被改写为通过。

## 4. T0 边界 Gate

| Gate | 结论 | 依据 |
|---|---|---|
| master/base identity | pass | `origin/master` 与 merge-base 均为 `438caf...` |
| branch/upstream identity | pass | 指定 Task038-extra 分支，HEAD/upstream 相同，0/0 |
| clean worktree | pass | `status --short` 为空；写文档前已核验 |
| Task37-extra boundary | explicit | 当前树不含其权威路径；旧分支只读档案不迁移 |
| Task39 boundary | 已通过只读远端 ref 验证 | `origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` at `f4073adabb91bffe5c3954b8ae8b63270efa3e15`，见单独审计 |
| no Python changes | pass | 本阶段只允许三份 Markdown |
| formal/PDE/benchmark | not_run | T0 明确禁止 |

T0 结论：可以进入监督审阅；不能据此开始 T1、迁移 Python、运行 0.7 nm PDE 或宣称 Full3D iterative 已资格化。
