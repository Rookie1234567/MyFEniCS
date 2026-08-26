# p6 positive selected hierarchy

| 字段 | 状态 |
| --- | --- |
| classification | `not_run_by_gate` |
| selected hierarchy | `NONE` |
| reason | Route A、C1、C2 未形成 qualified multilevel PC；C2 已按 hard Gate 关闭 |
| p6/h10 positive sources | `not_run_by_gate` |
| official solver result | `not_run_by_gate` |

本文件是明确的未运行边界，不是空白 PASS 模板。Route B 曾有结构与 setup evidence，但 random 只到 7000 步即受控停止，不能代替完整四源 positive qualification。C2 的小型 MPI1 诊断中 `h3star→h1star` owned-packet work relative 为 `0.018392534459166617 > 1e-11`，因此没有 selected hierarchy 可供 p6 positive 运行。

证据入口：[`interlevel_route_selection_v1.md`](interlevel_route_selection_v1.md)、[`nested_lor_edge_hmg_c2_mpi1_diagnostic_v1.json`](records/nested_lor_edge_hmg_c2_mpi1_diagnostic_v1.json)。
