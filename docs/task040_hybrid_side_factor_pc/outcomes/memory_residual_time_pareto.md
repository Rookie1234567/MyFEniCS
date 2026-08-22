# T40 memory–residual–time Pareto boundary

## 已测量的组件与继承 baseline

| 路线 | residual / rho | peak RSS GiB | wall | swap | 状态 |
|---|---|---:|---:|---:|---|
| direct full workflow | inherited matched reference | 93.377006531 | inherited | 0 | reference |
| exact-side iterative full workflow | inherited five-Gate pass | 80.025856018 | inherited | 0 | reference |
| T40-3 Level-A component | worst rho `28.316064601533686` | 28.333576202392578 | 660.6481867840048 s | 0 | controlled numerical negative |

28.333576202392578 GiB 只覆盖 T40-3 bottom action component，不能与 93.377006531 GiB
direct workflow 比较成 saving tier，也不能写成完整 workflow 的 lower-memory pass。没有
T40-4 至 T40-12 的 checkpoint、full residual、cold/reuse peak 或 h3 scaling，因此 Pareto
曲线在本阶段停止。

PSS/USS 没有在 formal raw 中独立记录，均为 `not_recorded`；不从 RSS 推算。完整 workflow
peak 的 max(bottom, top, consumer) 口径也没有在本轮重新建立。
