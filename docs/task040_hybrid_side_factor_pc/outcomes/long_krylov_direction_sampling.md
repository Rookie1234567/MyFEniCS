# V4-4 long Krylov direction sampling

## Review V5 当前状态

`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的规定 screen 已无正
信号且 resource authority 有缺口，未授权本阶段额外的长方向采样；不是本算法普遍失败。

## Review V4 历史状态

`not_run_by_v4_1_identity_gate`。V4-4 不是生产 solver qualification；V4-1 的 canonical
identity stop 没有授权进入 V4-3/V4-4，因此没有用连续 FGMRES 采集困难接口方向。

## 冻结采样合同

| 项目 | 固定值 | 当前结果 |
|---|---|---|
| training sources | `external_dtn_coupling`、`fixed_random_repeat_0` | `not_run` |
| holdout sources | 其他三个冻结 source，仅后续审阅 | `not_run` |
| solve | continuous right-FGMRES、zero initial guess、restart `32` | `not_run` |
| checkpoints | `16 / 32 / 64 / 128`；条件 `256` | `not_run` |
| max directions | `<=256` at 128；`<=512` at conditional 256 | `not_run` |

只保留 owner-row 分布的 true residual、interface residual、最多8个 slow/harmonic Ritz
direction 及其摘要；不得 FE-sized numeric allgather、每 rank 复制完整 basis，也不得授权
`512` 或 `1000` 步。

## 进入与停止

条件 `256` 只在 finite、peak `<45 GiB`、swap `0`、wall仍可维持总计 `<=6 h` 且
`r128<=0.8` 或 `64→128` 至少下降 `0.05 decade` 时授权。结果分类为
`LATE_KRYLOV_ACCELERATION_OBSERVED`、`SLOW_BUT_INFORMATIVE` 或 `PURE_STAGNATION`。
若 V4-3 也无 signal 且这里为 pure stagnation，停止当前 coarse family；长迭代不能包装成
0.7 nm production pass。

## Review V4 历史收口

V4-4 的两源 training（`external_dtn_coupling`、`fixed_random_repeat_0`）、holdout、
`16/32/64/128` 及条件 `256` 均没有生成；没有 Krylov direction、Ritz direction、rank、
true residual 或 train/holdout 数据。原因是 V4-1 在任何 system/F/Vec 构造之前因
`CANONICAL_SOURCE_ROW_BINDING_UNAVAILABLE` 停止，而不是长方向采样或 FGMRES 算法失败。
后续阶段统一为 `not_run_by_v4_1_identity_gate`，不得据此给 production 或 0.7 nm 结论。
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 Route C 当前收口

本阶段实际运行的是 V5 Route C fallback，而不是 V4-4 的 holdout 采样。它只使用
`external_dtn_coupling` 与 `fixed_random_repeat_0`，每个 source 连续 right-FGMRES、
restart `32`，保存 `16/32/64/128` 的 explicit true residual 与 lower/upper canonical
interface traces。两源都在 `128` 结束，`256` 均未授权/未完成。

| source | r64 | r128 | `log10(r64/r128)` | 结果 |
|---|---:|---:|---:|---|
| external | `0.8906247440000827` | `0.9116861468870889` | `-0.010150598869495011` | no signal |
| fixed random repeat 0 | `1.036891675911675` | `1.0585987178847864` | `-0.008997975654488713` | no signal |

两源均满足 `r128>0.9` 且下降小于 `0.05 decade`；`shared_slow_directions.count=0`，
没有满足跨 restart 的稳定共享方向。因此 `ROUTE_C_NO_SIGNAL` 是停止 Gate，不继续
bounded rank 或更长迭代。后续方向筛选、packet-independent rebuild、Level B 和生产化
均为 `not_run_by_route_c_no_signal_and_resource_authority_gate`，不是 Krylov 算法的普遍
失败证明。

[V5 Route C signal ledger](route_signal_ledger.md)。
