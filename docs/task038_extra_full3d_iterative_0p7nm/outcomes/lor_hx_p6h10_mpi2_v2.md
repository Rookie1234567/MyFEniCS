# P5 p6/h10 physical MPI2：未运行

| 字段 | 事实 |
|---|---|
| status | `not_run_by_gate` |
| 直接上游 Gate | P1 p3/h50 MPI1/random fixed-cap residual failure |
| 实际范围 | 没有运行 MPI2 exact physical RHS/action identity、15,000 步 solve、cross-MPI physics comparator 或 recovery |
| 资源 | 没有 MPI2 process-tree peak、rank swap 或 2 GB authority |

P5 的 conditional MPI2 authorization 未被触发；不能用 P1 p2 MPI2 结果替代 p6/h10 MPI2。
