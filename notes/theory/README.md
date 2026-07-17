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
| 9 | [`hybrid_fem_modal_domain_decomposition.md`](hybrid_fem_modal_domain_decomposition.md) | 如何用二维截面本征模替代 z 不变中间体域，并与上下局部 3D FEM 通过双接口和 Modal-Schur 耦合 |
| 10 | [`high_order_hcurl_floquet_and_hp_adaptivity.md`](high_order_hcurl_floquet_and_hp_adaptivity.md) | Task033 的高阶 H(curl) orientation、分布式 Floquet、QEP、fixed-p 等精度结论，以及已移交 graded-h/adaptive、buffer、variable-p 的能力边界 |
| 11 | [`research_routes_and_negative_results.md`](research_routes_and_negative_results.md) | AMS/HX 等历史正负结果为何没有进入默认路径 |

## 旧理论长文

`layered_background_theory_and_code_walkthrough.md`、`port_total_formulation_and_run_management.md`、`reflection_transmission_metrics.md`、`stage2_3d_floquet_pml_fresnel.md` 等保留完整开发推导。上表是当前规范入口；旧文档若与代码或规范入口冲突，以当前源码、benchmark record 和上表为准。

## 约定总览

- 时间因子：`exp(-i*omega*t)`。
- 空间波：`exp(i*k dot x)`。
- 几何与波长：nm；因此 `k0=2*pi/lambda0` 的单位为 `nm^-1`。
- 材料：非磁性时 `mu_r=1`，`epsilon_r=n^2`；当前吸收材料使用 `Im(epsilon_r)>0`。
- 功率：`0.5*Re(E cross conjugate(H))`；代码归一化消去公共真空常数。
- 弱式：复数内积对测试函数取共轭。

## 统一符号表

| 符号/术语 | 2D 含义 | 3D 含义 | 项目约定 |
|---|---|---|---|
| `x` | 周期方向 | 第一周期方向 | 周期长度 `L_x` |
| `y` | 竖直传播方向 | 第二周期方向 | 2D top 为 `+y`、bottom 为 `-y` |
| `z` | 结构不变/偏振分量方向 | 竖直传播方向 | 3D top 为 `+z`、bottom 为 `-z` |
| `n_top/n_bottom` | air/substrate index | air/substrate index | `epsilon_r=n^2` |
| 入射方向 | 从 top 向 `-y` | 从 top 向 `-z` | 入射功率定义为正 |
| top outgoing | 向 `+y` | 向 `+z` | 反射 R |
| bottom outgoing | 向 `-y` | 向 `-z` | 透射 T |
| `alpha_m` | `kx+2*pi*m/Lx` | 同左 | x-Floquet 波数 |
| `gamma_n` | 不使用 | `ky+2*pi*n/Ly` | y-Floquet 波数 |
| `beta` | y 向纵向常数 | z 向纵向常数 | 取出射/衰减平方根分支；Task032 中也表示结构化横截面 eigenmode 的 z 传播常数 |
| TM | 面内 `(Ex,Ey)` H(curl) | 不作为 3D求解空间标签 | 2D 向量路线 |
| TE | 标量 `Ez` H1 | 不作为 3D求解空间标签 | 2D 标量路线 |
| s/p | 不作为 2D主路线标签 | 每个非退化 order 的两种 E 极化 | 正入射退化时用 x/y 基 |
| `F,C,D,H` | 2D 文档可类比使用 | 3D FE/modal 增广块 | 当前 3D port 的 `H=I`；Hybrid 内部 modal block 另记 `H_m` |
| `R,T,A` | 入射功率归一化比例 | 入射功率归一化比例 | `A` 优先指 `A_volume` |

3D 波矢写成 `(alpha,gamma,sign*beta)`；`sign=+1` 表示 top outgoing，`sign=-1` 表示 bottom outgoing。2D 代码中的 `ky` 是向下入射波的 y 分量，不能机械套用 3D `gamma_n` 的横向含义。

## 公式到代码的第一锚点

| 理论对象 | 规范代码锚点 |
|---|---|
| 2D TM/TE 弱式 | `solve_vector_maxwell::run_case`、`solve_te_maxwell::run_te_case` |
| 3D 弱式 | `common_3d_forms::_build_variational_forms` |
| 2D/3D Floquet | `floquet_constraint::build_floquet_constraints`、`floquet_3d::build_double_floquet_mpc` |
| 3D order/E/H/power | `modes_3d::outgoing_port_modes_3d` |
| 3D DtN 增广装配 | `dtn_port_3d::solve_stage4_dtn_port_total_field` |
| exact condensation | `condensed_dtn::create_matrix_free_condensed_operator` |
| 两级 PC | `physical_slab_two_level::SparseGalerkinTwoLevelPc.apply` |
| Hybrid eigenmodes / coupling / Schur | `src/modes/`、`src/coupling/`、`hybrid_fem_modal_*`；资格边界由 Case080/091 records 决定 |
| 高阶 p1--p4 Floquet / fixed-p Hybrid | `floquet_3d_high_order`、`high_order_floquet_trace`、`task033_reduced_equal_accuracy`；正式结论由 Case090/091 reduced-scope completion checker 决定；graded-h/adaptive 已移交下一任务，不是 master 能力 |
| 2D official RTA | `power_metrics::compute_dtn_auxiliary_power_metrics` |
| 3D official RTA/A | `dtn_port_3d::_port_power_metrics`、`rta_3d::compute_volume_absorption_3d` |

## 2D 与 3D 功率常数

连续 SI 功率包含真空阻抗、`epsilon0`、`mu0` 或 `c` 等公共常数。项目为避免在 nm 几何和 code-unit H 之间重复换算，在不同模块中省略了同一分子、分母都会出现的公共因子：

- 2D 模态功率按单位 z 长度计算，并使用对应 TM/TE admittance；因此绝对量的维度是“每单位不变方向长度”。
- 3D 模态功率乘完整 `L_x L_y` 单胞面积，并使用 `H_code=curl(E)/(i*k0*mu_r)`。
- 2D 体吸收和 3D 体吸收各自与本模块的入射功率采用配套 code units；同一模块内归一化后公共常数严格消去。

所以 `R`、`T`、`A` 和能量 closure 可以跨 2D/3D 比较物理比例；`incident_power_code_units`、未归一化 modal power、体吸收积分原值不能直接跨维度比较，也不能当作 SI W 或 W/m，除非把被省略常数和几何维度完整恢复。

连续理论只能说明公式结构。可运行性、离散误差、MPI 一致性和内存上限必须由 [`../../benchmarks/cases/README.md`](../../benchmarks/cases/README.md) 的案例证据确认。Task032 的 Hybrid 公式在通过 Case080 前只属于计划/理论，不属于已验证功能。
