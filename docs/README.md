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
| task006 | 70 nm 缩短计算域真实 3D 光栅 p=1/p=2 收敛、资源与 R/T 分析 | `task006_reduced_height_grating_convergence_memory/` | 已完成；待审查 |

## 合并前结论

当前 task006 分支可作为 reduced-height domain 资源与初步 R/T/A 阶段性结果审查。合并含义是：

```text
完成真实 100 nm x 100 nm x 70 nm Stage 4 block grating 的 p=1/p=2 资源扫描、default direct 边界、MUMPS OOC 对照、MPI=1 对照、R/T/A 初步收敛表和 70 nm vs 150 nm 对照。
```

不要把本次合并解读为：

```text
真实 100 nm 3D EUV grating 已完成物理收敛 benchmark。
```

task006 的关键结论是：70 nm 域显著降低矩阵资源，但与 150 nm 原域在 h=5 上的 R/T/A 差异明显，因此不能直接视为物理等价计算域。

详细边界说明见：

```text
notes/reference/current_version_boundaries.md
docs/task005_stage4_real_grating_memory_estimation/review_report.md
```

## task006 审查说明

`task006_reduced_height_grating_convergence_memory/outcomes/summary.md` 是本轮结果入口。审查时应重点看：

```text
failure_boundary.md
rta_convergence.csv
direct_default_scale.csv
reduced_vs_original_domain_comparison.csv
memory_profile_summary.csv
```

2026-07-05 补充：task006 summary 已加入 memory profiling、tuned MUMPS OOC、失败边界解释和 workstation recommendation。审查时还应查看：

```text
mumps_ooc_tuned_extra_scale.csv
workstation_recommendation.csv
```

新的关键结论是：`mat_mumps_icntl_14=200` tuned OOC 可以完成 p=2 h=4，但 p=2 h=3 仍在 MUMPS numerical factorization 阶段失败；h=0.5 nm 和 h=0.25 nm 已不适合 direct/OOC workstation 路线。

## 工作规则

1. Codex 开始新一轮前，读取上一轮任务目录中的 `review_report.md`。
2. Codex 同时读取本轮任务目录中的 `task.md`。
3. Codex 完成工作后，把本轮结果写入该任务目录的 `outcomes/`。
4. ChatGPT 审查后，把 `review_report.md` 提交到同一个任务目录。
5. 大体积计算结果仍保留在 `results/`，不提交到 Git。
