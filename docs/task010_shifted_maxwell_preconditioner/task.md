# CODEX TASK 20260707：Stage 4 3D Maxwell 物理预条件器与压缩直接预条件器原型验证

## 0. 分支与执行流程

本任务书写在当前 task009 分支中，供下一轮本地执行。**不要由 ChatGPT 代为创建远程分支。**

当前已完成分支：

```text
codex/20260706-iterative-solver-profile-screening
```

开始 task010 前，建议先完成 task009 审查、必要小修和合并：

```bash
git checkout master
git pull
git merge codex/20260706-iterative-solver-profile-screening
git push origin master
```

然后由本地 Codex/开发者从更新后的 `master` 新建 task010 分支，例如：

```bash
git checkout -b codex/20260707-maxwell-physics-blr-preconditioner-prototype
git push -u origin codex/20260707-maxwell-physics-blr-preconditioner-prototype
```

推荐本任务分支名：

```text
codex/20260707-maxwell-physics-blr-preconditioner-prototype
```

开始前必须阅读：

```text
docs/task009_iterative_solver_profile_screening/review_report.md
docs/task009_iterative_solver_profile_screening/outcomes/summary.md
docs/task009_iterative_solver_profile_screening/outcomes/profile_ranking.md
docs/task009_iterative_solver_profile_screening/outcomes/workstation_recommendation.md
docs/task009_iterative_solver_profile_screening/outcomes/iterative_profile_summary.csv
docs/task008_70nm_official_convergence_benchmark/review_report.md
docs/task008_70nm_official_convergence_benchmark/outcomes/summary.md
docs/task008_70nm_official_convergence_benchmark/outcomes/p2_convergence.csv
docs/task007_dtn_port_modal_official_rta/review_report.md
notes/reference/current_version_boundaries.md
README.md
```

同时阅读用户上传论文：

```text
High Performance Parallel Solvers for the time-harmonic Maxwell Equations
arXiv:2507.13066v1
```

该论文对本任务的启发是：普通 SAI/RAS 类黑盒预条件器不是最有希望方向；更值得优先尝试的是：

```text
1. MUMPS Block Low-Rank factorization as FGMRES preconditioner；
2. Hiptmair-Xu / hypre AMS based positive Maxwell preconditioner；
3. positive / shifted Maxwell operator used as preconditioner。
```

本任务的任务书、outcomes 和后续 review report 都应保存在：

```text
docs/task010_shifted_maxwell_preconditioner/
├── task.md
├── outcomes/
└── review_report.md
```

目录名保留 `shifted_maxwell_preconditioner`，但本轮任务已经扩展为：

```text
Maxwell physics-based and compressed-direct preconditioner prototype
```

所有轻量结果写入：

```text
docs/task010_shifted_maxwell_preconditioner/outcomes/
```

不要改写 task000-task009 的 outcomes 或 review report。

---

## 1. 本任务与后续任务拆分

此前确定的四个优先级为：

```text
Priority 1: compressed direct / BLR and shifted/positive Maxwell 物理预条件器；
Priority 2: FEM field + DtN auxiliary block / Schur 预条件器；
Priority 3: H(curl) AMS / Hiptmair-Xu auxiliary-space 预条件器；
Priority 4: two-level DDM / matrix-free Krylov。
```

本轮拆分为：

```text
Task010 = 短期最可能落地的 compressed-direct + physics-based preconditioner prototype：
          A. MUMPS-BLR as FGMRES preconditioner；
          B. positive / shifted Maxwell preconditioner；
          C. HX/AMS real-split feasibility；
          D. 最小 FE/aux block-Schur feasibility。

Task011 = 若 Task010 仍无 production candidate，再进入：
          H(curl) AMS 完整实现、two-level DDM、matrix-free Krylov / sweeping。
```

本 task010 的第一优先级是 **MUMPS-BLR quick test**，因为它最接近当前 MUMPS/direct 路径，短期最可能在 1 TB 工作站上突破 `p=2 h=1.5` 或 `p=2 h=1`。

---

## 2. 背景

task009 已完成 PETSc 现成黑盒 iterative profiles 快速筛选。结论是：

```text
GMRES/FGMRES/BiCGStab + Jacobi/BJacobi/ASM/ILU/local LU 没有任何 profile 达到 rtol=1e-6；
没有任何 iterative run 生成可信 official R/T/A；
GMRES + Jacobi 只是 residual-only diagnostic path，不是 production solver；
ASM/ILU/local LU、BiCGStab、GAMG、现成 fieldsplit Schur 均未给出 production candidate。
```

另外，task009 里必须更正 residual 口径：

```text
p=2 h=1.5 的 3.56e-3 是 residual_final_over_initial，不是 true_relative_residual_norm；
对应 true_relative_residual_norm 约为 1.62e-1。
```

因此 task010 不再继续盲扫黑盒 PETSc profile，而是转向 Maxwell 专用或半专用预条件器。

---

## 3. 固定物理与几何设置

所有 task010 测试均固定使用 task008/task009 主设置：

```text
stage_case = stage4_block_grating
period_x = 50 nm
period_y = 25 nm
domain_x = 50 nm
domain_y = 25 nm
substrate_thickness = 10 nm
grating_height = 120 nm
top_air_above_grating = 10 nm
air_height = 130 nm
total_height = 140 nm
grating_width_x = 17 nm
grating_width_y = 25 nm
lambda0 = 13.5 nm
incident_theta_from_z_deg = 80
incident_azimuth_phi_deg = 0
polarization_kind = s
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
official_power_source = dtn_port_modal_amplitudes
A = A_volume_total from volume_integral_Im_epsilon_E2
MPI ranks = 8 unless otherwise specified
```

必须保留 task008 中验证过的：

```text
kx = 0.458350341046137
ky = 0
kz = -0.0808195317433606
Floquet phase x = -0.600741134898 - 0.799443612046j
Floquet phase y = 1
polarization = (0,1,0)
k dot E = 0
```

---

## 4. Stage A：MUMPS-BLR as FGMRES preconditioner

### 4.1 目标

优先实现并测试：

```text
FGMRES + MUMPS Block Low-Rank approximate factorization as preconditioner
```

解释：BLR 是压缩的 multifrontal factorization。它仍然属于近似 direct/factorization 路线，但可通过低秩压缩降低 factor memory，并作为 FGMRES 的预条件器使用。

该路线短期价值最高：

```text
1. 与当前 MUMPS/direct 路径最接近；
2. 不需要立即实现 H(curl) AMS 所需的 discrete gradient / nodal interpolation；
3. 可能直接帮助突破 p=2 h=1.5 的 direct memory boundary；
4. 若成功，可优先带到 1 TB 工作站。
```

### 4.2 必须实现的 BLR profiles

第一批 profiles：

```text
iter_fgmres_mumps_blr_eps1e-3
iter_fgmres_mumps_blr_eps1e-5
```

可选 profiles：

```text
iter_fgmres_mumps_blr_eps5e-3
iter_fgmres_mumps_blr_eps1e-4
iter_fgmres_mumps_blr_eps1e-9
```

PETSc/MUMPS 选项需要 Codex 根据当前 PETSc/MUMPS build 确认。必须在 `implementation_notes.md` 中记录实际使用的 MUMPS BLR ICNTL/CNTL 选项，例如：

```text
mat_mumps_icntl_35 / mat_mumps_cntl_7 / other BLR-related options
```

如果当前 PETSc/MUMPS build 不支持 BLR，必须明确输出：

```text
mumps_blr_supported = false
reason = ...
```

并生成 `mumps_blr_feasibility.md`，不要伪造结果。

### 4.3 BLR KSP 口径

BLR profiles 应优先使用：

```text
-ksp_type fgmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_norm_type unpreconditioned
-pc_side right
-pc_type lu
-pc_factor_mat_solver_type mumps
MUMPS BLR enabled
```

如果 PETSc 的 BLR factorization 只能作为 PC factor 使用，而不是独立 P matrix，仍可接受；但必须记录：

```text
BLR is used as compressed factorization PC, not as separate assembled P matrix.
```

### 4.4 BLR 测试流程

先运行：

```text
p=2 h=5
p=2 h=4
```

若至少一个 BLR profile 收敛或明显优于 task009 Jacobi，再继续：

```text
p=2 h=3
p=2 h=2.5
p=2 h=2
```

只有当 `p=2 h=2` 收敛并复现 task008 direct R/T/A 后，才尝试：

```text
p=2 h=1.5
```

必须比较：

```text
1. BLR factor memory vs full MUMPS direct factor memory；
2. compression ratio；
3. FGMRES iterations；
4. setup time / solve time；
5. R/T/A error vs direct；
6. 是否比 task009 Jacobi 更接近可用 production solver。
```

---

## 5. Stage B：positive / shifted Maxwell preconditioner

### 5.1 原系统

当前 Stage 4 dtn_port auxiliary 系统为：

```text
A x = b
```

其中 `A` 是原始 Maxwell + Floquet + DtN auxiliary augmented matrix。任何 shifted/positive matrix 都只能作为预条件器，不得改变原问题 residual 和 R/T/A 后处理。

### 5.2 Two candidate preconditioner matrices

本轮比较两个方向：

#### Candidate 1：shifted Maxwell

```text
P_shift(alpha) = curl curl - (1 + i alpha) k0^2 epsilon
```

对应 profiles：

```text
iter_fgmres_shifted_a0p2_asm1_ilu0
iter_fgmres_shifted_a0p5_asm1_ilu0
iter_fgmres_shifted_a1p0_asm1_ilu0
```

#### Candidate 2：positive Maxwell

参考论文中 HX 思路，构造 positive Maxwell-like preconditioner：

```text
P_positive ≈ curl curl + k0^2 epsilon + boundary_absorption
```

在论文符号中类似：

```text
C + M + B
```

对应 profiles：

```text
iter_fgmres_positive_maxwell_asm1_ilu0
iter_fgmres_positive_maxwell_asm1_lu
```

如果当前 code structure 难以精确构造 `C+M+B`，可以先实现最小版本：

```text
P_positive_minimal = FE field block with curl-curl + positive mass, same augmented size as A
```

但必须在 `implementation_notes.md` 中写清：

```text
哪些项被保留；
哪些项被忽略；
DtN auxiliary coupling 如何处理；
P 是否与 A 同尺寸同 layout。
```

### 5.3 KSP setOperators(A, P)

对于 shifted/positive Maxwell，必须支持：

```text
ksp.setOperators(A_original, P_preconditioner)
```

不得把 `P_preconditioner` 当成原问题直接求解。

### 5.4 Right preconditioning and residual norm

所有 shifted/positive profiles 必须优先使用：

```text
-pc_side right
-ksp_norm_type unpreconditioned
```

并显式计算：

```text
true_residual_norm = ||b - A x||
true_relative_residual_norm = ||b - A x|| / ||b||
```

### 5.5 测试流程

先 smoke test：

```text
p=2 h=5
profile = iter_fgmres_shifted_a0p5_asm1_ilu0
```

必须检查：

```text
A rows/cols == P rows/cols
A nnz, P nnz
A/P matrix norm
P 是否成功 assemble
KSP.setOperators(A, P) 是否成功
pc_side = right
ksp_norm_type = unpreconditioned
true residual 使用 A 而不是 P
```

然后运行：

```text
p=2 h=5
p=2 h=4
```

若有希望，再继续：

```text
p=2 h=3
p=2 h=2.5
p=2 h=2
p=2 h=1.5 only after h=2 converges and matches direct R/T/A
```

---

## 6. Stage C：HX/AMS real-split feasibility

### 6.1 目标

本阶段不要求完整实现 HX/AMS production solver，但必须评估可行性。

论文中的核心实现是：

```text
complex Maxwell system -> split into real/imag 2N system；
用 positive Maxwell block diag preconditioner；
每个 positive Maxwell block 用 Hiptmair-Xu / hypre AMS 近似求解。
```

因此本阶段输出 feasibility，而不是强行完成 production。

### 6.2 必须回答的问题

生成：

```text
hx_ams_feasibility.md
```

必须回答：

```text
1. 当前 DOLFINx Nedelec space 是否能构造对应 nodal H1 space？
2. 是否能构造 discrete gradient matrix G？
3. 是否能构造 Nedelec-to-nodal interpolation/prolongation P_curl？
4. 当前 complex matrix 是否能可靠 split 为 real 2N system？
5. hypre AMS 在当前 PETSc build 中是否可用？
6. 若可用，需要哪些 PETSc/HYPRE options？
7. 当前 DtN auxiliary unknowns 如何进入 real split system？
8. Floquet complex phase 是否会使 real split / AMS coupling 更复杂？
9. 若要把 HX/AMS 做成 task011，需要哪些最小代码改动？
```

### 6.3 可选 smoke test

若可行，可在一个极小 case 上测试：

```text
p=1 or p=2, h=5, simplified boundary/model
```

但不要让 HX/AMS 实现拖垮 task010。若 feasibility 不清楚，应优先如实记录而不是强行拼接。

---

## 7. Stage D：FE/aux block-Schur 最小 feasibility

这是 Priority 2 的最小探针，不是 task010 主线。生成：

```text
block_preconditioner_feasibility.md
```

必须回答：

```text
1. 当前 augmented matrix 是否能稳定构造 FE field unknowns 和 DtN auxiliary unknowns 的 IS？
2. FE block size 和 aux block size 分别是多少？
3. auxiliary block 是否足够小，能否 exact inverse / dense LU？
4. block extraction 是否在 MPI 下可靠？
5. 现成 PETSc fieldsplit 为什么在 task009 中停滞？
6. 下一步若要实现物理 Schur，需要哪些最小代码改动？
```

若 shifted/positive/BLR 已找到 production candidate，可以不深入 block-Schur，只保留 feasibility。

---

## 8. Official R/T/A 安全口径

保持 task009 的安全策略：

```text
如果 KSP 未收敛，不输出 official R/T/A；
可以输出 diagnostic residual-only summary；
不能把未收敛场用于物理结论。
```

若某个 profile 收敛，必须计算并比较：

```text
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R_plus_T_plus_A_volume
energy_closure_error
R/T/A error vs task008 direct reference
```

`p=2 h=2` direct reference：

```text
R_direct = 0.0013429328462348958
T_direct = 0.5992132294442478
A_direct = 0.3994438377095067
R+T+A = 0.9999999999999893
```

---

## 9. 必须记录字段

每个 run 至少记录：

```text
p
h_nm
profile_name
mpi_ranks
solver_method
ksp_type
pc_type
pc_side
ksp_norm_type
preconditioner_family
mumps_blr_enabled
mumps_blr_epsilon
mumps_blr_options
mumps_blr_compression_ratio
shifted_preconditioner_enabled
shifted_preconditioner_alpha
positive_maxwell_preconditioner_enabled
A_matrix_rows
P_matrix_rows
A_nnz_used
P_nnz_used
A_estimated_memory_GB
P_estimated_memory_GB
A_norm_frobenius
P_norm_frobenius
ksp_converged
ksp_converged_reason_text
ksp_iterations
ksp_initial_residual_norm
ksp_final_residual_norm
residual_final_over_initial
true_residual_norm
true_relative_residual_norm
setup_time_seconds
solve_time_seconds
elapsed_seconds
max_rss_mb
RSS_upper_GB
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R_plus_T_plus_A_volume
energy_closure_error_dtn_port_modal_volume
R_direct
T_direct
A_direct
abs_error_R
abs_error_T
abs_error_A
relative_error_R
relative_error_T
relative_error_A
status
case_status
failure_stage
returncode
stdout_tail
stderr_tail
```

---

## 10. 输出文件要求

本任务 outcomes 至少包含：

```text
docs/task010_shifted_maxwell_preconditioner/outcomes/
├── summary.md
├── implementation_notes.md
├── blr_profile_summary.csv
├── blr_vs_direct_rta.csv
├── shifted_positive_profile_summary.csv
├── shifted_positive_vs_direct_rta.csv
├── preconditioner_matrix_stats.csv
├── preconditioner_resource.csv
├── preconditioner_failure_cases.csv
├── preconditioner_profile_ranking.md
├── mumps_blr_feasibility.md
├── hx_ams_feasibility.md
├── block_preconditioner_feasibility.md
├── next_decision.md
├── workstation_recommendation.md
├── parameters.json
├── run_log.txt
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保存轻量文件：

```text
run_summary.json
progress_3d.jsonl
solver_log.txt
stdout_tail.txt
stderr_tail.txt
profile_row.json
preconditioner_matrix_stats.json
```

不要提交大型文件：

```text
results/*/*.vtu
results/*/*.bp
results/*/*.h5
完整 results/ 目录
大型临时矩阵文件
MUMPS OOC scratch 文件
```

---

## 11. summary.md 必须回答的问题

summary 必须用中文撰写，并回答：

1. MUMPS-BLR 是否被当前 PETSc/MUMPS build 支持？实际使用了哪些 BLR options？
2. BLR profiles 是否明显优于 task009 Jacobi/ASM/ILU？
3. BLR 是否能在 p=2 h=2 收敛并复现 direct R/T/A？
4. BLR 是否能尝试或突破 p=2 h=1.5？
5. shifted Maxwell P(alpha) 是否成功构造，是否与 A 同尺寸同 layout？
6. positive Maxwell preconditioner 是否成功构造？
7. shifted/positive profiles 是否明显优于 task009？
8. residual_final_over_initial 和 true_relative_residual_norm 是否一致？若不一致，如何解释？
9. HX/AMS real-split feasibility 如何？是否建议 task011 进入完整实现？
10. FE/aux block-Schur feasibility 如何？是否值得继续？
11. 是否建议上 1 TB 工作站？若建议，优先 profile 和 h 是什么？
12. 若仍失败，下一步是否转向 Task011：H(curl) AMS + two-level DDM / matrix-free？

---

## 12. workstation_recommendation.md 要求

必须给出明确工作站建议：

```text
workstation_first_profile = ... or none
workstation_second_profile = ... or none
workstation_first_case = p=2 h=1.5 or none
workstation_second_case = p=2 h=1 or none
```

判断原则：

```text
若 p=2 h=2 未收敛，不建议上工作站做 h=1/h=0.75 物理求解；
可以只建议 residual-only / memory 探针；
若 p=2 h=2 收敛且 R/T/A 对照通过，则可建议工作站先跑 p=2 h=1.5，再跑 h=1。
```

不得建议直接跳到：

```text
h = 0.14~0.16 nm
```

---

## 13. 验收标准

本任务通过标准：

1. 至少完成 MUMPS-BLR support check，并输出 `mumps_blr_feasibility.md`。
2. 若 MUMPS-BLR 可用，至少测试 `eps=1e-3` 和 `eps=1e-5` 在 `p=2 h=5/h=4` 上的表现。
3. 至少完成 shifted Maxwell 或 positive Maxwell 中一种 P 的 smoke test，并验证 `KSP.setOperators(A, P)` 或明确说明为什么当前实现不能做到。
4. 若 shifted/positive P 可构造，至少完成 `p=2 h=5/h=4` 的初筛。
5. 必须记录 KSP residual 和 true residual，且不得混淆二者。
6. 若有 profile 在 `p=2 h=2` 收敛，必须输出 official R/T/A 并对比 task008 direct reference。
7. 必须生成 `preconditioner_profile_ranking.md`、`next_decision.md` 和 `workstation_recommendation.md`。
8. 必须生成 `hx_ams_feasibility.md`，即使只是说明当前尚不能实现。
9. 不提交大型结果文件或空 placeholder raw files。

---

## 14. 不在本任务范围内的内容

本任务暂不做：

```text
1. 完整 H(curl) AMS / Hiptmair-Xu production solver；
2. two-level Schwarz / BDDC / FETI-DP 完整实现；
3. matrix-free operator 完整实现；
4. sweeping preconditioner；
5. 真实 0.7~0.8 nm 波长完整网格；
6. p polarization；
7. 反演流程；
8. common-reference-plane T。
```

这些内容留给可能的 Task011。是否开启 Task011，取决于 task010 的结果。

---

## 15. 最终预期

task010 完成后，应能回答：

```text
MUMPS-BLR 是否能作为短期工作站可用 preconditioner？
positive/shifted Maxwell 是否比 task009 黑盒 PETSc profiles 明显更有效？
是否有 profile 能在 p=2 h=2 上收敛并复现 direct R/T/A？
是否值得把某个 profile 带到 1 TB 工作站突破 p=2 h=1.5 / h=1？
HX/AMS 是否具备进入 task011 完整实现的条件？
如果 BLR、positive/shifted Maxwell 仍失败，下一步是否必须转向 H(curl) AMS、two-level DDM 或 matrix-free？
```
