# 3D Maxwell 求解器 profile 原理和使用说明

## 2026-06-18 更新：当前可靠性结论

对当前 3D complex full-vector Maxwell H(curl) 空气盒 benchmark，直接法仍然是唯一可靠默认求解器：

```text
SOLVER_PROFILE_3D = "direct"
```

`default` 和 `direct_lu` 仍然保留为兼容别名，但新文档里统一推荐写 `direct`。它内部使用：

```text
ksp_type = preonly
pc_type = lu
```

也就是说，PETSc 不做 Krylov 迭代，而是用直接 LU 分解求解线性系统。它最吃内存，但最适合作为 correctness benchmark，用来判断网格、边界条件、后处理和解析平面波误差是否合理。

## 当前可选 profile

| profile | 状态 | 作用 |
|---|---|---|
| `direct` | 可靠默认 | 当前 3D 空气盒的基准求解器 |
| `default` | 兼容别名 | 等价于 `direct` |
| `direct_lu` | 兼容别名 | 等价于 `direct` |
| `iterative_asm_lu` | 实验 | `fgmres + asm + local lu`，比 ILU 更强，优先用于迭代测试 |
| `iterative_asm_lu_overlap2` | 实验 | overlap=2 的 ASM+local LU，预条件更强但更吃内存 |
| `iterative_asm_ilu` | 诊断 | 可运行，但已观察到 degree-2 case 不可靠收敛 |
| `iterative_bjacobi_ilu` | 诊断 | 可运行，但预条件偏弱，不作为可靠求解器 |
| `iterative_jacobi` | 诊断 | 只用于低内存基线，通常太弱 |
| `iterative_hypre` | 禁用 | BoomerAMG 在当前 complex H(curl) Maxwell 系统中可能触发底层崩溃 |

## 为什么普通迭代法会困难

当前离散方程是频域 Maxwell 的 curl-curl 系统：

```text
curl(mu^-1 curl E) - k0^2 eps E = 0
```

有限元空间是 3D Nedelec H(curl) 空间。这个系统和普通 Poisson 标量椭圆问题不一样：

1. 矩阵是复数矩阵；
2. curl-curl 算子有特殊的零空间和梯度场结构；
3. Helmholtz 型的 `-k0^2 eps E` 项会让系统更接近不定问题；
4. 简单 Jacobi、block-Jacobi、ILU 或普通 AMG 不一定能处理 H(curl) 结构。

所以不能把标量 Poisson 问题里常用的 BoomerAMG 直接当成 Maxwell H(curl) 的默认预条件器。后续真正适合这类问题的方向是 auxiliary-space Maxwell preconditioner，例如 hypre AMS 或 Hiptmair-Xu 类预条件器。

## 新增的 ASM+local LU

`iterative_asm_lu` 的 PETSc 设置是：

```text
ksp_type = fgmres
pc_type = asm
pc_asm_overlap = 1
sub_ksp_type = preonly
sub_pc_type = lu
```

它不是全局 LU。它把全局问题分成多个局部子问题，每个子问题内部用 LU 近似求解，再由 FGMRES 在全局层面迭代修正。和 `asm + ilu` 相比，它的局部预条件更强，但内存也会更高。

`iterative_asm_lu_overlap2` 把 overlap 从 1 增加到 2。重叠越大，局部子问题包含的邻域越多，预条件通常更强，但每个 rank 的局部矩阵更大。

## 不收敛时程序怎么处理

现在代码严格使用 PETSc KSP reason 判断结果状态：

```text
reason > 0  收敛，本次是有效解
reason < 0  不收敛，本次是 failed diagnostic
```

如果 `reason < 0`：

1. `run_summary.json` 中 `case_status = "failed_not_converged"`；
2. `official_result = False`；
3. `diagnostic_only = True`；
4. 跳过正式后处理；
5. 不输出正式 ParaView 场文件；
6. 不报告正式误差和 Poynting 结果。

这样做是为了避免把未收敛 Krylov 迭代的中间向量误认为物理解。

## 输出里应该看哪些字段

每次运行都建议先看 `solver_log.txt` 或 `run_summary.json`：

```text
case_status
official_result
diagnostic_only
solver_profile
solver_profile_resolved
solver_reliability
solver_petsc_options
actual_ksp_type
actual_pc_type
ksp_converged
ksp_converged_reason_name
ksp_iterations
solver_residual_norm
matrix_stats
max_rss_mb
timings_seconds
```

其中 `matrix_stats` 包含：

```text
matrix_rows
matrix_cols
matrix_nnz_used
matrix_average_nnz_per_row
matrix_memory_bytes
```

这些字段用于判断自由度规模、矩阵稀疏程度、矩阵内存和求解器内存压力。

## 推荐测试顺序

不要从最大模型开始测试迭代法。建议按这个顺序：

```text
1. p=1, 粗网格，验证 profile 能收敛
2. p=2, 粗网格，对比 direct 误差
3. p=2, 中等网格，观察迭代数和内存
4. p=2, h=30/40 nm 压力测试
```

示例：

```text
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case normal --nedelec-degree 1 --visualization-degree 1 --mesh-target-size 300 --solver-profile iterative_asm_lu
```

MPI 示例：

```text
mpiexec -n 4 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case normal --nedelec-degree 2 --visualization-degree 2 --mesh-target-size 80 --solver-profile iterative_asm_lu
```

如果迭代法收敛，也仍然要和 `direct` 对比误差。当前阶段不要把实验性迭代法当成最终物理结论来源。
