# T40-10 both-side setup

## Review V5 当前状态

`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的 no-signal stop 与
resource-authority gap 未授权 both-side setup；不是双侧 setup 数值失败。

## Review V4 历史状态

T40-10 原计划只做 bottom/top 两侧 setup，不做完整 solve。它仍要求前置传输机制和两侧
side route 通过；T40-3 失败后按顺序停止，因此没有 both-side factor inventory、资源或
生命周期测量。

## V1-8 收口

Both-side setup 为 `not_run_by_gate`。V1-2 硬停止发生在依赖它的 projected screen 之前，
因此没有 two-side factor inventory、资源或生命周期测量。

## V2-G 收口

V2-E both-side setup 为 `not_run_by_gate`。V2-B2 数值 Gate 未通过，未进入两侧 setup，
没有新的 factor、资源或生命周期结果。

## V3-6 gate status

`not_run_by_v3_2_numerical_gate`。V3-2 full-span 数值 Gate 未通过，未进入 bottom/top
组合 setup，也没有新的双侧 factor、资源或生命周期测量。

## Review V4 历史收口

`not_run_by_v4_1_identity_gate`。V4-8 both-side setup 在 system/F、interface mass、Vec 和
factor 生命周期开始前停止；没有 bottom/top factor、setup、R/T/A、DoF、资源或生命周期测量。
这是旧 exact spool 缺少 source-row 到当前物理自由度地图造成的身份停止，不是双侧 setup 失败。
记录见 [V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 当前收口

both-side setup 未运行，状态为 `not_run_by_route_c_no_signal_and_resource_authority_gate`。
Route C 明确是 bottom-only、两源 screen；没有 bottom/top 同时 setup、两侧 factor、
interface solve、physics 或资源测量。该状态是 V5 stop Gate 的后续边界，不是双侧方法的
数值失败。
