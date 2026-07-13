# Physical-slab two-level PC：真实对象、apply 顺序与 MPI ownership

## 1. 文件与职责

`src/solvers/physical_slab_two_level.py` 实现 sparse coarse correction 和 owner-computes physical-slab smoother。它接收 condensed FE operator，不知道 DtN auxiliary unknowns。

## 2. 关键类/函数

| 符号 | 责任 |
|---|---|
| `SparseCoarseVector` | 稀疏保存一个分布式 coarse vector |
| `compress_petsc_vector` | 阈值压缩并全局归一化 |
| `SparseGalerkinTwoLevelPc` | smoother-first 两级 PC |
| `gather_global_subdomain_indices` | 合并 rank-local slab DoF |
| `balanced_subdomain_owners` | 把完整 subdomain 分配给 owners |
| `DistributedPhysicalSlabSmoother` | owner 解 local shifted-F factors |

## 3. `SparseCoarseVector` 的真实字段

源码 dataclass 字段是：

```text
indices: np.ndarray
values: np.ndarray
slab: int
eigenvalue: float
eigenpair_residual: float
```

没有 `global_size` 字段。`indices` 是当前 rank 持有的全局 DoF index；向量全局尺寸由 operator/PETSc ownership 决定。`storage_bytes` 只统计本 rank indices+values，diagnostics 再通过 MPI 汇总。

## 4. Coarse 对象尺寸

固定 target 使用 24 个 z intervals，节点数 25，每节点 3 个方向 hat vectors，共 75 个 coarse vectors。对 h5：

```text
Z shape = 44,698 x 75
E = Z^H A Z shape = 75 x 75
coarse rank = 75
coarse condition = 900.955
```

`SparseGalerkinTwoLevelPc` 把本 rank 的 Z 片段建成 CSC，并用真实 matrix-free `A*z_j` 形成 coarse matrix。

## 5. 真实 apply 顺序

源码不是 coarse-first。`SparseGalerkinTwoLevelPc::apply` 执行：

```text
approximation = 0
smoother.solve(source, approximation)
residual = source - A*approximation
rhs_c = Z^H residual
coefficients = E^{-1} rhs_c
approximation += Z*coefficients
if post_smooth:
    residual = source - A*approximation
    approximation += weight*smoother(residual)
```

公式为：

```math
y_0=M_s^{-1}x,\quad r=x-Ay_0,\quad
y=y_0+Z(Z^HAZ)^{-1}Z^Hr.
```

## 6. Physical slabs 如何形成

`benchmarks.run_workstation_iterative::_complete_physical_slabs` 用 cell midpoint 的 z 范围选 local cells，再把 cell DoF 转成 global indices。`gather_global_subdomain_indices` 通过 allgather 得到每个 complete slab 的全局 DoF 集。

## 7. Owner distribution

`balanced_subdomain_owners` 按子域行数 largest-first 分配。canonical h5 的 16 slabs owners 为：

```text
[0,0,1,1,2,2,3,3,0,0,1,1,2,2,3,3]
```

即每个 MPI rank 拥有 4 个完整 factors；非 owner 不复制该 factor。

## 8. Local factor 与 sm2

每个 owner 对 shifted-F submatrix 建 ILU1。`DistributedPhysicalSlabSmoother` 的单次 Schwarz apply 用 scatter 收 RHS、owner solve、reverse ADD 回全局。`smoother_iterations=2` 时，外层使用固定两步 inner GMRES；inner KSP 的 operator 是真实 action，PC 是一次 slab apply。

## 9. h5 资源对象

| 量 | h5 record |
|---|---:|
| physical slabs | 16 |
| global factor rows（含重叠累计） | 71,344 |
| global factor nnz | 7,046,752 |
| rows per owner | 17,836 |
| smoother iterations | 2 |
| outer PC apply count | 1,201 附近，具体见 record |

这些是 factor 规模，不等于 `n_fe`。

## 10. PETSc/MPI ownership

外层 source/target 按 condensed operator ownership 分布。每个 `_OwnedSubdomainFactor` 拥有 index set、scatter、local Mat/KSP/Vec；`DistributedPhysicalSlabSmoother.destroy()` 必须释放全部。两级 PC 拥有 coarse work Vec/CSC/dense coarse factor，但不拥有传入 operator。

## 11. 一次真实调用顺序

```text
build 16 complete slab index sets
-> balanced owners
-> extract shifted-F local matrices
-> local GMRES+ILU1 setup
-> build 75 sparse coarse vectors
-> form/factor E=Z^HAZ
-> attach SparseGalerkinTwoLevelPc as Python PC
-> outer right FGMRES repeatedly calls apply
```

## 12. Diagnostics

`diagnostics` 写出 owner map、global factor rows/nnz、max/min owner rows、local/inner KSP 信息、apply counts/times、coarse rank/condition/action error 和 basis storage。

## 13. 测试与 benchmark

- `src.test.test_23_physical_slab_two_level`：owner、empty owner、repeat、sm2 true action、MPI、destroy。
- Case031：[`../../../benchmarks/cases/031_workstation_iterative/README.md`](../../../benchmarks/cases/031_workstation_iterative/README.md)。
- h5/h3/h2 canonical records 保存真实 owner/资源数据。

## 14. 身份与限制

代码是 stable PC infrastructure；“qualified”只属于 4 ranks、16 slabs、overlap 0.25、shift 0.1、ILU1、sm2、75D coarse 的冻结 target。类能接受其他参数不等于它们已通过工程验证。

## 15. Task030 storage path

Task030 为 `DistributedPhysicalSlabSmoother` 增加两个显式 opt-in：

- `diagonal_shift`：从原 F 逐 subdomain 提取矩阵后只修改 local diagonal，不保留一份完整 shifted-F；
- `factor_only_storage`：要求 `local_ksp_iterations=1`，local PC setup 后对 factor Mat `incRef()`，销毁 KSP 和 source submatrix，apply 直接调用 factor solve。

factor-only 模式逐块提取/分解，避免所有 local source matrices 同时驻留。`_OwnedSubdomainFactor` 的 Mat/KSP 因而可为 `None`，destroy 必须按实际所有权释放 factor/rhs/solution。serial 与 MPI2 测试比较普通与 compact action，误差约 `2e-12`；h5/h3 物理 full solve 证明 true residual 不漂移。

`SparseGalerkinTwoLevelPc(post_smooth=True)` 在 coarse correction 后重算真实 residual，再执行同一 fixed smoother。它是 Task030 的主要收敛机制；只启用 storage flags 而不启用 post smooth 不是同一个候选。

理论见 [`../../theory/iterative_solver_and_preconditioner.md`](../../theory/iterative_solver_and_preconditioner.md)。
