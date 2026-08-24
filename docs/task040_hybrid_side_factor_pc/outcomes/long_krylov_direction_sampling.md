# V4-4 long Krylov direction sampling

## 状态

`planned_conditional_not_run`。V4-4 不是生产 solver qualification，只在 V4-3 有 signal
或 Review 条件允许时，用有限连续 FGMRES 采集困难接口方向。

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
