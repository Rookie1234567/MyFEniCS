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
| task007 | 恢复 DtN port modal amplitudes 作为 Stage 4 官方 R/T/A | `task007_dtn_port_modal_official_rta/` | 任务书已写入；待本地 Codex 新建分支后执行 |

## 合并前结论

当前 task006 分支可作为 reduced-height domain 资源探索与诊断阶段结果合并。合并含义是：

```text
完成真实 100 nm x 100 nm x 70 nm Stage 4 block grating 的 p=1/p=2 资源扫描、default direct 边界、MUMPS OOC tuned 对照、MPI=1 对照、memory profiling 和 R/T/A 初步表。
```

不要把本次合并解读为：

```text
真实 100 nm 3D EUV grating 已完成物理收敛 benchmark；
70 nm reduced-height domain 已证明与 150 nm 原域物理等价；
当前 R/T/A 已经是严格 DtN port modal amplitude 后处理。
```

关键审查结论是：task006 资源探索部分通过，但当前 3D block grating 的 official R/T 后处理仍来自 E/H Fourier probe-plane modal fitting，而不是直接来自 DtN port modal amplitudes。因此，task007 应优先修正 official/diagnostic 后处理边界。

详细边界说明见：

```text
notes/reference/current_version_boundaries.md
docs/task006_reduced_height_grating_convergence_memory/review_report.md
```

## task007 执行说明

`task007_dtn_port_modal_official_rta/task.md` 是后续任务书。执行 task007 前，应先在本地将当前 task006 分支合并到 `master`，再由本地 Codex 从更新后的 `master` 新建 task007 分支。ChatGPT 不负责创建远程任务分支。

## 工作规则

1. Codex 开始新一轮前，读取上一轮任务目录中的 `review_report.md`。
2. Codex 同时读取本轮任务目录中的 `task.md`。
3. Codex 完成工作后，把本轮结果写入该任务目录的 `outcomes/`。
4. ChatGPT 审查后，把 `review_report.md` 提交到同一个任务目录。
5. 大体积计算结果仍保留在 `results/`，不提交到 Git。
