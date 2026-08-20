# V7 streamed Petrov full-result boundary

这个文件专门防止把 bottom component 的 rank ladder 误读为完整 Hybrid formal。V7 Lane B consumer 在同一 MPI8 进程内完成 rank64→128→256→512；四级都通过 finite、repeat、linearity、E condition 和 resource/lifecycle 检查，但五个非退化 holdout 的 true residual 没有通过。

| Gate / 阶段 | 结果 | 实际边界 |
|---|---|---|
| rank64 | numerical fail | preferred max `219.3757739633316` |
| rank128 | numerical fail | preferred max `210.18097980391423` |
| rank256 | numerical fail | preferred max `1143.0925334334272` |
| rank512 | numerical fail | preferred max `1521.8160925296324` |
| E condition | pass at all evaluated ranks | maximum `278859.6049079984`，小于 `1e12` |
| component resource | pass | setup/overall peak `23.038208008 GiB`，swap `0` |
| factor/KSP inventory | pass | base ready `1`；exact/global `0/0`；nested KSP `0` |
| bottom result | `NUMERICAL_LIMIT_NOT_REACHED_BY_RANK512` | source-family capacity negative |
| top / both-side | `not_run` | bottom numerical Gate failed |
| outer / recovery / RTA / field | `not_run` | no full Petrov formal was authorized |

“失败”这里指具体 source family 不能在冻结 rank ladder 上重现 holdout 的 true residual，不是 ownership remap、telemetry、swap 或 resource failure。第一次 consumer root 的 ownership mismatch 是独立的 implementation failure，已保留并与本次 numerical result 分开。

因此，V7 没有一个 streamed Petrov full result，也没有 top/both-side/full 的 R/T/A、recovery 或 0.7 nm 结果。完整 bottom 数值与 raw hash 见 [compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_petrov_bottom_consumer_v1.json) 和 [bottom Pareto outcome](v7_petrov_bottom_pareto.md)。
