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
| task008 | 目标尺寸 50×25×140 nm official DtN-port R/T/A 本机收敛 benchmark 与资源报告 | `task008_70nm_official_convergence_benchmark/` | 任务书已按新几何更新；待本地 Codex 新建分支后执行 |

## 合并前结论

当前 task007 分支可作为 Stage 4 dtn_port 后处理口径修正阶段性结果合并。合并含义是：

```text
恢复 Stage 4 dtn_port 主线官方 R/T/A：R_total/T_total 来自 DtN port auxiliary modal amplitudes；E/H Fourier probe、E-only Fourier probe、sampled net flux 均降级为 diagnostic。
```

不要把本次合并解读为：

```text
真实 3D grating 已完成最终网格收敛 benchmark；
不同 total height 下的 T/A 可以直接代表同一物理界面透射；
p=2 h=5 已经是最终物理解。
```

详细边界说明见：

```text
notes/reference/current_version_boundaries.md
docs/task007_dtn_port_modal_official_rta/review_report.md
```

## task008 执行说明

`task008_70nm_official_convergence_benchmark/task.md` 是后续任务书。目录名保留了早期 70 nm 命名，但任务书已更新为新的目标几何。执行 task008 前，应先在本地将当前 task007 分支合并到 `master`，再由本地 Codex 从更新后的 `master` 新建 task008 分支。ChatGPT 不负责创建远程任务分支。

本轮 task008 的定位是：

```text
在 task007 修正后的 official dtn_port_modal R/T/A 口径下，针对目标计算域 50×25×140 nm、光栅 17×25×120 nm、空气 10 nm、基座 10 nm，完成本机可承受的 p/h 收敛 benchmark，并同步生成资源报告。
```

推荐 task008 分支名：

```text
codex/20260706-target-50x25x140-official-benchmark
```

## 工作规则

1. Codex 开始新一轮前，读取上一轮任务目录中的 `review_report.md`。
2. Codex 同时读取本轮任务目录中的 `task.md`。
3. Codex 完成工作后，把本轮结果写入该任务目录的 `outcomes/`。
4. ChatGPT 审查后，把 `review_report.md` 提交到同一个任务目录。
5. 大体积计算结果仍保留在 `results/`，不提交到 Git。
