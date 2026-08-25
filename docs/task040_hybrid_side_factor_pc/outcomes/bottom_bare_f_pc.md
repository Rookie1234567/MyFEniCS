# T40-5 bottom bare-F scalable PC

## Status: not_run_by_v4_1_identity_gate

T40-5 需要先有通过 T40-4 的 bounded patch core，再构造 bottom bare-F PC 并进行 one-apply
Gate。由于 T40-3 `TRANSMISSION_MECHANISM_FAIL`，本阶段未运行；没有 bottom scalable PC
residual、factor cap、FGMRES checkpoint、RSS、wall 或 swap 数值。

不能据此判断 bottom bare-F 的所有 iterative side inverse 都不可行。

## V1-8 收口

V1-5 bottom scalable PC 及其 Level-B 前置阶段仍为 `not_run_by_gate`：V1-2 在 exact probe
Gate 前触及资源线，没有生成 bottom scalable residual、factor cap、checkpoint、RSS 或 wall
结果。V1-2 峰值是停止的组件尝试，不是 bottom PC 资格结果。

## V3-5/V3-6 gate status

`not_run_by_v3_2_numerical_gate`。V3-2 full-span numerical Gate 未通过，未进入 bottom
bare-F production side inverse；没有新的 factor cap、full-side residual 或完整 workflow
资源结果。历史 V1/T40-3 结论保持不变。

## Review V4-1 当前状态

`not_run_by_v4_1_identity_gate`。V4-8 bottom bare-F route 未构造 system、裸 `F`、interface
mass、PETSc Vec 或 factor，也没有 one-apply、FGMRES、factor cap、DoF、R/T/A、RSS、wall 或
swap 数据。冻结 exact output 的 source-row bridge 未资格化，所以不能安全重建 RHS/解向量；这是
身份受控停止，不是 bottom PC 或算法失败。详见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。
