# Task037 F5b 资源与 MPI 边界报告

## 结论

F5b 是唯一一次正式 `p6/h10/S/MPI8` matrix-free full run。solver residual、
物理 observables 和 12+12 channel 通过，但 memory authority 为
13.658008575439453 GiB，高于 Task37 resource-positive 门槛 10.30 GiB。
因此资源分类为 `negative`，最终分类为
`PARTIAL_WITH_CONTROLLED_NEGATIVES`；不能写成整体 pass。

## direct / F3 / F5b 对比

| path | MPI | memory authority | process-tree RSS | worker PSS / USS | wall |
|---|---:|---:|---:|---:|---:|
| F0 direct authority | 8 | 15.255001068115234 GiB | 15621.121 MiB | 13254.321 / 13047.027 MiB | 370.18 s |
| F3 assembled FGMRES full | 8 | 13.652233123779297 GiB | 13965.281 MiB | 11980.911 / 11776.828 MiB | 410.5464700690354 s |
| F5b released matrix-free full | 8 | 13.658008575439453 GiB | 13985.80078125 MiB | 12058.8984375 / 11854.36328125 MiB | 396.60296967602335 s |

F5b watchdog warning 为 true，controlled termination 和 timeout 均为 false，
swap 为 0，最大观察到 8 个 MPI rank。10 GiB warning 只是记录，不等于
termination；14 GiB controlled cap 未触发。10.30 GiB resource-positive Gate
仍失败。

## 关键阶段峰值与对象账本

`memory_timeline.csv` 的关键峰值按
`process-tree RSS / worker PSS / worker USS`（MiB）为：assembly
`6998.4296875 / 6023.5869140625 / 5871.34375`，augmented matrix finalized
`13359.1640625 / 12058.8984375 / 11854.36328125`，after field output
`13985.80078125 / 12032.728515625 / 11732.80859375`。swap in/out pages 均为 0。

F5b core setup/solve/recovery/total 为
`26.169431037968025 / 252.79112647596048 / 0.028237071994226426 /
279.01592205197085 s`；stage4 port assembly+solve 为
`378.93804831197485 s`，postprocess 为 `9.14909775799606 s`，parent wall 为
`396.60296967602335 s`。对象摘要是 75/75 coarse、basis storage
9479364 bytes、factor CSR payload estimate 2067298912 bytes、16 factor-only
ILU(0)、14 unique factor classes、exact_duplicate_factor_count=2、global direct
factor count 0、global Schur materialized false。

## MPI 与范围边界

正式 F5b 只运行 MPI8；F5a 的轻量 owner/scatter 资格包含 MPI2/MPI4，但本
报告不把它们当作 F5b formal run。没有第二次 formal run，没有 MPI4 full
candidate，也没有 F5c、F6、Task037b、Hybrid、hp 或 0.7 nm 运行。唯一正式
F5b 预算已经消耗；所有 raw artifact、timeline、progress、stdout 和 hash
索引见 compact record。
这些源列名虽带 `_mb`，本报告按 1024 基准解释为 MiB。
