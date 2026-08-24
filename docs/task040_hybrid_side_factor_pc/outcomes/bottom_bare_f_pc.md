# T40-5 bottom bare-F scalable PC

## Status: not_run_by_v3_2_numerical_gate

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
