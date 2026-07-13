# 3D 直接求解 profile：default、MUMPS OOC 与 BLR

三个 profile 都是直接因子分解路径。OOC 改变因子存储位置，BLR 改变 MUMPS 因子近似；两者都不是 Krylov 迭代预条件器。

## Task29 更新（2026-07-13）

Review V1 线程审计的最终结论是 `threaded_direct_capability=unavailable_in_current_image`。活动 PETSc 3.24.0 / MUMPS 5.8.1 通过系统 BLAS 链接 OpenBLAS 0.3.26 pthread；运行时线程数可控，但固定 CPU `0-3` 的 MPI1×4 在 `during_ksp_setup_peak` 只使用 0.999/1.054 核均值/峰值，Stage4 48.273 s，相对 MPI1×1 只有 1.054× speedup。进程 thread 数从 3 增至 12 只证明线程池存在，不证明 MUMPS factorization 多核。threaded h3 因 T1/T3 失败而 `not_run`，ordinary default 不变。

`benchmarks.run_direct_memory_forensics` 的 `--threads-per-rank` 设置共享的 OpenBLAS 环境；runner 固定 `OMP_NUM_THREADS=1`、`OMP_MAX_ACTIVE_LEVELS=1`，避免 OpenMP 与 BLAS 嵌套。由于 NumPy scipy-openblas 与 PETSc system OpenBLAS 是不同 runtime，该环境不能保证只有一个线程池；`--cpu-affinity 0-3` 用 `taskset` 和 `mpiexec --bind-to none` 将实际执行封顶在固定 CPU budget。timeline 新增 worker/process-tree thread count、累计 CPU seconds、区间 CPU core equivalents 和 worker affinity；这些字段属于 capability/telemetry，不进入普通 Stage4 config。

最终 Case050 证据显示：MPI4 h5/h3 baseline simultaneous worker RSS 为 2328.145 / 8651.098 MiB，default MUMPS MPI2 为 1655.484 / 7343.137 MiB，即分别下降 28.893% / 15.119%。h3 未达到 20%，所以 MPI2 只是诊断运行点，不是合格 `optimized_direct_incore_candidate`。release-base MPI4 在 h3 只下降 5.462%，证明公共生命周期开销不是主峰根因；ordinary default 仍为 MPI4/default 行为。

OOC h5 降低 13.744% worker RSS，但使用 559,715,776 scratch bytes，Stage4 时间为 baseline 的 1.539 倍；成功路径删除全部 8 个文件。BLR `1e-5` 的进程返回码虽为 0，真残差 `4.704e-3` 与 R/T/A 失败；SuperLU_DIST 和 `ICNTL(7)=3` 都增加内存。因此没有 profile 获得 h3 20% 工程资格。

`petsc_extra_options.pc_factor_mat_solver_type` 现在会在 PETSc 实际提供且属于已批准的 MPI distributed LU package 时被尊重，不再被 MPI fallback 无条件改写为 MUMPS；未显式请求时 ordinary MPI default 仍选择 MUMPS。串行-only package 不允许进入 MPI direct 路径。

Task29 的低风险 H1 候选由 `SimulationConfig3D.direct_release_base_after_augmentation` 控制，默认 `false`。显式开启后，DtN 路径在 `A_base/b_base -> A_aug/b_aug` 完整复制并写出 checkpoint 后立即销毁 base Mat/Vec；KSP、真残差、场重建和 official R/T/A 仍只使用 augmented system。异常路径的 `DirectSolveFailure.cleanup()` 在诊断写盘后幂等销毁 KSP/x/b/A。

Case050 sampler 还记录 `ooc_scratch_*`、process-tree read/write bytes 与 block-I/O delay。后者是存活后代进程的累计计数最大观测值，block-I/O delay 是进程时间之和而非 wall time；OOC 报告必须同时给 KSPSetUp wall time、scratch peak、I/O counters 与 cleanup 状态。

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

`_prepare_direct_lu_options_for_comm` 根据 communicator 大小、显式 package 请求与 PETSc build 选择 backend。MPI 中没有可用 parallel LU 时返回环境不满足信息，case flow 写 failure summary；不能把它解释为 Maxwell 方程不收敛。

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

## 11. Task29 factored Mat 与内存遥测

`benchmarks.run_direct_memory_forensics` 用独立 0.25 s sampler 包住完整 MPI worker。worker 在 `KSPSetUp` 后通过 `PC.getFactorMatrix()` 读取 factor；已分解的 PETSc Mat 不能再次 `assemble()`，因此 `_petsc_matrix_stats(..., assemble=False)` 只读 size、type、ownership、`getInfo()` 和可安全获得的字段。

h5 冻结结果的 augmented/factor nnz 为 4,896,156 / 33,862,428，代数比为 6.916。PETSc 对 MUMPS factor 返回的 `fill_ratio_given/fill_ratio_needed/memory` 原始值均为 0，因此不把它们当有效 factor memory；统一 nnz estimator 的 775.391 MB 只用于同口径结构比较。INFOG/RINFOG 保留 raw index，代码不猜测其语义。

外部 sampler 的 worker 同时 RSS 与 cgroup charged memory 分开记录。h5/h3 的 worker/cgroup 主峰均位于 KSPSetUp；h3 factor estimated storage 是 augmented 的约 12.45 倍，KSPSetUp 峰值增量约 6.47 GiB。field/RTA/output 只形成较低尾部平台，不能与 factorization 主峰合并为一个“总峰值”字段。

## 12. 限制

OOC 会把 RAM 压力转成磁盘 I/O，不保证 14 GB 内完成；BLR 会引入 factor approximation，不保证所有参数 residual 合格。profile 对资源的表现依赖 PETSc/MUMPS build、MPI、磁盘和矩阵排序。理论见 [`../../theory/direct_solvers_and_factorization.md`](../../theory/direct_solvers_and_factorization.md)。
