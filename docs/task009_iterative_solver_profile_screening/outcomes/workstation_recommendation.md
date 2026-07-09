# Workstation Recommendation

```text
workstation_first_profile = iter_gmres_jacobi   # diagnostic only, not production
workstation_second_profile = none from current black-box PETSc profiles
workstation_first_case = p=2 h=1.5
workstation_second_case = p=2 h=1
workstation_third_case = p=2 h=0.75
workstation_fourth_case = p=2 h=0.5
```

## 建议

`iter_gmres_jacobi` 是当前唯一值得带到 1 TB 工作站继续做 residual-only 探针的 profile，因为它能在本机跑过 `p=2 h=1.5`，且内存远低于 direct LU 的 factorization 路线。但它不是正式求解器：本轮 `h=2` 和 `h=1.5` 都没有收敛，也没有 R/T/A。

| case | expected purpose | RAM guidance | decision |
|---|---|---:|---|
| p=2 h=1.5 | 先确认 residual 能否从 3.6e-3 推到 1e-6 | 本机已可 1000 步，1 TB 不是瓶颈 | 可以先做长迭代/参数诊断 |
| p=2 h=1 | 只在 h=1.5 收敛后尝试 | 粗略按 h=1 AIJ 10.3 GB、Jacobi RSS/AIJ 比例估计约 45 GB 以上 | 不应先跳过 h=1.5 |
| p=2 h=0.75 | 资源探针，不应直接追物理解 | 粗略 AIJ 约 24 GB，Jacobi 上界可能 100 GB 级 | 仅在 h=1 收敛后尝试 |
| p=2 h=0.5 | 高风险探索 | 粗略 AIJ 约 82 GB，Jacobi 上界可能 300-400 GB 级 | 当前不建议硬推 |

不要直接从 task009 跳到 `h=0.14~0.16 nm`。若 `p=2 h=1` 都不稳定，就不应继续硬推 `h=0.5` 或更细。当前真正的下一步不是买更大内存继续 Jacobi，而是开发或接入 Maxwell 物理预条件器。
