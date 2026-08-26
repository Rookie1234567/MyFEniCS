# T40-9 top full side

## Review V5 当前状态

`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的 no-signal stop 与
resource-authority gap 未授权 top full-side；不是 top route 算法失败。

## Review V4 历史状态

T40-9 的 top route 依赖 bottom 路线资格，且只能在前置 Gate 通过后执行。由于 T40-3
mandatory rho、worst rho 和 preferred rho 均失败，top bare-F/full-side 没有运行；没有
top factor、residual、RSS、wall 或 swap 结论。

## V1-8 收口

Top full-side 为 `not_run_by_gate`。V1-2 硬停止后没有创建 top factor、residual、physical
output 或资源测点；最新峰值不能作为 top 或完整 workflow 的测量。

## V2-G 收口

V2-E top full-side 为 `not_run_by_gate`。V2-B2 projected-transmission 数值负结果触发
停止，未创建 top factor，也未运行 top/full workflow 测量。

## V3-6 gate status

`not_run_by_v3_2_numerical_gate`。V3-2 full-span numerical Gate 未通过；top full-side 没有
启动，没有 top factor、residual、RSS 或物理结果。

## Review V4 历史收口

`not_run_by_v4_1_identity_gate`。V4-8 top route 未构造 top system/F、factor 或 physical solve，
因此没有 residual、R/T/A、DoF、RSS、wall 或 swap 数据。V4-1 的 canonical source-row bridge
身份门先于这些对象停止；不能把 top route 记为算法失败，也不能从该受控停止推出 production
或 0.7 nm 结论。详见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 当前收口

top bare-F/full-side 未运行，状态为 `not_run_by_route_c_no_signal_and_resource_authority_gate`。
V5 Route C 是 bottom-only fallback，且两源没有正信号；没有 top system、top factor、
residual、R/T/A、DoF、RSS 或 wall 新数据。不能从 bottom Route C 的 no-signal 推断 top
算法失败。
