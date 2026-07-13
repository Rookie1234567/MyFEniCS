# Task029 当前总结

## 最新状态

Task028 已合并并通过 master release check；Task29 已从 merge commit `2f9e56d2edddb801780504f681b2ff295d993e02` 建立独立分支。Commit A `8401b44` 已加入可开关的外部采样、阶段 checkpoint、PETSc matrix/factor inventory 和 raw MUMPS API 遥测。h5 baseline 已在 clean source SHA `208aaab149ca5c2be0aae09a8d893bfa02e3f8cc` 完整通过并冻结；h3 尚未运行，h2 保持锁定。物理配置、direct default profile 与 ordinary default 均未改变。

## Stage B h5 结论

| 项目 | h5 结果 |
|---|---:|
| full solve / qualification | pass |
| FE / auxiliary / augmented rows | 44,698 / 80 / 44,778 |
| true residual | `5.224671064148491e-12` |
| Task28 R/T/A delta | `0 / 0 / 0` |
| energy closure | `1.219024881038422e-13` |
| max simultaneous worker RSS | 2328.145 MB（2.274 GiB） |
| max cgroup current / kernel peak | 1729.035 / 1757.535 MB |
| sum-rank historical upper bound | 2373.371 MB（2.318 GiB） |
| KSPSetUp / KSPSolve | 1.838 / 0.0467 s |
| swap-in / swap-out | 0 / 0 pages |

最大同时 worker RSS 和最大 cgroup current 都位于 `during_ksp_setup_peak`。从 `before_ksp_setup` 到该阶段，worker RSS 增加约 945.55 MB，cgroup current 增加约 935.27 MB，说明 h5 的首要压力来自 MUMPS analysis/numeric factorization，而不是 KSPSolve。

augmented matrix 为 4,896,156 nnz，factor matrix 为 33,862,428 nnz，直接相除为 6.916 倍；同一 nnz storage estimator 给出 112.406 MB 与 775.391 MB，比例为 6.898。PETSc 对 factor 的 `fill_ratio_given/fill_ratio_needed/memory` 原始值均为 0，因此这些字段不冒充可用测量；775.391 MB 只是统一估算，不是 MUMPS allocator 实测内存。raw INFOG/RINFOG 只按索引保存，不解释含义。

Task28 h5 的历史峰值和口径为 2348.297 MB；新完整 checkpoint 上界为 2373.371 MB，相差 25.074 MB（1.068%）。这轮没有优化，差异只用于说明运行噪声和更完整的最终 checkpoint，不能称作内存改善。外部采样还发现 MPI 进程树在 field output 阶段达到 2385.141 MB，但 worker-rank RSS 和 cgroup current 的主峰仍在 KSPSetUp；factor/KSP 在 postprocess 期间尚未释放。

## 环境边界

容器镜像为 `myfenics-stage4:task28@sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`。WSL 可见内存约 13.65 GiB，cgroup 未另设硬上限。当前主机只有 16 GB 级物理内存，因此 h3 前必须确认无交换压力，h2 仅可在任务书全部解锁 Gate 满足时运行。

## 比较原则

主比较只使用同一 FEniCS target 的 Task28 baseline 与 Task29 candidate。COMSOL 的 22.989 GB direct 与 8.992–13.376 GB GMG 结果只作为另一机器、自由四面体、P 偏振、零级端口的定性架构参考，不能作为 FEniCS 的时间、RTA 或每 DoF 效率基准。

详见 [COMSOL 比较边界](comsol_reference_comparability.md)。

## Stage A 验证

Docker 完整轻量回归为 128 passed / 10 skipped，Benchmark checker 为 149/149；ruff、compileall 与文档合同均通过。基线前审计还确认 Task28 原生命周期会让 KSP/factor、system Mat、RHS 和 solution Vec 在 postprocess 期间继续被引用；Commit A 没有提前释放这些对象，避免把基线测低。

## 当前停止点

h5 baseline 已冻结，但 Stage B 尚未完成。下一步只能在用户单独确认后运行无 swap 的 h3 baseline；在此之前不进入生命周期、预分配、ordering、OOC 或 BLR 候选，也不解锁 h2。
