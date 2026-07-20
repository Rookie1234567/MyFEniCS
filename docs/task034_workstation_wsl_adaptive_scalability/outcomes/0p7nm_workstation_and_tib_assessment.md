# 0.7 nm 工作站与 TiB 评估

## 正式决定

```text
0p7nm_pde_executed = false
0p7nm_solver_pass = false
current_256gib_layout = infeasible
current_1tib_layout = infeasible
current_2tib_layout = infeasible
proves_0p7nm_feasible = false
```

Task034 明确禁止运行 0.7 nm 正式 PDE；本文件只解释 resource model v2 的预测。当前布局
在 2 TiB 下仍相差约 984x 的总量，不能通过增加 RAM 或省略未计组件改写为可行。

## 为什么先失败

在固定 points-per-wavelength 假设下，0.7 nm 预测为约 4.906 亿 local FE DoF、76.36 万
QEP DoF 和每方向 59,511 modes。当前实现最先失效的不是 assembly，而是：

1. dense multi-RHS：约 1.67 PiB；
2. local direct factor：约 194 TiB；
3. replicated modal arrays：约 59.4 TiB；
4. right/left vectors：约 5.15 TiB；
5. interface `N×M` projection：约 1.25 TiB。

单个 complex `(2M)^2` array 约 211 GiB，已接近整台 256 GiB 节点预算。任务书要求在这种
情况下直接把 current replicated modal layout 标为 infeasible；不得只展示一个较小 sparse
matrix 来制造可行性。

## 工作站与 TiB 分类

| 预算 | 当前布局 | 联合压缩下限 | 解释 |
|---:|---|---:|---|
| 256 GiB | infeasible | 7,871x | 单个 modal square 已接近预算，multi-RHS 超出约 6,827x |
| 1 TiB | infeasible | 1,968x | modal/runtime 本身约 1,772 TiB |
| 2 TiB | infeasible | 984x | local 与 modal 两侧都必须同时重构 |

Task034 measured graded-h 结果不能用于抵扣这些需求：其 raw DoF ratio 虽为 1.56x/3.17x/
9.59x，但三档都未满足固定 Full3D 同误差 Gate，正式可用 adaptive factor 仍为 1.0。

## 可重新评估的前置条件

- common-mesh、S/P、1°/5°/10° 均通过的真正 field-driven adaptivity；
- local matrix-free/iterative 路径在目标问题上有 true residual 与 official R/T/A 证据；
- mode core 不复制 `M^2`，vectors 和 multi-RHS 可分布/流式；
- 在 13.5/5/2 nm 逐级重新校准 component peak 与 M convergence；
- 新模型仍需保留 unknown material dispersion 与 cutoff sensitivity。

满足这些条件后才能重做资源评估；仍不能把新预测直接等同于 0.7 nm PDE pass。

