# 3D 直接求解 profile：default、MUMPS OOC 与 BLR

三个 profile 都是直接因子分解路径。OOC 改变因子存储位置，BLR 改变 MUMPS 因子近似；两者都不是 Krylov 迭代预条件器。

## 1. 配置入口

```text
SimulationConfig3D.petsc_direct_solver_profile_requested
run_3d_cases --petsc-direct-solver-profile {default,mumps_ooc,mumps_blr}
```

`src/main.py` 的 demo OOC/BLR preset 只翻译为该 flag。target direct h5/h3 preset 默认使用标准 MUMPS，不因名称暗中打开迭代器。

## 2. 关键函数

| 函数 | 责任 |
|---|---|
| `common_3d_solve::_direct_lu_petsc_options` | 基础 `preonly + lu + error_if_not_converged` |
| `_has_petsc_package` | 查询 PETSc 外部 factor package |
| `_available_parallel_lu_solver_type` | MPI 选择 MUMPS；不可用则显式失败 |
| `_mumps_ooc_minimal_options` | OOC、工作空间和基础 MUMPS controls |
| `_mumps_blr_minimal_options` | BLR controls 与默认阈值 `1e-5` |
| `_prepare_direct_lu_options_for_comm` | profile + communicator + 用户覆盖解析 |
| `_linear_system_diagnostics` | 解后 `||Ax-b||/||b||` |
| `_petsc_matrix_stats` | global rows、nnz、norm、storage estimate |

最终用户 PETSc option 在 profile option 之后应用，因此记录必须保存 resolved option；profile 名本身不完整描述一次求解。

## 3. Default 流程

```text
KSP type = preonly
PC type = lu
factor solver = serial available package or MPI MUMPS
```

`_prepare_direct_lu_options_for_comm` 根据 communicator 大小与 PETSc build 选择 backend。MPI 中没有可用 parallel LU 时返回环境不满足信息，case flow 写 failure summary；不能把它解释为 Maxwell 方程不收敛。

## 4. OOC 生命周期

`_prepare_mumps_ooc_runtime(cfg,out_dir,options,comm,log)` 创建/解析当前 case 的 OOC 目录并设置 MUMPS 环境。因子文件的生命周期是：

```text
prepare directory/env
-> assemble matrix
-> MUMPS analysis/factor/solve
-> write residual and summary
-> destroy KSP/matrix/factor owner
-> success: _cleanup_mumps_ooc_directory_on_success
   failure: _retain_mumps_ooc_directory_on_failure
```

不能在 KSP 销毁前删除目录，因为 MUMPS 可能仍持有文件句柄。失败时保留现场并写目录状态，方便区分磁盘不足、权限、factor allocation 与物理问题。

## 5. BLR 语义

BLR 是 MUMPS 的 block-low-rank compressed factorization。它仍在 `preonly+lu` 内完成一次近似直接 factor/solve；`blr_threshold=1e-5` 控制压缩误差与内存。线性真残差必须重新计算，不能把 `KSP iterations=1/0` 当作迭代收敛证据。

BLR 若失败或残差不合格，只能作为 direct fallback 的负结果；不能自动改写为 workstation iterative profile。

## 6. 矩阵 shape 与 ownership

标准 3D 系统是 distributed AIJ `N_fe x N_fe`；Stage4 auxiliary DtN 是 `(N_fe+N_aux)^2`。各 rank 拥有连续行区间；MUMPS 内部重新分发和 factor storage 不等于 PETSc row ownership。

matrix stats 使用 global sum；`memory` 字段若 PETSc 不提供，则按 nnz、scalar/index bytes 估计，不能等同进程 RSS。RSS 要看 runner 的 per-rank/total peak 字段。

## 7. 调用顺序

```text
run_3d_cases::main
-> SimulationConfig3D
-> run_prepared_3d_case_flow
-> _prepare_direct_lu_options_for_comm
-> _prepare_mumps_ooc_runtime
-> standard LinearProblem 或 dtn_port_3d::_solve_augmented_system
-> KSP.setFromOptions / solve
-> _linear_system_diagnostics
-> postprocess
-> destroy and OOC cleanup/retain
```

Stage4 DtN assemble-only 可返回 matrix/resource stats 而不 factor；它不是求解成功记录。

## 8. 失败对象

`common_3d_solve::DirectSolveFailure` 携带 failure stage、原 PETSc exception、A/b/x/KSP、backend、timing 和 diagnostics。case flow 先序列化可用证据，再统一 destroy，避免 double destroy 或只剩不完整日志。

## 9. 运行与输出

```powershell
python src/main.py --preset 3d_stage4b_demo_mumps_ooc
python src/main.py --preset 3d_stage4b_demo_mumps_blr
python src/main.py --preset 3d_target_grating_direct_h5
```

前两项是 demo 几何，不能与 Case021 target record 做数值对比。输出应检查 `solver_profile_requested/resolved`、factor package、PETSc options、matrix rows/nnz、true residual、RSS、OOC cleanup status 和 official RTA。

## 10. 证据与 Gate

- `test_18`：profile/options/包选择。
- `test_19`：OOC 成功清理和失败保留。
- Case030：OOC/BLR 功能 contract，身份为 direct fallback/experimental，不是 canonical 迭代结果。
- Case021：target p2 h5/h3 MPI4 MUMPS direct canonical；h2 direct 仅 reviewed reference，本轮未重跑。

## 11. 限制

OOC 会把 RAM 压力转成磁盘 I/O，不保证 14 GB 内完成；BLR 会引入 factor approximation，不保证所有参数 residual 合格。profile 对资源的表现依赖 PETSc/MUMPS build、MPI、磁盘和矩阵排序。理论见 [`../../theory/direct_solvers_and_factorization.md`](../../theory/direct_solvers_and_factorization.md)。
