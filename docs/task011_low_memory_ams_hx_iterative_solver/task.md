# CODEX TASK 20260707：Stage 4 3D Maxwell low-memory AMS/HX iterative solver prototype

## 0. 分支与执行流程

本任务书写在当前 task010 分支中，供下一轮本地执行。**不要由 ChatGPT 代为创建远程分支。**

当前已完成分支：

```text
codex/20260707-maxwell-physics-blr-preconditioner-prototype
```

开始 task011 前，建议先完成 task010 审查、必要小修和合并：

```bash
git checkout master
git pull
git merge codex/20260707-maxwell-physics-blr-preconditioner-prototype
git push origin master
```

然后从更新后的 `master` 新建 task011 分支，例如：

```bash
git checkout -b codex/20260707-low-memory-ams-hx-iterative-solver
git push -u origin codex/20260707-low-memory-ams-hx-iterative-solver
```

推荐分支名：

```text
codex/20260707-low-memory-ams-hx-iterative-solver
```

开始前必须阅读：

```text
docs/task010_shifted_maxwell_preconditioner/review_report.md
docs/task010_shifted_maxwell_preconditioner/outcomes/summary.md
docs/task010_shifted_maxwell_preconditioner/outcomes/mumps_blr_feasibility.md
docs/task010_shifted_maxwell_preconditioner/outcomes/hx_ams_feasibility.md
docs/task010_shifted_maxwell_preconditioner/outcomes/block_preconditioner_feasibility.md
docs/task010_shifted_maxwell_preconditioner/outcomes/blr_profile_summary.csv
docs/task009_iterative_solver_profile_screening/review_report.md
docs/task008_70nm_official_convergence_benchmark/review_report.md
docs/task008_70nm_official_convergence_benchmark/outcomes/p2_convergence.csv
notes/reference/current_version_boundaries.md
```

本任务所有文件保存到：

```text
docs/task011_low_memory_ams_hx_iterative_solver/
├── task.md
├── outcomes/
└── review_report.md
```

不要改写 task000-task010 的 outcomes 或 review report。

---

## 1. 背景与定位

Task009 结论：普通 PETSc 黑盒 iterative profiles 没有 production candidate。GMRES+Jacobi 内存较低但不收敛，不能输出 official R/T/A。

Task010 结论：FGMRES+MUMPS-BLR 在 `p=2 h=2` 上可收敛且 R/T/A 与 direct LU 一致，但 BLR 本质上仍是压缩直接 / 近似 factorization 路线，内存下降有限：

```text
direct LU RSS upper ≈ 20.53 GB
BLR eps=1e-5 RSS upper ≈ 17.85 GB
```

因此 task011 的目标不是继续调 BLR，而是探索真正的低内存迭代法。

本任务目标：

```text
找到或验证一个不依赖 global LU / MUMPS-BLR factorization 的迭代求解器路线；
它应能收敛、R/T/A 与 direct reference 基本一致，并且内存明显低于 direct/BLR。
```

不要把目标定成某个固定 GB 数字。先以“明显低于 direct/BLR 且结果正确”为第一标准。

---

## 2. 固定物理与参考解

所有主要测试保持 task008/task010 主设置：

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
MPI ranks = 8 unless otherwise specified
```

`p=2 h=2` direct reference：

```text
R_direct = 0.0013429328462348958
T_direct = 0.5992132294442478
A_direct = 0.3994438377095067
R+T+A = 0.9999999999999893
```

现有内存参考：

```text
p=2 h=2 direct LU RSS upper ≈ 20.53 GB
p=2 h=2 BLR eps=1e-5 RSS upper ≈ 17.85 GB
p=2 h=2 GMRES/Jacobi RSS upper ≈ 8.88 GB，但未收敛
```

---

## 3. Stage A：low-memory Krylov baseline

### 3.1 目的

建立“不使用 LU/BLR 时，assembled A + light preconditioner 的低内存基线”。这一步不一定成功，但能确定后续 AMS/HX 的收益。

### 3.2 禁止项

Stage A profiles 不得使用：

```text
global LU
local LU
MUMPS-BLR
MUMPS factor preconditioner
ASM/local LU
```

### 3.3 必测 profiles

新增并测试：

```text
iter_gmres_jacobi_restart20
iter_gmres_jacobi_restart40
iter_fgmres_jacobi_restart20
iter_lgmres_jacobi_restart20
iter_tfqmr_jacobi
iter_bicgstab_jacobi
iter_cgs_jacobi
```

若 PETSc 当前 build 不支持某 profile，必须记录在 `low_memory_krylov_failure_cases.csv`。

### 3.4 测试点

先跑：

```text
p=2 h=5
p=2 h=4
```

若 residual 明显下降，再跑：

```text
p=2 h=3
p=2 h=2.5
p=2 h=2
```

每个 run 记录：

```text
KSP type
PC type
restart / storage settings
iterations
KSP residual
true_relative_residual_norm
RSS upper GB
wall time
whether official R/T/A was allowed
R/T/A if converged
```

---

## 4. Stage B：H(curl) AMS/Hiptmair-Xu smoke test

### 4.1 目的

验证当前 DOLFINx + Nedelec + PETSc/hypre 环境能否真正构造 H(curl) auxiliary-space Maxwell preconditioner。

这不是 task010 的 positive Maxwell minimal P。真正 AMS/HX 需要 auxiliary-space 数据。

### 4.2 必须回答的问题

生成：

```text
ams_hx_smoke_notes.md
```

必须回答：

```text
1. PETSc 是否报告 hypre 可用？
2. hypre AMS 是否可通过 petsc4py 配置？
3. 当前 Nedelec space 对应的 compatible H1 nodal space 如何构造？
4. discrete gradient matrix G 如何构造？
5. AMS 需要的坐标、边元/节点映射、常量向量等数据如何提供？
6. 当前 complex PETSc 路径能否直接使用 AMS？
7. 若不能，是否需要 real/imag split？
8. Floquet MPC 约束会如何影响 G 和 H1 auxiliary space？
9. DtN auxiliary unknowns 暂时如何处理？
```

### 4.3 AMS smoke case

先做简化 FE-only case，不带 DtN auxiliary：

```text
positive Maxwell FE block: curl curl + k0^2 mass
boundary: simplest available valid boundary, preferably no DtN auxiliary
space: Nedelec p=1 first, then p=2 if possible
mesh: small h=5 or coarser smoke case
```

目标：

```text
AMS PC setup 成功；
KSP 能运行；
记录 residual 行为和内存；
不要求一开始复现 full Stage 4 R/T/A。
```

若 real-split 是必要的，本任务可只完成 real-split feasibility 和小矩阵构造，不强行完成 full solver。

---

## 5. Stage C：AMS/HX positive Maxwell FE-block preconditioner

如果 Stage B 证明 AMS 可用，则构造 FE-block preconditioner：

```text
P_FE ≈ positive Maxwell operator
P_FE^{-1} applied by AMS/HX
```

测试 profile：

```text
iter_fgmres_fe_ams_positive_maxwell
iter_fgmres_fe_ams_positive_maxwell_restart40
```

先在 simplified FE-only case 上测试：

```text
p=1 h=5
p=2 h=5
p=2 h=4
```

目标：

```text
不用 LU/BLR；
KSP 收敛或至少明显优于 Jacobi/ASM；
内存明显低于 direct/BLR；
记录 true residual。
```

---

## 6. Stage D：Stage 4 FE/aux block diagonal preconditioner

若 Stage C 有希望，再接入完整 Stage 4 augmented system。

当前 unknowns 结构：

```text
[ FE Nedelec field unknowns ; DtN auxiliary modal unknowns ]
```

第一版 block preconditioner：

```text
P^{-1} ≈ diag(P_FE_AMS^{-1}, I_aux)
```

其中：

```text
FE block: AMS/HX positive Maxwell preconditioner
aux block: identity or diagonal
coupling: first version ignored
```

测试 profiles：

```text
iter_fgmres_stage4_blockdiag_fe_ams_aux_identity
iter_fgmres_stage4_blockdiag_fe_ams_aux_diag
```

测试顺序：

```text
p=2 h=5
p=2 h=4
p=2 h=3
p=2 h=2.5
p=2 h=2 only if smaller cases show convergence
```

收敛后必须输出 official R/T/A，并与 direct reference 对比。

---

## 7. Stage E：matrix-free matvec feasibility

本阶段是后续降内存基础，不要求完成 full matrix-free solver。

目标：验证小 case 上：

```text
A_shell x ≈ A_aij x
```

测试：

```text
p=1 h=5 small case
p=2 h=5 small case
```

必须输出：

```text
matrix_free_matvec_feasibility.md
```

内容包括：

```text
1. MatShell / matrix-free operator 是否可实现；
2. FE curl-curl / mass matvec 如何做；
3. Floquet MPC 如何处理；
4. DtN auxiliary coupling 如何处理；
5. 与 assembled AIJ matvec 的相对误差；
6. 是否值得后续单独开 matrix-free task。
```

---

## 8. official R/T/A 安全口径

保持 task009/task010 的安全策略：

```text
KSP 未收敛时，不输出 official R/T/A；
可以输出 diagnostic residual-only summary；
不能把未收敛场用于物理结论。
```

若某个 run 收敛，必须计算：

```text
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R_plus_T_plus_A_volume
energy_closure_error
R/T/A error vs direct reference
```

---

## 9. 成功/失败分级

### A 档：真实低内存迭代候选

```text
p=2 h=2 收敛；
true_relative_residual_norm 达到 rtol 量级；
R/T/A 与 direct reference 基本一致；
不使用 LU/BLR；
RSS upper 明显低于 BLR/direct。
```

### B 档：有希望

```text
p=2 h=3 或 h=2.5 收敛；
R/T/A 与对应 direct/BLR reference 基本一致；
p=2 h=2 尚未完全成功；
内存明显低于 direct/BLR。
```

### C 档：基础设施成功

```text
AMS/HX setup 成功；
或 real-split / G matrix / H1 auxiliary space 构造成功；
或 matrix-free matvec 对照成功；
但尚不能作为 solver。
```

### D 档：失败

```text
AMS/HX 无法 setup；
低内存 Krylov 与 Jacobi baseline 无改善；
Stage 4 block diagonal residual 停滞；
true residual 与 KSP residual 严重背离且无法解释。
```

---

## 10. 必须输出文件

```text
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/
├── summary.md
├── low_memory_krylov_summary.csv
├── low_memory_krylov_failure_cases.csv
├── ams_hx_smoke_notes.md
├── ams_hx_smoke_summary.csv
├── stage4_blockdiag_ams_summary.csv
├── stage4_blockdiag_ams_vs_direct_rta.csv
├── matrix_free_matvec_feasibility.md
├── solver_memory_comparison.csv
├── profile_ranking.md
├── next_decision.md
├── parameters.json
├── changed_files.md
├── run_log.txt
└── raw_runs/
```

`raw_runs/` 只保存轻量、有内容的文件。不要提交 0-line placeholder，也不要提交大型 results 文件。

---

## 11. summary.md 必须回答

1. 哪些 low-memory Krylov profiles 已测试？哪些完全失败？
2. 是否有不使用 LU/BLR 的 profile 能收敛？
3. AMS/HX smoke test 是否成功？
4. 是否需要 real/imag split？
5. discrete gradient / H1 auxiliary space 是否可构造？
6. Stage 4 FE/aux block diagonal AMS 是否能运行？
7. 若收敛，R/T/A 是否与 direct reference 一致？
8. 内存是否明显低于 direct/BLR？
9. matrix-free matvec feasibility 是否通过？
10. 下一步应继续 AMS/HX、block-Schur，还是 matrix-free？

---

## 12. 不在本任务范围内

```text
1. 继续调 MUMPS-BLR epsilon；
2. 工作站 h=1.5/h=1 大规模求解；
3. 完整 two-level DDM / BDDC / FETI-DP；
4. 完整 matrix-free production solver；
5. 真实 0.7~0.8 nm 波长完整网格；
6. 反演流程。
```

这些可根据 task011 结果另开任务。

---

## 13. 最终预期

task011 完成后，应能回答：

```text
是否存在一个不依赖 LU/BLR 的真实迭代求解器候选？
AMS/HX 是否能在当前 DOLFINx + Nedelec + Floquet + DtN auxiliary 框架下推进？
若不能，卡点是 complex path、real split、G matrix、Floquet MPC，还是 DtN auxiliary block？
当前 assembled matrix 路径下最低内存 baseline 是多少？
后续是否需要转向 matrix-free 或更强 block-Schur / DDM？
```
