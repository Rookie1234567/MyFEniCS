# P3 p6/h10 positive long Krylov：未运行

| 字段 | 事实 |
|---|---|
| status | `not_run_by_gate` |
| 直接上游 Gate | P1 p3/h50 MPI1/random 固定 `max_it=2000` 后 residual `0.01027838962263555 > 1e-8` |
| 实际范围 | 没有运行 p6/h10 random/gradient positive long Krylov，也没有 5000 步 history |
| 资源 | 未测 process-tree `<2,000,000,000 B`、swap=0 或 live-set growth |
| 结论 | 不得把 p2/p3 partial 结果写成 p6 positive qualification |

P3 的 `right GMRES restart=20`、residual replacement 和 5000 步上限仍只是 V9 合同要求，不是本轮实测结果。
