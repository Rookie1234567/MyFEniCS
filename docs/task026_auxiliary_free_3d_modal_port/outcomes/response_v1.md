# Review V1 响应

## 总体响应

Review V1 对架构成功、h=2 未闭环的判断正确。本轮没有把 research signal 改写成 production pass；最终状态仍为：

```text
architecture_success_solver_research_only
```

## 已完成修正

| 审查项 | 响应 | 证据 |
|---|---|---|
| 回收旧 h=2 容器 | 完成 | 3 小时、0 迭代、约 7.2 GB swap，已终止 |
| monitor 流式写盘 | 完成 | 每 checkpoint append/flush residual、真残差、RSS、swap、elapsed |
| coarse rank/condition | 完成 | SVD rank gate；条件数大于 `1e10` 或秩亏直接失败 |
| 禁止 `pinv` 掩盖 | 完成 | coarse operator 改用 gate 后的 `inv` |
| h=2 100-step gate | 完成 | `5.024e-3`，strong gate pass |
| h=2 actual action | 完成 | MPI1/MPI4 最大误差 `1.001e-15` |
| complex-dot regression | 完成 | serial/MPI4 各 6 项测试通过 |
| 有限 PC refinement | 完成 | slab、ILU、coarse、谐波、restart、外层 KSP 均有停止门 |

## 未完成项

| 审查项 | 状态 | 原因 |
|---|---|---|
| h=2 residual `<=1e-6` | 未通过 | 当前最低 `7.051e-4` |
| h=2 official R/T/A | 未发布 | 遵守 residual gate |
| h=2 direct/OOC | 未运行 | 避免在已知 14 GB/swap 紧张环境重复高成本尝试 |
| MPI topology PC | 未实现 | 串行 PC 尚未达到 production，暂不提前工程化 |
| h=5 参数扰动 | 未运行 | h=2 solver gate 未关闭 |
| 2D actual action | 未补 | 本轮优先完成真实 h=2 MPI1/MPI4 action |

## 对 h=2 求解器的结论

本轮将 residual 从 `0.166485` 降到 `0.000705115`，并把峰值 RSS 控制在 `11.38 GB`。这证明无辅助两层方向具有强正信号，但仍差约 705 倍才能达到 `1e-6`。

继续扫描手工参数的边际收益已经很低。下一步应转向 GenEO/局部谱 coarse，或构建支持 HPDDM 的 complex PETSc 环境测试 GCRODR/PCHPDDM。
