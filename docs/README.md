# 任务流转索引

## task019 最新结论

| 项目 | 结论 |
|---|---|
| 任务 | p=2 h=5 qualification for residual-corrected true-FE sampled Schur |
| 目录 | `task019_p2_h5_true_fe_sampled_schur_qualification/` |
| 状态 | 已执行并已审查；minimum useful gate 未通过 |
| 关键数值 | 120-step baseline `1.6386e-2`；best required one-shot `1.6357e-2`，`1.0018x`；best creative variant `1.5166e-2`，`1.0804x` |
| 判断 | p=1 h=5 的 `top_bottom_y` true-FE sampled Schur 流程不能直接扩展到 p=2 h=5 |
| 下一步 | 先做 branch hygiene / selective docs merge audit；失败代码留在研究分支；然后由 Codex 自行开新执行分支做 Task020 |

本目录保存任务流转记录：任务书、outcomes、审查报告。理论说明和学习笔记继续放在 `notes/`。

每个任务目录采用同一结构：

```text
docs/taskXXX_task_name/
├── task.md
├── outcomes/
└── review_report.md
```

## 当前任务

| 编号 | 任务 | 目录 | 状态 |
|---|---|---|---|
| task000 | 初始代码审查整理 | `task000_review_code/` | 已完成，保留为历史闭环 |
| task001 | Stage 4 validation cleanup | `task001_stage4_validation_cleanup/` | 已完成并已审查 |
| task002 | R/T/A output 与 volume absorption | `task002_rta_output_volume_absorption/` | 已完成并已审查 |
| task003 | Stage 4 power consistency | `task003_stage4_power_consistency/` | 已完成并已审查 |
| task004 | small-cell p 收敛、MPI 一致性与全阶段回归 | `task004_small_cell_p_convergence_mpi_regression/` | 已完成并已审查 |
| task005 | 真实 3D 光栅 p=2 内存、OOC 与迭代法资源估算 | `task005_stage4_real_grating_memory_estimation/` | 已完成并已审查 |
| task006 | 70 nm 缩短计算域真实 3D 光栅 p=1/p=2 收敛、资源与 R/T 分析 | `task006_reduced_height_grating_convergence_memory/` | 已完成并已审查；R/T/A official 口径已在 task007 修正 |
| task007 | 恢复 DtN port modal amplitudes 作为 Stage 4 官方 R/T/A | `task007_dtn_port_modal_official_rta/` | 已完成并已审查 |
| task008 | 目标尺寸 50×25×140 nm、80° 斜入射 official DtN-port R/T/A 本机 benchmark | `task008_70nm_official_convergence_benchmark/` | 已完成并合并到 `master` |
| task009 | Stage 4 3D Maxwell 迭代求解器 profiles 快速筛选 | `task009_iterative_solver_profile_screening/` | 已完成并已审查；负结果作为 task010 输入 |
| task010 | Stage 4 3D Maxwell MUMPS-BLR 与物理预条件器原型验证 | `task010_shifted_maxwell_preconditioner/` | 已完成并已审查；BLR 为短期候选，不是最终低内存迭代法 |
| task011 | Stage 4 3D Maxwell low-memory AMS/HX iterative solver prototype | `task011_low_memory_ams_hx_iterative_solver/` | 已执行；无新的 production 低内存候选 |
| task012 | Maxwell 周期光栅低内存迭代求解器文献调研与路线设计 | `task012_literature_review_maxwell_preconditioners/` | 已完成并已审查；推荐 gated Task013 |
| task013 | real-split AMS/HX qualification with full Stage 4 gated breakthrough test | `task013_real_split_ams_hx_qualification/` | 已审查；B 档正结果，暂不建议合并 production code |
| task014a | reduced Stage 4 real-split FE/aux block PC integration | `task014a_real_split_stage4_reduced_block_pc/` | 已执行并已审查；基础设施通过，但 FE-AMS + aux identity 太弱 |
| task015 | reduced Stage 4 DtN/Floquet boundary-aware PC diagnostic | `task015_boundary_aware_pc_diagnostic/` | 已执行并已审查；瓶颈定位到 top zero-order FE/aux coupled modal slow direction |
| task016 | dominant zero-order FE+aux lifted coarse correction / low-rank sampled Schur | `task016_zero_order_lifted_coarse_correction/` | 已执行并已审查；right-only lifted correction 无效 |
| task017 | Petrov / adjoint-aware zero-order coarse correction and true-FE sampled Schur qualification | `task017_petrov_adjoint_coarse_correction/` | 已执行并已审查；Petrov 无效，true-FE sampled lift 有 one-shot 正信号，KSP right-PC 集成失败 |
| task018 | adaptive true-FE sampled Schur / AMS-HX Krylov integration | `task018_true_fe_sampled_schur_krylov_integration/` | 已执行并已审查；p=1 residual-corrected loop 通过 strong gate |
| task019 | p=2 h=5 qualification for residual-corrected true-FE sampled Schur | `task019_p2_h5_true_fe_sampled_schur_qualification/` | 已执行并已审查；p=2 h=5 gate 失败，低维 sampled Schur 主线暂停 |
| task020 | branch hygiene and wave-aware solver search | `task020_branch_hygiene_and_wave_solver_search/` | 任务书占位已写入；详细 scope 在 task019 review sections 11-13；执行分支由 Codex 创建 |

## 当前阶段结论

```text
task008：p=2 h=2 nm 是当前本机 best-effort official direct reference。
task009：普通 PETSc Krylov + Jacobi/BJacobi/ASM/ILU/local LU 没有 production candidate。
task010：MUMPS-BLR 在 p=2 h=2 nm 上可收敛并复现 R/T/A，但属于压缩直接路线，内存下降有限。
task011：Jacobi-Krylov 低内存但不收敛；real FE-only AMS 有收敛信号但内存前景未证明；complex AMS 直接路径不安全；matrix-free FE matvec 可行但尚未接入 Stage 4。
task012-task019：AMS/HX + low-dimensional sampled Schur 路线完成了从 FE-only 到 p=2 h=5 的闭环验证：p=1 h=5 有强正信号，但 p=2 h=5 失败。因此失败 solver code 不合并 production，文档和负结果证据可保留。
task020：下一步先由 Codex 做 branch hygiene / selective docs merge audit，再从 clean base 测试 impedance DDM、layered/sweeping、two-level adaptive Schwarz、matrix-free+physics PC 四条路线。
```

## task020 任务书

```text
docs/task020_branch_hygiene_and_wave_solver_search/task.md
```

说明：接口允许写入了精简任务书；详细执行范围已经写在：

```text
docs/task019_p2_h5_true_fe_sampled_schur_qualification/review_report.md
```

尤其是 section 11-13：

```text
11. Merge / branch hygiene recommendation
12. 下一步：Task020
13. 最终审查结论
```

## 工作规则

1. 开始新一轮前，读取上一轮任务目录中的 `review_report.md` 或 outcomes summary。
2. 同时读取本轮任务目录中的 `task.md`。
3. 完成工作后，把本轮结果写入该任务目录的 `outcomes/`。
4. 审查后，把 `review_report.md` 提交到同一个任务目录。
5. 大体积计算结果仍保留在 `results/`，不提交到 Git。
6. ChatGPT 不创建分支；执行分支由 Codex 创建。
7. failed solver code 默认留在对应 research branch，不合并 production；docs / review / outcome summaries 可以 selective merge。
