# 理论索引

本目录给出项目当前代码的理论依据。阅读顺序从连续方程到边界、端口、功率和线性代数；每篇都标出对应源码和资格边界。

## 主线

| 顺序 | 文档 | 回答的问题 |
|---:|---|---|
| 1 | [`maxwell_strong_weak_and_fem.md`](maxwell_strong_weak_and_fem.md) | 强形式如何变成 TM/TE/3D 弱式，为什么用 Nedelec |
| 2 | [`floquet_periodicity.md`](floquet_periodicity.md) | 周期相位如何约束 H(curl) 自由度 |
| 3 | [`pml_robin_and_open_boundaries.md`](pml_robin_and_open_boundaries.md) | 开域如何由 PML、Robin 或 DtN 截断 |
| 4 | [`dtn_modal_ports_and_condensation.md`](dtn_modal_ports_and_condensation.md) | Fourier-DtN、显式/辅助装配和 Schur 凝聚 |
| 5 | [`official_and_diagnostic_rta_methods.md`](official_and_diagnostic_rta_methods.md) | R/T/A 的定义、归一化和 official/diagnostic 边界 |
| 6 | [`3d_stages_and_validation_ladder.md`](3d_stages_and_validation_ladder.md) | Stage 1、2A/B/C、4A/B 各增加并证明什么 |
| 7 | [`direct_solvers_and_factorization.md`](direct_solvers_and_factorization.md) | PETSc LU、MUMPS OOC、BLR 的真实含义 |
| 8 | [`iterative_solver_and_preconditioner.md`](iterative_solver_and_preconditioner.md) | h=5/3/2 生产迭代器的算子与预条件器 |
| 9 | [`research_routes_and_negative_results.md`](research_routes_and_negative_results.md) | AMS/HX 等历史正负结果为何没有进入默认路径 |

## 旧理论长文

`layered_background_theory_and_code_walkthrough.md`、`port_total_formulation_and_run_management.md`、`reflection_transmission_metrics.md`、`stage2_3d_floquet_pml_fresnel.md` 等保留完整开发推导。上表是当前规范入口；旧文档若与代码或规范入口冲突，以当前源码、benchmark record 和上表为准。

## 约定总览

- 时间因子：`exp(-i*omega*t)`。
- 空间波：`exp(i*k dot x)`。
- 几何与波长：nm；因此 `k0=2*pi/lambda0` 的单位为 `nm^-1`。
- 材料：非磁性时 `mu_r=1`，`epsilon_r=n^2`；当前吸收材料使用 `Im(epsilon_r)>0`。
- 功率：`0.5*Re(E cross conjugate(H))`；代码归一化消去公共真空常数。
- 弱式：复数内积对测试函数取共轭。

连续理论只能说明公式结构。可运行性、离散误差、MPI 一致性和内存上限必须由 [`../../benchmarks/cases/README.md`](../../benchmarks/cases/README.md) 的案例证据确认。
