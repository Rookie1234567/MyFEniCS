# Solver Profile Ranking

## default100 p=1 h=5

| rank | profile / diagnostic | residual | improvement | decision |
|---:|---|---:|---:|---|
| 1 | one-shot `diag_lift_minres` | `2.146459669e-2` | `1.000045x` | 仅数值微小变化，不算正信号 |
| 2 | one-shot `pfe_lift_minres` | `2.146474918e-2` | `1.000038x` | 无效 |
| 3 | one-shot `pfe_lift_balanced_minres` | `2.146517759e-2` | `1.000018x` | 平衡 FE/aux 后仍无效 |
| 4 | KSP `xy_minres_additive`, `omega=0.01` | `2.146563635e-2` | `0.999996x` | 略差 |
| 5 | KSP `top_bottom_y_additive`, `omega=0.01` | `2.146564882e-2` | `0.999996x` | 略差 |
| 6 | KSP `top_y_minres_additive`, `omega=0.1` | `2.146608100e-2` | `0.999976x` | 略差 |
| 7 | un-damped lifted KSP, `omega=1.0` | PETSc FPE | - | 数值不稳定 |

## tiny10

| profile | residual | improvement | interpretation |
|---|---:|---:|---|
| baseline FE-AMS + aux identity | `9.601e-7` | 1.00x | 已收敛 |
| top_y additive | `5.028e-7` | `1.91x` | 弱正信号 |
| top_bottom_y additive | `2.916e-7` | `3.29x` | tiny10 最好 |
| xy additive | `5.562e-7` | `1.73x` | 弱正信号 |

tiny10 的正信号不能外推到 default100。default100 是本任务的 gate case，未通过。

## Go / No-Go

| route | status | reason |
|---|---|---|
| aux-only modal correction | stop | task015 和 task016 均无效 |
| `Z^T A Z` lifted right coarse correction | stop | one-shot 与 KSP 均无正信号 |
| minres lifted right coarse correction | stop for current form | 只能得到 `1.000045x` |
| p=2 h=5 | closed | default100 p=1 h=5 未过 B gate |
| Petrov/adjoint coarse or true FE Schur sample | next candidate | 需要 left/test space 或更准确 `A_FE^{-1}C` |
