# V4-3/V4-5 response-enriched coarse

## 状态

`planned_conditional_not_run`。本页冻结 train/holdout、方向来源和 bounded rank；没有
创建 coarse、没有读取 exact output values 作为运行时 basis，也没有预写通过。

## V4-3 train/holdout

| 角色 | 固定 source |
|---|---|
| train | `modal_traction_positive`、`external_dtn_coupling`、`fixed_random_repeat_0` |
| holdout | `modal_traction_negative`、`fixed_random_repeat_1` |
| response candidates | `R1`、`R2`、`R3`；由 exact trace 缺口及稳定接口方向构造 |

禁止直接使用 raw RHS/load vectors。先以 interface mass metric 去除当前 span，再用 complex
SVD/RRQR 形成 response directions。

## Gate 与边界

| 阶段 | frozen Gate | 当前结果 |
|---|---|---|
| V4-3 pilot | training 全部 `r16<=0.1`，且两个 holdout 均达到相对 V3-2 `r16` 的二倍改善 | `not_run` |
| 无 signal | `RESPONSE_TRACE_ENRICHMENT_NO_SIGNAL` | `not_evaluated` |
| V4-5 total rank | `64 / 128 / 256 / 512`，不得解释为在776上再加512 | `not_run` |
| offline authority | best/Petrov trace、lifted bare-F residual、train/holdout、basis hash | `not_run` |
| rank stop | rank512 仍不满足 `modal+/modal-/external<=0.1`、five-source worst `<=0.25` | `not_run` |

V4-5 若通过，只允许最多两个 rank 进入五源连续 FGMRES `16/32/64/128`、条件 `256`；即使
通过，当前仍是 response-enriched oracle，直到 V4-6 fresh reconstruction 移除 exact
authority 依赖后才可讨论 bounded local patch。
