# Profile Ranking

## 总体判断

当前 required PETSc iterative profiles 无一达到 `rtol=1e-6`，因此没有可作为正式 Stage 4 solver 的 profile。

| rank | profile | grade | decision | reason |
|---:|---|---|---|---|
| 1 | iter_gmres_jacobi | B- / diagnostic only | 保留为工作站 residual-only 探针 | 唯一在 h=5、4、3、2.5、2、1.5 均稳定下降；h=1.5 可跑完 1000 步；但不能产生 R/T/A。 |
| 2 | iter_gmres_none | C | baseline only | 无预条件也下降，但比 Jacobi 弱，工程上没有优势。 |
| 3 | iter_fgmres_gamg | C- | 不推荐 | 可运行但 residual 降幅不够，内存还高于 Jacobi。 |
| 4 | iter_fgmres_fieldsplit_schur_asm1_lu | C- | 不推荐 | 修正 IS 后可运行，但 residual 基本停滞。 |
| 5 | ASM/ILU/LU/BJacobi/BiCGStab required profiles | C | 淘汰 | 停滞、发散、breakdown，或局部 LU/overlap 增强后仍无明显改善。 |
| 6 | experimental_hypre_boomeramg | fail | 淘汰 | complex PETSc 路径下崩溃。 |

## 推荐下一步

不要继续把时间主要花在 Jacobi/BJacobi/ASM/ILU/LU 的小调参上。下一轮应转向 physics-based preconditioner：shifted Maxwell、H(curl) AMS、two-level DDM，或 matrix-free Krylov + Maxwell block preconditioner。
