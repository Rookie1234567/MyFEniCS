# T40-11 full Hybrid

## Review V5 当前状态

`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的 no-signal stop 与
resource-authority gap 未授权 full Hybrid；不是 full Hybrid 数值失败。

## Review V4 历史状态

T40-11 full Hybrid formal 没有运行。没有新的 QEP、global Hybrid action、recovery、true
residual、R/T/A、canonical、channel 或 full-workflow RSS/wall/swap 结果。保持 ordinary
Hybrid、global operator、DtN、M480 和物理输入不变；T40-3 的组件负结果不等于完整 Hybrid
失败。

## V1-8 收口

Full Hybrid 仍为 `not_run_by_gate`。最新 root 没有 QEP、global Hybrid action、recovery、
true residual、R/T/A 或完整 workflow 资源结果。V1-2 资源停止不是 full Hybrid 失败。

## V2-G 收口

V2-E full Hybrid 为 `not_run_by_gate`。V2-B2 的真实 projected-transmission 数值负结果
阻止后续进入；本轮没有 QEP、global action、recovery、R/T/A 或完整 workflow 资源结果。

## V3-6 gate status

`not_run_by_v3_2_numerical_gate`。V3-2 full-span mechanism 的资源/identity成立但数值 Gate
未通过；没有启动完整 Hybrid，因此不能把组件负结果写成 full Hybrid 失败。

## Review V4 历史收口

`not_run_by_v4_1_identity_gate`。V4-8 full Hybrid 在 global system/F、QEP、action、recovery、
PDE 和 factor 之前停止；没有 true residual、R/T/A、channel、DoF、RSS、wall 或 swap 数据。
canonical source-row bridge 未资格化，不能把旧 raw row 安全搬到当前系统；这不是 full Hybrid
失败，也不构成 production 或 0.7 nm 资格。见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 当前收口

full Hybrid、global action、recovery、PDE、R/T/A 和完整 workflow resource 均未运行，状态
为 `not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的
`ROUTE_C_NO_SIGNAL` 是 V5 明列的 stop Gate；不能继续到 full Hybrid，也不能把
`full_side_exact_factor_count=0` 或 QEP `0` 写成 full Hybrid 资格。
