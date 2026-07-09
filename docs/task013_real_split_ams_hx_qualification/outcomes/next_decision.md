# 下一步决策

## 推荐决策

继续 real-split AMS/HX，但下一步必须进入 Stage 4 FE/aux block integration，而不是继续 FE-only 调参。

推荐任务：

```text
Task014a：reduced Stage 4 real-split FE/aux block PC integration
```

## 为什么不是直接 full p2 h2

| 原因 | 说明 |
|---|---|
| FE-only 与 Stage 4 还差 MPC/DtN | 当前 PC 没处理 Floquet constraints 和 auxiliary modal unknowns |
| same-H1 是经验正信号 | 需要确认在 MPC 后是否仍可构造 compatible G |
| full p2 h2 成本高 | 不应在 block PC 未接好前硬跑 |
| official R/T/A 守门严格 | 未收敛不能输出 R/T/A |

## 下一任务最小范围

| 阶段 | 内容 | 成功标准 |
|---|---|---|
| A | Stage 4 assemble-only real split residual diagnostic | real block 与 complex residual 一致 |
| B | FE block same-H1 AMS + aux identity/exact block | reduced p1 h5 不崩溃 |
| C | reduced p1 h5 vs Jacobi residual | true residual 明显改善 |
| D | optional reduced p2 h5 | 内存低于 BLR，residual 可解释 |

## 暂不建议

- 不直接跑 full p2 h2。
- 不跑 p2 h1.5 breakthrough。
- 不做 Rayleigh/Floquet deflation full implementation。
- 不做 matrix-free Stage 4。

Rayleigh/Floquet deflation 仍很重要，但应等 FE/aux block PC 可进入 Stage 4 后再叠加。
