# Task029 当前总结

## 最新实现状态（2026-07-13，Stage C/D 候选冻结前）

H1–H7 假设表和逐对象生命周期清单已建立。低风险 H1 以 `direct_release_base_after_augmentation=false` 保持 ordinary default，只有 Case050 显式传入 `--release-base-after-augmentation` 才在 copy 后释放 `A_base/b_base`。异常 direct LU 路径增加幂等 PETSc cleanup；OOC sampler 增加 scratch peak、process-tree I/O bytes 和 block-I/O delay；显式且可用的 MPI distributed factor package 不再被 fallback MUMPS 覆盖。ruff、compileall、34 项 focused regression 与全量 133 passed / 10 skipped 均通过，待提交后进行 clean-source h5/h3 实跑。

BLR `1e-5` h5 screening 已被数值 Gate 淘汰：真残差 `4.704e-3`，R/T/A 最大偏差 `1.073e-3`，worker RSS 还比 baseline 高约 3.4%。首次 SuperLU_DIST 请求被旧选择逻辑覆盖，实际仍运行 MUMPS，因此标记 invalid screen，不用其数值作 package 对比；修正后将 clean rerun。

## 最新状态（2026-07-13，Stage B 完成）

Task28 已通过 review、合并并推送到 `master`；Task29 从 merge commit `2f9e56d2edddb801780504f681b2ff295d993e02` 建立独立分支。Stage A 遥测和 Stage B 的 h5/h3 MPI4 baseline 均已完成，两个 baseline 都是 full solve、数值 Gate 全通过且 swap-in/swap-out 为 0。ordinary default、物理模型、模式集合、网格和 official R/T/A 路径均未改变，h2 仍锁定。

| 项目 | h5 MPI4 baseline | h3 MPI4 baseline |
|---|---:|---:|
| source SHA | `208aaab` | `fba69d8` |
| FE / auxiliary / augmented rows | 44,698 / 80 / 44,778 | 198,438 / 80 / 198,518 |
| true residual | `5.225e-12` | `1.382e-11` |
| max Task28 R/T/A abs delta | `0` | `1.865e-14` |
| max simultaneous worker RSS | 2328.145 MB | 8651.098 MB |
| max cgroup current | 1729.035 MB | 8353.727 MB |
| historical rank-peak upper bound | 2373.371 MB | 8648.613 MB |
| KSPSetUp / KSPSolve | 1.838 / 0.0467 s | 31.200 / 1.603 s |
| augmented / factor nnz | 4,896,156 / 33,862,428 | 21,317,860 / 266,127,836 |
| factor / augmented storage estimate | 6.898× | 12.448× |
| swap-in / swap-out | 0 / 0 pages | 0 / 0 pages |

## Stage B 归因

两个网格的主峰都发生在 `during_ksp_setup_peak`，不是 `KSPSolve`、RTA 或 field output：

- h5：相对 `before_ksp_setup`，KSPSetUp 主峰增加 945.55 MB worker RSS、935.27 MB cgroup memory。
- h3：相对同一稳定点，KSPSetUp 主峰增加 6472.43 MB worker RSS、6474.57 MB cgroup memory。
- h3 的 KSPSolve 结束只比 factorized checkpoint 多 6.98 MB worker RSS；official RTA 再增加不足 1 MB；field output 与后处理增加约 129.06 MB worker RSS、112.51 MB cgroup memory，仍低于 KSPSetUp 主峰。
- h3 在 `A_base` 与 `A_aug` 共存区间相对 variational stage 增加约 729.07 MB worker RSS、754.62 MB cgroup memory；它值得检查生命周期，但只占 8.4%–9.0% 的最终主峰，无法单独解释瓶颈。
- h3 factor 的统一 nnz storage estimate 为 6092.70 MB，是 augmented matrix 的 12.448 倍；这是结构量级估算，不是 MUMPS allocator 实测值。PETSc 返回的 factor memory/fill 原始字段为 0，因此不冒充可用测量。

结论：Task29 的首要瓶颈是 MUMPS analysis/numeric factorization；base/augmented 生命周期与 postprocess 是次要项。若 H1–H3 的低风险公共改动收益不足 10%，应按任务书 Stop B 转向 rank/solver profile，而不是重写装配。

## rank-count 诊断

h5 固定每 rank 1 个线程，MUMPS 同后端 MPI1/2/4 的结果为：

| ranks | total threads | worker RSS | 相对 MPI4 | cgroup current | Stage4 时间 |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 1230.305 MB | -47.16% | 1096.766 MB | 25.969 s |
| 2 | 2 | 1697.980 MB | -27.07% | 1411.852 MB | 19.286 s |
| 4 | 4 | 2328.145 MB | baseline | 1729.035 MB | 14.800 s |

更多 ranks 缩短运行时间，但增加所有进程的总 RSS。MPI2/MUMPS 在 h5 已超过 20% worker-RSS 降幅，且时间代价小于 MPI1，因此选为 h3 的首个低风险候选。单 rank ordinary default 自动落到 PETSc 内置 LU，已单列为不同后端诊断，不与 MUMPS rank scaling 混为同一比较。

## 与 Task28 口径差异

Task29 不把历史 rank 峰值之和与同时 RSS 混写。h5 新历史上界比 Task28 高 25.074 MB（1.068%）；h3 高 270.520 MB（3.229%）。差异来自 0.25 s 外部采样、更多完整 checkpoint 和正常运行波动，不是优化收益。所有正式前后比较将以 Task29 的 `max_simultaneous_worker_rss_mb` 为主、cgroup memory 为交叉证据。

## 当前决策

Stage B 已闭合，可以进入 Stage C/D/E。下一步按独立归因依次调查 H1/H2/H3/H5/H6/H7；先完成 h5 OOC/BLR 等 profile screening，再只把最多两个候选送入 h3。h2 仅在 h5/h3 同一候选均降低至少 20%、h3 无 swap、预测上界不超过 13.5 GB且 watchdog 就绪时才可能解锁。
