# 任务流转索引

本目录只保存任务流转记录：ChatGPT 写给 Codex 的任务书、Codex 完成后的 outcomes、ChatGPT 的审查报告。理论说明、学习笔记和解释性文档继续放在 `notes/`。

每个任务目录采用同一结构：

```text
docs/taskXXX_task_name/
├── task.md
├── outcomes/
└── review_report.md
```

其中 `review_report.md` 只在 ChatGPT 已完成审查后存在；`outcomes/` 只在 Codex 已完成该轮工作后填充。

## 当前任务

| 编号 | 任务 | 目录 | 状态 |
|---|---|---|---|
| task000 | 初始代码审查整理 | `task000_review_code/` | 已完成，保留为历史闭环 |
| task001 | Stage 4 validation cleanup | `task001_stage4_validation_cleanup/` | 已完成并已审查 |
| task002 | R/T/A output 与 volume absorption | `task002_rta_output_volume_absorption/` | 已完成并已审查 |
| task003 | Stage 4 power consistency | `task003_stage4_power_consistency/` | 已完成并已审查 |
| task004 | small-cell p 收敛、MPI 一致性与全阶段回归 | `task004_small_cell_p_convergence_mpi_regression/` | 已完成并已审查；建议合并当前分支 |
| task005 | 真实 3D 光栅 p=2 内存、OOC 与迭代法资源估算 | `task005_stage4_real_grating_memory_estimation/` | 已完成并已审查；建议合并当前分支 |
| task006 | 70 nm 缩短计算域真实 3D 光栅 p=1/p=2 收敛、资源与 R/T 分析 | `task006_reduced_height_grating_convergence_memory/` | 已完成并已审查；建议合并当前分支，但 R/T/A official 口径需在 task007 修正 |
| task007 | 恢复 DtN port modal amplitudes 作为 Stage 4 官方 R/T/A | `task007_dtn_port_modal_official_rta/` | 已完成并已审查；建议合并当前分支 |
| task008 | 目标尺寸 50×25×140 nm、80° 斜入射 official DtN-port R/T/A 本机收敛 benchmark、内存边界与资源报告 | `task008_70nm_official_convergence_benchmark/` | 已在 `codex/20260706-target-50x25x140-oblique80-official-benchmark` 完成 outcomes 与 review；合并前建议轻量收尾 |
| task009 | Stage 4 3D Maxwell 迭代求解器 profiles 快速筛选 | `task009_iterative_solver_profile_screening/` | 任务书已写入；待本地 Codex 新建分支后执行 |

## 当前阶段结论

task007 已并入 `master`，task008 在新分支上完成了目标几何和 80° 斜入射的本机资源 benchmark。task007 的合并含义是：

```text
恢复 Stage 4 dtn_port 主线官方 R/T/A：R_total/T_total 来自 DtN port auxiliary modal amplitudes；E/H Fourier probe、E-only Fourier probe、sampled net flux 均降级为 diagnostic。
```

不要把本次合并解读为：

```text
真实 3D grating 已完成最终网格收敛 benchmark；
不同 total height 下的 T/A 可以直接代表同一物理界面透射；
p=2 h=5 已经是最终物理解。
```

task008 的阶段性结论是：

```text
50×25×140 nm / 17×25×120 nm / theta_from_z=80° / phi=0° / s polarization 已完成本机 official DtN-port modal R/T/A benchmark。
p=1 default direct 可完成到 h=1 nm；
p=2 default direct 可完成到 h=2 nm；
p=2 h=1.5 nm default direct 在 stage4_dtn_augmented_ksp_setup 被 signal 9 kill；
p=2 h=1 nm assemble-only 已超时并出现大量 swap，不进入 direct 计划。
p=2 h=2 nm 是当前个人电脑 best-effort official benchmark 主点，但不是最终网格收敛物理解；
p=2 h=5 nm 的 R≈0.089 明显受粗网格影响，不作为物理结论。
```

详细边界说明见：

```text
notes/reference/current_version_boundaries.md
docs/task007_dtn_port_modal_official_rta/review_report.md
docs/task008_70nm_official_convergence_benchmark/review_report.md
docs/task008_70nm_official_convergence_benchmark/outcomes/summary.md
```

## task008 执行结果

`task008_70nm_official_convergence_benchmark/task.md` 是本轮任务书。目录名保留了早期 70 nm 命名，但任务书实际目标已经更新为 50×25×140 nm、80° 斜入射。

本轮 task008 的输出位于：

```text
docs/task008_70nm_official_convergence_benchmark/outcomes/
```

重点文件：

```text
summary.md
assemble_matrix_scale.csv
official_convergence.csv
resource_convergence.csv
failure_boundary.md
raw_runs/
```

## task009 执行说明

`task009_iterative_solver_profile_screening/task.md` 是下一轮任务书。执行 task009 前，应先在本地完成 task008 的轻量收尾并合并到 `master`，再由本地 Codex 从更新后的 `master` 新建 task009 分支。ChatGPT 不负责创建远程任务分支。

本轮 task009 的定位是：

```text
在 task008 direct-reference cases 上快速筛选 PETSc 现成 iterative profiles，优先测试 GMRES/FGMRES/BiCGStab + Jacobi/BJacobi/ASM/ILU/local LU，找出能复现 p=2 h=2 direct R/T/A 并有希望突破 p=2 h=1.5 failure boundary 的 profile。
```

推荐 task009 分支名：

```text
codex/20260706-iterative-solver-profile-screening
```

## 工作规则

1. Codex 开始新一轮前，读取上一轮任务目录中的 `review_report.md`。
2. Codex 同时读取本轮任务目录中的 `task.md`。
3. Codex 完成工作后，把本轮结果写入该任务目录的 `outcomes/`。
4. ChatGPT 审查后，把 `review_report.md` 提交到同一个任务目录。
5. 大体积计算结果仍保留在 `results/`，不提交到 Git。
