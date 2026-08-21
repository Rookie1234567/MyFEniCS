# Review V8：内存—残差—时间 Pareto

## 口径

完整 workflow 包含 setup、outer、recovery 和物理检查；component 只覆盖一个受控阶段。下面两类
数字不能混作同一条性能曲线。V8-3 的 22.273887634 GiB 是 bottom component 的全 construction
envelope，不是完整 workflow 的内存节省率；V7 Lane A 的 80.025856018 GiB 才是当前唯一完成并
通过完整 workflow 的低于 direct 结果。

| 路线 | 范围 | process-tree peak | 时间 | 残差/状态 | 结论 |
|---|---|---:|---:|---|---|
| matched h4 direct | full workflow，inherited | 93.377006531 GiB | 7131.113596 s worker_total | direct authority | baseline |
| V7 Lane A setup-only | setup component | 81.056903839 GiB | 10649.634795 s observed | advancement line 84.039305878 GiB | setup pass |
| V7 Lane A exact-side full | full workflow | **80.025856018 GiB** | **10126.231902 s** | 1 iter，physics pass | `5NM_EXACT_SIDE_LOWER_MEMORY_CASE_RESULT` |
| V7 streamed producer | component | 11.630760193 GiB | ~415.6 s | basis/lifecycle pass | producer component pass |
| V7 streamed bottom consumer | component | 23.038208008 GiB | ~632.8 s | rank512 source-family residual fail | numerical negative |
| V8-1 layer block reconstruction | component | 15.0692863464 GiB (`16180523008 B`) | measured in V8-1 raw | F action/graph pass | graph component pass |
| V8-3 bottom layer sweep | component | **22.273887634 GiB** | **1713.580125 s** | all five methods fail numerical Gate | controlled numerical negative |

V7 Lane A full 相对 direct 节省 `14.298113646%`，但现有时间字段分别是 direct 的 inherited
`worker_total` 和 Lane A 的 parent/observed elapsed；两者是 non-identical timing authorities。
因此 `+2995.118306 s / +42.0007%` 只是 derived comparison，不是 strict performance qualification。
额外时间主要在两侧 factor 与 modal-Schur setup；outer 只有 1 iter。V8-3 未形成完整 workflow，
不能推测它的 full wall 或 iteration tradeoff。

## V8-3 五个候选

| method | setup s | apply wall s | common component peak GiB | worst mandatory residual（Gate `1e-2`） | preferred modal/external max（Gate `1e-3`） | K rank/condition | result |
|---|---:|---:|---:|---:|---:|---:|---|
| J1 | 74.049002075 | 4.768835524 | 22.273887634 | 45.24747348981373 | 34.24246487175865 | 296 / 63.94325058975744 | residual fail |
| F1 | 82.200138326 | 5.133227528 | 22.155353546 | 141.532433583195 | 137.9502681252083 | 296 / 63.94325058975718 | repeat/linearity/residual fail |
| FB1 | 159.145945567 | 9.839546085 | 22.156860352 | 1244.7282511892267 | 1244.7282511892267 | 296 / 19096010.927585065 | repeat/linearity/residual fail |
| FB2 | 337.447901805 | 20.597998448 | 22.158679962 | 52831.65459906019 | 52831.65459906019 | 296 / 7847304509017.3955 | repeat/linearity/residual fail |
| FB4 | 696.156728291 | 42.186354544 | 22.164176941 | 2025057925864.6484 | 1147917207920.235 | 55 / 3.1808907871836678e25 | repeat/linearity/residual fail |

四级的 RSS 是同一个 bottom consumer process 的共同 envelope，不是按 method 隔离的独立 RSS。
每个方法的 interval 仅为 `evidence_only_checkpoint`；preferred retained interval 因数值失败而
`not_available/not_run`，所以表中的 30 GiB 不是通过值。

## V7 saving tier 与 V8 边界

| full-workflow saving | peak upper bound | 状态 |
|---:|---:|---|
| 0% direct | 93.377006531 GiB | reference |
| 5% | 88.708156204 GiB | V7 Lane A full reached |
| 20% | 74.701605225 GiB | not reached |
| 30% | 65.363904572 GiB | not reached |
| 40% | 56.026203919 GiB | not reached |
| 50% | 46.688503266 GiB | not reached |
| 60% | 37.350802612 GiB | not reached |

V8-3 只证明 bottom construction 的资源线未触发，不改变 V7 的 full-workflow tier。top、both-side、
full formal、matrix-free K 和 0.7 nm PDE 均 `not_run`。

证据入口：[V8-3 bottom outcome](v8_layer_sweep_bottom.md)、[V8-3 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v8_layer_sweep_bottom_v1.json)。
