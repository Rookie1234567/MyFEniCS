# V7 Lane C：独立 side layer graph-only audit

这一步只回答一个结构问题：静态凝聚后的有限元细网格矩阵 `F`，在真实网格层标签下，非零连接是否只落在同层或相邻层。它没有求解电磁方程，也没有建立 ILU/LU、Woodbury、模态 Schur 或 outer KSP；因此它不能证明任何 solver 或 0.7 nm 资格结论。

## 执行边界与结果

| 项目 | 结果 |
| --- | --- |
| source / input | `95c20aad61414f3586651e960af9f20043462ef2` / `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| MPI | serial `MPI=1`；此前 graph helper 的 MPI2/4 tiny ownership/count tests 已通过 |
| 顺序 | 控制流完成 bottom build → F CSR graph → destroy → top build → F CSR graph → destroy |
| selected-mode packet / exact spool | 未 hydrate / 未打开 |
| QEP / factor / solve | `0` / `not_run` / `not_run` |
| F 图的范围 | 仅 local FE/static-condensation `F`；DtN 的低秩/global coupling 未计入 |
| wall / RSS / swap | `not_measured`；本次没有正式 graph telemetry |
| destroy-after object inventory | `not_measured`；仅记录 try-finally 控制流完成 |
| graph raw | `results/task039_v7_side_layer_graph_audit_serial_95c20aad/graph_only_audit.json`，SHA256 `aaf845886e37ee711de209e0ecba1c56da7726d77114a0007226f3a0b22a63c5` |

`F` 的显式 CSR 这里只是为了读取连接关系；它不是数值求解用的 factor，也没有形成 `F-C H^{-1}D` 的全局乘积。bottom 和 top 分开建造、统计、释放，避免两侧结构对象同时驻留。这里的“释放”是本次命令的 try-finally 控制流，不是独立 destroy-after 对象 inventory 的测量。host 观察到的约 16 分钟、约 5.6 GiB 只作运行过程观察，不进入正式 Pareto 或资源结论。

## 真实层映射

层标签来自 assembly-time 的 `owned_cell_recovery_maps`、`trace_constraints.expansion_by_original` 和真实 mesh geometry 的 `z_values`。共享 trace row 采用所有 incident owned cell layer 中的最小编号，这是确定的 bookkeeping 规则，不是按全局行号均匀分桶，也不是猜测层结构。临时 global row-layer 标签在统计后释放。

## bottom / top 统计

两侧都得到相同的连接计数；z 边界不同，但层数、行数和非零模式一致。

| 指标 | bottom | top | 解释 |
| --- | ---: | ---: | --- |
| 层数 | 6 | 6 | 真实 z-layer 标签 |
| active rows | 132300 | 132300 | 全局 F rows |
| owned-CSR NNZ | 105038640 | 105038640 | F 非零连接总数 |
| same-layer NNZ | 75327840 | 75327840 | `0.717144091` |
| adjacent-layer NNZ | 29710800 | 29710800 | `0.282855909` |
| long-range NNZ | 0 | 0 | 没有超过一层的连接 |
| block half-bandwidth | 1 | 1 | 最大 `|layer_i-layer_j|` |

每层 rows 为 `[28350, 20790, 20790, 20790, 20790, 20790]`；每层 NNZ 为
`[21088620, 17384220, 17384220, 17384220, 17384220, 14413140]`。完整 6×6 layer-pair
NNZ 矩阵保存在 compact record 和 ignored raw 中；其非零项只在主对角线及相邻对角线上。

### reference pattern 与 measured match

下表把审阅中已有的 expected pattern 与本次 raw 的 bottom/top 实测值分开，避免把
reference 当成运行输出。

| 字段 | reference | bottom measured | top measured | match |
| --- | ---: | ---: | ---: | --- |
| layer count | 6 | 6 | 6 | true |
| global rows | 132300 | 132300 | 132300 | true |
| total NNZ | 105038640 | 105038640 | 105038640 | true |
| same-layer NNZ | 75327840 | 75327840 | 75327840 | true |
| adjacent-layer NNZ | 29710800 | 29710800 | 29710800 | true |
| long-range NNZ | 0 | 0 | 0 | true |
| block half-bandwidth | 1 | 1 | 1 | true |

## 这项证据能说明什么

它为未来讨论 layer-local ordering 或分层 Schur 提供了独立的局部 FE connectivity 事实：在本次 h4 bottom/top side graph 中，连接带宽为 1，long-range NNZ 为 0。但它没有测试 sweeping、hierarchical Schur、cyclic reduction、Petrov consumer 或 full solve；这些路线仍是 `not_authorized/not_run`。也不能把 local `F` 图的带宽直接外推为完整 `F-C H^{-1}D` 的带宽，因为 DtN 低秩/global coupling 被明确排除。

## 证据边界

- compact record：[task039_v7_side_layer_graph_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_side_layer_graph_v1.json)
- raw graph audit：`results/task039_v7_side_layer_graph_audit_serial_95c20aad/graph_only_audit.json`（ignored local raw）
- 本结果是独立 Lane C graph-only evidence，不改写 V6/V7 的数值负结果，也不授权 top/both/full 或 0.7 nm PDE。
