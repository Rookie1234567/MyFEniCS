# Outcome Summary

## Task

task009：Stage 4 3D Maxwell + DtN port 的 PETSc 迭代求解器 profiles 快速筛选。

## Branch

`codex/20260706-iterative-solver-profile-screening`

## 结论先行

本轮要求的 PETSc 黑盒 iterative profiles 没有任何一个达到 `rtol=1e-6`，因此没有任何 iterative run 产生可接受的 official R/T/A。最接近可继续诊断的是 `iter_gmres_jacobi`：它内存低，能跑过 `p=2 h=1.5` 的 KSP setup 边界，1000 步后 true relative residual 约为 `3.56e-3`。但它仍未收敛，不能作为 production solver，也不能替代 task008 direct benchmark。

## 表 1：测试设置

| item | value |
|---|---|
| geometry | 50 x 25 x 140 nm, grating 17 x 25 x 120 nm |
| incidence | theta_from_z=80 deg, phi=0 deg, s polarization |
| official reference | task008 p=2 h=2 direct |
| MPI | 8 |
| target | iterative profile screening |
| power source | dtn_port_modal_amplitudes + A_volume |

## 表 2：profiles 列表

| profile | ksp | pc | overlap | sub_pc | purpose |
|---|---|---|---:|---|---|
| iter_gmres_none | gmres | none | - | - | 无预条件 baseline |
| iter_gmres_jacobi | gmres | jacobi | - | - | 最稳定下降的低内存 baseline |
| iter_gmres_bjacobi_ilu0 | gmres | bjacobi | - | ilu0 | 块 Jacobi/ILU0 baseline |
| iter_fgmres_asm1_ilu0 | fgmres | asm | 1 | ilu0 | 任务书首选 profile |
| iter_fgmres_asm2_ilu0 | fgmres | asm | 2 | ilu0 | 检查 overlap=2 |
| iter_fgmres_asm1_ilu1 | fgmres | asm | 1 | ilu1 | 检查 ILU fill level |
| iter_fgmres_asm1_lu | fgmres | asm | 1 | local lu | 强局部直接解 |
| iter_fgmres_asm2_lu | fgmres | asm | 2 | local lu | 更强 overlap + local LU |
| iter_bicgstab_asm1_ilu0 | bcgs | asm | 1 | ilu0 | PETSc 中 BiCGStab 对应 `bcgs` |
| iter_bicgstab_bjacobi_ilu0 | bcgs | bjacobi | - | ilu0 | PETSc bcgs/bjacobi 备选 |

## 表 3：p=2 h=5/h=4 初筛结果

| profile | h | converged | iterations | final residual | final/initial | RSS upper GB | status |
|---|---:|---|---:|---:|---:|---:|---|
| iter_gmres_none | 5 | False | 1000 | 1.340 | 0.1967 | 2.794 | failed |
| iter_gmres_none | 4 | False | 1000 | 1.308 | 0.1767 | 3.297 | failed |
| iter_gmres_jacobi | 5 | False | 1000 | 0.1209 | 0.01775 | 2.643 | failed |
| iter_gmres_jacobi | 4 | False | 1000 | 0.08653 | 0.01169 | 3.266 | failed |
| iter_gmres_bjacobi_ilu0 | 5 | False | 1000 | 339.8 | 49.90 | 2.654 | failed |
| iter_gmres_bjacobi_ilu0 | 4 | False | 80 | 347.7 | 46.97 | 3.263 | failed |
| iter_fgmres_asm1_ilu0 | 5 | False | 1000 | 6.810 | 0.99998 | 2.890 | failed |
| iter_fgmres_asm1_ilu0 | 4 | False | 1000 | 7.402 | 0.99999 | 3.656 | failed |
| iter_fgmres_asm2_ilu0 | 5 | False | 1000 | 6.810 | 0.99996 | 3.234 | failed |
| iter_fgmres_asm2_ilu0 | 4 | False | 1000 | 7.402 | 0.99998 | 3.986 | failed |
| iter_fgmres_asm1_ilu1 | 5 | False | 1000 | 23.63 | 3.469 | 3.622 | failed |
| iter_fgmres_asm1_ilu1 | 4 | False | 1000 | 6.590 | 0.8903 | 5.099 | failed |
| iter_fgmres_asm1_lu | 5 | False | 1000 | 6.801 | 0.9987 | 3.605 | failed |
| iter_fgmres_asm1_lu | 4 | False | 1000 | 7.393 | 0.9988 | 5.278 | failed |
| iter_fgmres_asm2_lu | 5 | False | 1000 | 6.772 | 0.9943 | 4.560 | failed |
| iter_fgmres_asm2_lu | 4 | False | 1000 | 7.382 | 0.9973 | 6.609 | failed |
| iter_bicgstab_asm1_ilu0 | 5 | False | 1000 | 4.041e4 | 5.934e3 | 2.911 | failed |
| iter_bicgstab_asm1_ilu0 | 4 | False | 1000 | 1.620e5 | 2.189e4 | 3.525 | failed |
| iter_bicgstab_bjacobi_ilu0 | 5 | False | 1000 | 7.707e4 | 1.132e4 | 2.648 | failed |
| iter_bicgstab_bjacobi_ilu0 | 4 | False | 5 | 2.876e8 | 3.885e7 | 3.260 | failed |

## 表 4：p=2 h=3/h=2.5 复筛结果

| profile | h | converged | iterations | final residual | final/initial | RSS upper GB | status |
|---|---:|---|---:|---:|---:|---:|---|
| iter_gmres_jacobi | 3 | False | 1000 | 0.06157 | 0.007913 | 4.332 | failed |
| iter_gmres_jacobi | 2.5 | False | 1000 | 0.05254 | 0.006853 | 5.756 | failed |

## 表 5：p=2 h=2 direct-reference 复现结果

| profile | converged | iterations | R_iter | T_iter | A_iter | abs_error_R | abs_error_T | abs_error_A | RSS upper GB | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| iter_gmres_jacobi | False | 1000 | - | - | - | - | - | - | 8.880 | failed |

`iter_gmres_jacobi` 在 h=2 的 residual final/initial 为 `0.005036`，但未收敛，所以正式后处理被跳过，不能比较 R/T/A。

## 表 6：p=2 h=1.5 boundary 尝试

| profile | status | iterations | final residual | final/initial | R | T | A | RSS upper GB | failure stage | note |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| iter_gmres_jacobi | failed_not_converged | 1000 | 0.02845 | 0.003558 | - | - | - | 13.99 | - | 越过 direct KSP setup 边界，但未收敛 |

## 表 7：profile ranking

| rank | profile | grade | reason | workstation use |
|---:|---|---|---|---|
| 1 | iter_gmres_jacobi | B- / diagnostic only | 唯一在 h=5 到 h=1.5 均稳定降低 residual；h=1.5 可完成 1000 步，RSS upper 约 13.99 GB；但无法达到 rtol=1e-6，也无 R/T/A | 1 TB 工作站第一诊断 profile，不是 production solver |
| 2 | iter_gmres_none | C | 无预条件也下降，但比 Jacobi 弱，工程上没有优势 | 只作 baseline |
| 3 | iter_fgmres_gamg | C- | GAMG 可运行但 residual 只降到约 0.15，内存高于 Jacobi | 不推荐，除非后续专门调 GAMG |
| 4 | iter_fgmres_fieldsplit_schur_asm1_lu | C- | FE/aux fieldsplit 可运行，但 residual 基本不变 | 当前不推荐 |
| 5 | ASM/BJacobi/ILU/LU/BiCGStab 系列 | C | 多数停滞、发散或 breakdown；local LU/overlap 也未改善 | 淘汰 |

## 额外探针

| profile | h | reason | iterations | final/initial | RSS upper GB | note |
|---|---:|---|---:|---:|---:|---|
| iter_fgmres_gamg | 5 | DIVERGED_MAX_IT | 1000 | 0.1544 | 5.171 | 额外 PETSc AMG 探针 |
| iter_fgmres_gamg | 4 | DIVERGED_MAX_IT | 1000 | 0.1564 | 7.482 | 额外 PETSc AMG 探针 |
| iter_fgmres_fieldsplit_schur_asm1_lu | 5 | DIVERGED_MAX_IT | 1000 | 0.9996 | 3.668 | 额外 FE/aux block split 探针 |
| iter_fgmres_fieldsplit_schur_asm1_lu | 4 | DIVERGED_MAX_IT | 1000 | 0.9997 | 5.528 | 额外 FE/aux block split 探针 |
| iter_gmres_jacobi_maxit5000 | 5 | DIVERGED_MAX_IT | 5000 | 0.01073 | 2.765 | Jacobi 加长迭代，仍停滞 |
| iter_gmres_jacobi_maxit5000 | 4 | DIVERGED_MAX_IT | 5000 | 0.008239 | 3.270 | Jacobi 加长迭代，仍停滞 |
| experimental_lgmres_jacobi | 5 | DIVERGED_MAX_IT | 1000 | 0.01798 | 2.765 | LGMRES 未改善 GMRES/Jacobi |
| experimental_lgmres_jacobi | 4 | DIVERGED_MAX_IT | 1000 | 0.01137 | 3.261 | LGMRES 未改善 GMRES/Jacobi |
| experimental_hypre_boomeramg | 5 | MPI abort | - | - | 2.792 | complex PETSc 路径下崩溃 |

## 回答 task009 关键问题

1. 已实现 required profiles：`iter_gmres_none`、`iter_gmres_jacobi`、`iter_gmres_bjacobi_ilu0`、`iter_fgmres_asm1_ilu0`、`iter_fgmres_asm2_ilu0`、`iter_fgmres_asm1_ilu1`、`iter_fgmres_asm1_lu`、`iter_fgmres_asm2_lu`、`iter_bicgstab_asm1_ilu0`、`iter_bicgstab_bjacobi_ilu0`。PETSc 本机名称中 BiCGStab 对应 `bcgs`。
2. required profiles 中没有任何一个在 h=4 收敛；BJacobi/ILU、ASM/ILU/LU、BiCGStab 系列应淘汰。
3. 没有任何 profile 能复现 p=2 h=2 direct R/T/A；所有 iterative runs 均未达到收敛，正式后处理被跳过。
4. `iter_gmres_jacobi` 能尝试并越过 p=2 h=1.5 direct failure boundary 的 KSP setup 阶段，但只完成未收敛的 1000 步。
5. 1 TB 工作站若必须继续 PETSc 黑盒路线，第一诊断 profile 是 `iter_gmres_jacobi`，但只能用于 residual/memory 探路。
6. 当前没有可作为 production 的第二备选；`iter_fgmres_gamg` 和 fieldsplit 只能保留为后续调参方向。
7. 需要转向 shifted Maxwell、H(curl) AMS、two-level DDM 或 matrix-free + physics-based preconditioner。普通 Jacobi/BJacobi/ASM/ILU/LU 不足以解决该问题。
8. 当前代码可以合并为“筛选基础设施 + 负结果记录”，但不应合并为“已有可用迭代求解器”。

## Key Results

- `iter_gmres_jacobi` 在 p=2 h=2 的 RSS upper 约 `8.88 GB`，显著低于 task008 direct p=2 h=2 的 `20.5 GB`，但未收敛。
- `iter_gmres_jacobi` 在 p=2 h=1.5 的 RSS upper 约 `13.99 GB`，1000 步 solve 约 `360.9 s`，true relative residual 约 `3.56e-3`。
- `iter_gmres_jacobi` 加长到 5000 步在 h=5/h=4 仍停滞在约 `1e-2`，说明它不是简单增加迭代次数即可解决。
- `hypre boomeramg` 在 complex PETSc 路径下触发 glibc/PETSc 崩溃，本轮不建议继续使用。

## Known Issues

- 当前 iterative runs 未收敛时不会保存正式场输出，也不会产生 official R/T/A，这是故意的，避免把未收敛解误作物理解。
- `RSS_upper_GB` 是 rank max RSS 乘以 ranks 的保守上界，不等于严格实测总 RSS。
- FieldSplit Schur 只是 PETSc 现成 block split 探针，不是完整物理预条件器。

## Next Questions for Review

1. 是否接受“当前 PETSc 黑盒 profiles 无 production 候选”的结论？
2. 下一轮是否转向 H(curl) AMS / shifted Maxwell / DDM，而不是继续微调 ASM/ILU？
3. 是否要在工作站上仅用 `iter_gmres_jacobi` 做 h=1/h=0.75 的 residual-only 资源探针？
