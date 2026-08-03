# Task004 order-resolved qualification v3（train112）

order-resolved 资格与 aggregate 资格独立判定。112 点训练包的 mask 由
解析 power-carrying authority 重新核对；没有把未携带功率的通道填成零功率
通过。

| Gate | 实测结果 | 限值 | 结论 |
|---|---:|---:|---|
| mask agreement | 100% | 100% | pass |
| 最大 side-wise ledger error | `2.220446049250313e-16` | `1e-12` | pass |
| primary-channel NRMSE | 最大 `0.15142` | `0.03` | fail |
| primary-channel p95 absolute error | 最大 `0.0490633` | `0.01` | fail |
| unsupported topology | 0（本训练包） | 0 | pass |

因此 `order_resolved_qualified = false`。例如 selected `gp:F3` 的
reflection `m=0,S`（order index 7）p95 为 `0.0490633`、max 为
`0.115679`；其它主要通道也有 NRMSE 超限。side-wise 功率守恒账本通过，
但这不能掩盖通道级预测误差，故不创建 order model lock。

该负结果不会阻塞未来独立的 aggregate Level A，但在 aggregate lock 缺失时
不得运行 blind validation；order 输出继续 fail closed。
