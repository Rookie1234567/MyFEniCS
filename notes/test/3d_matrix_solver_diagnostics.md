# 3D Maxwell 矩阵与求解器诊断记录

## 2026-07-01 更新：MUMPS OOC 修复、progress 日志和 h=1.5 组装诊断

本轮完成了直接 LU 诊断路径修复：`mumps_ooc` 不再默认设置会触发 `INFOG(1)=-38` 的并行 analysis 组合，而是使用：

```text
pc_factor_mat_solver_type = mumps
mat_mumps_icntl_22 = 1
mat_mumps_icntl_14 = 80
```

如果需要复现旧错误，使用：

```text
--petsc-direct-solver-profile mumps_ooc_requested_legacy
```

每个 3D case 现在会写：

```text
progress_3d.jsonl
```

它会在 mesh、function space、Floquet、form、DtN matrix assembly、direct solve 开始/结束时落盘。若程序被系统杀掉，优先看这个文件最后一行。

小模型 profile 验证：

```text
results/matrix_scale_20260701_094444/matrix_scale.csv
```

| h nm | np | profile | status | factor solver | MUMPS INFOG(1) | OOC 残留 | R+T |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| 20 | 1 | default | completed | petsc |  |  | 0.999999773 |
| 20 | 1 | mumps | completed | mumps |  |  | 0.999999773 |
| 20 | 1 | mumps_ooc | completed | mumps |  | 2 files / 8.28 MB | 0.999999773 |
| 20 | 1 | mumps_ooc_seq_analysis | completed | mumps |  | 2 files / 8.28 MB | 0.999999773 |
| 20 | 1 | mumps_ooc_requested_legacy | failed_direct_lu_exception | mumps | -38 | 0 |  |
| 20 | 1 | mkl_pardiso | failed_parallel_direct_lu_unavailable |  |  |  |  |
| 20 | 2 | default | completed | mumps |  |  | 0.999999773 |
| 20 | 2 | mumps | completed | mumps |  |  | 0.999999773 |
| 20 | 2 | mumps_ooc | completed | mumps |  | 4 files / 10.00 MB | 0.999999773 |
| 20 | 2 | mumps_ooc_seq_analysis | completed | mumps |  | 4 files / 10.00 MB | 0.999999773 |
| 20 | 2 | mumps_ooc_requested_legacy | failed_direct_lu_exception | mumps | -38 | 0 |  |
| 20 | 2 | mkl_pardiso | failed_parallel_direct_lu_unavailable |  |  |  |  |

大模型 assemble-only 诊断：

```text
results/matrix_scale_20260701_094705/matrix_scale.csv
```

| h nm | np | DOF | Floquet 约束 | nnz used | nnz/row | 估算 AIJ MB | peak RSS MB | status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 | 8 | 15936 | 1311 | 530606 | 33.30 | 12.27 | 284.66 | diagnostic_assemble_only |
| 5 | 8 | 39270 | 2470 | 1307032 | 33.28 | 30.22 | 280.02 | diagnostic_assemble_only |
| 3 | 8 | 197136 | 7261 | 6538846 | 33.17 | 151.17 | 337.55 | diagnostic_assemble_only |
| 2 | 8 | 605904 | 15477 | 20069534 | 33.12 | 463.98 | 460.34 | diagnostic_assemble_only |
| 1.5 | 8 | 1452174 | 27982 | 48064000 | 33.10 | 1111.18 | 662.08 | diagnostic_assemble_only |

判断：

```text
1. h=1.5 已能完成矩阵组装，且 nnz/row 仍约 33.1，没有矩阵变稠迹象。
2. 因此当前内存/时间爆点不是 Floquet/MPC 或 DtN matrix assembly，而是直接 LU factorization fill-in。
3. h=2, np=8, mumps_ooc 运行约 30 分钟仍停在 stage4_dtn_zero_order_solve，内存约 12.8 GiB / 13.65 GiB，OOC 文件约 3.18 GB，已人工停止。
4. 这说明 MUMPS OOC 能绕开旧的 -38 参数错误，但在当前 Docker 内存限制下，h=2 级别直接 LU 仍非常吃内存和时间。
```

对应 h=2 中断 case：

```text
results/3D_stage4_block_grating_normal_p1_h2p0_np8_20260701_094942/progress_3d.jsonl
results/3D_stage4_block_grating_normal_p1_h2p0_np8_20260701_094942/mumps_ooc_files
```

## 2026-07-01 续跑：完整默认尺度表已生成

本轮补跑了上次因额度限制未完成的默认直接法尺度扫描：

```bash
python3 -m src.studies.run_3d_matrix_scale \
  --mesh-sizes 20 15 12 10 8 \
  --mpi-procs 1 \
  --stage-case stage4_block_grating \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --petsc-direct-solver-profile default
```

输出 CSV：

```text
results/matrix_scale_20260701_085320/matrix_scale.csv
```

核心结果：

| h nm | DOF | Floquet 约束 | nnz used | nnz/row | 估算 AIJ 矩阵 MB | solve/assembly 诊断秒 | peak RSS MB | R+T |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 1696 | 275 | 56398 | 33.25 | 1.30 | 6.44 | 294.61 | 0.99999977 |
| 15 | 2844 | 412 | 95230 | 33.48 | 2.20 | 0.45 | 293.04 | 0.99999996 |
| 12 | 6384 | 697 | 212734 | 33.32 | 4.92 | 2.73 | 375.57 | 0.99999084 |
| 10 | 6384 | 697 | 212734 | 33.32 | 4.92 | 6.20 | 375.56 | 0.99999084 |
| 8 | 15936 | 1311 | 530606 | 33.30 | 12.27 | 18.84 | 678.78 | 0.85333423 |

初步判断：

```text
1. nnz/row 基本稳定在 33 左右，没有随网格细化爆炸。
2. 因此当前这组 p1 + zero_order 的内存增长主要来自 DOF/nnz 规模增长，而不是 Floquet/MPC 让矩阵明显变稠。
3. h12 与 h10 得到同样 DOF/nnz，说明 boundary-fitted hexa 网格解析后落到了同一组轴向 cell 数。
4. h8 的 R+T 明显低于 1，这属于物理/边界/离散误差诊断信号；本表主要用于矩阵规模，不作为物理收敛结论。
```

MUMPS out-of-core h20 单点补跑：

```text
np=1: results/matrix_scale_20260701_085507/matrix_scale.csv
np=2: results/matrix_scale_20260701_085545/matrix_scale.csv
```

结果：

```text
np=1 和 np=2 均进入 MUMPS，但都在 MUMPS analysis 阶段失败。
错误：INFOG(1)=-38
```

也就是说，当前 PETSc 镜像识别 MUMPS，但用户指定的 out-of-core 参数组合还不能直接作为可用求解器。下一步应优先查 MUMPS `INFOG(1)=-38` 对应参数兼容性，尤其是 `ICNTL(22/28/29)` 与当前 PETSc/MUMPS 构建方式，而不是继续扩大 WSL swap。

MKL PARDISO h20 检查：

```text
results/matrix_scale_20260701_085623/matrix_scale.csv
```

结果：

```text
当前 PETSc build 不报告 mkl_pardiso。
程序在建网格前停止，case_status = failed_parallel_direct_lu_unavailable。
没有静默切换到其它 solver。
```

## 2026-07-01 实跑记录：诊断路径 smoke

编译和单元测试：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
Ran 54 tests in 1.687s
OK (skipped=10)
```

默认直接法小算例：

```text
stage4_flat_layer_sanity, h=50 nm, p=1, np=1, zero_order
原始 Nedelec dofs = 75
Floquet constraints = 31
约束后系统大小 = 75
matrix nnz_used / nnz_allocated = 2057 / 2057
average nnz/row = 27.43
explicit C^H A C constructed = False
R/T = 9.999104e-01 / 8.960401e-05
```

这组 h=50 只是诊断 smoke，不是物理 benchmark。

PETSc 参数解析已验证：

```text
-ksp_view -log_view
```

可以放在 `src.runners.run_3d_cases` 命令末尾；`log_view` 只写入 PETSc 全局 options，不再作为 prefixed KSP option 造成 unused option 噪声。

MUMPS out-of-core 测试：

```text
profile = mumps_ooc
np = 1 和 np = 2 均进入 MUMPS
当前镜像在 MUMPS analysis 阶段失败：
INFOG(1)=-38
```

这说明当前 PETSc/MUMPS 确实识别到 MUMPS，但用户指定的 out-of-core 参数组合在当前镜像里还不能直接作为可用解法。下一步如果继续优化 MUMPS，需要针对 `INFOG(1)=-38` 查 MUMPS 参数兼容性，而不是继续扩大 swap。

MKL PARDISO 支持检查：

```text
profile = mkl_pardiso
当前 PETSc build 不报告 mkl_pardiso
程序在建网格前停止并写出 diagnostic summary，没有静默切换到其它求解器
```

尺度测试 CSV smoke：

```text
python3 -m src.studies.run_3d_matrix_scale --mesh-sizes 50 --mpi-procs 1 --stage-case stage4_flat_layer_sanity --nedelec-degree 1 --stage4-dtn-order-policy zero_order
```

输出：

```text
results/matrix_scale_20260701_084630/matrix_scale.csv
```

CSV 已包含 DOF、约束数、nnz、平均 nnz/row、PETSc memory、RSS、swap、KSP/PC/factor solver、R/T 等字段。

## 2026-07-01 更新：新增矩阵结构、PETSc solver 与尺度测试诊断

本轮目标不是继续增大 WSL swap，而是把内存爆炸拆成可观测指标：自由度、MPC 约束、矩阵 nnz、DtN auxiliary block、实际 PETSc 求解器和峰值内存。

每次 3D 运行的 `run_summary.json` 现在会补充这些字段：

```text
num_nedelec_dofs
floquet_num_constraints
constrained_linear_system_size
stage4_dtn_num_auxiliary_dofs
matrix_stats.matrix_rows / matrix_cols
matrix_stats.matrix_nnz_used
matrix_stats.matrix_nnz_allocated
matrix_stats.matrix_memory_mb
matrix_stats.matrix_average_nnz_per_row
actual_ksp_type
actual_pc_type
actual_pc_factor_solver_type
explicit_chac_constructed
constraint_matrix_transform
stage4_dtn_auxiliary_block_stats
```

其中：

```text
explicit_chac_constructed = False
```

表示当前 3D 主线没有走旧的显式 `C^H A C` dense/serial 消元路线。Floquet 约束由 `dolfinx_mpc` 低层拓扑约束装配；Stage 4 DtN 是 FEM unknown + auxiliary modal unknown 的增广稀疏系统。

## 运行时打开 PETSc view/log

可以直接把 PETSc 风格参数放在命令最后：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 20 \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  -ksp_view -log_view
```

也可以使用显式 CLI：

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --mesh-target-size 20 \
  --petsc-ksp-view \
  --petsc-log-view
```

## 测试 MUMPS out-of-core

单进程：

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 20 \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --petsc-direct-solver-profile mumps_ooc \
  -ksp_view -log_view
```

双进程：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 20 \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --petsc-direct-solver-profile mumps_ooc \
  -ksp_view -log_view
```

`mumps_ooc` 会设置：

```text
ksp_type = preonly
pc_type = lu
pc_factor_mat_solver_type = mumps
mat_mumps_icntl_22 = 1
mat_mumps_icntl_14 = 80
mat_mumps_icntl_28 = 2
mat_mumps_icntl_29 = 2
```

如果当前 PETSc 镜像不支持 MUMPS，程序会在建网格前写出失败 summary，不会静默切回其它求解器。

## 测试 MKL PARDISO 是否可用

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 20 \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --petsc-direct-solver-profile mkl_pardiso \
  -ksp_view
```

如果 PETSc 不支持 `mkl_pardiso`，程序会记录错误并停止，不会强行继续。

## 生成尺度测试 CSV

默认扫描：

```bash
python3 -m src.studies.run_3d_matrix_scale \
  --mesh-sizes 20 15 12 10 8 \
  --mpi-procs 1 \
  --stage-case stage4_block_grating \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --petsc-direct-solver-profile default
```

MUMPS out-of-core 双进程：

```bash
python3 -m src.studies.run_3d_matrix_scale \
  --mesh-sizes 20 15 12 10 8 \
  --mpi-procs 2 \
  --stage-case stage4_block_grating \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --petsc-direct-solver-profile mumps_ooc \
  --petsc-option ksp_view \
  --petsc-option log_view
```

输出位置：

```text
results/matrix_scale_YYYYMMDD_HHMMSS/matrix_scale.csv
```

CSV 字段包括：

```text
mesh_target_size_nm
mpi_procs
solver_profile
dof_raw_nedelec
floquet_constraints
constrained_system_size
dtn_auxiliary_dofs
nnz_used
nnz_allocated
average_nnz_per_row
solve_time_seconds
peak_rss_mb
swap_used_before_mb
swap_used_after_mb
actual_ksp_type
actual_pc_type
actual_pc_factor_solver_type
explicit_chac_constructed
dtn_augmented_to_base_nnz_ratio
constrained_to_unconstrained_nnz_ratio
```

## 如何判断矩阵是否变稠

优先看三个比值：

```text
matrix_stats.matrix_average_nnz_per_row
constraint_matrix_transform.constrained_to_unconstrained_nnz_ratio
constraint_matrix_transform.dtn_augmented_to_base_nnz_ratio
```

如果 `average_nnz_per_row` 随网格细化只是温和增长，内存主要来自自由度规模。如果它突然大幅上升，才说明 Floquet/MPC 或 DtN auxiliary block 正在让矩阵结构变稠。

对比关闭 DtN 的路径：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 20 \
  --nedelec-degree 1 \
  --stage4-boundary-model robin0
```

这个结果不是正式物理 R/T，只用于比较矩阵 nnz 和内存。
