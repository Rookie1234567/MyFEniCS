# Task029 少 rank + 多线程 direct 能力审计

## 最终身份

```text
threaded_direct_capability = unavailable_in_current_image
T0 = failed_at_runtime
T1 = failed
T2 = pass_but_not_sufficient
T3 = negative
T4 = stop; h3 = not_run
ordinary default changed = no
image rebuild = no
```

这里的 `unavailable` 不是说 OpenBLAS 无法创建 pthread，而是说当前镜像内的 MUMPS `KSPSetUp` 因子化没有把 MPI1×4 的 BLAS 线程转化为多核工作与足够加速。因此不能把“线程存在”写成“threaded MUMPS 可用”。

## 静态构建与链接审计

审计脚本为 [`benchmarks/scripts/audit_direct_thread_capability.sh`](../../../benchmarks/scripts/audit_direct_thread_capability.sh)，在与正式结果相同的 `myfenics-stage4:task28` 镜像中运行。

| 项目 | 实测 |
|---|---|
| PETSc | 3.24.0，活动架构 `linux-gnu-complex128-32` |
| PETSc scalar/index | complex double / 32-bit indices |
| MUMPS | 5.8.1，PETSc configure 使用 `--download-mumps` |
| MUMPS linkage | `-lzmumps -lmumps_common -lpord -lpthread` |
| BLAS/LAPACK | PETSc `-llapack -lblas`；动态链最终解析到 system OpenBLAS |
| system OpenBLAS | 0.3.26，`openblas-pthread`，`parallel_mode=1`，`MAX_THREADS=64` |
| OpenBLAS 控制 | `OPENBLAS_NUM_THREADS=4` 被运行时 API 读为 4；API 改为 2 后读回 2 |
| PETSc/MUMPS OpenMP | configure/header 未显示 OpenMP 构建；运行链未链接 OpenMP runtime |
| NumPy BLAS | 独立的 scipy-openblas 0.3.29，只作 Python 侧交叉检查，不代表 MUMPS 链路 |
| CPU 可见性 | i7-13620H；16 logical CPUs；容器允许 `0-15` |

为了排除 OpenMP→BLAS 嵌套，正式运行固定 `OMP_NUM_THREADS=1`、`OMP_DYNAMIC=FALSE`、`OMP_MAX_ACTIVE_LEVELS=1`，并用 `OPENBLAS_NUM_THREADS` 控制 BLAS。四个 h5 运行都用 `taskset -c 0-3`，并以 `mpiexec --bind-to none` 让 MPI rank 与 pthread 共享同一个四逻辑 CPU 预算；所有 worker 的实际 `Cpus_allowed_list=0-3`。

必须保留一项限制：NumPy 的 scipy-openblas 与 PETSc/MUMPS 的 system OpenBLAS 是不同 runtime，同一个 `OPENBLAS_NUM_THREADS` 会影响多个线程池。`rank×threads` 的意图预算没有超过四核，affinity 也封顶了实际 CPU 执行，但 runnable-thread oversubscription 不能被当前环境变量完全排除。MPI1×4 的 process threads 从 3 增到 12 也印证存在额外 runtime threads；这不是可用多核证据，而是 T0 停止结论的另一项限制。

## 固定四核 h5 结果

所有运行均来自 clean source `48958571f62590418bf4281f09ad22b1419eb880`，保持相同物理、MUMPS、ordering、80 个 auxiliary DoF、full residual、official R/T/A 与场输出。完整轻量表见 [`threaded_direct_matrix.csv`](threaded_direct_matrix.csv)。

| 配置 | worker RSS | cgroup | KSPSetUp | Stage4 | KSPSetUp CPU 核均值/峰值 | 数值 Gate |
|---|---:|---:|---:|---:|---:|---|
| MPI4×1 | 2351.707 MiB | 1813.465 MiB | 2.385 s | 18.311 s | 3.906 / 4.061 | pass |
| MPI2×2 | 1677.062 MiB | 1391.320 MiB | 1.953 s | 20.687 s | 3.272 / 4.025 | pass |
| MPI1×4 | 1399.648 MiB | 1272.477 MiB | 23.841 s | 48.273 s | 0.999 / 1.054 | pass |
| MPI1×1 | 1401.988 MiB | 1269.812 MiB | 25.578 s | 50.891 s | 0.999 / 1.060 | pass |

`worker process threads` 从 MPI1×1 的 3 增到 MPI1×4 的 12，证明线程池被创建；但 `during_ksp_setup_peak` 的 CPU 核均值没有从约 1.0 增加，峰值也没有超过 MPI1×1 的正常采样波动。MPI1×4 相对 MPI1×1 的 Stage4 speedup 只有 `50.891/48.273 = 1.054×`，低于 `1.25×` 最低门槛；相对原非亲和性 MPI4×1 14.800 s 基线为 `3.262×`，也超过 1.5×负向时间门槛。

内存方面，MPI1×4 / MPI1×1 worker RSS 比为 `0.9983`，cgroup 比为 `1.0021`，所以 T2 通过；但这只是少 rank 的内存效果，不能弥补 T1 与 T3 失败。MPI2×2 的 KSPSetUp 确有约 3.27 核均值，但 Stage4 仍比同亲和性 MPI4×1 慢 13.0%，不形成新推荐。

## 门槛决定

| Gate | 结果 | 决定依据 |
|---|---|---|
| T0 build/control | static pass, runtime fail | OpenBLAS pthread 可控，但存在多个 BLAS runtime 且目标 MPI1×4 KSPSetUp 仍约 1 核 |
| T1 actual parallelism | fail | MPI1×4 KSPSetUp mean/max = 0.999 / 1.054 cores |
| T2 memory | pass | MPI1×4 RSS/cgroup 均不超过 MPI1×1 的 1.20× |
| T3 engineering | negative | Stage4 48.273 s；对 MPI1×1 仅 1.054× speedup；远慢于 18.5/22.2 s 门槛 |
| T4 h3 | stop | strong positive 不成立，h3 threaded direct 明确 `not_run` |

最终不重建镜像、不运行线程版 h3、不改变 ordinary default，也不创建 threaded direct workstation profile。若未来换到明确支持 threaded MUMPS 或更合适 dense-kernel 并行的镜像，应从本脚本和固定四核 h5 矩阵重新资格化，不能沿用本次负结果作为新环境结论。
