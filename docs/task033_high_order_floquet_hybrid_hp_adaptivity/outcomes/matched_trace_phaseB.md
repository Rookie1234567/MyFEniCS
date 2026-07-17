# Task033 Phase B：p3/p4 matching-interface 迹组件

## 1. 结论

`review_report_v2.md` 批准的 Phase B 最小矩阵已经执行完毕：

```text
p2: MPI1 regression anchor
p3: MPI1 + MPI4
p4: MPI1 + MPI4
```

五条实测 shard 均在 clean source
`bd7a6023bde7a7c06d456e702af4b7f9f047b3fc` 和同一镜像 digest
`sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`
上通过。独立聚合器在 clean source
`9ac29db45b387d4590de084710abe2cc38b25ffe` 上重新计算全部 Gate，得到：

```text
p2 MPI1 regression = pass
p3 matched trace = pass
p4 matched trace = pass independently
p3/p4 MPI1-MPI4 identity = pass
raised quadrature = stable
no full vector gather = true
no dense interface square = true
Phase C = wait_for_independent_review
```

这只资格化小型 matching-interface 组件，不资格化目标光栅的 p3/p4 full3D 或
Hybrid 求解。

## 2. 夹具与空间身份

夹具使用 `h=10 nm` 的固定匹配网格。3D 端为六面体 N1curl，2D 截面为四边形
N1curl，二者阶次相同；中截面材料为 `stage4_xy`。每条记录只求两个实际左右
双正交模态，用于验证迹重构与投影，不做目标 full3D/Hybrid 求解。

| degree | 3D global DoF | 2D trace global DoF | 3D 单面 trace DoF / cell | 2D cell DoF |
|---:|---:|---:|---:|---:|
| p2 | 7,246 | 162 | 12 | 12 |
| p3 | 23,073 | 351 | 24 | 24 |
| p4 | 53,084 | 612 | 40 | 40 |

匹配网格 SHA256 在 MPI1/MPI4 间逐字节相同。规范迹固定为 `(E_x,E_y)`：

- bottom：local FEM normal `+z`，modal normal `-z`；
- top：local FEM normal `-z`，modal normal `+z`；
- 两侧的 `n × E_t` 对置误差均为零。

## 3. 迹、重构与 Petrov 投影

| shard | 最大 3D→2D 迹误差 | coefficient round-trip | right reconstruction residual | 最大 left unit projection error | Gram cond |
|---|---:|---:|---:|---:|---:|
| p2 MPI1 | `5.951e-15` | `2.948e-16` | `3.485e-16` | `3.469e-18` | `30.4995` |
| p3 MPI1 | `9.310e-15` | `2.828e-16` | `8.067e-17` | `1.112e-16` | `90.7920` |
| p3 MPI4 | `9.566e-15` | `2.685e-16` | `3.326e-16` | `6.939e-18` | `90.7920` |
| p4 MPI1 | `9.614e-15` | `5.769e-16` | `5.227e-16` | `2.220e-16` | `35.2663` |
| p4 MPI4 | `9.835e-15` | `2.611e-16` | `4.466e-16` | `3.469e-18` | `35.2663` |

全部 Gram 块均为满秩 `2/2`。p3、p4 的两个模态都被记录为真实的
`near_degenerate_block_inverse` 二维块；每个模态分别保存 beta、左右 QEP
残差、左右 beta 配对误差和 unit-vector Petrov 投影误差，聚合器没有只检查一个
总 beta 漂移。

## 4. 积分加阶

迹质量矩阵和左右 Gram 块使用显式策略：

```text
selected = 2p + 2g + c + 2
raised = selected + 2
g = 1, c = 0
```

| degree | selected | raised | trace-mass delta | Gram delta | coefficient delta |
|---:|---:|---:|---:|---:|---:|
| p2 | 8 | 10 | `0` | `0` | `0` |
| p3 | 10 | 12 | `0` | `0` | `0` |
| p4 | 12 | 14 | `0` | `0` | `0` |

`ModalTraceProjection` 的普通调用仍保留原默认行为；只有 Phase B runner 显式传入
上述阶次。因此 ordinary default 没有改变。

## 5. MPI 与存储

| degree | MPI1→MPI4 最大 beta 匹配差 | Gram cond 相对差 | Gram 奇异值最大相对差 | MPI4 切向值通信 | MPI4 最大历史 RSS |
|---:|---:|---:|---:|---:|---:|
| p3 | `5.546e-14` | `6.887e-15` | `1.162e-14` | 17,856 B | 238.75 MiB |
| p4 | `4.267e-14` | `6.850e-15` | `9.464e-15` | 27,264 B | 252.45 MiB |

MPI identity 还要求网格 hash、3D/2D global DoF、投影/重构形状、trace-mass NNZ、
积分阶次和近简并块结构相同。所有 rank 的全局结果签名一致。

通信仅发送点所有权所需的查询和两个 complex128 切向值；记录的字节数不包含 MPI
协议开销。3D 场和模态向量没有 gather。存储只有分布式左右迹列、稀疏 trace mass
和复制的 `2×2` Gram 块，`N_Gamma×N_Gamma` dense square 字节数为零。

## 6. Case090 与源码边界

本阶段修改了 `src/coupling/modal_trace_projection.py`，加入可选显式积分阶次和通信
遥测。因此 `review_report_v2.md` 接受的 Phase A Case090 descendant-reuse 结论不能
机械延伸到当前 SHA。

本轮没有重跑 Case090，理由不是把旧证据冒充为新证据，而是：

1. Phase B 是独立的小型迹组件资格，不提出新的 Case090 直接 3D Floquet 结论；
2. 五条 Phase B shard 都在新 clean SHA 上实测；
3. Phase A/Case090 的历史结论仍严格绑定原证据 SHA；
4. 后续 Phase C 若获批，必须在包含本次迹代码的 clean SHA 上生成新的目标
   full3D/Hybrid 记录，不能用旧 Case090 代替目标耦合证据。

## 7. 证据

轻量可审计聚合：

[`phaseB_summary.json`](../../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage2_matched_trace/phaseB_summary.json)

其 `evidence_sha256` 为
`3e606384f68ecad28d02eb4113ca515d24c39bab767df5586c61846ed44f7a04`，并内嵌五条
ignored 原始 shard 的路径、文件 SHA256、关键实测量、逐模式/逐块诊断及重算 Gate。

## 8. 下一步

Phase B 已完成但不能在同一提交中进入 Phase C。下一步是独立复审本记录与
`response_v3.md`。只有复审明确批准后，才考虑 Phase C 的 p3/h5 目标光栅
full3D reference 与最小 Hybrid 漏斗；p4 目标 Hybrid、自适应和完整 p/h 矩阵仍不启动。
