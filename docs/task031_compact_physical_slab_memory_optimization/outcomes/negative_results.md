# Task031 负结果与停止路线

| 路线 | 证据 | 停止原因 |
|---|---|---|
| factor dedup | 16 个 exact fingerprints 全部唯一 | 无精确重复；任务禁止近似共享 |
| FGMRES restart50 | worker RSS -1.89%，residual/time 更差 | 内存收益 `<3%` 且成本恶化 |
| ordinary GMRES + adaptive PC | linearity error `2.374308e-2` | PC 非线性，普通 GMRES 不合法，fail closed |
| fixed Richardson + GMRES90 | linearity `3.611e-15`，200 步 residual 0.7703 | 合法但不收敛 |
| 20 slabs overlap0.125 | residual 0.001478、worker 1.680 GiB | 比 16 slabs 更慢、更大、更差 |
| boundary Jacobi1 | stored factor nnz -9.95%，residual 0.0118 | RSS 收益不足且残差恶化约 13.7x |
| h3 max_it1600 | full residual `5.490e-6` | 未达到 numeric Gate；同候选延长上限后才通过 |
| second h2 | not_run | 首个已 `<8.0 GiB`，没有机制不同且预测 `<=7.5 GiB` 的候选 |

assembled-F-free public MPC form action 不是纯负结果：200-step RSS 仅下降约 2–3%，时间约 3.18x，但 h3/h2 的结构比例更有利，最终 h2 external simultaneous peak 达到 7.898 GiB。因此保留为内存优先 opt-in，同时明确它不是吞吐优化，也不是缓存优化的低层 element-kernel matrix-free。
