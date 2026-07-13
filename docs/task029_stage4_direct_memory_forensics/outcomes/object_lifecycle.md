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
