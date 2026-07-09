# AMS 内存拆解

## 关键表

| case | auxiliary | n real | real block AIJ est | B nnz | G cols | G nnz | RSS assembly | RSS solve/setup | 说明 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| p2 h5 | standard H1=p+1 | 74,892 | 0.159 GB | 3.558M | 42,160 | 4.130M | 1.081 GB | 6.306 GB | AMS hierarchy 是主要内存来源 |
| p2 h5 | same H1=p | 74,892 | 0.159 GB | 3.558M | 13,167 | 1.572M | 1.042 GB | 1.323 GB | 本轮最佳 |
| p2 h5 | linear H1=1 | 74,892 | 0.159 GB | 3.558M | 1,914 | 0.355M | 1.058 GB | 1.322 GB | 最小但收敛弱 |
| p2 h4 | same H1=p | 165,756 | 0.361 GB | 8.058M | 28,755 | 3.552M | 1.924 GB | not run | 只做 memory audit |

## 判断

1. 显式 real block `A_real` 不是本轮内存主因。p2 h5 的 real block 估算仅约 `0.159 GB`，组装后 RSS 约 `1.08 GB`。
2. standard H1=p+1 的 AMS setup 会把 RSS 推到 `6.306 GB`，说明 auxiliary hierarchy 和 high-degree H1 空间是主要瓶颈。
3. same-H1=p 把 H1 dofs 从 `42160` 降到 `13167`，G nnz 从 `4.13M` 降到 `1.57M`，RSS 从 `6.31 GB` 降到 `1.32 GB`。
4. linear H1=1 更小，但 residual 明显变差，不建议作为主路线。

## 收敛与内存权衡

| auxiliary | 50-step residual | converged residual | converged iterations | RSS |
|---|---:|---:|---:|---:|
| standard H1=p+1 | 3.515e-5 | not reached in 150 | >150 | 6.306 GB |
| same H1=p | 9.502e-6 | 9.964e-7 | 310 | 1.323 GB |
| linear H1=1 | 7.764e-5 | not tested further | >50 | 1.322 GB |

## 对 task011 的解释

task011 real FE-only p2 h5 standard AMS RSS 约 `6.93 GB`，本轮 standard-H1 p2 h5 RSS 约 `6.31 GB`，量级一致。same-H1 的 `1.32 GB` 说明内存瓶颈可以通过 lower H1 auxiliary 显著缓解。

## 下一步需要审计

| 项目 | 为什么 |
|---|---|
| same-H1 是否理论兼容 | 本轮只证明代码可构造并收敛，需进一步确认空间嵌入/近似含义 |
| p2 h4 same-H1 AMS setup | 只做了 assembly audit，未验证 solve |
| MPC 后 G 的构造 | Stage 4 侧边 Floquet 约束会改变空间 |
| FE/aux block split | DtN auxiliary 不应进入 AMS FE block |
