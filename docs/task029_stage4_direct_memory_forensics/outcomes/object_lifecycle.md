# Task029 direct object lifecycle

## baseline 路径

```text
assemble constrained A_base / b_base
  -> allocate A_aug / b_aug
  -> copy A_base and insert auxiliary DtN coupling
  -> KSPSetUp (analysis + numeric factorization)
  -> KSPSolve
  -> true residual
  -> FE field reconstruction
  -> official modal R/T
  -> field output / diffraction / volume absorption
  -> function return and Python/PETSc reference cleanup
```

Task28 路径在 postprocess 期间仍由 `dtn_result` 或 `problem` 引用 KSP/factor、system Mat、RHS Vec 和 solution Vec。Task29 baseline 只记录 `solver_objects_retained_for_postprocess`，没有提前 destroy，所以 h5/h3 与原生命周期可比。

## 同时存在对象与量级

- `A_base` 与 `A_aug` 在复制和 DtN coupling/finalize 阶段同时存在。
- KSP factorization 后，`A_aug`、factor、`b_aug`、`x_aug` 与重建后的 FE field 同时存在。
- ordinary default 不装配 unconstrained diagnostic matrix；两个 baseline 的 `unconstrained_matrix_stats` 均为空。
- h5/h3 的 base、augmented matrix 都显示 `nz_unneeded=0`、`mallocs=0`，说明当前预分配没有明显的 PETSc 动态重分配证据。
- factor 的 PETSc raw memory/fill 字段为 0；只报告 nnz 和统一 storage estimator，不推断 MUMPS INFOG/RINFOG 的含义。

## h5/h3 定量归因

| 阶段/增量 | h5 worker / cgroup MB | h3 worker / cgroup MB | 结论 |
|---|---:|---:|---|
| base + augmented 共存，相对 variational stage | 226.09 / 148.21 | 729.07 / 754.62 | 次要但可审计 |
| KSPSetUp 峰值，相对 pre-setup | 945.55 / 935.27 | 6472.43 / 6474.57 | 主瓶颈 |
| KSPSolve retained 增量 | 1.32 / 0.25 | 6.98 / 6.28 | 很小 |
| official RTA 增量 | 0.00 / 0.00 | 0.78 / -0.02 | 可忽略 |
| field output 增量 | 35.45 / 10.93 | 129.06 / 112.51 | 不形成全局主峰 |

h3 KSPSetUp 外部主峰为 8651.10 MB，而 postprocess/field-output 区间最高约 8345.76 MB。即使 factor 与输出生命周期完全分离，也只能降低后段平台，不能降低本次运行已经出现的 KSPSetUp 全局峰值；因此 H7 可作为清理质量候选，但不能预期获得 20% 峰值收益。

## Stage C 判据

- H1：base/augmented 双份存在已确认，但其上界约为 h3 主峰的 9%，预计无法单独达到 20%。
- H2：现有精确预分配已有 `mallocs=0`、`nz_unneeded=0`，没有支持继续调优的实测信号。
- H3：ordinary default 不存在额外 unconstrained diagnostic copy；应检查临时 Python/PETSc 引用和异常清理，不应虚构默认矩阵副本。
- H5/H6：因子化主导，rank-count、ordering、OOC、BLR 是后续最有价值的筛选方向。
- H7：factor 在 postprocess 保留属实，但只影响尾部平台，不是全局主峰。
