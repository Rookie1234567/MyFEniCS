# Next Decision

## 档位

```text
decision_class: B-/C+
```

解释：

| 条件 | 本轮结果 |
|---|---|
| Stage A real split equivalence | 通过 |
| MPC 后 AMS data | 可构造 |
| p1 h5 FE-AMS + aux identity 强改善 | 未通过 |
| p2 h5 optional | 未运行 |
| full p2 h2 资格 | 不具备 |

这不是完全放弃 AMS，而是说明 “FE-only AMS 直接 blockdiag 到 Stage4” 不够。

## 不建议做

| 方向 | 原因 |
|---|---|
| 直接 full Stage4 p2 h2 | p1 h5 gate 未过 |
| 直接 p2 h5 reduced | 不满足 task14a gate |
| 继续黑盒 PETSc profile sweep | task009-task011 已证明低收益 |
| 未收敛时输出 R/T/A | 会制造假物理结果 |

## 建议下一步

| 优先级 | 下一步 | 目标 |
|---:|---|---|
| 1 | DtN-aware block correction | 不再把 708 个 aux unknowns 只用 identity 处理 |
| 2 | Rayleigh/Floquet modal deflation | 针对传播/近截止模态的低维粗空间 |
| 3 | FE block shifted/positive AMS 改造 | 让 AMS 处理 Helmholtz 不定性，而不仅是 positive proxy |
| 4 | 小规模 exact FE block / exact aux Schur 对照 | 分离 FE 近似误差和 aux 耦合误差 |

## 下一轮最小可执行任务

```text
Task015: reduced Stage4 DtN-aware Schur / Rayleigh modal coarse correction diagnostic
```

建议先在 `default100 p=1 h=5` 上做：

| 子任务 | 成功标准 |
|---|---|
| 构造 aux exact block 或 low-rank Schur 对照 | true residual 明显低于 current FE-AMS |
| 构造 Rayleigh/Floquet coarse vectors | GMRES residual 至少 10x 改善 |
| 组合 FE-AMS + modal correction | 达到或接近 `1e-6` |
