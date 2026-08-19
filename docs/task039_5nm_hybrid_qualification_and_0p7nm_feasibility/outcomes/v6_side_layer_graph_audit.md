# V6-1 side layer-graph audit：未建立

## 裁决

V6 计划中的 layer graph 用真实 assembly 的 row-to-z-layer 归属统计 `F` 的 same-layer、adjacent-layer 和 long-range NNZ，并给出每层 rows/NNZ 与 block half-bandwidth。该审计要求在 `bottom_F_ready` 后形成可审阅的真实映射；不能用全局行号分桶、均匀分层或已知矩阵容量猜测。

本次唯一正式 attempt 在完成 one-cell factor、lift、两方向 apply、bottom/top projection 后，于 `one_cell_factor_destroyed` 之后触发 V6 effective memory hard stop。raw 中没有 `bottom_F_ready` 或 layer-graph result marker，也没有完整 layer-pair NNZ、row-layer labels 或 bandwidth 输出。因此结论为：

| Gate/字段 | 结果 |
| --- | --- |
| row-to-z-layer mapping | `not_available` |
| same-layer NNZ | `not_available` |
| adjacent-layer NNZ | `not_available` |
| long-range NNZ | `not_available` |
| block half-bandwidth | `not_available` |
| layer graph overall | `controlled_stop_before_bottom_F_ready` |
| sweeping prototype | `not_authorized` |

硬线观测为 `42.70841979980469 GiB > 42.019652939 GiB`，swap 为 0，process group 已成功 SIGTERM 退出。该资源停止不能被解释为层结构结论；尤其不能据此宣称局部带状、95% 近邻或适合 sweeping。V6-1 的 exact-side full formal 已关闭，exact-side 只保留 oracle 角色。

## 可复核入口

- [V6-1 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v6_post_compaction_exact_side_setup_v1.json)
- [V6-1 setup outcome](v6_post_compaction_exact_side_setup.md)
- ignored raw：`results/task039_v6_h4_post_compaction_exact_side_setup_only_mpi8_35b1532e/numerical_output/memory_stages.jsonl`
- ignored raw：`results/task039_v6_h4_post_compaction_exact_side_setup_only_mpi8_35b1532e/numerical_output/process_tree_samples.jsonl`

这些 raw 只证明 setup 生命周期、marker 对齐 RSS 和受控终止；不含可裁决的 layer-pair 结构结果。任何 sweeping 或 layer-aware solver 原型都需要另行批准，不能在本记录上先行展开。
