# 对 `review_report_v2.md` 的回复

## 总体处理

接受审阅结论：

```text
Phase A = PASS_WITH_QUALIFICATIONS
Phase B matched trace = APPROVED_TO_START
Phase C = WAIT_FOR_PHASE_B_REVIEW
```

本轮只执行 Phase B 的小型 matching-interface 组件，没有运行目标光栅 full3D、
Hybrid、Case090、QEP36 或自适应阶段。

## 已完成的审阅要求

| 要求 | 处理 | 结果 |
|---|---|---|
| p2 MPI1 regression | 1 条 clean-source shard | pass |
| p3 MPI1 + MPI4 | 2 条 clean-source shard | pass |
| p4 MPI1 + MPI4 | 与 p3 独立判定 | pass |
| 3D/2D 空间身份 | Basix family、degree、entity/trace DoF | pass |
| matching geometry | axis hash、orientation、normal convention | pass |
| right/left algebra | reconstruction、Petrov projection、Gram rank/cond/NNZ | pass |
| accuracy | affine E trace、coefficient round-trip、right/left errors | pass |
| quadrature | `2p+4` 与 `2p+6` 对照 | delta = 0 |
| MPI | rank ownership、ghost/scatter、MPI1/MPI4 compact identity | pass |
| scalability | communication bytes、RSS、time、gather/dense flags | pass |

独立聚合状态为
`phaseB_p3_p4_matched_trace_pass`。p3 与 p4 的决策链已拆开；测试覆盖“p4 shard
失败时 p3 仍可通过、p4 独立 fail-closed”，不会由 `all five pass` 错误阻塞 p3。

## 对 p4 MPI4 裕量意见的处理

没有沿用 Phase A 的单一 overlap 作为 Phase B 结论。每条 p3/p4 记录保留：

- 两个模式各自的 beta、左右残差、左右 beta 配对误差与 unit Petrov 投影误差；
- 二维近简并块的 indices、beta spread、overlap condition 与归一化后 identity error；
- Gram rank、condition 和奇异值；
- MPI1/MPI4 的最优 beta assignment、块结构和 Gram 不变量。

p3/p4 的 MPI1→MPI4 最大 beta 差分别为 `5.546e-14`、`4.267e-14`；Gram condition
相对差分别为 `6.887e-15`、`6.850e-15`。这里没有形成或 gather 完整特征向量，
所以结论明确限定为 matching-trace 组件的 compact invariant identity，不声称新的
全向量能量范数证明。

## Case090 复用边界

审阅指出：若 Phase B 修改 trace、modal projection 或 quadrature，必须重新判断
Case090 reuse。当前确实修改了 `modal_trace_projection.py`，因此没有把 Phase A 的
descendant-reuse 判定延伸到新 SHA。

本轮仍不重跑 Case090，因为 Phase B 的五条新 shard 已在新 clean SHA 上独立测量，
而本轮不提出新的 Case090 直接 3D 结论。旧 Case090 只保留为原 SHA 的历史证据。
若 Phase C 获批，目标 full3D/Hybrid 必须使用包含本次迹修改的新 clean source
重新测量，旧 Case090 不能替代目标耦合记录。

## 关键证据

- 实测 source：
  `bd7a6023bde7a7c06d456e702af4b7f9f047b3fc`
- 聚合工具 source：
  `9ac29db45b387d4590de084710abe2cc38b25ffe`
- [Phase B 结果说明](outcomes/matched_trace_phaseB.md)
- [独立轻量聚合](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage2_matched_trace/phaseB_summary.json)
- aggregate evidence SHA256：
  `3e606384f68ecad28d02eb4113ca515d24c39bab767df5586c61846ed44f7a04`

## 当前停止点

```text
Phase B p3 matched trace = pass
Phase B p4 matched trace = pass independently
Phase C p3/h5 target full3D + Hybrid = not started; wait for review
p4 target Hybrid = not started
adaptive / full p-h matrix = deferred
ordinary default = unchanged
```

请先复审 Phase B。不会在本次回复中自行进入 Phase C。
