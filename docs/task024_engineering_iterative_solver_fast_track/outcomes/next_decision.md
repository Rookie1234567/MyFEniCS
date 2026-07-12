# 下一步决策

## 推荐主线

1. 先统一 Task022/Task024 的初值、true residual、FE/full matvec 和 wall-time 预算。
2. 优先改进 FE inner solve；当前 block Jacobi 虽低内存，但 inverse 质量不足。
3. 只有相对严格同预算基线至少改善 2x，才扩展 m=2/4 response cache。
4. 不恢复已证实负收益的本任务 root p1 SPLU；也不把特定失败推广到所有 AMS/HX 或 h-GMG。

## 停止条件

| 条件 | 决策 |
|---|---|
| 相对同预算基线改善小于 2x | 不称为算法突破 |
| m=2/4 相对 m=1 改善小于 10% | 停止增加 mode，转向 stronger FE inner solve |
| true residual <= 0.1 且明显优于基线 | 记为 strong research signal |
| true residual <= 1e-6 | 才进入 production-like 与 official R/T/A 资格验证 |
| peak RSS 明显超过 14 GB | 停止该配置并保留资源边界证据 |

Task024 当前只关闭复现缺口，没有解决 production-level 迭代求解器问题。
