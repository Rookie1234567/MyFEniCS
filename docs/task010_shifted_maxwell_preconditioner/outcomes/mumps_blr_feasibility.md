# MUMPS-BLR Feasibility

## 结论

MUMPS-BLR 是本轮唯一达到 production 基本要求的路线。`iter_fgmres_mumps_blr_eps1e-5` 在 p=2/h=2 下收敛，并复现 direct LU 的 R/T/A。`eps=1e-4` 也收敛，但迭代数更多；`eps=1e-3` 在 h=2 超时，不建议作为主 profile。

## 论文对应关系

用户提供的论文把 MUMPS-BLR 作为 FGMRES 预条件器，与本轮实现一致。本轮 PETSc 选项为：

```text
ksp_type = fgmres
ksp_pc_side = right
ksp_norm_type = unpreconditioned
pc_type = lu
pc_factor_mat_solver_type = mumps
mat_mumps_icntl_35 = 1
mat_mumps_cntl_7 = epsilon
```

## h=2 关键对照

| profile | iterations | true relative residual | R | T | A | RSS upper GB | wall s |
|---|---:|---:|---:|---:|---:|---:|---:|
| eps=1e-5 | 4 | 2.085e-08 | 0.0013429328 | 0.59921323 | 0.39944384 | 17.85 | 1358 |
| eps=1e-4 | 7 | 1.883e-07 | 0.0013429337 | 0.59921323 | 0.39944384 | 18.09 | 1234 |
| eps=1e-3 | timeout | - | - | - | - | 16.27 | 1801 |
| direct LU | - | - | 0.0013429328462348958 | 0.5992132294442478 | 0.3994438377095067 | 20.532958984375 | 1665.7796797530027 |

## compression ratio 状态

当前 CSV 中 `mumps_blr_compression_ratio` 为空。原因不是未启用 BLR，而是当前 PETSc/petsc4py summary 没有稳定暴露 MUMPS BLR 压缩率字段。本轮已经通过 live PETSc 选项接受测试和数值结果确认 BLR 选项可用；后续若要把压缩率作为正式指标，需要新增 MUMPS verbose/INFOG 采集。

## 风险

h=1.5 在 KSP setup 阶段 signal 9。失败前已经完成 mesh、Floquet MPC、DtN mode preparation 和 base matrix assembly，base nnz 约 1.421e8；真正的峰值很可能发生在 MUMPS factor/preconditioner setup 内部，当前 RSS 采样没有抓到瞬时峰值。
