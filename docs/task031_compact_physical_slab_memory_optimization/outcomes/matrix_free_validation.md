# Assembled-F-free public MPC form action 验证

## 实现

`src/solvers/mpc_form_action.py` 只使用 public DOLFINx/DOLFINx-MPC API：把输入 active vector 写入 MPC `Function`，执行 backsubstitution，使用 `dolfinx_mpc.assemble_vector(ufl.action(a, u))` 得到 form action，并显式恢复 MPC slave unit rows。首个 smoke 未处理 unit rows，误差约 0.0263；修复后误差降到 `9.718e-16`，该失败过程保留为研究诊断。

`CondensedDtnOperator` 可接收 external fine action，并用 `require_f()` / `release_f()` 管理只在 coarse/slab setup 所需的 assembled `F`。最终 solve ledger 中没有 `F`，且 no-double-destroy 测试覆盖重复释放。

本文中的“matrix-free fine”精确指 public form-action path：它消除 solve 阶段常驻的 assembled `F`，但不是已完成缓存优化的低层 element-kernel matrix-free 实现。每次 apply 仍调用 `assemble_vector(ufl.action(...))`，并包含 Function 写入、ghost/MPC backsubstitution、slave unit-row 恢复和通信。

## Correctness

| mesh/run | action relative error | full action/solve 结果 |
|---|---:|---|
| h5 smoke after unit-row fix | `9.718e-16` | 1-step action pass |
| h5 full | `9.718e-16` | full residual `9.959903e-7` |
| h3 full | `9.460e-16` | full residual `9.973853e-7` |
| h2 full | `9.248e-16` | full residual `9.998454e-7` |

h5 200-step assembled 与 public form-action residual 分别为 `8.611995756e-4` 和 `8.611995763e-4`，数值差约 `6.3e-13`。

## 资源代价

h5 200-step worker RSS 从 1.693619 降到 1.659306 GiB（-2.03%），cgroup 从 1.120045 降到 1.085526 GiB（-3.08%），payload model 从 0.3582 降到 0.2679 GiB；solve time 从 18.478 增到 58.837 s（3.18x）。最终 h2 external simultaneous peak 为 7.898 GiB，但 solve 约为 Task030 的 5.01x。

`release_f()` 的一次性销毁开销不是主要瓶颈。Task030 h2 约 1.278 s/outer iteration，Task031 约 6.061 s/outer iteration；迭代数只增加约 5.55%，每步成本却增加约 4.74x。主要成本是每次 outer apply 重复 form assembly 和通信。

结论：这是 memory-first 正结果，不是 performance positive；必须保持 explicit opt-in。
