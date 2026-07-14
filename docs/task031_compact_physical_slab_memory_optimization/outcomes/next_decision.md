# Task031 下一步决定

Task031 已证明 h2 在真实收敛下可压到 7.898 GiB，因此下一步不应再追逐 restart 微调或近似 factor dedup：前者收益不足 3%，后者没有 exact duplicate。

若目标转向“保持低内存同时显著缩短 3.33 小时 solve”，优先级应是：

1. 为 assembled-F-free public MPC form action 设计可缓存/批量 apply，减少每次 form action 的装配与通信开销；
2. 研究固定线性且保留平滑能力的 local polynomial/Chebyshev action，使普通低存储 Krylov 合法；
3. 用多 RHS/重复 solve 评估 setup cache 是否能摊薄成本；
4. 每条路线先过 h5 action equivalence、PC legality、true residual 与 simultaneous peak，再进入 h3/h2。

在这些证据出现前，Task030 是速度较优但历史峰值约 9.375 GiB 的 profile；Task031 是 external simultaneous / legacy internal 约 7.898 / 8.176 GiB、但约 5.01x solve time 的 profile。应按机器约束选择，而不是替换 ordinary default。
