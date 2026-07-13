# Task029 direct object lifecycle

## Stage A baseline path

```text
assemble constrained A_base / b_base
  -> allocate A_aug / b_aug
  -> copy base and insert auxiliary DtN coupling
  -> KSPSetUp (analysis + numeric factorization)
  -> KSPSolve
  -> true residual
  -> FE field reconstruction
  -> official modal R/T
  -> field output / diffraction / volume absorption
  -> function return and Python/PETSc reference cleanup
```

Task28 路径在 postprocess 期间仍由 `dtn_result` 或 `problem` 引用 KSP/factor、system Mat、RHS Vec 和 solution Vec。Stage A 只记录 `solver_objects_retained_for_postprocess`，不提前 destroy；这样 h5/h3 baseline 保留原始生命周期。

## 已确认的同时存在对象

- `A_base` 与 `A_aug` 在复制和 DtN coupling/finalize 阶段同时存在；
- KSP factorization 后，`A_aug`、factor、`b_aug`、`x_aug` 和重建后的 FE field 同时存在；
- ordinary default 不默认装配 unconstrained diagnostic matrix，但若显式开启则会额外存在；
- factor matrix 字段只读取当前 petsc4py/MUMPS API 实际暴露的数据，缺失项保留 unavailable，不推断 INFOG 含义。

提前释放 KSP/factor 或 base objects 属于后续 Commit C 候选，必须在 Stage B 基线报告完成后单独实现和验证。

## h5 实测归因

冻结运行：`h5_default_mpi4_20260713T050814Z`。

| 外部采样阶段 | worker rank 同时 RSS 和 MB | cgroup current MB | 解释 |
|---|---:|---:|---|
| `variational_form_setup` | 1255.148 | 763.672 | form 与 constrained base assembly 区间 |
| `after_augmented_matrix_allocation` | 1391.535 | 806.027 | 新增 augmented shell/storage |
| `after_base_matrix_copy` | 1481.234 | 911.879 | base 与 augmented copy 同时存在 |
| `before_ksp_setup` | 1382.598 | 793.762 | factorization 前稳定点 |
| `during_ksp_setup_peak` | 2328.145 | 1729.035 | analysis/numeric factorization 主峰 |
| `solver_objects_retained_for_postprocess` | 2309.957 | 1718.262 | KSP/factor 与场后处理继续同时存在 |
| `after_field_output` | 2312.051 | 1724.129 | worker/cgroup 次峰；MPI tree 在此达到 2385.141 MB |

`KSPSetUp` 相对其前一稳定点增加约 945.55 MB worker RSS、935.27 MB cgroup current。KSPSolve 只运行约 0.0467 s，短于 0.25 s sampler 的可靠分辨率；因此不虚构独立 solve 内部峰值，使用 `after_ksp_solve` checkpoint 与总计时证明它没有取代 factorization 主峰。

当前 lifecycle 在 official RTA、field output 和 volume absorption 完成前仍保留 KSP/factor、system Mat、RHS Vec 和 solution Vec。h5 证据支持把“factor 与 postprocess 生命周期分离”列为后续候选，但 Stage B h3 完成前不实施。
