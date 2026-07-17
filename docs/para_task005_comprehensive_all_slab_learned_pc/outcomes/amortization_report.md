# Amortization report

## 状态

正式 learned full-solve profile 未通过 P2 storage Gate，因此 1/10/100/1000 RHS 的
端到端 break-even **不计算**。用 model-only microbenchmark 代替全局 solve 会制造
无效结论。

| 成本 | 已知值 | 可否进入 break-even |
|---|---:|---|
| 16-slab teacher generation | 430.304 s | 仅离线已知 |
| captures | 四次完整 852-iteration runs | 未统一计时，不伪造 |
| representative Lane B training | 每 candidate/slab约 0.8–2.6 s | 仅 R4 screen |
| owner model-only inference | 1.34–4.93 ms/four slabs | 不含 PETSc/MPI/audit |
| feasible full learned solve | 不存在 | **否** |

只有解决 storage/audit blocker、完成 P6 true no-hidden-ILU 和 P7 paired A/B 后，
才有合法的 per-RHS candidate cost 可用于：

```text
total(N) = capture + teacher + training + setup + N * learned_full_solve
```

当前结论为 `not_meaningful_by_gate`，不是零成本或无限 break-even 的声明。
