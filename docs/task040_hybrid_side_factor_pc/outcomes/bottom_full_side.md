# T40-8 bottom full side

## Status: not_run_by_v4_1_identity_gate

T40-8 需要先通过 Level-A transmission、bounded patch 和 bottom scalable PC 前置 Gate，
然后才允许在冻结 DtN 和物理身份下构造完整 `A_bottom`。T40-3 rho Gate 失败，故没有
bottom full-side setup、factor、true residual、physics 或资源结果。

## V1-8 收口

V1-6 bottom full-side 仍为 `not_run_by_gate`。Run B 在 projected screen 资格化前停止，因此
没有测得 bottom full-side factor、true residual、physical output 或 workflow RSS。

## V2-G 收口

V2-E bottom full-side 为 `not_run_by_gate`。V2-B2 数值 Gate 未通过，因此没有构造 bottom
full-side factor 或运行完整物理/资源测量。

## V3-6 gate status

`not_run_by_v3_2_numerical_gate`。V3-2 full-span residual Gate 未通过；bottom full-side 没有
启动，未产生 factor、true residual、physics 或资源数据。

## Review V4-1 当前状态

`not_run_by_v4_1_identity_gate`。V4-8 bottom full-side 在 system/F/interface mass/Vec/factor
之前停止；没有 `A_bottom`、true residual、物理输出、R/T/A、DoF、RSS、wall 或 swap 数据。旧
 exact spool 缺少可资格化的 canonical source-row bridge，不能把 raw global row 当成物理身份；
这不是 bottom full-side 数值失败。见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。
