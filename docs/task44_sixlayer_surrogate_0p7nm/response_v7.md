# Task44 执行响应 v7：顶部空气间距稳定性超限

## 本轮结论

以 B 样本为基线的顶部空气间距对照已完成。完整系统的显式相对真残差为 `6.752756601e-10`，低于 `1e-6`；DtN 端口吸收与材料体积吸收之间的能量闭合误差为 `-7.221615528e-10`，低于 `1e-5`。因此该 run 有合格解，并生成了 official 端口模态 `R/T/R00` 与 `A_volume`。

但空气高度从 `0.5 nm` 增到 `1.0 nm` 后，三个主输出相对 B 的绝对变化均略高于 `2e-4`。本项判定为 `accuracy_gate_failed`。这是已通过线性方程与能量检查的结果，空间稳定性门仍未通过；不据此更新 B 或 A–D 的 GP 标签。

这里的 `official` 表示数值场通过本任务的残差与能量门，端口结果可用于这组离散对照。run summary 仍将本 case 标为 `validation_role=numerical_sanity_only`、`physical_benchmark_candidate=false`；该结果不是独立物理基准，也不提供连续解误差保证。

## 对照设置与主结果

该对照保持柱顶以下的层材料、六层厚度、横向周期、入射波、P6、自动传播 DtN、MPI1 和 MUMPS direct 设置不变。顶部空气由 `0.5 nm` 增至 `1.0 nm`，底面保持 `z=-0.5 nm`，顶部边界随之从 `z=5.0 nm` 移至 `z=5.5 nm`。为显式表示新增的顶部空气段，z 网格从 `[3,6,8]` 改为 `[3,6,9]`：网格由 144 增至 162 个六面体。因而本项检查的是计划中的空气高度变化及其顶部网格延伸，不是纯粹的材料内部网格加密。

R/T 主结果来自完整 DtN 端口模态功率；`R00_total=R00_s+R00_p`。表中差值按“空气间距 run − B”计算，门限分别作用于三个差值的绝对值。

| 指标 | B 基线 | 空气 1.0 nm | 有符号差值 | 稳定性门 `abs(Δ)≤2e-4` |
|---|---:|---:|---:|---|
| `R_total` | 0.0952190944953505 | 0.0949840957114875 | `-2.349987839e-4` | failed，超出 `3.499878386e-5` |
| `T_total` | 0.8831311299072778 | 0.8833595386823099 | `+2.284087750e-4` | failed，超出 `2.840877503e-5` |
| `R00_s` | — | 0.09498364561553266 | — | `R00_p` 可忽略但仍保留在总和内 |
| `R00_p` | — | 1.4852399663711567e-22 | — | — |
| `R00_total` | 0.0952186487281771 | 0.09498364561553266 | `-2.350031126e-4` | failed，超出 `3.500311264e-5` |
| `A_balance / A_volume` | — | 0.021656365606202654 / 0.021656364884041122 | — | 两种吸收相差约 `7.22e-10` |
| `R_total+T_total+A_volume−1` | — | `-7.221615528e-10` | — | 能量闭合 `pass`，门限 `1e-5` |

因此，线性求解通过、端口与体积能量平衡通过，但三个输出对空气高度改变均未达到规定的离散稳定性。z 加密的单方向通过不能抵消本项与 y 加密的负结果。DtN 倏逝壳层对照没有通过真残差门，仍不能判断其模态稳定性。

## 真残差、系统规模与耗时

静态凝聚先在单元内部消去不与邻单元共享的自由度，解较小的全局迹与 DtN 系统后再恢复完整场。这里的“显式真残差”会把恢复场代入原方程：对迹/DtN 方程显式作用矩阵，并用 matrix-free UFL 作用检查所有已消去的单元内部测试方程；计算中也包括完整空间的右端项，没有为检查另建完整全局矩阵。它用于确认求得的场满足原始离散系统，而不是只相信 MUMPS 返回状态或内部的零 residual norm。

| 检查项 | 实测 | 判定 |
|---|---:|---|
| 完整残差范数 / 完整 RHS 范数 | `8.725136768e-10 / 1.292085186 = 6.752756601e-10` | `≤1e-6`，pass |
| KSP 内部信息 | `CONVERGED_ITS`，1 次迭代，内部 residual norm 为 0 | 仅作诊断；以左侧显式真残差作数值 Gate |
| 网格 / 完整自由度 | 162 个六面体 / 112,212 个 Nédélec DoF | measured |
| 凝聚后系统 | 33,532 行，27,295,720 used NNZ；包含 160 个 DtN auxiliary 模态 | measured |
| 数值 worker wall time | 1,877.662 s（31.3 min） | measured |
| service 全生命周期 | 1,944.634 s（32.4 min） | measured |

## 运行身份与资源

| 项目 | 记录 |
|---|---|
| Run / service / Invocation | `task44_accuracy_air_gap_1nm_20261031` / `task44-sample-accuracy-airgap1.service` / `eb20ca7c129c4feaab0e95785e4de400` |
| 输入 SHA-256 | `ddaa97857a43390ee372b9b005f7ee4a2ea9eae0b77ae43fb190a8b9bc65a766` |
| 物理模型 SHA-256 / source SHA | `21a04d37c04869a0625ee01fb314f023cbf6a5e60807b1b1e8caf573a6143158` / `a2009b1268c314fcceb9df33d38dad9b217410a1` |
| 执行准入 | CPU 8，MPI 1，单线程；专属 cgroup 上限 `137,438,953,472 B`（128 GiB），swap 上限 0 B；`performance_not_isolated=false` |
| 同时进程树 RSS 峰值 | `8,538,501,120 B`；这是进程树同时 RSS 样本峰值 |
| 专属 cgroup memory peak / swap peak | `9,228,845,056 B` / `0 B`；cgroup 峰值与进程树 RSS 是不同统计口径 |
| 监控与清场 | service `COMPLETED`、leader exit 0、身份样本完整、watchdog 无 warning、全部 descendants 清理、剩余子 PID 为空 |

## 证据入口与身份哈希

- [输入文件](../../input/task44_accuracy_air_gap_1nm_v1.dat)
- [数值 run summary](../../results/task44_sixlayer_0p7nm/task44_accuracy_air_gap_1nm_20261031__full3d_direct__mpi1__Mna/20261031T114301.012893Z/numerical_output/run_summary.json)
- [官方端口功率](../../results/task44_sixlayer_0p7nm/task44_accuracy_air_gap_1nm_20261031__full3d_direct__mpi1__Mna/20261031T114301.012893Z/numerical_output/port_power.json)
- [材料体积吸收](../../results/task44_sixlayer_0p7nm/task44_accuracy_air_gap_1nm_20261031__full3d_direct__mpi1__Mna/20261031T114301.012893Z/numerical_output/volume_absorption.json)
- [完整线性系统日志](../../results/task44_sixlayer_0p7nm/task44_accuracy_air_gap_1nm_20261031__full3d_direct__mpi1__Mna/20261031T114301.012893Z/numerical_output/solver_log.txt)
- [外层 run summary](../../results/task44_sixlayer_0p7nm/task44_accuracy_air_gap_1nm_20261031__full3d_direct__mpi1__Mna/20261031T114301.012893Z/run_summary.json)
- [run manifest](../../results/task44_sixlayer_0p7nm/task44_accuracy_air_gap_1nm_20261031__full3d_direct__mpi1__Mna/20261031T114301.012893Z/run_manifest.json)
- [service summary](../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-airgap1.service/service_summary.json)
- [watchdog summary](../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-airgap1.service/watchdog/summary.json)

| 证据文件 | SHA-256 |
|---|---|
| 输入 | `ddaa97857a43390ee372b9b005f7ee4a2ea9eae0b77ae43fb190a8b9bc65a766` |
| run manifest | `6bcdeb988cfdb6a38498a113c1da14d3fc06a29d6770fcb63cb2f5e8a0c9b1db` |
| 外层 run summary | `41b6ef3fd4ca5f299694e1bbe31fcd1c572a59f603cce635303ceb3deda4fb65` |
| 数值 run summary | `1aebc6d95f3e72bfd90e7861b6847d88edc08be1974177f9be45954c579b3108` |
| `port_power.json` | `03897383334550a97d838adae357b8a4240cf2e9eb853809b295dc0c21a6ebf3` |
| `volume_absorption.json` | `64b12f074e6a1420f010f0200a3d597fd2e8702e28184d1c288b245307514bf0` |
| service summary | `9a1820477f34604e2fbca945c86dfa45a29c48404b1b90600e27a1c20ca9986e` |
| watchdog summary | `6d5aac90868e6e4b6928c59add8e01b372eae9dcc577b6adf4f63b487efde9ec` |
| solver log | `f361eb8ae01772e99f8b3e02ccf4bd717faaa925085ad0cc256047157f81a70c` |

精度对照累计使用 `5/12` 次额外 attempt，尚余 7 次。y 与顶部空气间距对照的三个主输出变化超限，z 对照通过，DtN 壳层对照因残差失败而未判定；A–D 继续为 `gp_eligible=false`。有限元 GP 训练、开发评估、盲测和标准尺寸计算仍为 `not_run`。完整汇总见 [outcomes/summary.md](outcomes/summary.md)。
