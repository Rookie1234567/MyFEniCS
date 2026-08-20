# Review V7：0.7 nm 含义与边界

## 结论先行

本轮没有运行 0.7 nm PDE、Full3D 新 heavy 或 arbitrary-3D qualification。因此，V7 不给出“0.7 nm 可行”的数值结论。

Lane A 证明了一个 5 nm、h4、M480 的 exact-side Hybrid full workflow 可以在 `80.025856018 GiB` 完成，低于 matched direct `93.377006531 GiB`，但仍保留两侧 full sparse factors，且只达到 14.298113646% saving。这个结果是 5 nm case result，不是 continuum 或 0.7 nm 外推。

Lane B 的 streamed producer 本身只占 `11.630760193 GiB`，bottom consumer 只占 `23.038208008 GiB`；然而四级 rank ladder 的 source-family residual 都失败，rank512 也没有通过 mandatory/preferred numerical Gate。低 component RSS 不能抵消 source family 不合格。

## 当前主要瓶颈的物理含义

| 项目 | 当前证据 | 对 0.7 nm 的含义 |
|---|---|---|
| full side factors | Lane A 仍是两侧 exact-side factor workflow；旧 V4 iterative 也出现 resource regression | full-side factor 的规模增长仍是主要 blocker，未建立 0.7 nm 上界 |
| streamed basis/consumer | producer/consumer 的 component RSS 很低，但 bottom residual 在 64/128/256/512 全部失败 | 省内存不等于可用的物理近似；不能宣称已解决 |
| Lane C graph | bottom/top local-F graph 6 层、same/adjacent pattern 一致；未测 wall/RSS | 只说明当前局部连接结构可审计，不提供 solver 或容量资格 |
| DtN coupling | Lane C 明确未把 global low-rank DtN 纳入 local-F graph | DtN 的 global low-rank 内存/时间仍需独立处理，不能从 local bandwidth 直接推断 |

## 允许的下一步边界

Lane C 只授权下一轮考虑 z-sweeping、hierarchical Schur 或 cyclic reduction 这类沿 z 方向减少同时保留对象的研究路线。它们本轮没有实现、没有测试成可用 solver，也没有得到资源或数值资格。任何下一步仍需独立的 source、residual、factor lifecycle 和 process-tree authority；不能把 Lane C 的 graph count 直接升级为 0.7 nm capacity claim。

ordinary/default Hybrid、Full3D new heavy、0.7 nm PDE、第三 BLR、普通 ILU/budget scan 和 master 均未改变/未运行。

相关证据：[V7 memory summary](v7_memory_limit_summary.md)、[Lane B bottom Pareto](v7_petrov_bottom_pareto.md)、[Lane C graph-only outcome](v7_side_layer_graph.md)。
