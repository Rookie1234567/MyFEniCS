# 0.7 nm 工作站与 TiB 评估（Review V2）

## 正式决定

```text
0p7nm_pde_executed = false
0p7nm_solver_pass = false
current_layout_stress_test = infeasible_by_single_component
production_target_accuracy_layout = unknown
predicted_simultaneous_peak = unknown
proves_0p7nm_feasible = false
```

Task034 明确不运行 0.7 nm PDE。本文件只解释 resource model v2.1 的 current-layout
mechanical stress test；它不把累计组件库存冒充同时峰值，也不把 p2/p3/p4 离散点冒充共同
target accuracy。

## 三场景结论

| 场景 | 最大单组件 GiB | 累计 envelope GiB | 256 GiB | 1 TiB | 2 TiB | simultaneous peak |
|---|---:|---:|---|---|---|---|
| p2/h3 | 1,747,721 | 2,014,975 | 单组件超限 | 单组件超限 | 单组件超限 | unknown |
| p3/h3 | 5,713,351 | 6,804,671 | 单组件超限 | 单组件超限 | 单组件超限 | unknown |
| p4/h5 | 2,567,626 | 3,008,763 | 单组件超限 | 单组件超限 | 单组件超限 | unknown |

这里的 `cumulative_component_envelope_gib` 是 local、QEP、mode、projection、Schur、recovery
与 runtime 组件的逐项累计，不是进程生命周期中的同时 RSS。外推波长没有 overlap 模型，
所以 `predicted_simultaneous_peak_gib = null`；不得把 envelope/budget ratio 写成 peak 压缩倍数。

仍可严格保留的负结论是：三个 stress-test 场景各自都有单一组件超过 2 TiB，故 current
layout 在三档预算上均不可行。不能从这些结果推出生产 target accuracy 下所需 DoF、M、
wall time 或 peak；这些量全部保持 `unknown`。

## 失败组件与边界

三个场景的最大组件都是 current dense multi-RHS inventory。p2/h3 场景的 0.7 nm 机械外推还给出：

- local subtotal：199,869 GiB；
- modal/runtime subtotal：1,815,106 GiB；
- cumulative envelope：2,014,975 GiB；
- 单个 complex `(2M)^2` object：211.093 GiB（`M=59,511`）。

这些数值分别描述组件规模与累计库存。当前 48-rank replicated layout、六个 dense modal
objects、right/left modes、projection 和 multi-RHS 都必须在生产路径中重新设计；不能通过
只省略一个较小 sparse matrix 制造可行性。

## Adaptive 不能抵扣

Task034 的 graded-h mechanism 已通过“机制存在”资格化，但 conservative/balanced/aggressive
三档都未通过固定 Full3D 同误差 Gate。因此：

```text
accuracy_preserving_adaptive_compression_factor = 1.0
field_driven_adaptivity_qualified = false
```

raw DoF ratio 不能抵扣资源 envelope，也不能改写为 0.7 nm 可行。

## 可重新评估的前置条件

- common-mesh、S 主线及 1°/5°/10° 均通过的 field-driven adaptivity；
- local matrix-free/iterative 路径具有 true residual 与 official R/T/A 证据；
- mode core 不复制 `M^2`，vectors 与 multi-RHS 可分布/流式；
- 在 13.5/5/2 nm 逐级校准 component lifecycle 和 simultaneous peak；
- 对 production target accuracy 重新确定 p/h/M，并保留 material dispersion 与 cutoff unknown。

满足这些前置条件后才能建立新的生产资源模型；新的预测仍不等同于 0.7 nm PDE pass。
