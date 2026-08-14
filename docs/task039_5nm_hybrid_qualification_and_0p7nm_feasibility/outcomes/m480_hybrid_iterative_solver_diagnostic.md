# Review V1 E8–E9：M480 Hybrid iterative solver-only diagnostic

## 1. 结论

本阶段没有启动 M480 Hybrid iterative MPI8，也没有启动条件性的 MPI1 lane。根据
Review V1 §7.3，M960 direct 完成后任务在该分支停止；因此 E8/E9 的正式状态均为：

```text
not_run_by_review_v1_7p3_stop_after_m960_direct
```

这不是 iterative 的成功或失败。首轮 T6 的 `Hybrid iterative 从未运行` 事实仍然
保留；T4 的 Full3D iterative 4000 步残差约 `0.1553` 也不能被本阶段改写为 Hybrid
iterative 结果。

## 2. 原计划的窄问题

iterative solver 是用 Krylov 迭代逐步逼近线性方程解；本诊断原本只想回答它能否
求解已经存在的 M480 Hybrid direct 方程，不会证明 Hybrid 模型与 Full3D 等价。M480
direct 仍是合法的 solver reference，但不是 Full3D-qualified model reference。

| 冻结项 | 计划合同 | 实际状态 |
| --- | --- | --- |
| wavelength / mesh / M | 5 nm / p6h10 / 480 | not_run |
| external inventory | 604 exact keys | not_run |
| outer solver | right FGMRES, restart 90, max_it 6000 | not_run |
| initial guess | zero | not_run |
| five residual limits | `5e-9` | not_run |
| preconditioner | whole-endcap ILU(0) + dynamic Woodbury | not_run |
| residual correction | fixed two-pass | not_run |
| nested local KSP / direct side factors | false / bottom-top `0/0` | not_run |
| exact traction | `1e-8` | not_run |
| MPI8 / MPI1 | MPI8 first；通过后才允许 MPI1 | 两者均 not_run |

因此不存在合法的 iterative iterations、residual history、R/T/A、selected E/H、RSS、
PSS、USS 或 wall 可填写；这些字段不是零，也不是 pass。

## 3. 为什么本阶段停止

Review V1 的停止条件是完成唯一 M960 direct 后停在该分支等待审阅。M960 own residual、
traction、projection、canonical backward-error、R/T/A、closure 和 604 keys 均通过，
但 `official_record=false` 仍表示 M convergence / model qualification 未建立。它不
授权自动进入 E8/E9，也不授权开发新的 Full3D PC、modal matrix-free、0.7 nm PDE 或
更细网格。

`M_robust_h10` 仍为 `not_established`；不能用 M960 direct 或 M480 H diagnostic 把它
伪造成已建立的 iterative 前置条件。E5 的 Full3D classification 仍为
`FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_WITHIN_RESOURCE_BUDGET`。

## 4. 证据入口

- [首轮 T6 MPI8/MPI1 boundary](hybrid_iterative_mpi8_mpi1.md)
- [T5 M convergence](hybrid_m_convergence.md)
- [E5 Full3D grid decision](full3d_direct_grid_convergence_v2.md)
- [E7 M960 numerical audit](m960_trace_numerical_audit.md)
- [Review V1 §8](../review_report_v1.md)

E8/E9 未运行，没有新增 raw artifact、solver record 或资源 authority；后续若要重新
启动，必须由新的明确审阅授权单独解锁，并继续沿用上述冻结合同。
