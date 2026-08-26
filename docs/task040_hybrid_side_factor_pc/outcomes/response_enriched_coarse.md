# V4-3/V4-5 response-enriched coarse

## Review V5 当前状态

`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的 no-signal stop 与
resource-authority gap 未授权本阶段的 coarse、rank 或 train/holdout；不是 coarse 算法失败。

## Review V4 历史状态

`not_run_by_v4_1_identity_gate`。本页仍冻结 train/holdout、方向来源和 bounded rank；
V4-1 identity stop 未授权创建 coarse，也没有读取 exact output values 作为运行时 basis。

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

## Review V4 历史收口

V4-3 response enrichment 与 V4-5 bounded rank（`64/128/256/512`）均未运行。固定的
train/holdout、`R1/R2/R3`、basis、rank、lifted bare-F residual 和任何 accuracy 数值均未
生成；`not_run_by_v4_1_identity_gate` 是前置 canonical source-row identity 未资格化，
不是 response/coarse 算法失败。V4-2、V4-3、V4-5 后续映射均保持未授权，不能把缺少数据写成
无 signal 或 overfit。证据边界见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 当前收口

V5 没有进入 response-enriched coarse。Route C 的两个固定 screen RHS 均在 128 步满足
no-signal stop 条件，且资源 authority 存在中段 live-unreadable 缺口；因此 R1/R2/R3、
train/holdout、total-rank `64/128/256/512`、response basis 与 Level B 均为
`not_run_by_route_c_no_signal_and_resource_authority_gate`。没有新的 rank、basis、
residual、内存或 wall 数据，也没有 overfit 结论。

Route C 的方向审计虽观察到 canonical interface projection 与 basis persistence，且
`replicated=false`，但这只证明采样产物的存储合同；它不是 response coarse 的正信号。
