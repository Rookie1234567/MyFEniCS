# P2 p6/h10 setup：未运行

| 字段 | 事实 |
|---|---|
| status | `not_run_by_gate` |
| 直接上游 Gate | P1 p3/h50 MPI1/random 在 2000 步后的 explicit true residual = `0.01027838962263555 > 1e-8` |
| 实际范围 | 没有构造 p6/h10 cold setup、LOR/GAMG inventory 或 repeated-apply 资源结果 |
| 2 GB / swap | 未验证；没有可写成 formal resource PASS 的 process-tree peak |
| evidence | 见 `outcomes/memory_first_small_v2.md`、`outcomes/records/memory_first_small_v2.json` 与 `outcomes/records/memory_first_small_v2_checker.json` |

P2 需要先证明 p6/h10 的正定辅助空间、矩阵/层级容量、重复 apply 和 swap/进程树边界；P1 hard stop 后不应把 p2 的内存观察外推到 p6。
