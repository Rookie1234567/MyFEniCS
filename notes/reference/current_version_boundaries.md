# 当前版本能力边界说明

本说明用于防止合并后误读当前分支的能力范围。

对应分支：

```text
codex/20260707-maxwell-physics-blr-preconditioner-prototype
```

对应任务闭环：

```text
docs/task002_rta_output_volume_absorption/
docs/task003_stage4_power_consistency/
docs/task004_small_cell_p_convergence_mpi_regression/
docs/task005_stage4_real_grating_memory_estimation/
docs/task006_reduced_height_grating_convergence_memory/
docs/task007_dtn_port_modal_official_rta/
docs/task008_70nm_official_convergence_benchmark/
docs/task009_iterative_solver_profile_screening/
docs/task010_shifted_maxwell_preconditioner/
```

---

## 0. task010 MUMPS-BLR 与物理预条件器原型边界

task010 在 task009 负结果基础上，阅读 `papers/High Performance Parallel Solvers for the time-harmonic Maxwell Equations.pdf`，优先测试 MUMPS-BLR compressed factorization as FGMRES preconditioner，并做 minimal shifted/positive Maxwell operator preconditioner smoke：

```text
MUMPS-BLR profiles:
  iter_fgmres_mumps_blr_eps1e-3
  iter_fgmres_mumps_blr_eps1e-4
  iter_fgmres_mumps_blr_eps1e-5

minimal operator P profiles:
  iter_fgmres_shifted_a0p2_asm1_ilu0
  iter_fgmres_shifted_a0p5_asm1_ilu0
  iter_fgmres_shifted_a1p0_asm1_ilu0
  iter_fgmres_positive_maxwell_asm1_ilu0
  iter_fgmres_positive_maxwell_asm1_lu
```

当前结论是：

```text
FGMRES + MUMPS-BLR 是当前唯一达到 production 基本要求的候选。
p=2 h=2 nm:
  eps=1e-5 收敛，4 iterations，true_relative_residual_norm≈2.09e-8；
  eps=1e-4 收敛，7 iterations，true_relative_residual_norm≈1.88e-7；
  R/T/A 与 task008 direct LU 对照一致到约 1e-9。
p=2 h=1.5 nm:
  eps=1e-5 在 stage4_dtn_augmented_ksp_setup / KSP setup 阶段被 signal 9 kill；
  因此当前本机 production 上限仍是 p=2 h=2 nm。
minimal shifted/positive Maxwell P:
  A/P 双矩阵路径可构造，P rows/nnz 可记录；
  h=5/h=4 初筛均 1000 步未收敛；
  不能作为当前 production solver。
```

这意味着：

```text
工作站第一候选是 iter_fgmres_mumps_blr_eps1e-5；
第一工作站 case 应从 p=2 h=1.5 nm 开始，不应直接跳到 h=1 或 h=0.5；
eps=1e-4 可作为 BLR 备选；
eps=1e-3 在 h=2 超时，不建议作为主路线；
完整 H(curl) AMS / Hiptmair-Xu 仍然需要单独实现，当前 positive P 不是 AMS。
```

主要记录：

```text
docs/task010_shifted_maxwell_preconditioner/outcomes/summary.md
docs/task010_shifted_maxwell_preconditioner/outcomes/mumps_blr_feasibility.md
docs/task010_shifted_maxwell_preconditioner/outcomes/preconditioner_profile_ranking.md
docs/task010_shifted_maxwell_preconditioner/outcomes/workstation_recommendation.md
docs/task010_shifted_maxwell_preconditioner/outcomes/blr_vs_direct_rta.csv
docs/task010_shifted_maxwell_preconditioner/outcomes/preconditioner_failure_cases.csv
```

---

## 1. task009 迭代求解器筛选边界

task009 在 task008 的目标几何、p=2、80° 斜入射和 official DtN-port modal R/T/A 口径上，筛选 PETSc 现成 iterative profiles：

```text
GMRES / FGMRES / BiCGStab
Jacobi / BJacobi / ASM / ILU / local LU
附加诊断：GAMG、fieldsplit Schur、LGMRES + Jacobi、hypre BoomerAMG
```

当前结论是：

```text
没有找到可正式替代 direct/MUMPS 的生产迭代求解器。
所有可运行 iterative profiles 均未达到 KSP 收敛，因此不输出可信 official R/T/A。
iter_gmres_jacobi 是相对最稳的诊断路径，但不是物理解路径。
h=1.5 nm 上 iter_gmres_jacobi 可以越过 direct 在 stage4_dtn_augmented_ksp_setup 被 signal 9 kill 的边界，但 3.6e-3 是 residual_final_over_initial，不是 true_relative_residual_norm；对应 true_relative_residual_norm 约 1.6e-1。
ASM/ILU/local LU、BiCGStab、GAMG、fieldsplit Schur、hypre BoomerAMG 在本矩阵上表现为停滞、发散、setup 失败或底层崩溃风险。
```

这意味着：

```text
task009 证明了“现成黑盒 PETSc 迭代组合不足以解决本问题”，不是证明“迭代法已经可用”。
后续若要突破 p=2 h=1.5 nm，应设计 Maxwell/H(curl) 友好预条件器，例如 auxiliary-space/AMS、shifted Laplacian 或物理分块 Schur。
task009 的 h=1.5 nm iterative 结果只能作为资源和残差诊断，不应进入物理 R/T/A 表格。
```

主要记录：

```text
docs/task009_iterative_solver_profile_screening/outcomes/summary.md
docs/task009_iterative_solver_profile_screening/outcomes/profile_ranking.md
docs/task009_iterative_solver_profile_screening/outcomes/workstation_recommendation.md
docs/task009_iterative_solver_profile_screening/outcomes/iterative_profile_summary.csv
docs/task009_iterative_solver_profile_screening/outcomes/raw_runs/
```

---

## 2. task008 目标几何 80° 斜入射本机边界

task008 在 task007 的 official DtN-port modal R/T/A 口径上，固定如下目标几何和入射：

```text
period = 50 x 25 nm
domain = 50 x 25 x 140 nm
grating = 17 x 25 x 120 nm
substrate_thickness = 10 nm
top_air_above_grating = 10 nm
air_height = 130 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s, E along y
n_substrate = n_grating = 0.999002304859 + 0.00182649365j
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
power_source = dtn_port_modal_amplitudes
```

几何和入射验证：

```text
grating_width_y = period_y = 25 nm 合法支持，未使用 24.999 nm fallback；
kx = 0.458350341046137
ky = 0
kz = -0.0808195317433606
Floquet phase x = -0.600741134898 - 0.799443612046j
Floquet phase y = 1
k dot E = 0
DtN mode count = top 40 + bottom 40 = 80
```

本机 default MUMPS direct 边界：

```text
p=1:
  completed direct: h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
  first failed direct: 未尝试 h < 1 nm

p=2:
  completed direct: h = 5, 4, 3, 2.5, 2 nm
  first failed direct: h = 1.5 nm
  failure stage: stage4_dtn_augmented_ksp_setup
  returncode: 9 / signal 9 / Killed

p=2 h=1 nm:
  assemble-only timeout at stage4_dtn_base_matrix_assembled
  estimated AIJ matrix = 10.313 GB
  RSS upper = 14.129 GB
  swap delta ≈ 33.4 GB
```

当前建议使用的本机 official benchmark 主点：

```text
p=2 h=2 nm, personal-computer best-effort direct benchmark:
  R = 0.0013429328462348958
  T = 0.5992132294442478
  A_volume = 0.3994438377095067
  R + T + A_volume = 0.9999999999999893
  closure = -1.07e-14
```

注意：

```text
p=1 h=1 虽然能完成，但与 p=2 finest completed 仍不接近，不应作为最终物理收敛解；
p=2 h=2 是当前个人电脑 best-effort direct benchmark，不是最终网格收敛物理解；
p=2 h=5 的 R≈0.089 明显受粗网格影响，不应作为真实物理反射率结论；
p=2 h=1.5 的 assemble-only AIJ 矩阵约 3.20 GB，但 direct MUMPS 在 KSP setup 被 kill，瓶颈来自 LU fill-in / solver workspace；
后续若要推进 p=2 h=1.5 或更细网格，应单独评估 tuned MUMPS OOC 或迭代法。
```

主要记录：

```text
docs/task008_70nm_official_convergence_benchmark/outcomes/summary.md
docs/task008_70nm_official_convergence_benchmark/outcomes/assemble_matrix_scale.csv
docs/task008_70nm_official_convergence_benchmark/outcomes/official_convergence.csv
docs/task008_70nm_official_convergence_benchmark/outcomes/failure_boundary.md
```

---

## 3. task007 official DtN port modal 口径

task007 已把 Stage 4 `dtn_port` 主线的 official R/T/A 统一为：

```text
power_source = dtn_port_modal_amplitudes
```

含义：

```text
R_total = R_total_dtn_port_modal
T_total = T_total_dtn_port_modal
A_volume_total = volume_integral_Im_epsilon_E2
energy_closure_error_port_volume
  = R_total_dtn_port_modal + T_total_dtn_port_modal + A_volume_total - 1
```

probe-plane 方法现在只作为 diagnostic：

```text
diagnostic_eh_fourier_probe
diagnostic_e_only_fourier_probe
diagnostic_sampled_net_flux
```

不要再把 E/H Fourier probe 的 `R/T` 当作 Stage 4 dtn_port official 结论。

本轮 height scan 的 `T_total` 是 bottom physical port plane 上的功率。由于 substrate 为有损 Si，70 / 110 / 130 / 150 nm 的 bottom port reference plane 不同，`T_total` 随 substrate 厚度变化是当前定义下的预期现象。若要比较不同 total height 是否物理等价，下一轮应新增统一 reference plane 或界面处外推功率。

主要记录：

```text
docs/task007_dtn_port_modal_official_rta/outcomes/summary.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_modal_investigation.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_power_formula.md
```

---

## 4. task006 reduced-height domain 补充

task006 对真实 `100 nm x 100 nm x 70 nm`、`stage4_block_grating`、`dtn_port + auto_propagating` 路径做了资源和初步 R/T/A 检查。几何传参为：

```text
air_height = 60 nm
substrate_thickness = 10 nm
grating_height = 50 nm
top air above grating = 10 nm
total z height = 70 nm
```

当前结论：

```text
assemble-only:
  p=1 h=1 nm 可完成；
  p=2 h=2 nm 可完成；
  p=2 h=1.5 nm 超时；
  p=2 h=1 nm 在 base matrix assembled 后被 signal 9 kill，
  rows ≈ 16.99M，nnz ≈ 1.77e9，AIJ matrix ≈ 40.6 GB。

default MUMPS direct:
  p=1 最后完成 h=2 nm，h=1.5 nm 被 signal 9 kill；
  p=2 最后完成 h=4 nm，h=3 nm 被 signal 9 kill。

MUMPS OOC:
  p=1 h=2 nm 完成，但 h=1.5 nm 仍失败；
  p=2 h=4 nm 运行 5400 s 超时。
```

70 nm 域显著降低矩阵资源，但 `h=5 nm` 与 150 nm 原域的 R/T/A 差异明显。因此当前不能把 70 nm reduced-height domain 当作与 150 nm 原域等价的物理 benchmark；后续应做 top/bottom port distance 或空气/基座厚度扫描。

task006 还修正了真实光栅 reduced-height domain 下的自动 top probe 位置：有光栅块时，top probe 从 `grating_z_max` 到 `physical_z_max` 之间取，而不是从 interface 到 top boundary 之间取。

2026-07-05 补充运行后，边界更新为：

```text
memory profiling:
  p=2 h=5 default direct 的进程树 RSS 峰值约 13.65 GB；
  matrix-scale 中的 RSS upper 是 max_rss_mb x ranks 的保守上界，不是实测总 RSS。

tuned MUMPS OOC:
  p=2 h=5 完成，OOC scratch 约 4.95 GB；
  p=2 h=4 完成，OOC scratch 约 14.24 GB；
  p=2 h=3 失败，MUMPS INFOG(1)=-90；
  p=1 h=1.5 失败，MUMPS INFOG(1)=-90。

workstation:
  p=2 h=3 建议至少按 128 GB 级别压力测试；
  p=2 h=2 建议 256-512 GB；
  p=2 h=1 约为 TB 级内存问题；
  h=0.5 / 0.25 nm 不建议继续 direct/OOC workstation 路线。
```

失败点中记录到的 RSS 可能低估，因为 signal 9 或 MUMPS error 发生后，进程可能来不及写出 factorization 峰值。

---

## 4. 当前可以较有信心使用的能力

### 1.1 Stage 4 主功率口径

当前 Stage 4 主线是：

```text
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
unknown = E_total
x/y side = Floquet MPC
z top/bottom = Fourier-DtN auxiliary modal port
```

主功率口径：

```text
port = primary
```

吸收闭合口径：

```text
A_volume = volume_integral_Im_epsilon_E2
P_abs = integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV
```

在 small-cell flat-layer 中，`R_port + T_port + A_volume - 1` 已经可以达到机器精度量级。

### 1.2 small-cell flat-layer sanity

推荐 sanity benchmark：

```text
stage_case = stage4_flat_layer_sanity
period_x = period_y = 10 nm
air_height = substrate_thickness = 5 nm
lambda0 = 13.5 nm
n_substrate = 0.999002304859 + 0.00182649365j
```

该模型是平坦界面 sanity，不是 3D 光栅散射。

当前结论：

```text
p=2 明显优于 p=1；
port + A_volume 主线稳定；
MPI 1/4/8 不改变主线结果。
```

### 1.3 全阶段 smoke 回归

当前分支中以下路径已完成轻量 smoke：

```text
Stage 1: stage1_airbox
Stage 2A: floquet_airbox
Stage 2B: pml_airbox
Stage 2C: fresnel_interface
Flat-layer sanity: stage4_flat_layer_sanity
3D grating path smoke: stage4_block_grating zero-contrast
```

这些结果说明代码路径没有被 task002/task003/task004 的修改破坏。

---

## 5. 当前必须谨慎解读的能力

### 2.1 probe_eh_fourier / net_flux

当前定位：

```text
probe_eh_fourier = diagnostic only
net_flux = diagnostic only
```

原因：

```text
analytic-only 测试已经通过，说明公式层面基本正确；
但 FEM 场下仍受采样、curl(E) 重构、probe plane 和离散误差影响；
p=2 h=1.5 small-cell 中仍出现 probe 过冲和 net_flux 负分量。
```

因此，当前不能用 probe/net_flux 代替 port 作为主验收。

### 2.2 Stage 2B / Stage 2C

task004 中 Stage 2B/2C 只做了极粗网格 smoke。

当前不能声称：

```text
Stage 2B PML 精度已经通过；
Stage 2C Fresnel 精度已经通过。
```

它们只说明路径可运行。

### 2.3 stage4_block_grating

`stage4_block_grating` 是当前真实 3D 周期矩形柱/光栅散射路径。

当前可以说：

```text
zero-contrast smoke 已通过；
p=1/p=2 路径可以运行；
几何、材料 tag、Floquet、DtN port 和输出结构没有明显崩溃。
```

当前不能说：

```text
真实 100 nm 3D EUV grating 已完成物理收敛 benchmark。
```

真实 100 nm 周期、13.5 nm EUV、h≈1 nm 的计算规模对小电脑不现实，后续应在更高计算资源或更高效求解策略下推进。

---

## 6. 合并后推荐表述

推荐说法：

```text
当前版本完成了 Stage 4 R/T/A 输出重构、A_volume 体吸收、flat-layer 解析参考、small-cell p 收敛、MPI 一致性、全阶段 smoke 回归、目标几何本机 direct benchmark，以及现成 PETSc iterative profiles 的失败边界筛选。port + A_volume 是当前主线；task009 没有找到生产可用迭代求解器。
```

避免说法：

```text
当前版本已完成真实 3D EUV 光栅物理 benchmark。
```

---

## 7. 后续可能任务

后续不需要在当前分支阻塞合并。如果需要继续，可以新开任务：

```text
task005_probe_flux_diagnostic_cleanup
```

重点研究：

```text
probe plane 位置扫描；
采样点加密；
curl(E) 重构 H 的误差；
element-wise Poynting flux integral；
p=2 下 probe/net_flux 过冲原因。
```

真实 100 nm 3D grating benchmark 应作为未来高资源条件下的应用验证目标。

---

## 8. task005 资源边界补充

task005 对真实 `100 nm x 100 nm x 150 nm`、p=2、MPI=8、`stage4_block_grating`、`dtn_port + auto_propagating` 路径做了资源评估。当前结论是：

```text
assemble-only:
  h=2 nm 仍可完成；
  rows ≈ 4.76M；
  nnz ≈ 5.24e8；
  AIJ matrix ≈ 11.74 GB。

default MUMPS direct:
  h=5 nm 可完成；
  h=4 nm 在 stage4_dtn_augmented_ksp_setup 被 signal 9 kill；
  主要瓶颈是 LU fill-in 峰值内存，不是矩阵本体。

MUMPS OOC:
  默认 OOC 可完成到 h=5 nm；
  h=4 nm 返回 MUMPS INFOG(1)=-90；
  tuned OOC h=4 在 90 分钟超时，保留约 30 GB OOC 文件。
```

这说明当前小电脑可以用于资源摸底，但不适合继续硬跑真实 3D p=2 的 h=4 nm 及更细 direct LU 计算。若目标是 `h=3` 到 `h=2.5 nm` 的真实 3D 计算，应考虑 512 GB RAM 和 1 TB 级别 SSD scratch；若目标包含 `h=2 nm` 或更细，应按 1 TB RAM 起步，或优先开发可收敛的迭代求解器与预条件器。
# 当前版本能力边界说明

## 2026-07-07 更新：task011 low-memory AMS/HX iterative solver prototype

对应分支：

```text
codex/20260707-low-memory-ams-hx-iterative-solver
```

当前求解器边界更新为：

```text
1. 纯 Jacobi-Krylov 不是可用 Stage 4 求解器。
   p=2 h=5/h=4 的 GMRES/FGMRES/LGMRES/TFQMR/BiCGStab/CGS + Jacobi 全部不收敛。
   最好结果是 iter_gmres_jacobi_restart40, p=2 h=4, true_relative_residual_norm ≈ 0.234。

2. hypre AMS/HX 的 real FE-only smoke 是正信号。
   real p=2 h=5 FE-only positive Maxwell: 7 iterations, true_relative_residual_norm ≈ 4.02e-7。

3. complex hypre AMS 不能直接用于当前 Stage 4。
   complex p=1 h=10 最小 smoke 触发 malloc invalid size 与 PETSc signal 11。
   因此不能简单新增 pc_type=hypre, pc_hypre_type=ams 的 complex Stage 4 profile。

4. 下一步真正候选应是 real-imag split AMS/HX block preconditioner。
   把 A = Ar + i Ai 改写为 real block [[Ar, -Ai], [Ai, Ar]]，
   对 real/imag 主块使用 real hypre AMS，再逐步接入 Floquet MPC 与 DtN auxiliary。

5. matrix-free FE matvec 已通过 smoke。
   complex p=2 h=5 的 UFL action matvec 与 assembled matrix matvec 相对误差 ≈ 7.56e-16。
   但它只是降低矩阵存储压力的方向，不单独解决收敛。
```

最新记录：

```text
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/summary.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/profile_ranking.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/next_decision.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/matrix_free_matvec_feasibility.md
```

---

## 2026-07-07 更新：task012 Maxwell 低内存迭代求解器文献调研

对应分支：

```text
codex/20260707-literature-review-maxwell-preconditioners
```

task012 不修改 solver 代码，只做文献调研与路线设计。当前结论是：

```text
1. 不再继续 Jacobi/ASM/ILU/GAMG/BoomerAMG 黑盒 profile 调参。

2. BLR/H-matrix 类压缩因子化保留为 fallback。
   task010 的 MUMPS-BLR eps=1e-5 仍是短期可出 p=2 h=2 R/T/A 的候选，
   但不是最终低内存迭代法。

3. 下一步第一主线是 real-split AMS/HX block preconditioner。
   把 complex Maxwell A = Ar + i Ai 改写为
   [[Ar, -Ai], [Ai, Ar]]，
   先用 real hypre AMS/HX 预条件 real/imag 主块。

4. 第二主线是 Rayleigh/Floquet modal deflation。
   利用已有 DtN port 的 propagating / near-cutoff modal basis 构造低维 coarse correction，
   处理局部 PC 难以消除的全局传播误差。

5. DtN-aware FE/aux block preconditioner 是与前两条组合的方向。
   FE block 用 AMS/HX，auxiliary modal block 用 small dense/exact 或 modal diagonal solve。

6. layered-background / RCWA-like approximate inverse 是长期高潜力方向。
   它最贴合周期光栅物理，但实现复杂，应在 real-split AMS 与 modal deflation 后再推进。

7. matrix-free 是内存优化层。
   task011 已证明 FE-only action matvec 正确，但 matrix-free 本身不解决 indefinite Maxwell 收敛。
```

推荐下一轮最小任务：

```text
Task013：real-split AMS/HX block preconditioner minimal prototype。

先做 FE-only / reduced Stage 4 small cases，
记录 true residual、AMS auxiliary matrix 规模、setup RSS 和失败边界；
不直接跑 full p=2 h=2 或 h=1.5 大算例；
未收敛时不输出 official R/T/A。
```

主要记录：

```text
docs/task012_literature_review_maxwell_preconditioners/outcomes/summary.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/recommended_routes.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/method_scorecard.csv
docs/task012_literature_review_maxwell_preconditioners/outcomes/physics_custom_preconditioner_ideas.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/implementation_feasibility.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/next_task_proposal.md
notes/theory/maxwell_iterative_preconditioners_task012.md
```

---

## 2026-07-07 更新：task013 real-split AMS/HX qualification

对应分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

task013 新增了隔离的研究脚本：

```text
src/studies/run_real_split_ams_qualification.py
```

它只做 FE-only real split qualification，不修改正式 Stage 4 solver 主线。当前结论：

```text
1. real split 等价性通过。
   p1 h10、p1 h5、p2 h10、p2 h5、p2 h4 的 real block matvec error 均约为 1e-16。

2. p2 h5 FE-only same-H1 auxiliary 是本轮最佳。
   H1 degree = p，G nnz ≈ 1.572M，RSS ≈ 1.323 GB，
   310 iterations 达到 true_relative_residual_norm ≈ 9.96e-7。

3. standard H1=p+1 不建议作为主路线。
   p2 h5 RSS ≈ 6.306 GB，150 步 true residual ≈ 8.00e-6，
   内存和速度都不如 same-H1。

4. linear H1=1 太弱。
   p2 h5 50 步 true residual ≈ 7.76e-5，虽然 cheap，但预条件强度不足。

5. p2 h4 只做 memory audit。
   same-H1 p2 h4 real block assembly RSS ≈ 1.924 GB，没有求解，不能声称 p2 h4 已解决。

6. reduced/full Stage 4 未接入。
   当前没有 official R/T/A；不能把 task013 结果当成 production Stage 4 solver。
```

合并建议：

```text
merge_code: no
merge_docs_only: yes / optional

原因：FE-only qualification 给出 B 档正结果，但没有 reduced/full Stage 4 R/T/A。
下一步应先做 reduced Stage 4 real-split FE/aux block PC integration。
```

主要记录：

```text
docs/task013_real_split_ams_hx_qualification/outcomes/summary.md
docs/task013_real_split_ams_hx_qualification/outcomes/ams_memory_breakdown.md
docs/task013_real_split_ams_hx_qualification/outcomes/solver_profile_ranking.md
docs/task013_real_split_ams_hx_qualification/outcomes/merge_recommendation.md
docs/task013_real_split_ams_hx_qualification/outcomes/next_decision.md
```
