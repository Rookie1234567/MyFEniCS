# Task029 结果总结

## 1. 最终状态

```text
classification = diagnostic_success
engineering_success = no
strong_engineering_success = no
threaded_direct_capability = unavailable_in_current_image
h2 = not_run
h3_threaded_direct = not_run
ordinary default changed = no
master decision = pending final review
```

Task029 建立了可信的 Stage4 direct 分阶段内存证据，确认 MUMPS analysis/numeric LU factorization 是主峰，并完成 H1–H7、rank/profile、h2 安全门槛与线程条件审计。最佳 h3 in-core 候选只降低 simultaneous worker RSS 15.119%，未达到 20% 工程门槛。当前镜像的 MPI1×4 虽能创建 OpenBLAS pthread，但 `KSPSetUp` 仍约使用 1 核，Stage4 只比 MPI1×1 快 1.054×，所以没有 low-memory 或 threaded direct 推荐 profile。

## 2. 任务目标与非目标

目标是回答三个工程问题：目标 p2 Stage4 direct 的内存在哪个阶段增长；公共生命周期、rank 数和 direct backend/profile 能否在保持数值等价时把 h3 峰值降低至少 20%；若不能，h2 是否应被安全 Gate 阻止。

本任务不改变物理模型、`auto_propagating` 全传播衍射级、official R/T/A、ordinary direct 默认，不实现新的多重网格/预条件器，也不以 COMSOL 的另一机器结果替代本仓库前后对照。

## 3. 基线、冻结配置和环境

| 项目 | 冻结值 |
|---|---|
| period / cell | 50 × 25 × 140 nm |
| Si block | 17 × 25 × 120 nm |
| wavelength / incidence | 13.5 nm；theta=80°；phi=0；s polarization |
| discretization | p2 Nédélec；h=5/3，h=2 条件式 |
| boundary | double Floquet + auxiliary Fourier-DtN |
| modal identity | `auto_propagating`；top/bottom 40/40；`n_aux=80` |
| baseline solver | PETSc `preonly+LU` / MUMPS，MPI4，每 rank 1 thread |
| numerical Gate | full true residual、Task28 R/T/A delta、closure 均 `<=1e-8` |
| environment | `myfenics-stage4:task28`；digest `sha256:08c61b...76d` |

正式前后比较使用 simultaneous worker RSS；cgroup current、swap、历史 rank 峰值和只作独立交叉证据，不互相替代。详细环境见 [`environment.json`](environment.json)。

## 4. 实现与方法

| 方法 | 目的 | 证据 |
|---|---|---|
| 0.25 s 外部进程/cgroup sampler | 把内存峰值归到 solver stage，避免只看最终 RSS | `baseline_memory_timeline.csv` |
| base/augmented/factor inventory | 区分 FE/DtN 共存与 LU fill | `baseline_matrix_inventory.csv`、`baseline_factorization_summary.csv` |
| raw INFOG/RINFOG | 保留 MUMPS 原始索引，不猜测字段语义 | Case050 records/artifacts |
| clean-source provenance | 所有正式运行绑定 commit、image digest、command | candidate records |
| H1–H7 单因素筛选 | 生命周期、预分配、cleanup、assembly、rank/backend、OOC/BLR/ordering | `optimization_hypotheses.csv` |
| 两路径 h2 外推 + G1–G10 | 在启动高风险 h2 前量化内存范围与 stop Gate | `h2_memory_prediction.md`、`gate_decision.csv` |
| 构建/链接 + `/proc` CPU/thread 审计 | 验证少 rank + 多线程是否真的进入 MUMPS factorization | `threaded_direct_capability_audit.md` |

实现还增加了 `DirectSolveFailure.cleanup()` 幂等清理、OOC scratch/I/O/cleanup 遥测、显式 MPI distributed factor package 选择正确性，以及默认关闭的 `direct_release_base_after_augmentation` opt-in 生命周期控制。

## 5. 实验/运行矩阵

实际完成：MPI4 h5/h3 baseline；h5 MPI1/2/4 rank 诊断；release-base h5/h3；OOC、BLR、SuperLU_DIST、MUMPS ordering h5 筛选；正式 MPI2 h5/h3；h2 两类外推；PETSc/MUMPS/BLAS 静态审计；固定 CPU `0-3` 的 h5 MPI4×1、MPI2×2、MPI1×4、MPI1×1。

明确未运行：h2 direct（G3/G5/G7/G9 失败）；threaded h3（T1/T3 失败，T4 stop）；MPI1×2（MPI1×4 已触发强负向 stop，建议模板中的可选点不再增加决策信息）；镜像重建与新迭代算法（超出 Task029）。

## 6. 关键结果表

### 6.1 Baseline 与最佳内存候选

| h / 候选 | full solve / 数值 Gate | worker RSS | 相对 MPI4 baseline | cgroup | 处置 |
|---|---|---:|---:|---:|---|
| h5 MPI4 baseline | pass | 2328.145 MiB | baseline | 1729.035 MiB | 冻结基线 |
| h3 MPI4 baseline | pass | 8651.098 MiB | baseline | 8353.727 MiB | 冻结基线 |
| h5 release-base MPI4 | pass | 2217.172 MiB | -4.767% | 1932.539 MiB | 低风险 opt-in，非 profile |
| h3 release-base MPI4 | pass | 8178.539 MiB | -5.462% | 7593.148 MiB | 公共生命周期非主瓶颈 |
| h5 MUMPS MPI2 | pass | 1655.484 MiB | -28.893% | 1370.473 MiB | 进入 h3 |
| h3 MUMPS MPI2 | pass | 7343.137 MiB | -15.119% | 7070.438 MiB | 最佳诊断点，未达 20% |

这里负号表示内存比同 h 的 MPI4 baseline 减少；分母始终是同口径 MPI4 simultaneous worker RSS。

### 6.2 固定四核线程审计

| 配置 | worker RSS | KSPSetUp | Stage4 | KSPSetUp CPU 核均值/峰值 | 处置 |
|---|---:|---:|---:|---:|---|
| MPI4×1 | 2351.707 MiB | 2.385 s | 18.311 s | 3.906 / 4.061 | 同亲和性参考 |
| MPI2×2 | 1677.062 MiB | 1.953 s | 20.687 s | 3.272 / 4.025 | 时间负向 |
| MPI1×4 | 1399.648 MiB | 23.841 s | 48.273 s | 0.999 / 1.054 | KSPSetUp 仍近似单核 |
| MPI1×1 | 1401.988 MiB | 25.578 s | 50.891 s | 0.999 / 1.060 | 单 rank 对照 |

四组 true residual 均不高于 `2.765e-11`，最大 Task28 R/T/A 绝对差不高于 `1.729e-13`，swap in/out 均为 0。线程存在不等于因子化并行：MPI1×4 的 worker threads 从 3 增到 12，但 KSPSetUp CPU 使用没有增加。

## 7. 数值正确性与 Gate

h5/h3 baseline、release-base、正式 MPI2、OOC 与四组线程审计都完成 full solve，并通过 full true residual、Task28 R/T/A、closure 和 modal identity Gate。BLR `1e-5` 虽返回 0，但 true residual 为 `4.704e-3` 且 R/T/A 最大偏差 `1.073e-3`，按数值 Gate 拒绝。未运行项始终写为 `not_run`，不记为 pass。

## 8. 性能和资源结果

h3 baseline 的 augmented/factor nnz 为 21,317,860 / 266,127,836，统一 nnz-storage estimator 比约 12.45×。从 KSPSetUp 前到主峰，worker RSS 与 cgroup 分别增加约 6472.43 / 6474.57 MiB；KSPSolve、official RTA 与 field output 只增加较小尾部平台。

OOC h5 worker RSS 降低 13.744%，但 Stage4 为 baseline 的 1.539×并使用 559,715,776 bytes scratch。SuperLU_DIST 增加 14.462% RSS；`ICNTL(7)=3` 增加 factor nnz 与峰值。线程审计中 MPI1×4 相对 MPI1×1 的 Stage4 speedup 只有 1.054×，低于 1.25×，且相对原 14.800 s MPI4 baseline 为 3.262×。

## 9. 根因解释

实测表明主导量是 MUMPS 在 `KSPSetUp` 中形成的 LU fill，而不是 80 个 auxiliary DoF、KSPSolve、official RTA 或场输出。base/augmented 共存约占 h3 主峰 8%–9%，因此提前释放只能得到约 5% 全局收益。减少 MPI rank 能降低进程重复与总 RSS，但会牺牲 MUMPS 并行因子化。

当前 PETSc 3.24.0 / MUMPS 5.8.1 链接 system OpenBLAS 0.3.26 pthread，线程数可控；然而目标 MPI1×4 KSPSetUp 仍约 1 核，说明此矩阵/构建的主因子化路径没有从 BLAS pthread 获得有效并行。该结论只适用于当前 image 与冻结问题，不外推到其他 threaded MUMPS 构建。

## 10. 成功路线

- 分阶段 simultaneous RSS/cgroup/swap/CPU/thread 遥测与 clean-source provenance 可复用。
- matrix/factor inventory、raw MUMPS telemetry 和数值 Gate 形成可审查闭环。
- 幂等异常 cleanup、正确 factor package 选择、OOC I/O/cleanup 证据属于低风险基础设施。
- `direct_release_base_after_augmentation` 可作为显式 opt-in 生命周期控制保留，但不是低内存 profile。
- h2 G1–G10 guard 和预测 helper 成功阻止不安全运行。

## 11. 失败、负结果与未运行项

- MPI2：h3 仅 -15.119%，工程 Gate 失败。
- OOC：内存收益不足 20%，且有明显 I/O/时间代价。
- BLR：数值 Gate 失败。
- SuperLU_DIST 与 ordering：内存负收益。
- MPI1×4 threaded direct：T1/T3 失败，身份为 `unavailable_in_current_image`。
- h3 threaded direct：`not_run`，因为 h5 没有 strong positive。
- h2 direct：`not_run`，预测 18.882–27.913 GiB，G3/G5/G7/G9 失败。

## 12. 代码和文件变化

公共代码变化集中在 direct 生命周期/cleanup、factor package 选择和只读 telemetry；benchmark 增加 Case050 runner、审计脚本、CPU/thread sampler 与轻量 records；文档增加 Task029 outcomes、项目级回顾、solver/capability/benchmark 边界和长期 Task 回顾标准。完整列表见 [`changed_files.md`](changed_files.md)。

## 13. 最终合并建议

建议在最终 review 通过后合并 telemetry、cleanup、package-selection correctness、显式 release-base 控制、Case050、h2 guard、审计证据和文档契约。不得提升 MPI2、OOC、BLR、SuperLU_DIST、ordering 或 threaded direct 为推荐 profile；ordinary default 不变；Task28 canonical records 不覆盖。详见 [`merge_recommendation.md`](merge_recommendation.md)。

## 14. 局限

PETSc 对 MUMPS factor 的部分 memory/fill 原始字段为 0，factor storage 是统一 nnz estimator 而非 allocator 实测。CPU 核使用来自 0.25 s `/proc` 累计 CPU 时间差分，适合判定约 1 核与约 4 核，不代表硬件性能计数器。NumPy 与 PETSc 使用不同 OpenBLAS runtime，runnable-thread oversubscription 不能由共享环境变量完全排除；affinity 只封顶实际 CPU 执行。完整 artifacts 只在本地 ignored 目录。COMSOL 机器、网格、偏振、几何与衍射范围不同，只提供架构方向。

## 15. 下一步决定

停止继续扫描 direct ordering、对象生命周期和当前镜像的 BLAS 线程。后续优先：先完成 h3/h2 的物理网格收敛或 graded/adaptive mesh 资格化，因为 residual/closure 不等于物理收敛；若继续降内存，转向真正 multilevel H(curl)、low-order-refined multigrid 或受控 coarse direct solve 的并行 physical Schwarz。只有更换为明确支持 threaded factorization 的 image 时，才从固定四核 h5 能力审计重新开始。

## 16. 证据索引

- [任务书](../task.md)
- [Task029 review V1](../review_report_v1.md)
- [P0-C 长期补充](../review_report_v1_p0c_addendum.md)
- [线程能力审计](threaded_direct_capability_audit.md)
- [线程矩阵 CSV](threaded_direct_matrix.csv)
- [候选统一对比](candidate_comparison.csv)
- [h2 Gate](gate_decision.csv)
- [h2 启动决定](h2_launch_decision.md)
- [合并建议](merge_recommendation.md)
- [Case050](../../../benchmarks/cases/050_stage4_direct_memory_forensics/README.md)
- [Case050 线程审计 record](../../../benchmarks/cases/050_stage4_direct_memory_forensics/records/h5_threaded_direct_audit.json)
- [Task 回顾标准](../../task_retrospective_standard.md)
