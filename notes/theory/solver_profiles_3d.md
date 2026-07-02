# 3D Maxwell 求解器 profile 原理和使用说明

## 2026-07-02 更新：MUMPS OOC 文件管理策略

`mumps_ooc` 会把 LU 因子临时写到磁盘。现在代码采用自动管理：

```text
成功完成并写正式结果：
  删除 mumps_ooc_files/ 内的 OOC 文件。

求解失败、能量诊断失败、assemble-only 或其它非 completed 状态：
  保留 mumps_ooc_files/，并在 summary 里记录路径、文件数和字节数。
```

这和 COMSOL 的思路更接近：正常计算不让临时因子文件长期占盘；异常退出时保留现场，方便判断是 LU fill-in、磁盘、内存还是 PETSc 错误。

## 2026-07-02 更新：代码已删去无效/低价值 direct solver profile

当前正式代码只保留两个公开 profile：

| profile | 当前用途 | 建议 |
| --- | --- | --- |
| `default` | 普通 direct LU；MPI 下要求 PETSc 有 MUMPS | 日常默认 |
| `mumps_ooc` | MUMPS out-of-core，因子文件写到当前 case 的 `mumps_ooc_files/` | 内存接近上限时测试 |

已经从公开代码入口删除的 profile：

| 已删除 profile | 前期测试结论 | 后续意义 |
| --- | --- | --- |
| `mumps` | 和 `default` 在当前 MPI Docker 环境下本质等价，显式保留只会增加混乱 | 不再作为用户选项 |
| `mumps_ooc_seq_analysis` | h=2.5 能跑，但比 `mumps_ooc` 更慢，内存也没有明显优势 | 只作为历史诊断记录 |
| `mumps_ooc_parallel_analysis` | 当前检测到 PT-SCOTCH 后可进入，但 h=2.5 已接近 Docker 内存上限 | 后续只在大内存服务器上重新评估 |
| `mumps_ooc_requested_legacy` | 只用于复现旧的 MUMPS `INFOG(1)=-38` 错误 | 不再进入主代码 |
| `mkl_pardiso` | 当前 PETSc 镜像不支持 | 若要接近 COMSOL，应该重新构建 PETSc/MKL 后另测 |
| `superlu_dist` | 当前 PETSc 支持，但 h=2.5 未在可接受时间内完成 | 暂不保留在主入口 |
| `strumpack` | 当前 PETSc 镜像不支持 | 需要新 PETSc build 才有意义 |

因此现在的理解可以更简单：

```text
想正常跑：      --petsc-direct-solver-profile default
想试 OOC：      --petsc-direct-solver-profile mumps_ooc
想研究 COMSOL： 不在当前代码里切 profile，而是换 PETSc build / 服务器环境
```

这次清理不改变物理方程、不改变矩阵装配，也不改变 `mumps_ooc` 已经验证过的 OOC 文件目录行为。它只删除低价值运行入口，避免后续调试时把“PETSc 后端实验”和“Maxwell 模型错误”混在一起。

## 2026-07-01 历史测试记录：direct LU profiles 的含义和选择建议

当前 3D 主线仍然只使用直接法，不引入 Krylov 迭代。代码里的 `petsc_direct_solver_profile` 不是“不同物理模型”，而是同一个稀疏线性系统的不同 LU 分解后端：

```text
KSP = preonly
PC  = lu
```

也就是说，PETSc 不做迭代，而是把矩阵交给某个 sparse direct solver 做符号分析、重排序、数值因子分解和回代。

| profile | 实际含义 | 当前状态 | 适用场景 |
| --- | --- | --- | --- |
| `default` | 串行时 PETSc 默认 LU；MPI 时自动选可用并行 LU，当前通常是 MUMPS | 推荐默认 | 不想指定后端时使用 |
| `mumps` | 显式使用 MUMPS sparse LU | 可用 | MPI 直接法基线 |
| `mumps_ooc` | MUMPS + out-of-core factor storage，`ICNTL(22)=1` | 可用，当前推荐大模型优先测试 | 内存接近上限时，把部分因子写到磁盘 |
| `mumps_ooc_seq_analysis` | MUMPS OOC + sequential analysis | 可用但不一定更快 | 并行 analysis 不稳定时的保守诊断 |
| `mumps_ooc_parallel_analysis` | MUMPS OOC + parallel analysis，依赖 PT-SCOTCH/ParMETIS | 当前可进入，但 h=2.5 内存压力高 | 只有在更大内存服务器上再测 |
| `mumps_ooc_requested_legacy` | 旧的 `ICNTL(28)=2, ICNTL(29)=2` 组合 | 只用于复现 `INFOG(1)=-38` | 不推荐正式使用 |
| `mkl_pardiso` | Intel MKL PARDISO sparse direct solver | 当前镜像不支持 | 若重新构建 PETSc/MKL，可能接近 COMSOL 体验 |
| `superlu_dist` | SuperLU_DIST 并行稀疏 LU | 当前 PETSc 支持，但 h=2.5 未完成 | 备选并行 direct 后端 |
| `strumpack` | STRUMPACK sparse direct/压缩直接法 | 当前镜像不支持 | 需要重新构建 PETSc |

直接法的总内存不由原始稀疏矩阵决定，而主要由 LU factor fill-in 决定。对当前 Stage 4 block grating / zero-order DtN 诊断，h=1.5 已经能完成矩阵组装：

```text
DOF = 1,452,174
nnz = 48,064,000
nnz/row = 33.10
估算 AIJ 矩阵内存约 1.1 GB
```

但 LU factorization 会把稀疏矩阵展开成更大的 L/U 因子。这个 fill-in 可能比原始矩阵大几十倍甚至更多，所以“矩阵本身能组装”不等于“直接法能解完”。

### 为什么 MUMPS OOC 不等于 COMSOL

`mumps_ooc` 的作用是把部分 LU 因子写到磁盘，降低内存峰值。它不能消除：

```text
1. 符号分析和重排序阶段的内存；
2. MPI 并行 LU 中部分元数据/树结构的复制；
3. H(curl) 3D Maxwell 复数矩阵带来的高 fill-in；
4. Docker/WSL 的内存上限。
```

COMSOL 常见配置可能使用高度优化的 PARDISO/MUMPS、共享内存线程、自动 out-of-core、METIS/SCOTCH 重排序、以及更大的主机内存/磁盘缓存。当前 Docker 容器只有约 13.65 GiB 内存上限，所以即使 OOC 能工作，也可能在 h=2 或 h=1.5 的直接 LU 阶段非常慢或接近内存上限。

如果目标是“像 COMSOL 一样跑 200 万自由度直接法”，优先级应是：

```text
1. 在 Linux 服务器或 WSL/Docker 中给容器更高内存，而不是只加 swap。
2. 使用快速 NVMe 盘作为 MUMPS OOC 目录。
3. 构建带 MKL PARDISO 的 PETSc，并测试 mkl_pardiso 单机多线程。
4. 构建 MUMPS + METIS/SCOTCH/PT-SCOTCH/ParMETIS，比较 ordering。
5. 保留 assemble-only 表，确认矩阵 nnz/row 没有异常变稠。
```

本轮 h=2.5 对比报告见：

```text
notes/test/3d_direct_solver_profile_h2p5_report.md
```

## 2026-06-24 更新：当前代码已改为 direct-only

为了降低阅读和调试复杂度，当前 3D 代码路径只保留直接法：

```text
solver_profile = direct
ksp_type = preonly
pc_type = lu
```

CLI 仍兼容 `--solver-profile direct`，`default` 和 `direct_lu` 也只是 direct 别名。下面关于 ASM/ILU/Jacobi/HYPRE 的内容是历史记录，不再对应当前正式代码入口；后续如果重新做求解器优化，应新开一个独立分支或文档，不要混入 Stage 4 物理验证路径。

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
matrix_memory_estimate_bytes
```

这些字段用于判断自由度规模、矩阵稀疏程度、矩阵内存和求解器内存压力。
其中 `matrix_memory_bytes` 来自 PETSc 自身统计；如果当前 PETSc build 返回 0，可以参考 `matrix_memory_estimate_bytes`，它按 AIJ/CSR 结构粗略估算复数矩阵值、列索引和行指针的存储量。

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
