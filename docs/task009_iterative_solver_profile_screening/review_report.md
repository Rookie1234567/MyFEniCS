# REVIEW REPORT 20260707：Task009 Stage 4 3D Maxwell 迭代求解器 profiles 快速筛选

## 1. 审查对象

本报告审查分支：

```text
codex/20260706-iterative-solver-profile-screening
```

对应任务目录：

```text
docs/task009_iterative_solver_profile_screening/
```

重点阅读文件：

```text
docs/task009_iterative_solver_profile_screening/task.md
docs/task009_iterative_solver_profile_screening/outcomes/summary.md
docs/task009_iterative_solver_profile_screening/outcomes/profile_ranking.md
docs/task009_iterative_solver_profile_screening/outcomes/workstation_recommendation.md
docs/task009_iterative_solver_profile_screening/outcomes/iterative_profile_summary.csv
docs/task009_iterative_solver_profile_screening/outcomes/iterative_vs_direct_rta.csv
docs/task009_iterative_solver_profile_screening/outcomes/iterative_resource.csv
docs/task009_iterative_solver_profile_screening/outcomes/iterative_failure_cases.csv
docs/task009_iterative_solver_profile_screening/outcomes/parameters.json
docs/task009_iterative_solver_profile_screening/outcomes/changed_files.md
src/common/config_3d.py
src/solvers/common_3d_solve.py
src/solvers/dtn_port_3d.py
src/solvers/common_3d_case_flow.py
src/studies/run_3d_matrix_scale.py
```

本轮任务目标是：在 task008 的 direct-reference cases 上快速筛选 PETSc 现成 iterative profiles，尽快判断是否存在可用于 1 TB 工作站扩展的候选迭代求解器。

---

## 2. 总体结论

Task009 主目标已经完成，可以作为“现成 PETSc 黑盒 iterative profiles 的筛选记录”和“负结果基线”保留。

结论明确：

```text
当前测试的 GMRES / FGMRES / BiCGStab + Jacobi / BJacobi / ASM / ILU / local LU / GAMG / FieldSplit 组合中，没有任何一个达到生产级收敛；没有任何 iterative run 生成可信 official R/T/A。
```

因此，本轮没有找到可直接替代 MUMPS direct 的 production iterative solver。

当前唯一保留价值较高的是：

```text
iter_gmres_jacobi
```

但它只能作为 residual-only diagnostic path，不能作为物理求解器。它可以越过 `p=2 h=1.5` direct solver 在 KSP setup 阶段被系统 kill 的边界，但 1000 步后仍未收敛，且 true residual 仍很大。

本报告建议：

```text
1. 接受 task009 的负结果；
2. 合并 task009 的代码基础设施和 outcomes；
3. 不再继续把主要时间花在 Jacobi/BJacobi/ASM/ILU/local LU 的小调参；
4. 下一步转向 Maxwell 专用预条件器和压缩直接预条件器，例如 MUMPS-BLR、positive/shifted Maxwell、HX/AMS。
```

---

## 3. 已实现 profiles 审查

本轮实现并测试了任务书要求的 profiles：

```text
iter_gmres_none
iter_gmres_jacobi
iter_gmres_bjacobi_ilu0
iter_fgmres_asm1_ilu0
iter_fgmres_asm2_ilu0
iter_fgmres_asm1_ilu1
iter_fgmres_asm1_lu
iter_fgmres_asm2_lu
iter_bicgstab_asm1_ilu0
iter_bicgstab_bjacobi_ilu0
```

并额外测试了：

```text
iter_fgmres_gamg
iter_fgmres_fieldsplit_schur_asm1_lu
iter_gmres_jacobi_maxit5000
experimental_lgmres_jacobi
experimental_hypre_boomeramg
```

代码中已经把 iterative profiles 与 direct solver profile 区分开，并记录了 KSP type、PC type、sub-PC、iterations、residual、setup/solve time、memory 等字段。这个基础设施对后续 task010/task011 仍然有用。

---

## 4. 主要数值结果审查

### 4.1 required profiles 无一收敛

所有 required profiles 在 `p=2 h=5` 和 `p=2 h=4` 初筛中均未达到 `rtol=1e-6`。

代表性结果：

| profile | h=4 residual final/initial | 判断 |
|---|---:|---|
| iter_gmres_none | 0.1767 | 有下降，但弱于 Jacobi |
| iter_gmres_jacobi | 0.01169 | required profiles 中相对最好 |
| iter_gmres_bjacobi_ilu0 | 46.97 | 发散/恶化 |
| iter_fgmres_asm1_ilu0 | 0.99999 | 基本停滞 |
| iter_fgmres_asm2_ilu0 | 0.99998 | 基本停滞 |
| iter_fgmres_asm1_ilu1 | 0.8903 | 未形成有效预条件 |
| iter_fgmres_asm1_lu | 0.9988 | local LU 未改善全局收敛 |
| iter_bicgstab_asm1_ilu0 | 21891.6 | 发散 |

这说明普通 ASM/RAS-like one-level subdomain preconditioner 在当前矩阵上没有起到有效的全局谱改善作用。

### 4.2 GMRES + Jacobi 是唯一可保留的 diagnostic path

`iter_gmres_jacobi` 从 `h=5` 到 `h=1.5` 都能稳定降低 KSP residual：

| h/nm | iterations | residual final/initial | RSS upper GB | status |
|---:|---:|---:|---:|---|
| 5 | 1000 | 0.01775 | 2.64 | failed_not_converged |
| 4 | 1000 | 0.01169 | 3.27 | failed_not_converged |
| 3 | 1000 | 0.00791 | 4.33 | failed_not_converged |
| 2.5 | 1000 | 0.00685 | 5.76 | failed_not_converged |
| 2 | 1000 | 0.00504 | 8.88 | failed_not_converged |
| 1.5 | 1000 | 0.00356 | 13.99 | failed_not_converged |

该 profile 的价值是：

```text
1. 内存显著低于 direct LU factorization；
2. 能跑过 direct 在 p=2 h=1.5 的 setup kill 边界；
3. 可用于工作站 residual/memory/matvec 诊断。
```

但它不能作为生产求解器，原因是：

```text
1. 未达到 KSP 收敛；
2. 未生成 official R/T/A；
3. true residual 仍然很大；
4. 加长到 5000 步仍停滞在 1e-2 级别的 KSP residual final/initial。
```

### 4.3 重要更正：3.56e-3 不是 true relative residual

task009 summary 和 docs 中有一处表达需要特别注意：

```text
p=2 h=1.5 的 3.56e-3 是 residual_final_over_initial，不是 true_relative_residual_norm。
```

CSV 中对应数据为：

```text
p=2 h=1.5, iter_gmres_jacobi:
residual_final_over_initial = 0.003558492368846422
true_relative_residual_norm = 0.16174109818404858
```

`p=2 h=2` 也类似：

```text
residual_final_over_initial = 0.005036181952190794
true_relative_residual_norm = 0.19617301722076627
```

这说明 task009 中 KSP residual 与 true residual 存在明显差异。这个问题不改变“未收敛、不能出物理结果”的结论，但会影响对 Jacobi 的乐观程度。

后续任务必须明确：

```text
1. 同时记录 KSP residual 和 true residual；
2. 不把 preconditioned/KSP residual final-over-initial 误写成 true relative residual；
3. 优先使用 right preconditioning 和 unpreconditioned residual norm 进行新 profile 测试。
```

建议 task009 文档可不强制回改，但 task010 summary 必须更正该口径。

---

## 5. 额外探针审查

### 5.1 GAMG

`iter_fgmres_gamg` 可运行，但 residual final/initial 约 `0.154~0.156`，且内存高于 Jacobi。当前不推荐作为主线。

### 5.2 FieldSplit Schur

`iter_fgmres_fieldsplit_schur_asm1_lu` 可运行，但 residual 基本不变，final/initial 接近 1。

这并不说明 block preconditioner 方向失败，只能说明：

```text
当前 PETSc 现成 FE/aux FieldSplit + selfp/ASM-LU 不是有效物理 Schur 预条件器。
```

后续若继续 block preconditioner，应当设计物理 block/Schur 结构，而不是简单重复现成 fieldsplit。

### 5.3 LGMRES/Jacobi 和 maxit=5000

LGMRES 没有改善 GMRES/Jacobi；GMRES/Jacobi 加长到 5000 步仍停滞，说明问题不是简单增加迭代次数即可解决。

### 5.4 hypre BoomerAMG

`experimental_hypre_boomeramg` 在 complex PETSc 路径下崩溃。本轮不建议继续该路径。若要测试 hypre AMS/HX，建议后续考虑 real-split system 和 Maxwell-specific AMS，而不是 complex matrix 上直接套 BoomerAMG。

---

## 6. 对工作站求解的判断

task009 没有给出可以直接带到 1 TB 工作站做物理求解的 profile。

可以带到工作站的只有：

```text
iter_gmres_jacobi 作为 residual-only diagnostic path
```

使用场景：

```text
1. p=2 h=1.5 长迭代 residual 曲线；
2. p=2 h=1 的 matrix/matvec/RSS 探针；
3. 判断装配、matvec 和 Krylov memory 是否可承受。
```

不能用于：

```text
1. 生成 official R/T/A；
2. 判定物理收敛；
3. 直接外推 h=0.5 或 h=0.14~0.16 nm 的可行性。
```

---

## 7. 是否建议合并

建议合并，但只能以如下语义合并：

```text
task009 是 iterative profile screening infrastructure + negative result record。
```

不要以如下语义合并：

```text
已经找到可用的 iterative production solver。
```

建议合并前或合并后轻量修正 README/summary 中对 true residual 的表述：

```text
把“true relative residual≈3.56e-3”改为“KSP residual final/initial≈3.56e-3，而 true relative residual≈1.62e-1”。
```

当前分支中的代码基础设施值得保留：

```text
1. iterative solver profile 表；
2. residual / true residual / time / memory 输出；
3. 未收敛时禁止 official R/T/A；
4. FieldSplit IS 和后续 block preconditioner 的初步支撑。
```

---

## 8. 下一步建议

读完新论文 `High Performance Parallel Solvers for the time-harmonic Maxwell Equations` 后，下一步不建议只做 shifted Maxwell，而应把 task010 调整为更贴近论文启发的三条线：

```text
Stage A: MUMPS-BLR as FGMRES preconditioner quick test；
Stage B: positive / shifted Maxwell preconditioner prototype；
Stage C: HX/AMS real-split feasibility report。
```

原因：

```text
1. 论文中 SAI/RAS 不是最终推荐方向，和 task009 负结果一致；
2. 论文中 HX/AMS 和 MUMPS-BLR 是最有希望的方向；
3. BLR 可能是短期最容易在当前 complex PETSc/MUMPS 路径上尝试的工作站候选；
4. HX/AMS 更符合 H(curl) Maxwell 结构，但可能需要 real/imag split 和 auxiliary-space 矩阵构造，适合作为 feasibility 阶段或后续 task011。
```

因此，task010 应从“单纯 shifted Maxwell”升级为：

```text
Task010：Maxwell physics-based and compressed-direct preconditioner prototype
```

---

## 9. 最终结论

```text
task009 通过；
建议合并为 iterative screening 基础设施与负结果记录；
当前没有 production iterative solver；
GMRES+Jacobi 仅作为 residual-only diagnostic path；
下一步应转向 MUMPS-BLR、positive/shifted Maxwell、HX/AMS feasibility。
```

关键记录：

```text
Best diagnostic profile: iter_gmres_jacobi
p=2 h=2: residual_final_over_initial≈5.04e-3, true_relative_residual≈1.96e-1, not converged
p=2 h=1.5: residual_final_over_initial≈3.56e-3, true_relative_residual≈1.62e-1, not converged
No official R/T/A from iterative runs
No production candidate from black-box PETSc profiles
```
